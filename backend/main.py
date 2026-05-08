import os
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import uuid

import secrets
import requests
import threading
import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
import json
import time
from logging_config import setup_logging
from database import (
    init_db, get_connection, get_cursor, get_placeholder, get_row_value,
    utcnow, JobStatus, safe_delete, seed_admin, archive_old_jobs, backup_database
)
from services.recovery import recover_stuck_jobs, check_database_integrity
from services.alerts import alert, alert_deduplicated
from datetime import datetime, timezone
from services.barcode_service import build_print_payload, generate_patient_id
from services.routing_service import print_with_failover, mark_job, log_print_event
from services.utils import is_usb_stale
from services.auth import hash_password, verify_password, create_token, decode_token
from services.audit import log_audit
from config import settings
from queue import PriorityQueue
from apscheduler.schedulers.background import BackgroundScheduler
import shutil
from threading import Lock
import logging
import concurrent.futures

# 🔹 Logging Setup
setup_logging()
logger = logging.getLogger("Main")

print_queue = PriorityQueue(maxsize=500)
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="🏥 Clinical PrintHub Professional API",
    description="""
    Production-grade hospital print management infrastructure.
    
    ### Key Clinical Features:
    * **🛡️ Security:** Role-Based Access Control (RBAC) & Token Authentication.
    * **📊 Monitoring:** Real-time hardware heartbeat and health analytics.
    * **💾 Persistence:** Multi-dialect support (PostgreSQL/SQLite) with auto-backups.
    * **🚑 Reliability:** Automated job recovery and clinical queue management.
    
    *Authorized hospital personnel only. All access is logged for HIPAA auditing.*
    """,
    version="3.5.0-PRO",
    contact={
        "name": "Savetha Hospital IT Engineering",
        "url": "https://github.com/MANIBAALAKRISHNANS/print_centre",
    },
    license_info={
        "name": "Enterprise Clinical License",
    }
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000)
    
    # Log request details in structured JSON
    logger.info(f"Request: {request.method} {request.url.path}", extra={"details": {
        "type": "request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_ms": duration_ms,
        "client_ip": request.client.host
    }})
    return response

@app.get("/health")
def health_check():
    """
    Used by load balancers and monitoring.
    Returns 200 if healthy, 503 if degraded.
    """
    checks = {}
    overall = "healthy"
    
    # 1. Database check
    try:
        conn = get_connection()
        cur = get_cursor(conn)
        cur.execute("SELECT 1")
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        overall = "critical"

    
    # 2. Active agents check
    try:
        conn = get_connection()
        cur = get_cursor(conn)
        cur.execute("SELECT COUNT(*) FROM agents WHERE status='Online'")
        row = cur.fetchone()
        online_agents = get_row_value(row, 'count', 0) or 0
        conn.close()

        checks["agents_online"] = online_agents
        if online_agents == 0:
            checks["agents_warning"] = "No agents online"
            if overall == "healthy":
                overall = "warning"
    except Exception as e:
        checks["agents"] = f"error: {str(e)}"
    
    # 3. Stuck jobs check
    try:
        conn = get_connection()
        cur = get_cursor(conn)
        cur.execute("SELECT COUNT(*) FROM print_jobs WHERE status='Printing' AND locked_at < ?", 
                    ((datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S UTC"),))
        row = cur.fetchone()
        stuck = get_row_value(row, 'count', 0) or 0
        conn.close()
        checks["stuck_jobs"] = stuck
        if stuck > 10:
            checks["stuck_jobs_warning"] = f"{stuck} jobs in printing state"
            if overall == "healthy":
                overall = "warning"
    except Exception as e:
        checks["stuck_jobs"] = f"error: {str(e)}"
    
    status_code = 200 if overall in ("healthy", "warning") else 503
    return JSONResponse(
        content={
            "status": overall, 
            "checks": checks, 
            "version": "1.0.0", 
            "timestamp": utcnow()
        },
        status_code=status_code
    )
metrics_lock = Lock()

# 🔹 In-Memory Cache with Thread Safety
_cache = {}
cache_lock = Lock()

def get_cached_data(key, ttl=10):
    now = time.time()
    with cache_lock:
        if key in _cache:
            data, expiry = _cache[key]
            if now < expiry:
                return data
    return None

def set_cached_data(key, data, ttl=10):
    with cache_lock:
        if len(_cache) > 100:
            _cache.clear()
        _cache[key] = (data, time.time() + ttl)

def invalidate_cache(key=None):
    with cache_lock:
        if key: _cache.pop(key, None)
        else: _cache.clear()

# 🔹 Startup Dependency Checks
def check_dependencies():
    deps = ["soffice"]
    gs_cmd = "gswin64c" if os.name == 'nt' else "gs"
    deps.append(gs_cmd)
    
    missing = [d for d in deps if not shutil.which(d)]
    if missing:
        logger.critical(f"⚠️  MISSING DEPENDENCIES: {', '.join(missing)}")
        logger.critical("Document conversion (PDF/DOCX) will fail until these are installed and added to PATH.")

# 🔹 Initialize Database
init_db()

check_dependencies()

def self_healing():
    """🔹 Classify and fix printer data on startup"""
    logger.info("Running printer self-healing...")
    conn = get_connection()
    cur = conn.cursor()
    
    # 1. Force USB printers to have NULL IP
    cur.execute("SELECT id, name FROM printers WHERE connection_type='USB' AND ip IS NOT NULL")
    bad_usb = cur.fetchall()
    for p in bad_usb:
        logger.warning(f"SELF-HEAL: USB printer '{p['name']}' had an IP. Clearing it.")
        cur.execute("UPDATE printers SET ip=NULL WHERE id=?", (p["id"],))
        
    # 2. Warn about IP printers without IP
    cur.execute("SELECT id, name FROM printers WHERE connection_type='IP' AND (ip IS NULL OR ip='')")
    bad_ip = cur.fetchall()
    for p in bad_ip:
        logger.error(f"DATA INTEGRITY: IP printer '{p['name']}' is missing an IP address!")
        
    conn.commit()
    conn.close()

def startup_cleanup():
    """🔹 Clear uploads folder completely on restart to remove stale data"""
    if os.path.exists("uploads"):
        logger.info("Running startup cleanup for 'uploads/' - clearing all stale data")
        for f in os.listdir("uploads"):
            path = os.path.join("uploads", f)
            if os.path.isfile(path):
                try: os.remove(path)
                except: pass

def recover_queue():
    """🔹 Startup recovery: Reload interrupted jobs into queue"""
    logger.info("MANDATORY: Running queue recovery...")
    conn = get_connection()
    cur = conn.cursor()
    
    # 1. Queued & Retrying
    cur.execute("SELECT * FROM print_jobs WHERE status IN (?, ?)", 
                (JobStatus.QUEUED, JobStatus.RETRYING))
    pending_jobs = [dict(r) for r in cur.fetchall()]
    
    # 2. Stale Agent Printing (> 120s)
    stale_limit = datetime.now(timezone.utc).timestamp() - 120
    cur.execute("SELECT * FROM print_jobs WHERE status=? AND locked_at < ?", 
                (JobStatus.AGENT_PRINTING, str(stale_limit)))
    stale_jobs = [dict(r) for r in cur.fetchall()]
    
    # Reset stale jobs so they can be re-assigned
    for job in stale_jobs:
        logger.warning(f"RECOVERY: Job {job['id']} was stale in 'Agent Printing'. Resetting to 'Queued'.")
        cur.execute("UPDATE print_jobs SET status=?, locked_at=NULL, locked_by=NULL WHERE id=?", 
                    (JobStatus.QUEUED, job["id"]))
        job["status"] = JobStatus.QUEUED
        
    all_to_queue = pending_jobs + stale_jobs
    for job in all_to_queue:
        logger.info(f"RECOVERY: Re-queuing job {job['id']} (Category: {job['category']})")
        
        # If barcode job hasn't generated a file yet, we must re-generate the bytes payload
        if job["category"] == "Barcode" and not job["file_path"]:
            payload = build_print_payload(job)
        else:
            payload = job["file_path"]
            
        print_queue.put((job["priority"], {
            "job_id": job["id"],
            "location_id": job["location_id"],
            "category": job["category"],
            "payload": payload
        }))
        
    conn.commit()
    conn.close()
    logger.info(f"RECOVERY COMPLETE: {len(all_to_queue)} jobs re-queued.")

startup_cleanup()
self_healing()

@app.get("/metrics")
def get_metrics():
    cached = get_cached_data("metrics", 10)
    if cached: return cached
    
    with metrics_lock:
        conn = get_connection()
        try:
            cur = conn.cursor()
            
            # 1. Job Stats
            cur.execute("SELECT status, COUNT(*) as count FROM print_jobs GROUP BY status")
            job_stats = {row["status"]: row["count"] for row in cur.fetchall()}
            
            # 2. Agent Status
            cur.execute("SELECT agent_id, status, last_seen FROM agents")
            agents = [dict(row) for row in cur.fetchall()]
            
            # 3. Printer Status Breakdown
            cur.execute("SELECT status, COUNT(*) as count FROM printers WHERE status != 'Maintenance' GROUP BY status")
            printer_stats = {row["status"]: row["count"] for row in cur.fetchall()}
            
            # 4. Storage Info
            uploads_count = 0
            if os.path.exists("uploads"):
                uploads_count = len(os.listdir("uploads"))
                
            res = {
                "jobs": job_stats,
                "agents": agents,
                "printers": printer_stats,
                "storage": {"pending_uploads": uploads_count}
            }
            set_cached_data("metrics", res, 10)
            return res
        finally:
            conn.close()

# 🔹 Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# 🔹 CORS SETUP - MUST BE OUTERMOST (Added Last)
ALLOWED_ORIGINS = [
    "http://localhost:5173", 
    "http://localhost:5174", 
    "http://127.0.0.1:5173", 
    "http://127.0.0.1:5174"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# 🔹 Seed Default Admin (Hospital-grade initial creds)
seed_admin("admin", hash_password("Admin@PrintHub2026"))

# 🔹 Authentication Dependencies
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return payload

def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Insufficient permissions: Admin role required")
    return user

# ━━━ SECURITY MODELS ━━━

class LoginRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    username: str = Field(..., min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(..., min_length=8, max_length=128)

class PrintJobRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    category: str = Field(..., min_length=1, max_length=100)
    location_id: str = Field(..., min_length=1, max_length=64)
    patient_id: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9-_/]+$')
    priority: int = Field(default=5, ge=1, le=10)
    # Metadata for labels
    patient_name: str = None
    age: str = None
    gender: str = None
    tube_type: str = None
    test_name: str = None

class CategoryRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str = Field(..., min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9 -_]+$')

class AgentRegisterRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    activation_code: str = Field(..., min_length=8, max_length=8, pattern=r'^[A-F0-9]+$')
    hostname: str = Field(..., min_length=1, max_length=255)

# ━━━ RBAC ROLES ━━━
ROLES = {
    "admin": {
        "label": "Administrator",
        "description": "Full access. Can manage users, activation codes, and system settings.",
        "can": ["view_all", "manage_users", "manage_printers", "manage_categories", 
                "clear_jobs", "view_audit_logs", "generate_activation_codes"]
    },
    "operator": {
        "label": "IT Operator",
        "description": "Can manage printers, categories, and view all jobs. Cannot manage users.",
        "can": ["view_all", "manage_printers", "manage_categories", "clear_jobs"]
    },
    "viewer": {
        "label": "Viewer",
        "description": "Read-only access. Suitable for nursing staff checking print status.",
        "can": ["view_all"]
    }
}

def validate_password_complexity(password: str):
    if len(password) < 10:
        raise HTTPException(400, "Password must be at least 10 characters")
    if not any(c.isupper() for c in password):
        raise HTTPException(400, "Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in password):
        raise HTTPException(400, "Password must contain at least one number")

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=10, max_length=128)
    role: str = "viewer" # admin, operator, viewer

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=10, max_length=128)

class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=10, max_length=128)

class RoleUpdateRequest(BaseModel):
    role: str

class CategoryRequest(BaseModel):
    name: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

# ━━━ AUTH ENDPOINTS ━━━


@app.post("/auth/login")
@limiter.limit("10/minute")
def login(request: Request, data: LoginRequest):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT * FROM users WHERE username={placeholder}", (data.username,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        log_audit(data.username, "user", "LOGIN", status="FAILURE", ip_address=request.client.host)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Polymorphic access
    username = get_row_value(row, "username", 0)
    db_hash = get_row_value(row, "password_hash", 1) # index 1 usually
    role = get_row_value(row, "role", 2)
    
    # Verify password
    if not verify_password(data.password, db_hash):
        log_audit(username, "user", "LOGIN", status="FAILURE", ip_address=request.client.host)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    log_audit(username, "user", "LOGIN", status="SUCCESS", ip_address=request.client.host)
    token = create_token(username, role)
    
    # Update last login
    try:
        conn = get_connection()
        cur = get_cursor(conn)
        cur.execute(f"UPDATE users SET last_login={placeholder} WHERE username={placeholder}", (utcnow(), username))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Could not update last_login for {username}: {e}")


    return {
        "access_token": token,
        "token_type": "bearer",
        "role": role,
        "username": username,
        "force_password_change": False # Default to false if not in dict
    }


@app.get("/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return user

@app.post("/auth/change-password")
def change_password(data: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    username = current_user.get("sub") or current_user.get("username")
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"SELECT password_hash FROM users WHERE username={placeholder}", (username,))
        row = cur.fetchone()
        
        db_hash = get_row_value(row, "password_hash", 0)
        
        if not db_hash or not verify_password(data.current_password, db_hash):
            conn.close()
            raise HTTPException(401, "Invalid current password")
        
        validate_password_complexity(data.new_password)
        
        new_hash = hash_password(data.new_password)
        cur.execute(f"UPDATE users SET password_hash={placeholder}, force_password_change=0 WHERE username={placeholder}", 
                   (new_hash, username))
        conn.commit()
        conn.close()
        log_audit(username, "user", "CHANGE_PASSWORD", resource_type="user", resource_id=username)
        return {"message": "Password changed successfully"}
    except Exception as e:
        if conn: conn.close()
        if isinstance(e, HTTPException): raise e
        logger.error(f"Password change error: {e}")
        raise HTTPException(500, str(e))

# ━━━ USER MANAGEMENT (ADMIN ONLY) ━━━

@app.get("/admin/users")
def list_users(current_user=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, role, created_at, last_login, force_password_change FROM users ORDER BY created_at DESC")
    return [dict(r) for r in cur.fetchall()]

@app.post("/admin/users")
def create_user(data: CreateUserRequest, current_user=Depends(require_admin)):
    validate_password_complexity(data.password)
    
    if data.role not in ROLES:
        raise HTTPException(400, "Invalid role")
        
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if exists
    cur.execute("SELECT id FROM users WHERE username=?", (data.username,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(400, "Username already exists")
        
    cur.execute("""
        INSERT INTO users (username, password_hash, role, created_at, force_password_change)
        VALUES (?, ?, ?, ?, 1)
    """, (data.username, hash_password(data.password), data.role, utcnow()))
    
    conn.commit()
    conn.close()
    
    log_audit(current_user.get("sub", "unknown"), "user", "USER_CREATE", status="SUCCESS", details=f"Created user {data.username} as {data.role}")
    return {"message": "User created"}

@app.put("/admin/users/{user_id}/role")
def update_user_role(user_id: int, data: RoleUpdateRequest, current_user=Depends(require_admin)):
    if data.role not in ROLES:
        raise HTTPException(400, "Invalid role")
        
    conn = get_connection()
    cur = conn.cursor()
    
    # Get username for audit
    cur.execute("SELECT username FROM users WHERE id=?", (user_id,))
    target = cur.fetchone()
    if not target:
        conn.close()
        raise HTTPException(404, "User not found")
        
    cur.execute("UPDATE users SET role=? WHERE id=?", (data.role, user_id))
    conn.commit()
    conn.close()
    
    log_audit(current_user.get("sub", "unknown"), "user", "ROLE_CHANGE", status="SUCCESS", details=f"Changed {target['username']} to {data.role}")
    return {"message": "Role updated"}

@app.put("/admin/users/{user_id}/password")
def admin_reset_password(user_id: int, data: ResetPasswordRequest, current_user=Depends(require_admin)):
    validate_password_complexity(data.new_password)
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get username for audit
    cur.execute("SELECT username FROM users WHERE id=?", (user_id,))
    target = cur.fetchone()
    if not target:
        conn.close()
        raise HTTPException(404, "User not found")
        
    cur.execute("UPDATE users SET password_hash=?, force_password_change=1 WHERE id=?", 
               (hash_password(data.new_password), user_id))
    conn.commit()
    conn.close()
    
    log_audit(current_user.get("sub", "unknown"), "user", "PASSWORD_RESET", status="SUCCESS", details=f"Reset password for {target['username']}")
    return {"message": "Password reset successfully"}

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current_user=Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    
    # Prevent self-deletion
    cur.execute("SELECT id, username FROM users WHERE username=?", (current_user["username"],))
    me = cur.fetchone()
    if me and me["id"] == user_id:
        conn.close()
        raise HTTPException(400, "You cannot delete your own account")
        
    # Get username for audit
    cur.execute("SELECT username FROM users WHERE id=?", (user_id,))
    target = cur.fetchone()
    if not target:
        conn.close()
        raise HTTPException(404, "User not found")
        
    cur.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    
    log_audit(current_user.get("sub", "unknown"), "user", "USER_DELETE", status="SUCCESS", details=f"Deleted user {target['username']}")
    return {"message": "User deleted"}

class Printer(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str = Field(..., min_length=1, max_length=100)
    ip: str = None
    category: str
    status: str
    language: str = "PS"
    connection_type: str = "IP"

class Category(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str

@app.get("/dashboard")
def get_dashboard(user: dict = Depends(get_current_user)):
    cached = get_cached_data("dashboard", 10)
    if cached: return cached

    conn = get_connection()
    try:
        cur = get_cursor(conn)
        
        cur.execute("SELECT COUNT(*) FROM printers")
        total = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute("SELECT COUNT(*) FROM printers WHERE status='Online'")
        live = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute("SELECT COUNT(*) FROM printers WHERE status='Offline'")
        offline = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute("SELECT COUNT(*) FROM print_jobs")
        job_total = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute("SELECT COUNT(*) FROM print_jobs WHERE status='Completed'")
        job_completed = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute("SELECT COUNT(*) FROM print_jobs WHERE status='Failed'")
        job_failed = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute("SELECT COUNT(*) FROM print_jobs WHERE retry_count > 0")
        job_retried = get_row_value(cur.fetchone(), 'count', 0) or 0


        cur.execute("""
            SELECT printer, 
                   COUNT(*) as total, 
                   SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) as completed,
                   SUM(CASE WHEN status='Failed' THEN 1 ELSE 0 END) as failed,
                   SUM(CASE WHEN retry_count > 0 THEN 1 ELSE 0 END) as retried
            FROM print_jobs 
            WHERE printer != 'Pending'
            GROUP BY printer
        """)
        printer_stats = []
        for row in cur.fetchall():
            success_rate = round((row["completed"] / row["total"]) * 100) if row["total"] > 0 else 0
            printer_stats.append({
                "printer": row["printer"],
                "job_count": row["total"],
                "completed": row["completed"],
                "failed": row["failed"],
                "retried": row["retried"],
                "success_rate": success_rate
            })

        # 🔹 REAL-TIME STATUS OVERRIDE
        for p in printer_stats:
            # We don't have connection_type in printer_stats query easily, 
            # but we can fetch it if needed. For now, let's focus on /printers.
            pass

        res = {
            "total": total, "live": live, "offline": offline,
            "jobs": {"total": job_total, "completed": job_completed, "failed": job_failed, "retried": job_retried},
            "printer_stats": printer_stats
        }
        set_cached_data("dashboard", res, 10)
        return res
    finally:
        conn.close()

@app.get("/printers")
def get_printers(user: dict = Depends(get_current_user)):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM printers")
        rows = [dict(r) for r in cur.fetchall()]
        
        # 🔹 REAL-TIME STATUS OVERRIDE (USB Stale Detection)
        for p in rows:
            if p.get("connection_type") == "USB" and p.get("status") == "Online":
                if is_usb_stale(p.get("last_updated")):
                    p["status"] = "Offline"
        return rows
    finally:
        conn.close()

@app.get("/printers/{printer_name}/status")
def force_printer_status_check(printer_name: str, current_user=Depends(get_current_user)):
    """Triggers an immediate status check for a specific printer."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM printers WHERE name=?", (printer_name,))
    printer = cur.fetchone()
    if not printer:
        conn.close()
        raise HTTPException(404, "Printer not found")
    
    p_dict = dict(printer)
    
    # For network printers, do an immediate socket ping
    if p_dict.get("connection_type") == "IP" and p_dict.get("ip"):
        import socket as sock
        try:
            # Try to connect to port 9100 (standard raw print port)
            s = sock.create_connection((p_dict["ip"], 9100), timeout=3)
            s.close()
            new_status = "Online"
        except:
            new_status = "Offline"
        
        cur.execute("UPDATE printers SET status=?, last_updated=? WHERE name=?",
                   (new_status, utcnow(), printer_name))
        conn.commit()
        conn.close()
        invalidate_cache("dashboard")
        return {"printer": printer_name, "status": new_status, "checked_at": utcnow()}
    
    # For USB printers, status comes from agent — return current status with warning
    conn.close()
    return {
        "printer": printer_name, 
        "status": p_dict["status"], 
        "note": "USB printer status is agent-reported. Trigger a new heartbeat on the workstation workstation if needed."
    }

@app.post("/printers")
def add_printer(data: Printer, admin: dict = Depends(require_admin)):
    # 🔹 STRICT CLASSIFICATION VALIDATION
    if data.connection_type == "USB":
        data.ip = None
    elif data.connection_type == "IP" and not data.ip:
        raise HTTPException(400, "IP address is required for IP printers")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO printers (name, ip, category, status, language, connection_type, last_updated, last_update_source) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data.name, data.ip, data.category, data.status, data.language, data.connection_type, utcnow(), "Initial"))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    invalidate_cache("dashboard")
    return {"id": new_id}

@app.put("/printers/{printer_id}")
def update_printer(printer_id: int, data: Printer, admin: dict = Depends(require_admin)):
    # 🔹 STRICT CLASSIFICATION VALIDATION
    if data.connection_type == "USB":
        data.ip = None
    elif data.connection_type == "IP" and not data.ip:
        raise HTTPException(400, "IP address is required for IP printers")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE printers 
        SET name=?, ip=?, category=?, status=?, language=?, connection_type=? 
        WHERE id=?
    """, (data.name, data.ip, data.category, data.status, data.language, data.connection_type, printer_id))
    conn.commit()
    conn.close()
    invalidate_cache("dashboard")
    return {"message": "Updated"}

@app.delete("/printers/{printer_id}")
def delete_printer(printer_id: int, admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM printers WHERE id=?", (printer_id,))
    conn.commit()
    conn.close()
    invalidate_cache("dashboard")
    return {"message": "Deleted"}

@app.get("/locations")
def get_locations(user: dict = Depends(get_current_user)):
    cached = get_cached_data("locations", 30)
    if cached: return cached
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, external_id FROM locations")
    res = [dict(r) for r in cur.fetchall()]
    conn.close()
    set_cached_data("locations", res, 30)
    return res

@app.get("/mapping")
def get_mapping(user: dict = Depends(get_current_user)):
    cached = get_cached_data("mapping", 10)
    if cached: return cached
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mapping")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    set_cached_data("mapping", rows, 10)
    return rows

@app.put("/mapping/{mapping_id}")
def update_mapping(mapping_id: int, data: dict, admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE mapping SET a4Primary=?, a4Secondary=?, barPrimary=?, barSecondary=? WHERE id=?",
                (data.get("a4Primary"), data.get("a4Secondary"), data.get("barPrimary"), data.get("barSecondary"), mapping_id))
    conn.commit()
    conn.close()
    invalidate_cache("mapping")
    invalidate_cache("dashboard")
    return {"message": "Updated"}

@app.get("/print-jobs")
def get_print_jobs(
    status: str = None,
    location_id: str = None,
    patient_id: str = None,
    from_date: str = None,
    to_date: str = None,
    retried: bool = False,
    search: str = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user)
):
    conn = get_connection()
    cur = conn.cursor()
    
    where_clauses = []
    params = []
    
    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if location_id:
        where_clauses.append("location_id = ?")
        params.append(location_id)
    if patient_id:
        where_clauses.append("patient_id LIKE ?")
        params.append(f"%{patient_id}%")
    if from_date:
        where_clauses.append("time >= ?")
        params.append(from_date)
    if to_date:
        where_clauses.append("time <= ?")
        params.append(to_date + " 23:59:59")
    if retried:
        where_clauses.append("retry_count > 0")
    if search:
        where_clauses.append("(printer LIKE ? OR category LIKE ? OR patient_name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # Get Total Count
    cur.execute(f"SELECT COUNT(*) FROM print_jobs {where_sql}", params)
    total = cur.fetchone()[0]
    
    # Get Results
    query = f"SELECT * FROM print_jobs {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?"
    cur.execute(query, params + [limit, offset])
    jobs = [dict(r) for r in cur.fetchall()]
    
    conn.close()
    log_audit(user.get("sub", "unknown"), "user", "VIEW_JOBS", details={"filter": status, "search": search, "offset": offset})
    return {"jobs": jobs, "total": total}

@app.delete("/print-jobs")
def delete_all_jobs(admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM print_jobs")
    count = cur.fetchone()[0]
    cur.execute("DELETE FROM print_jobs")
    cur.execute("DELETE FROM print_logs")
    conn.commit()
    conn.close()
    log_audit(admin.get("sub", "unknown"), "user", "CLEAR_JOBS", details={"count": count})
    return {"message": "All jobs cleared"}

@app.get("/print-logs/{job_id}")
def get_print_logs(job_id: int, user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM print_logs WHERE job_id=? ORDER BY id ASC", (job_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/categories")
def get_categories(user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = get_cursor(conn)
    cur.execute("SELECT name FROM categories")
    rows = [get_row_value(r, "name", 0) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/categories")
def add_category(data: CategoryRequest, admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"INSERT INTO categories (name) VALUES ({placeholder})", (data.name,))
    conn.commit()
    conn.close()
    log_audit(admin.get("sub", "unknown"), "user", "CREATE_CATEGORY", resource_type="category", resource_id=data.name)
    return {"message": "Added"}

@app.delete("/categories/{name}")
def delete_category(name: str, admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"DELETE FROM categories WHERE name={placeholder}", (name,))
    conn.commit()
    conn.close()
    log_audit(admin.get("sub", "unknown"), "user", "DELETE_CATEGORY", resource_type="category", resource_id=name)
    return {"message": "Deleted"}


@app.post("/print-job")
def print_job(data: PrintJobRequest):
    location_id = data.location_id
    category = data.category
    if not location_id: raise HTTPException(400, "location_id is required")
    
    # 🔹 Strict Category Validation
    if category not in ["A4", "Barcode"]:
        raise HTTPException(400, "Invalid category. Must be 'A4' or 'Barcode'")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM locations WHERE external_id=?", (location_id,))
    loc = cur.fetchone()
    if not loc:
        conn.close()
        return {"error": "Invalid location_id"}
    patient_id = data.patient_id or generate_patient_id()
    cur.execute("INSERT INTO print_jobs (location, location_id, category, printer, status, type, time, patient_name, age, gender, patient_id, tube_type, test_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (loc["name"], location_id, category, "Pending", "Queued", "None", utcnow(), data.patient_name, data.age, data.gender, patient_id, data.tube_type, data.test_name))
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    log_audit("system", "user", "CREATE_JOB", resource_type="print_job", resource_id=job_id, patient_id=patient_id, details={"category": category, "location": location_id})
    return {"job_id": job_id, "status": "Queued"}

@app.get("/mapping-validate")
def validate_mapping(user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mapping")
    rows = [dict(r) for r in cur.fetchall()]
    
    issues = []
    # Fetch all printer names for validation
    cur.execute("SELECT name, ip FROM printers")
    active_printers_map = {r["name"]: r["ip"] for r in cur.fetchall()}

    from services.printer_service import check_printer

    for r in rows:
        checks = [
            ("a4Primary", "A4 Primary"),
            ("a4Secondary", "A4 Secondary"),
            ("barPrimary", "Barcode Primary"),
            ("barSecondary", "Barcode Secondary")
        ]
        for key, label in checks:
            val = r[key]
            if not val or val == "None":
                if "Primary" in label:
                    issues.append({"location": r["location"], "field": label, "issue": "Not configured"})
            elif val not in active_printers_map:
                issues.append({"location": r["location"], "field": label, "issue": f"Printer '{val}' no longer exists"})
            else:
                # 🔹 Hybrid Health Check: Skip IP check for USB printers (no IP)
                ip = active_printers_map[val]
                if ip:
                    if not check_printer(ip, timeout=1):
                        issues.append({"location": r["location"], "field": label, "issue": f"Printer '{val}' is OFFLINE ({ip})"})
            
    conn.close()
    return {"valid": len(issues) == 0, "issues": issues, "issues_count": len(issues)}

@app.post("/print-a4-file")
async def print_a4_file(location_id: str = Form(...), file: UploadFile = File(...)):
    # 🔹 MIME & Extension Validation
    allowed_exts = (".pdf", ".doc", ".docx", ".txt")
    allowed_mimes = ("application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain")
    
    if not file.filename.lower().endswith(allowed_exts):
        raise HTTPException(400, "Unsupported file format.")
        
    if file.content_type not in allowed_mimes:
        # Some OS might send different mimes, we mainly rely on extension but check mime for safety
        pass

    import re
    # 🔹 Filename Sanitization
    safe_name = re.sub(r'[^a-zA-Z0-9.-]', '_', file.filename)
    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads", f"{uuid.uuid4()}_{safe_name}")
    
    # 🔹 Chunked Reading + Configurable Size Limit
    file_size = 0
    MAX_UPLOAD_MB = 50 # Standard hospital limit
    MAX_SIZE = MAX_UPLOAD_MB * 1024 * 1024 
    try:
        with open(file_path, "wb") as f:
            while chunk := await file.read(1024 * 1024): # 1MB chunks
                file_size += len(chunk)
                if file_size > MAX_SIZE:
                    f.close() # Close before removal
                    os.remove(file_path)
                    raise HTTPException(400, f"File too large (max {MAX_UPLOAD_MB}MB)")
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path): os.remove(file_path)
        raise HTTPException(500, f"Upload failed: {str(e)}")
            
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM locations WHERE external_id=?", (location_id,))
    loc = cur.fetchone()
    if not loc:
        conn.close()
        os.remove(file_path)
        return {"error": "Invalid location_id"}
    cur.execute("INSERT INTO print_jobs (location, location_id, category, printer, status, type, time, file_path, file_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (loc["name"], location_id, "A4", "Pending", "Queued", "None", utcnow(), file_path, file.filename.split(".")[-1]))
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    print_queue.put((2, {"job_id": job_id, "location_id": location_id, "category": "A4", "payload": file_path}))
    return {"job_id": job_id, "status": "Queued"}

@app.get("/sync-locations")
def sync_locations():
    url = "https://vhealth.saveetha.com/api/api/v1/clinics/public"
    try:
        response = requests.get(url, timeout=10)
        clinics = response.json()
        conn = get_connection()
        cur = conn.cursor()
        for clinic in clinics:
            name, block, external_id = clinic.get("name", "").strip(), clinic.get("block", ""), str(clinic.get("id"))
            if not name or not external_id: continue
            final_name = f"{name} ({block})" if block else name
            cur.execute("INSERT INTO locations (name, block, external_id) VALUES (?, ?, ?) ON CONFLICT(external_id) DO UPDATE SET name=excluded.name, block=excluded.block", (final_name, block, external_id))
            cur.execute("INSERT INTO mapping (location, external_id, a4Primary, a4Secondary, barPrimary, barSecondary) VALUES (?, ?, 'None', 'None', 'None', 'None') ON CONFLICT(external_id) DO UPDATE SET location=excluded.location", (final_name, external_id))
        conn.commit()
        conn.close()
        invalidate_cache() # 🔹 Use thread-safe clear
        return {"message": "Synced", "count": len(clinics)}
    except Exception as e: return {"error": str(e)}

@app.get("/agent/jobs")
def get_agent_jobs(agent_id: str, token: str, location_id: str = None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        # 🔹 1. Secure Token Validation / Registration
        cur.execute("SELECT token, location_id FROM agents WHERE agent_id=?", (agent_id,))
        agent_row = cur.fetchone()
        
        if agent_row:
            if agent_row["token"] != token:
                raise HTTPException(401, "Invalid Agent Token")
            # Update location_id if provided and different
            if not location_id:
                location_id = agent_row["location_id"]
            elif agent_row["location_id"] != location_id:
                cur.execute("UPDATE agents SET location_id=? WHERE agent_id=?", (location_id, agent_id))
        else:
            # First contact registration
            cur.execute("INSERT INTO agents (agent_id, location_id, status, last_seen, token) VALUES (?, ?, 'Online', datetime('now'), ?)",
                        (agent_id, location_id, token))
            conn.commit()
        
        # 🔹 2. Atomic Lease Mechanism
        # Fetch jobs that are Pending OR have a timed-out lease (older than 2 mins)
        cur.execute("BEGIN TRANSACTION")
        try:
            reclaim_threshold = datetime.now(timezone.utc).timestamp() - 300 # 5 mins
            
            # 🔹 Step 1: Find candidates with PRIORITY ORDERING
            cur.execute("""
                SELECT id FROM print_jobs 
                WHERE location_id=? 
                AND (status=? OR (status=? AND locked_at < ?))
                AND retry_count < 3
                ORDER BY priority ASC, id ASC
                LIMIT 1
            """, (location_id, JobStatus.PENDING_AGENT, JobStatus.AGENT_PRINTING, str(reclaim_threshold)))
            
            candidates = [r["id"] for r in cur.fetchall()]
            
            if candidates:
                placeholders = ",".join(["?"] * len(candidates))
                cur.execute(f"""
                    UPDATE print_jobs 
                    SET status=?, locked_at=?, locked_by=?
                    WHERE id IN ({placeholders})
                """, (JobStatus.AGENT_PRINTING, str(datetime.now(timezone.utc).timestamp()), agent_id, *candidates))
                
                # 🔹 3. Only fetch what we JUST locked to prevent duplication
                # Filter: Ensure agents never receive jobs with 'Pending' or missing printer names
                cur.execute(f"""
                    SELECT id, category, printer, patient_id, priority, retry_count, location_id
                    FROM print_jobs 
                    WHERE id IN ({placeholders})
                    AND printer IS NOT NULL
                    AND printer != 'Pending'
                    AND printer != ''
                """, candidates)
                rows = cur.fetchall()
                if not rows:
                    logger.warning("[DATA INTEGRITY] /agent/jobs returned no valid jobs after printer filter — possible routing delay")
                    conn.commit()
                    return []
                    
                jobs = [dict(row) for row in rows]
            else:
                jobs = []
            
            conn.commit()
            return jobs
        except Exception as e:
            conn.rollback()
            raise HTTPException(500, str(e))
    finally:
        conn.close()

@app.get("/admin/audit-logs")
def get_audit_logs(
    actor: str = None,
    patient_id: str = None, 
    action: str = None,
    from_date: str = None,
    to_date: str = None,
    limit: int = 100,
    offset: int = 0,
    current_user = Depends(require_admin)
):
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    
    if actor:
        query += " AND actor=?"
        params.append(actor)
    if patient_id:
        query += " AND patient_id=?"
        params.append(patient_id)
    if action:
        query += " AND action=?"
        params.append(action)
    if from_date:
        query += " AND timestamp >= ?"
        params.append(from_date)
    if to_date:
        query += " AND timestamp <= ?"
        params.append(to_date)
        
    # Total count
    placeholder = get_placeholder()
    count_query = query.replace("SELECT *", "SELECT COUNT(*)").replace("?", placeholder)
    cur.execute(count_query, params)
    total = get_row_value(cur.fetchone(), 'count', 0) or 0
    
    final_query = query.replace("?", placeholder) + " ORDER BY timestamp DESC LIMIT " + placeholder + " OFFSET " + placeholder
    params.extend([limit, offset])
    cur.execute(final_query, params)
    logs = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {"logs": logs, "total": total}


@app.get("/admin/archive-stats")
def get_archive_stats(current_user: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    
    cur.execute("SELECT COUNT(*) FROM print_jobs")
    active_count = get_row_value(cur.fetchone(), 'count', 0) or 0
    
    cur.execute("SELECT COUNT(*) FROM archived_jobs")
    archived_count = get_row_value(cur.fetchone(), 'count', 0) or 0
    
    cur.execute("SELECT MIN(time) FROM print_jobs")
    oldest_job = get_row_value(cur.fetchone(), 'min', 0)

    
    db_size = os.path.getsize(settings.database_path) / (1024 * 1024) # MB
    
    conn.close()
    return {
        "active_jobs": active_count,
        "archived_jobs": archived_count,
        "oldest_active_job": oldest_job,
        "db_size_mb": round(db_size, 2)
    }

@app.get("/admin/job-health")
def get_job_health(current_user: dict = Depends(require_admin)):
    """Anomalous job state detection for reliability."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) as count FROM print_jobs GROUP BY status")
    rows = cur.fetchall()
    counts = {r['status']: r['count'] for r in rows}
    conn.close()
    
    # Threshold-based warnings
    warnings = []
    if (counts.get(JobStatus.PRINTING, 0) + counts.get(JobStatus.AGENT_PRINTING, 0)) > 10:
        warnings.append(f"Stuck detections: {counts.get(JobStatus.PRINTING, 0) + counts.get(JobStatus.AGENT_PRINTING, 0)} jobs active for too long.")
    if counts.get(JobStatus.FAILED, 0) > 20:
        warnings.append(f"High failure alert: {counts[JobStatus.FAILED]} jobs in Failed state.")
    if counts.get(JobStatus.QUEUED, 0) > 50:
        warnings.append(f"Congestion alert: {counts[JobStatus.QUEUED]} jobs waiting in queue.")
        alert_deduplicated("large_queue_backlog", 
          "Large Print Queue Backlog",
          f"<p>{counts[JobStatus.QUEUED]} jobs are queued but not printing. Check printer and agent status.</p>")
    
    return {"status_counts": counts, "warnings": warnings}

@app.post("/admin/test-alert")
def test_alert(current_user: dict = Depends(require_admin)):
    alert("Test Alert", "<p>This is a test alert from PrintHub. If you receive this, alerting is working correctly.</p>")
    return {"status": "alert sent via all configured channels"}

@app.post("/agent/fail")
def fail_agent_job(job_id: int, agent_id: str, token: str, error: str):
    conn = get_connection()
    cur = conn.cursor()
    # Security
    cur.execute("SELECT id FROM agents WHERE agent_id=? AND token=?", (agent_id, token))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(401)
        
    # Increment retries
    cur.execute("UPDATE print_jobs SET retry_count = retry_count + 1 WHERE id=?", (job_id,))
    
    # Check if max retries exceeded
    cur.execute("SELECT retry_count, file_path, category, location_id, printer FROM print_jobs WHERE id=?", (job_id,))
    row = cur.fetchone()
    if row and row["retry_count"] >= 3:
        cur.execute("UPDATE print_jobs SET status=?, error_message=? WHERE id=?", (JobStatus.FAILED_AGENT, error, job_id))
        
        # 🔹 ALERT: Critical failure
        alert_deduplicated(f"job_failed_{job_id}",
          f"Print Job Failed: JOB{str(job_id).zfill(3)}",
          f"<p>Job <b>JOB{str(job_id).zfill(3)}</b> failed permanently after {row['retry_count']} retries.<br>Category: {row['category']}<br>Location: {row['location_id']}<br>Last error: {error}</p>")
        
        # 🔹 CLEANUP: Upload file after failure exhaustion
        safe_delete(row["file_path"])
    else:
        # Release for retry
        cur.execute("UPDATE print_jobs SET status=?, locked_by=NULL, error_message=? WHERE id=?", (JobStatus.PENDING_AGENT, None, job_id))
        
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/agent/job/{job_id}/file")
def get_agent_job_file(job_id: int, agent_id: str, token: str):
    conn = get_connection()
    cur = conn.cursor()
    # 🔹 1. Validate Agent Token & Job Ownership
    cur.execute("""
        SELECT a.location_id, j.file_path, j.locked_by 
        FROM agents a, print_jobs j
        WHERE a.agent_id=? AND a.token=? AND j.id=?
    """, (agent_id, token, job_id))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(401, "Unauthorized access to job")
    
    if row["locked_by"] != agent_id:
        raise HTTPException(403, "Job owned by another agent (Lease expired)")
        
    if not row["file_path"] or not os.path.exists(row["file_path"]):
        raise HTTPException(404, "File not found")
        
    # 🔹 2. Streaming Response for Large Files
    from fastapi.responses import StreamingResponse
    def iterfile():
        with open(row["file_path"], "rb") as f:
            while chunk := f.read(1024 * 1024): # 1MB chunks
                yield chunk
                
    return StreamingResponse(iterfile(), media_type="application/octet-stream")

@app.post("/agent/heartbeat")
def agent_heartbeat(agent_id: str, token: str, location_id: str = None, hostname: str = None):
    conn = get_connection()
    cur = conn.cursor()
    
    # 1. Token Check
    cur.execute("SELECT token FROM agents WHERE agent_id=?", (agent_id,))
    agent = cur.fetchone()
    if agent:
        if agent["token"] != token:
            conn.close()
            raise HTTPException(401, "Invalid agent token")
        # Update
        cur.execute("UPDATE agents SET last_seen=?, status='Online', hostname=? WHERE agent_id=?", (utcnow(), hostname, agent_id))
        if location_id:
            cur.execute("UPDATE agents SET location_id=? WHERE agent_id=?", (location_id, agent_id))
    else:
        # Register
        cur.execute("INSERT INTO agents (agent_id, location_id, status, last_seen, token, hostname) VALUES (?, ?, 'Online', datetime('now'), ?, ?)",
                    (agent_id, location_id, token, hostname))
    
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/agents")
def get_agents(user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT agent_id, location_id, status, last_seen, hostname
        FROM agents
        ORDER BY last_seen DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/admin/activation-codes")
def list_activation_codes(current_user: dict = Depends(require_admin)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, code, location_id, used, agent_id, created_at, used_at
        FROM activation_codes
        ORDER BY created_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    # Mask raw code for used codes
    for r in rows:
        if r['used']:
            r['code'] = "USED-****"
    return rows

@app.delete("/admin/activation-codes/{code_id}")
def revoke_activation_code(code_id: int, current_user: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT used FROM activation_codes WHERE id={placeholder}", (code_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Code not found")
    
    used = get_row_value(row, "used", 0)
    if used:
        conn.close()
        raise HTTPException(400, "Cannot revoke an already-used code")
    
    cur.execute(f"DELETE FROM activation_codes WHERE id={placeholder}", (code_id,))
    conn.commit()
    conn.close()
    return {"status": "revoked"}


@app.post("/admin/activation-codes")
@limiter.limit("30/hour")
def create_activation_code(request: Request, location_id: str, admin: dict = Depends(require_admin)):
    # Note: admin_token check removed as require_admin already validates admin identity via JWT
    code = secrets.token_hex(4).upper()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO activation_codes (code, location_id, used, created_at)
        VALUES (?, ?, 0, ?)
    """, (code, location_id, utcnow()))
    conn.commit()
    conn.close()
    log_audit(admin.get("sub", "unknown"), "user", "CREATE_ACTIVATION_CODE", details={"location_id": location_id})
    return {"activation_code": code, "location_id": location_id}

@app.post("/agent/register")
@limiter.limit("5/minute")
def register_agent(request: Request, data: AgentRegisterRequest):
    activation_code = data.activation_code
    hostname = data.hostname
    
    if not activation_code:
        raise HTTPException(400, "Activation code required")
        
    conn = get_connection()
    cur = conn.cursor()
    
    # Validate activation code
    cur.execute("SELECT * FROM activation_codes WHERE code=? AND used=0", (activation_code,))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(403, "Invalid or already used activation code")
        
    location_id = row["location_id"]
    agent_id = f"agent_{secrets.token_hex(6)}"
    token = secrets.token_hex(24)
    
    # Create agent
    cur.execute("""
        INSERT INTO agents (agent_id, location_id, status, last_seen, token, hostname)
        VALUES (?, ?, 'Online', ?, ?, ?)
    """, (agent_id, location_id, utcnow(), token, hostname))
    
    # Mark code as used
    cur.execute("""
        UPDATE activation_codes 
        SET used=1, agent_id=?, used_at=? 
        WHERE code=?
    """, (agent_id, utcnow(), activation_code))
    
    conn.commit()
    conn.close()
    
    log_audit(agent_id, "agent", "REGISTER_AGENT", details={"hostname": hostname, "location_id": location_id})
    
    return {
        "agent_id": agent_id,
        "token": token,
        "location_id": location_id
    }

@app.get("/agent/config")
def get_agent_config(agent_id: str, token: str, location_id: str = None):
    conn = get_connection()
    cur = conn.cursor()
    
    # 1. Token Check / Registration
    cur.execute("SELECT token FROM agents WHERE agent_id=?", (agent_id,))
    agent = cur.fetchone()
    if agent:
        if agent["token"] != token:
            conn.close()
            raise HTTPException(401, "Invalid agent token")
    else:
        # First contact registration
        cur.execute("INSERT INTO agents (agent_id, location_id, status, last_seen, token) VALUES (?, ?, 'Online', datetime('now'), ?)",
                    (agent_id, location_id, token))
        conn.commit()

    # 2. Get location_id if not provided
    if not location_id:
        cur.execute("SELECT location_id FROM agents WHERE agent_id=?", (agent_id,))
        agent_row = cur.fetchone()
        location_id = agent_row["location_id"] if agent_row else None

    # 3. Get all USB printers mapped to this location
    if not location_id:
        conn.close()
        return {"printers": []}

    cur.execute("""
        SELECT p.name 
        FROM printers p
        JOIN mapping m ON (
            m.a4Primary = p.name OR 
            m.a4Secondary = p.name OR 
            m.barPrimary = p.name OR 
            m.barSecondary = p.name
        )
        WHERE m.external_id=? AND p.connection_type='USB'
    """, (location_id,))
    printers = [r["name"] for r in cur.fetchall()]
    conn.close()
    return {"printers": list(set(printers))}

@app.post("/agent/confirm")
def confirm_agent_job(job_id: int, agent_id: str, token: str):
    conn = get_connection()
    cur = conn.cursor()

    try:
        # ── 1. Security ──────────────────────────────────────────────────────────
        cur.execute("SELECT id FROM agents WHERE agent_id=? AND token=?", (agent_id, token))
        if not cur.fetchone():
            conn.close()
            raise HTTPException(401)

        # ── 2. Fetch job ─────────────────────────────────────────────────────────
        cur.execute("SELECT printer, file_path, category, locked_by FROM print_jobs WHERE id=?", (job_id,))
        job = cur.fetchone()
        if not job:
            conn.close()
            raise HTTPException(404, "Job not found")

        # ── Ownership: allow if locked_by matches OR is NULL (spooler fallback) ──
        if job["locked_by"] is not None and job["locked_by"] != agent_id:
            conn.close()
            raise HTTPException(403, "Job owned by another agent or lease expired")

        # ── 3. Fetch printer ─────────────────────────────────────────────────────
        cur.execute("SELECT status, last_updated, last_update_source FROM printers WHERE name=?", (job["printer"],))
        printer = cur.fetchone()

        if not printer:
            logger.error(f"[CONFIRM REJECTED] Job {job_id}: Printer not found. Marking Failed.")
            cur.execute("UPDATE print_jobs SET status=? WHERE id=?", (JobStatus.FAILED, job_id))
            conn.commit()
            conn.close()
            return {"status": "error", "message": "Printer not found"}

        # ── Gate A: Printer must be Online ────────────────────────────────────────
        if printer["status"] != "Online":
            logger.error(f"[CONFIRM REJECTED] Job {job_id}: Printer is '{printer['status']}'. Marking Failed.")
            cur.execute("UPDATE print_jobs SET status=? WHERE id=?", (JobStatus.FAILED, job_id))
            conn.commit()
            conn.close()
            return {"status": "error", "message": "Printer not Online"}

        # ── Gate B: Heartbeat freshness (90s threshold) ───────────────────────────
        try:
            if printer["last_updated"]:
                last_updated_dt = datetime.strptime(printer["last_updated"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - last_updated_dt).total_seconds()
                if age > 90:
                    logger.error(f"[CONFIRM REJECTED] Job {job_id}: Printer heartbeat stale ({age:.1f}s). Marking Failed.")
                    cur.execute("UPDATE print_jobs SET status=? WHERE id=?", (JobStatus.FAILED, job_id))
                    conn.commit()
                    conn.close()
                    return {"status": "error", "message": "Printer status stale"}
        except Exception as e:
            logger.warning(f"[GATE B] Timestamp parse error for job {job_id}: {e} — skipping gate")

        # ── Gate C: Minimum duration (skip if locked_at is missing) ──────────────
        try:
            cur.execute("SELECT locked_at FROM print_jobs WHERE id=?", (job_id,))
            locked_row = cur.fetchone()
            locked_at_str = locked_row["locked_at"] if locked_row else None
            if locked_at_str:
                duration = datetime.now(timezone.utc).timestamp() - float(locked_at_str)
                if duration < 0.05:
                    logger.error(f"[CONFIRM REJECTED] Job {job_id}: Instant completion ({duration:.2f}s). Marking Failed.")
                    cur.execute("UPDATE print_jobs SET status=? WHERE id=?", (JobStatus.FAILED, job_id))
                    conn.commit()
                    conn.close()
                    return {"status": "error", "message": "Instant completion detected"}
        except Exception as e:
            logger.warning(f"[GATE C] Duration check error for job {job_id}: {e} — skipping gate")

        # ── Gate D: Source must be from Agent ─────────────────────────────────────
        source = str(printer["last_update_source"] or "")
        if not source.startswith("Agent"):
            logger.error(f"[CONFIRM REJECTED] Job {job_id}: Untrusted source '{source}'. Marking Failed.")
            cur.execute("UPDATE print_jobs SET status=? WHERE id=?", (JobStatus.FAILED, job_id))
            conn.commit()
            conn.close()
            return {"status": "error", "message": "Untrusted status source"}

        # ── Success ───────────────────────────────────────────────────────────────
        logger.info(f"[CONFIRM ACCEPTED] Job {job_id}: Marking Completed.")
        cur.execute("UPDATE print_jobs SET status=?, completed_at=? WHERE id=? AND status!=?",
                    (JobStatus.COMPLETED, utcnow(), job_id, JobStatus.COMPLETED))
        safe_delete(job["file_path"])
        conn.commit()
        conn.close()
        log_audit(agent_id, "agent", "JOB_COMPLETED", resource_type="print_job", resource_id=job_id, details={"printer": job["printer"], "category": job["category"]})
        return {"status": "ok"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CONFIRM ERROR] Job {job_id}: Unexpected error: {e}", exc_info=True)
        try:
            conn.close()
        except: pass
        raise HTTPException(500, f"Internal error: {str(e)}")

@app.post("/agent/printer-status")
def update_agent_printer_status(agent_id: str, token: str, data: dict):
    # Security
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM agents WHERE agent_id=? AND token=?", (agent_id, token))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(401)
        
    printer_name = data.get("printer_name")
    new_status = data.get("status")
    
    if printer_name and new_status:
        # 🔹 STRICT OWNERSHIP: ONLY USB PRINTERS
        cur.execute("SELECT id, status, connection_type FROM printers WHERE name=?", (printer_name,))
        printer = cur.fetchone()
        
        if not printer:
            logger.warning(f"Agent {agent_id} reported unknown printer: {printer_name}")
        elif printer["connection_type"] != "USB":
            logger.warning(f"CONFLICT: Agent {agent_id} tried to update IP printer '{printer_name}'. REJECTED.")
        else:
            old_status = printer["status"]
            # 🔹 Always update last_updated even if status unchanged
            cur.execute("""
                UPDATE printers 
                SET status=?, last_updated=?, last_update_source=? 
                WHERE id=?
            """, (new_status, utcnow(), f"Agent:{agent_id}", printer["id"]))
            
            if old_status != new_status:
                logger.info(f"STATUS CHANGE: '{printer_name}' [USB] | {old_status} -> {new_status}")
            else:
                logger.debug(f"STATUS REFRESH: '{printer_name}' [USB] | Still {new_status}")
            
            conn.commit()
            
    conn.close()
    return {"status": "ok"}

@app.get("/debug/printers")
def debug_printers():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, ip, status, category, connection_type, last_updated, last_update_source FROM printers")
    rows = []
    for r in cur.fetchall():
        row = dict(r)
        row["source_of_truth"] = "agent" if row["connection_type"] == "USB" else "server"
        rows.append(row)
    conn.close()
    return rows

@app.post("/admin/cleanup-logs")
def cleanup_logs(days: int = 30, admin_token: str = None):
    expected_token = settings.admin_cleanup_token
    if admin_token != expected_token:
        raise HTTPException(403, "Invalid admin token")
        
    conn = get_connection()
    cur = conn.cursor()
    # Calculate threshold based on current time
    threshold_dt = datetime.now(timezone.utc).timestamp() - (days * 86400)
    
    # Logs use utcnow() which is formatted string. We need to handle comparison.
    # Simplified: DELETE WHERE time < (current_time - days)
    # Using SQLITE date functions if possible, or just string comparison if sorted.
    cur.execute("DELETE FROM print_logs WHERE time < datetime('now', '-' || ? || ' days')", (str(days),))
    count = cur.rowcount
    conn.commit()
    conn.close()
    return {"status": "ok", "deleted_logs": count}

def process_queue(worker_id):
    import time
    logger.info(f"Worker-{worker_id} started")
    while True:
        job_item = None
        try:
            priority, job = print_queue.get()
            job_item = job
            if not job: continue
            
            logger.info(f"Worker-{worker_id} processing job {job['job_id']} (Prio: {priority})")
            
            # 🔹 DUPLICATE PREVENTION: Verify status is still valid
            conn = get_connection()
            try:
                cur = conn.cursor()
                cur.execute("SELECT status FROM print_jobs WHERE id=?", (job['job_id'],))
                row = cur.fetchone()
                if not row or row['status'] not in [JobStatus.QUEUED, JobStatus.RETRYING]:
                    logger.warning(f"Worker-{worker_id} skipping job {job['job_id']} - already in state '{row['status'] if row else 'Unknown'}'")
                    continue
            finally:
                conn.close()

            # 🔹 Timeout-safe execution (60s limit)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                if job["category"] == "Barcode":
                    os.makedirs("uploads", exist_ok=True)
                    barcode_file = f"uploads/barcode_{job['job_id']}.zpl"
                    payload = job["payload"]
                    zpl_content = payload if isinstance(payload, bytes) else payload.encode()
                    logger.info("[ZPL DEBUG]\n" + zpl_content.decode(errors='ignore'))
                    with open(barcode_file, "wb") as f:
                        f.write(zpl_content)
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE print_jobs SET file_path=? WHERE id=?", (barcode_file, job['job_id']))
                    conn.commit()
                    conn.close()
                    job["payload"] = barcode_file

                future = executor.submit(print_with_failover, job["job_id"], job["location_id"], job["category"], job["payload"])
                try:
                    future.result(timeout=60)
                except concurrent.futures.TimeoutError:
                    logger.error(f"Worker-{worker_id} job {job['job_id']} TIMED OUT after 60s")
            
        except Exception as e:
            if "RETRY" in str(e) and job_item:
                logger.warning(f"Worker-{worker_id} retrying job {job_item['job_id']} in 2s")
                time.sleep(2)
                print_queue.put((2, job_item))
            else:
                logger.error(f"Worker-{worker_id} error: {e}")
        finally:
            if job_item:
                print_queue.task_done()

# 🔹 Uvicorn server startup
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)

# 🔹 Startup: Recover jobs BEFORE starting workers
recover_queue()

# 🔹 Scale: 3 Parallel Workers
for i in range(3):
    threading.Thread(target=process_queue, args=(i,), daemon=True).start()

# 🔹 BACKGROUND TASKS: Monitoring & Maintenance
def monitor_loop():
    logger.info("Background Monitoring Thread started")
    while True:
        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            
            # 1. HEARTBEAT ENFORCEMENT (Mark agents Offline if > threshold)
            cur.execute("SELECT agent_id, hostname, location_id FROM agents WHERE status='Online' AND last_seen < datetime('now', '-' || ? || ' seconds')", (str(settings.stale_threshold_seconds),))
            dead_agents = cur.fetchall()
            for agent in dead_agents:
                logger.warning(f"Agent {agent['agent_id']} TIMED OUT. Marking Offline.")
                cur.execute("UPDATE agents SET status='Offline' WHERE agent_id=?", (agent["agent_id"],))
                
                # 🔹 ALERT: Agent disconnected
                alert_deduplicated(f"agent_offline_{agent['agent_id']}",
                  f"Agent Offline: {agent['hostname']}",
                  f"<p>Print agent <b>{agent['hostname']}</b> (ID: {agent['agent_id']}) at location <b>{agent['location_id']}</b> stopped heartbeating.</p>")

            # 2. USB PRINTER TIMEOUT FALLBACK (Every 60s)
            cur.execute("""
                SELECT name, location_id FROM printers 
                WHERE connection_type='USB' AND status='Online'
                AND last_updated < datetime('now', '-' || ? || ' seconds')
            """, (str(settings.stale_threshold_seconds),))
            timed_out = cur.fetchall()
            for p in timed_out:
                logger.warning(f"TIMEOUT: USB Printer '{p['name']}' stale (>45s). Marking Offline.")
                cur.execute("UPDATE printers SET status='Offline', last_update_source='Server:USBTimeout' WHERE name=?", (p["name"],))
                
                # 🔹 ALERT: Printer offline
                alert_deduplicated(f"printer_offline_{p['name']}", 
                  f"Printer Offline: {p['name']}",
                  f"<p>Printer <b>{p['name']}</b> at location <b>{p['location_id']}</b> went offline at {utcnow()}.</p>")
                
            # 3. IP PRINTER MONITORING (Every 60s)
            cur.execute("SELECT id, name, ip, status FROM printers WHERE connection_type='IP' AND ip IS NOT NULL AND ip != ''")
            ip_printers = cur.fetchall()
            from services.printer_service import check_printer
            for p in ip_printers:
                is_alive = check_printer(p["ip"], timeout=2)
                new_status = "Online" if is_alive else "Offline"
                
                if p["status"] != new_status:
                    logger.info(f"STATUS UPDATE: '{p['name']}' [IP] | Source: Server | {p['status']} -> {new_status}")
                    cur.execute("""
                        UPDATE printers 
                        SET status=?, last_updated=?, last_update_source=? 
                        WHERE id=?
                    """, (new_status, utcnow(), "Server:IPMonitor", p["id"]))
                
            # 4. AUTOMATED LOG CLEANUP (Daily)
            cur.execute("DELETE FROM print_logs WHERE time < datetime('now', '-30 days')")
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Monitoring Loop error: {e}")
        finally:
            # 🔹 CRITICAL: Always close connection to prevent WAL lock accumulation
            if conn:
                try: conn.close()
                except: pass
            
        time.sleep(60)

# 🔹 SCHEDULER: Production Maintenance
scheduler = BackgroundScheduler()

@scheduler.scheduled_job('cron', hour=0, minute=0)
def clinical_daily_cleanup():
    """🔹 Runs every night at midnight"""
    logger.info("[MAINTENANCE] Starting clinical cleanup...")
    # 1. Backup
    backup_database()
    # 2. Archive
    archive_old_jobs(days_to_keep=30)
    # 3. Expire stale jobs (Safety)
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S UTC")
    cur.execute(f"UPDATE print_jobs SET status='Expired' WHERE status='Queued' AND time < {placeholder}", (cutoff,))
    conn.commit()
    conn.close()

# Real-time recovery
scheduler.add_job(recover_stuck_jobs, 'interval', minutes=1)
scheduler.start()


threading.Thread(target=monitor_loop, daemon=True).start()
