import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import uuid

import secrets
import requests
import threading
import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field, ConfigDict
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from logging_config import setup_logging
from database import (
    init_db, init_pool, close_pool,
    get_connection, get_cursor, get_placeholder, get_row_value,
    utcnow, JobStatus, safe_delete, seed_admin, archive_old_jobs, backup_database
)
from services.recovery import recover_stuck_jobs, check_database_integrity
from services.alerts import alert, alert_deduplicated
from services.barcode_service import build_print_payload, generate_patient_id
from services.routing_service import print_with_failover
from services.utils import is_usb_stale
from services.auth import hash_password, verify_password, create_token, decode_token
from services.audit import log_audit
from config import settings
from queue import PriorityQueue
import shutil
import json
from threading import Lock
import logging
import concurrent.futures

# 🔹 Logging Setup
setup_logging()
logger = logging.getLogger("Main")

# ━━━ WEBSOCKET BROADCAST INFRASTRUCTURE ━━━

_ws_loop: "asyncio.AbstractEventLoop | None" = None


class ConnectionManager:
    """Thread-safe WebSocket connection manager."""
    def __init__(self):
        self.active: list = []
        self._lock = threading.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        with self._lock:
            if ws in self.active:
                self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        with self._lock:
            targets = list(self.active)
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()


def broadcast_sync(event_type: str, data: dict):
    """Bridge from sync worker/monitor threads to async WebSocket broadcast."""
    if _ws_loop and not _ws_loop.is_closed():
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast({"type": event_type, "data": data}),
            _ws_loop,
        )


# ━━━ AGENT WEBSOCKET MANAGER ━━━

class AgentConnectionManager:
    """Manages persistent WebSocket connections from print agents (one per agent_id)."""
    def __init__(self):
        self._connections: dict = {}  # agent_id -> WebSocket
        self._lock = threading.Lock()

    async def connect(self, agent_id: str, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self._connections[agent_id] = ws

    def disconnect(self, agent_id: str):
        with self._lock:
            self._connections.pop(agent_id, None)

    async def send_to_agent(self, agent_id: str, message: dict):
        with self._lock:
            ws = self._connections.get(agent_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(agent_id)

    async def broadcast_to_agents(self, agent_ids: list, message: dict):
        for aid in agent_ids:
            await self.send_to_agent(aid, message)

    def connected_count(self) -> int:
        with self._lock:
            return len(self._connections)


agent_ws_manager = AgentConnectionManager()


def notify_agents_at_location_sync(location_id: str):
    """Push job_available to all WebSocket-connected agents at a location (sync-safe)."""
    if not (_ws_loop and not _ws_loop.is_closed()):
        return
    try:
        conn = get_connection()
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(
            f"SELECT agent_id FROM agents WHERE location_id={placeholder} AND status='Online'",
            (location_id,)
        )
        rows = cur.fetchall()
        conn.close()
        agent_ids = [get_row_value(r, "agent_id", 0) for r in rows]
    except Exception:
        return
    if not agent_ids:
        return
    asyncio.run_coroutine_threadsafe(
        agent_ws_manager.broadcast_to_agents(agent_ids, {"type": "job_available"}),
        _ws_loop,
    )


# ━━━ LIFESPAN: CLEAN STARTUP / SHUTDOWN ━━━

@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _ws_loop
    _ws_loop = asyncio.get_event_loop()

    # Ordered startup sequence
    init_db()
    init_pool()
    check_dependencies()
    startup_cleanup()
    self_healing()
    seed_admin("admin", hash_password("Admin@PrintHub2026"))
    recover_queue()

    for i in range(3):
        threading.Thread(target=process_queue, args=(i,), daemon=True).start()
    threading.Thread(target=monitor_loop, daemon=True).start()

    scheduler.add_job(recover_stuck_jobs, "interval", minutes=1)
    scheduler.add_job(check_database_integrity, "cron", hour=2, minute=0)
    scheduler.start()
    logger.info("PrintHub production system ready")

    yield

    # Ordered shutdown
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    close_pool()
    logger.info("PrintHub shutdown complete")


print_queue = PriorityQueue(maxsize=500)
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    lifespan=lifespan,
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
        placeholder = get_placeholder()
        cur.execute(f"SELECT 1")
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        overall = "critical"

    
    # 2. Active agents check
    try:
        conn = get_connection()
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"SELECT COUNT(*) FROM agents WHERE status='Online'")
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
        placeholder = get_placeholder()
        cur.execute(f"SELECT COUNT(*) FROM print_jobs WHERE status='Printing' AND locked_at < {placeholder}",
                    (str((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()),))
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
    
    checks["queue_depth"] = print_queue.qsize()
    checks["ws_clients"] = len(ws_manager.active)
    checks["ws_agents"] = agent_ws_manager.connected_count()

    status_code = 200 if overall in ("healthy", "warning") else 503
    return JSONResponse(
        content={
            "status": overall,
            "checks": checks,
            "version": "3.5.0-PRO",
            "timestamp": utcnow()
        },
        status_code=status_code
    )
metrics_lock = Lock()

# 🔹 In-Memory Cache with Thread Safety
_cache = {}
cache_lock = Lock()

def get_cached_data(key):
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


def self_healing():
    """🔹 Classify and fix printer data on startup"""
    logger.info("Running printer self-healing...")
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    # 1. Force USB printers to have NULL IP
    cur.execute(f"SELECT id, name FROM printers WHERE connection_type='USB' AND ip IS NOT NULL")
    bad_usb = cur.fetchall()
    for p in bad_usb:
        logger.warning(f"SELF-HEAL: USB printer '{p['name']}' had an IP. Clearing it.")
        cur.execute(f"UPDATE printers SET ip=NULL WHERE id={placeholder}", (p["id"],))
        
    # 2. Warn about IP printers without IP
    cur.execute(f"SELECT id, name FROM printers WHERE connection_type='IP' AND (ip IS NULL OR ip='')")
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    # 1. Queued & Retrying
    cur.execute(f"SELECT * FROM print_jobs WHERE status IN ({placeholder}, {placeholder})", 
                (JobStatus.QUEUED, JobStatus.RETRYING))
    pending_jobs = [dict(r) for r in cur.fetchall()]
    
    # 2. Stale Agent Printing (> 120s)
    stale_limit = datetime.now(timezone.utc).timestamp() - 120
    cur.execute(f"SELECT * FROM print_jobs WHERE status={placeholder} AND locked_at < {placeholder}", 
                (JobStatus.AGENT_PRINTING, str(stale_limit)))
    stale_jobs = [dict(r) for r in cur.fetchall()]
    
    # Reset stale jobs so they can be re-assigned
    for job in stale_jobs:
        logger.warning(f"RECOVERY: Job {job['id']} was stale in 'Agent Printing'. Resetting to 'Queued'.")
        cur.execute(f"UPDATE print_jobs SET status={placeholder}, locked_at=NULL, locked_by=NULL WHERE id={placeholder}", 
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

@app.get("/metrics")
def get_metrics():
    cached = get_cached_data("metrics")
    if cached: return cached
    
    with metrics_lock:
        conn = get_connection()
        try:
            cur = get_cursor(conn)
            placeholder = get_placeholder()
            
            # 1. Job Stats
            cur.execute(f"SELECT status, COUNT(*) as count FROM print_jobs GROUP BY status")
            job_stats = {row["status"]: row["count"] for row in cur.fetchall()}
            
            # 2. Agent Status
            cur.execute(f"SELECT agent_id, status, last_seen FROM agents")
            agents = [dict(row) for row in cur.fetchall()]
            
            # 3. Printer Status Breakdown
            cur.execute(f"SELECT status, COUNT(*) as count FROM printers WHERE status != 'Maintenance' GROUP BY status")
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

# 🔹 X-Request-ID Tracing Middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response

# 🔹 Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# 🔹 CORS SETUP
# Explicit origins from .env + a regex that covers any local-network IP so the
# same backend works from localhost, hotspot (192.168.137.x), WiFi IP, or any
# future IP without editing .env or restarting the backend.
_allowed_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

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
        placeholder = get_placeholder()
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

# ━━━ REAL-TIME WEBSOCKET ━━━

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=1008, reason="Invalid or expired token")
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.websocket("/ws/agent")
async def agent_websocket_endpoint(websocket: WebSocket, agent_id: str = None, token: str = None):
    """Persistent real-time channel for print agents."""
    if not agent_id or not token:
        await websocket.close(code=1008, reason="Missing agent_id or token")
        return
    # Authenticate agent credentials against DB
    row = None
    try:
        conn = get_connection()
        cur = get_cursor(conn)
        ph = get_placeholder()
        cur.execute(
            f"SELECT agent_id FROM agents WHERE agent_id={ph} AND token={ph}",
            (agent_id, token)
        )
        row = cur.fetchone()
        conn.close()
    except Exception:
        pass
    if not row:
        await websocket.close(code=1008, reason="Invalid agent credentials")
        return
    await agent_ws_manager.connect(agent_id, websocket)
    logger.info(f"[WS-AGENT] {agent_id} connected via WebSocket")
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        agent_ws_manager.disconnect(agent_id)
        logger.info(f"[WS-AGENT] {agent_id} disconnected")


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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT id, username, role, created_at, last_login, force_password_change FROM users ORDER BY created_at DESC")
    return [dict(r) for r in cur.fetchall()]

@app.post("/admin/users")
def create_user(data: CreateUserRequest, current_user=Depends(require_admin)):
    validate_password_complexity(data.password)
    
    if data.role not in ROLES:
        raise HTTPException(400, "Invalid role")
        
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    # Check if exists
    cur.execute(f"SELECT id FROM users WHERE username={placeholder}", (data.username,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(400, "Username already exists")
        
    cur.execute(f"""
        INSERT INTO users (username, password_hash, role, created_at, force_password_change)
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, 1)
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    # Get username for audit
    cur.execute(f"SELECT username FROM users WHERE id={placeholder}", (user_id,))
    target = cur.fetchone()
    if not target:
        conn.close()
        raise HTTPException(404, "User not found")
        
    cur.execute(f"UPDATE users SET role={placeholder} WHERE id={placeholder}", (data.role, user_id))
    conn.commit()
    conn.close()
    
    log_audit(current_user.get("sub", "unknown"), "user", "ROLE_CHANGE", status="SUCCESS", details=f"Changed {target['username']} to {data.role}")
    return {"message": "Role updated"}

@app.put("/admin/users/{user_id}/password")
def admin_reset_password(user_id: int, data: ResetPasswordRequest, current_user=Depends(require_admin)):
    validate_password_complexity(data.new_password)
    
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    # Get username for audit
    cur.execute(f"SELECT username FROM users WHERE id={placeholder}", (user_id,))
    target = cur.fetchone()
    if not target:
        conn.close()
        raise HTTPException(404, "User not found")
        
    cur.execute(f"UPDATE users SET password_hash={placeholder}, force_password_change=1 WHERE id={placeholder}", 
               (hash_password(data.new_password), user_id))
    conn.commit()
    conn.close()
    
    log_audit(current_user.get("sub", "unknown"), "user", "PASSWORD_RESET", status="SUCCESS", details=f"Reset password for {target['username']}")
    return {"message": "Password reset successfully"}

@app.delete("/admin/users/{user_id}")
def delete_user(user_id: int, current_user=Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    # Prevent self-deletion
    cur.execute(f"SELECT id, username FROM users WHERE username={placeholder}", (current_user["username"],))
    me = cur.fetchone()
    if me and me["id"] == user_id:
        conn.close()
        raise HTTPException(400, "You cannot delete your own account")
        
    # Get username for audit
    cur.execute(f"SELECT username FROM users WHERE id={placeholder}", (user_id,))
    target = cur.fetchone()
    if not target:
        conn.close()
        raise HTTPException(404, "User not found")
        
    cur.execute(f"DELETE FROM users WHERE id={placeholder}", (user_id,))
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
    cached = get_cached_data("dashboard")
    if cached: return cached

    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        
        cur.execute(f"SELECT COUNT(*) FROM printers")
        total = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute(f"SELECT COUNT(*) FROM printers WHERE status='Online'")
        live = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute(f"SELECT COUNT(*) FROM printers WHERE status='Offline'")
        offline = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute(f"SELECT COUNT(*) FROM print_jobs")
        job_total = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute(f"SELECT COUNT(*) FROM print_jobs WHERE status='Completed'")
        job_completed = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute(f"SELECT COUNT(*) FROM print_jobs WHERE status='Failed'")
        job_failed = get_row_value(cur.fetchone(), 'count', 0) or 0
        
        cur.execute(f"SELECT COUNT(*) FROM print_jobs WHERE retry_count > 0")
        job_retried = get_row_value(cur.fetchone(), 'count', 0) or 0


        cur.execute(f"""
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
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        cur.execute(f"SELECT * FROM printers")
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT * FROM printers WHERE name={placeholder}", (printer_name,))
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
        
        cur.execute(f"UPDATE printers SET status={placeholder}, last_updated={placeholder} WHERE name={placeholder}",
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"""
        INSERT INTO printers (name, ip, category, status, language, connection_type, last_updated, last_update_source)
        VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
        RETURNING id
    """, (data.name, data.ip, data.category, data.status, data.language, data.connection_type, utcnow(), "Initial"))
    new_id = get_row_value(cur.fetchone(), 'id', 0)
    conn.commit()
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"""
        UPDATE printers 
        SET name={placeholder}, ip={placeholder}, category={placeholder}, status={placeholder}, language={placeholder}, connection_type={placeholder} 
        WHERE id={placeholder}
    """, (data.name, data.ip, data.category, data.status, data.language, data.connection_type, printer_id))
    conn.commit()
    conn.close()
    invalidate_cache("dashboard")
    return {"message": "Updated"}

@app.delete("/printers/{printer_id}")
def delete_printer(printer_id: int, admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"DELETE FROM printers WHERE id={placeholder}", (printer_id,))
    conn.commit()
    conn.close()
    invalidate_cache("dashboard")
    return {"message": "Deleted"}

@app.get("/locations")
def get_locations(user: dict = Depends(get_current_user)):
    cached = get_cached_data("locations")
    if cached: return cached
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT name, external_id FROM locations")
    res = [dict(r) for r in cur.fetchall()]
    conn.close()
    set_cached_data("locations", res, 30)
    return res

@app.get("/mapping")
def get_mapping(user: dict = Depends(get_current_user)):
    cached = get_cached_data("mapping")
    if cached: return cached
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT * FROM mapping")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    set_cached_data("mapping", rows, 10)
    return rows

@app.put("/mapping/{mapping_id}")
def update_mapping(mapping_id: int, data: dict, admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"UPDATE mapping SET a4Primary={placeholder}, a4Secondary={placeholder}, barPrimary={placeholder}, barSecondary={placeholder} WHERE id={placeholder}",
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    where_clauses = []
    params = []
    
    if status:
        where_clauses.append(f"status = {placeholder}")
        params.append(status)
    if location_id:
        where_clauses.append(f"location_id = {placeholder}")
        params.append(location_id)
    if patient_id:
        where_clauses.append(f"patient_id LIKE {placeholder}")
        params.append(f"%{patient_id}%")
    if from_date:
        where_clauses.append(f"time >= {placeholder}")
        params.append(from_date)
    if to_date:
        where_clauses.append(f"time <= {placeholder}")
        params.append(to_date + " 23:59:59")
    if retried:
        where_clauses.append(f"retry_count > 0")
    if search:
        where_clauses.append(f"(printer LIKE {placeholder} OR category LIKE {placeholder} OR patient_name LIKE {placeholder})")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    # Get Total Count
    cur.execute(f"SELECT COUNT(*) FROM print_jobs {where_sql}", params)
    total = get_row_value(cur.fetchone(), 'count', 0) or 0
    
    # Get Results
    query = f"SELECT * FROM print_jobs {where_sql} ORDER BY id DESC LIMIT {placeholder} OFFSET {placeholder}"
    cur.execute(query, params + [limit, offset])
    jobs = [dict(r) for r in cur.fetchall()]
    
    conn.close()
    log_audit(user.get("sub", "unknown"), "user", "VIEW_JOBS", details={"filter": status, "search": search, "offset": offset})
    return {"jobs": jobs, "total": total}

@app.delete("/print-jobs")
def delete_all_jobs(admin: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT COUNT(*) FROM print_jobs")
    count = get_row_value(cur.fetchone(), 'count', 0) or 0
    cur.execute(f"DELETE FROM print_jobs")
    cur.execute(f"DELETE FROM print_logs")
    conn.commit()
    conn.close()
    log_audit(admin.get("sub", "unknown"), "user", "CLEAR_JOBS", details={"count": count})
    return {"message": "All jobs cleared"}

@app.get("/print-logs/{job_id}")
def get_print_logs(job_id: int, user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT * FROM print_logs WHERE job_id={placeholder} ORDER BY id ASC", (job_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/categories")
def get_categories(user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT name FROM categories")
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
def print_job(data: PrintJobRequest, user: dict = Depends(get_current_user)):
    location_id = data.location_id
    category = data.category
    if not location_id: raise HTTPException(400, "location_id is required")
    
    # 🔹 Strict Category Validation
    if category not in ["A4", "Barcode"]:
        raise HTTPException(400, "Invalid category. Must be 'A4' or 'Barcode'")

    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT name FROM locations WHERE external_id={placeholder}", (location_id,))
    loc = cur.fetchone()
    if not loc:
        conn.close()
        return {"error": "Invalid location_id"}
    patient_id = data.patient_id or generate_patient_id()
    loc_name = get_row_value(loc, "name", 0)
    cur.execute(f"INSERT INTO print_jobs (location, location_id, category, printer, status, type, time, patient_name, age, gender, patient_id, tube_type, test_name) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) RETURNING id",
            (loc_name, location_id, category, "Pending", "Queued", "None", utcnow(), data.patient_name, data.age, data.gender, patient_id, data.tube_type, data.test_name))
    job_id = get_row_value(cur.fetchone(), 'id', 0)
    conn.commit()
    conn.close()
    log_audit(user.get("sub", "api"), "user", "CREATE_JOB", resource_type="print_job", resource_id=job_id, patient_id=patient_id, details={"category": category, "location": location_id})
    if category == "Barcode":
        payload = build_print_payload({
            "patient_name": data.patient_name,
            "age": data.age,
            "gender": data.gender,
            "patient_id": patient_id,
            "tube_type": data.tube_type,
            "test_name": data.test_name,
            "category": category,
            "location": loc_name,
        })
        print_queue.put((data.priority, {
            "job_id": job_id,
            "location_id": location_id,
            "category": category,
            "payload": payload
        }))
    # Push real-time notification to agent(s) at this location
    notify_agents_at_location_sync(location_id)
    return {"job_id": job_id, "status": "Queued"}

@app.get("/mapping-validate")
def validate_mapping(user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT * FROM mapping")
    rows = [dict(r) for r in cur.fetchall()]
    
    issues = []
    # Fetch all printer names for validation
    cur.execute(f"SELECT name, ip FROM printers")
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT name FROM locations WHERE external_id={placeholder}", (location_id,))
    loc = cur.fetchone()
    if not loc:
        conn.close()
        os.remove(file_path)
        return {"error": "Invalid location_id"}
    cur.execute(f"INSERT INTO print_jobs (location, location_id, category, printer, status, type, time, file_path, file_type) VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}) RETURNING id",
                (loc["name"], location_id, "A4", "Pending", "Queued", "None", utcnow(), file_path, file.filename.split(".")[-1]))
    job_id = get_row_value(cur.fetchone(), 'id', 0)
    conn.commit()
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
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        for clinic in clinics:
            name, block, external_id = clinic.get("name", "").strip(), clinic.get("block", ""), str(clinic.get("id"))
            if not name or not external_id: continue
            final_name = f"{name} ({block})" if block else name
            cur.execute(f"INSERT INTO locations (name, block, external_id) VALUES ({placeholder}, {placeholder}, {placeholder}) ON CONFLICT(external_id) DO UPDATE SET name=excluded.name, block=excluded.block", (final_name, block, external_id))
            cur.execute(f"INSERT INTO mapping (location, external_id, a4Primary, a4Secondary, barPrimary, barSecondary) VALUES ({placeholder}, {placeholder}, 'None', 'None', 'None', 'None') ON CONFLICT(external_id) DO UPDATE SET location=excluded.location", (final_name, external_id))
        conn.commit()
        conn.close()
        invalidate_cache() # 🔹 Use thread-safe clear
        return {"message": "Synced", "count": len(clinics)}
    except Exception as e: return {"error": str(e)}

@app.get("/agent/jobs")
def get_agent_jobs(agent_id: str, token: str, location_id: str = None):
    conn = get_connection()
    try:
        cur = get_cursor(conn)
        placeholder = get_placeholder()
        # 🔹 1. Secure Token Validation / Registration
        cur.execute(f"SELECT token, location_id FROM agents WHERE agent_id={placeholder}", (agent_id,))
        agent_row = cur.fetchone()
        
        if agent_row:
            if agent_row["token"] != token:
                raise HTTPException(401, "Invalid Agent Token")
            # Update location_id if provided and different
            if not location_id:
                location_id = agent_row["location_id"]
            elif agent_row["location_id"] != location_id:
                cur.execute(f"UPDATE agents SET location_id={placeholder} WHERE agent_id={placeholder}", (location_id, agent_id))
        else:
            # First contact registration
            cur.execute(f"INSERT INTO agents (agent_id, location_id, status, last_seen, token) VALUES ({placeholder}, {placeholder}, 'Online', {placeholder}, {placeholder})",
                        (agent_id, location_id, utcnow(), token))
            conn.commit()
        
        # 🔹 2. Atomic Lease Mechanism
        # Fetch jobs that are Pending OR have a timed-out lease (older than 2 mins)
        if settings.db_type == "sqlite":
            cur.execute("BEGIN IMMEDIATE")
        # PostgreSQL: psycopg2 auto-starts a transaction on first query — no BEGIN needed
        try:
            reclaim_threshold = datetime.now(timezone.utc).timestamp() - 300 # 5 mins
            
            # 🔹 Step 1: Find candidates with PRIORITY ORDERING
            cur.execute(f"""
                SELECT id FROM print_jobs 
                WHERE location_id={placeholder} 
                AND (status={placeholder} OR (status={placeholder} AND locked_at < {placeholder}))
                AND retry_count < 3
                ORDER BY priority ASC, id ASC
                LIMIT 1
            """, (location_id, JobStatus.PENDING_AGENT, JobStatus.AGENT_PRINTING, str(reclaim_threshold)))
            
            candidates = [r["id"] for r in cur.fetchall()]
            
            if candidates:
                placeholders = ",".join([placeholder] * len(candidates))
                cur.execute(f"""
                    UPDATE print_jobs 
                    SET status={placeholder}, locked_at={placeholder}, locked_by={placeholder}
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    query = "SELECT * FROM audit_log WHERE 1=1"
    params = []
    
    if actor:
        query += " AND actor={placeholder}"
        params.append(actor)
    if patient_id:
        query += " AND patient_id={placeholder}"
        params.append(patient_id)
    if action:
        query += " AND action={placeholder}"
        params.append(action)
    if from_date:
        query += " AND timestamp >= {placeholder}"
        params.append(from_date + " 00:00:00 UTC")
    if to_date:
        query += " AND timestamp <= {placeholder}"
        params.append(to_date + " 23:59:59 UTC")
        
    # Total count
    placeholder = get_placeholder()
    count_query = query.replace("SELECT *", "SELECT COUNT(*)").replace("{placeholder}", placeholder)
    cur.execute(count_query, params)
    total = get_row_value(cur.fetchone(), 'count', 0) or 0
    
    final_query = query.replace("{placeholder}", placeholder) + " ORDER BY timestamp DESC LIMIT " + placeholder + " OFFSET " + placeholder
    params.extend([limit, offset])
    cur.execute(final_query, params)
    logs = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {"logs": logs, "total": total}


@app.get("/admin/archive-stats")
def get_archive_stats(current_user: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    cur.execute(f"SELECT COUNT(*) FROM print_jobs")
    active_count = get_row_value(cur.fetchone(), 'count', 0) or 0
    
    cur.execute(f"SELECT COUNT(*) FROM archived_jobs")
    archived_count = get_row_value(cur.fetchone(), 'count', 0) or 0
    
    cur.execute(f"SELECT MIN(time) FROM print_jobs")
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT status, COUNT(*) as count FROM print_jobs GROUP BY status")
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
    cur = get_cursor(conn)
    if settings.db_type == "sqlite":
        cur.execute("BEGIN IMMEDIATE")
    placeholder = get_placeholder()
    # Security
    cur.execute(f"SELECT id FROM agents WHERE agent_id={placeholder} AND token={placeholder}", (agent_id, token))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(401)
        
    # Increment retries
    cur.execute(f"UPDATE print_jobs SET retry_count = retry_count + 1 WHERE id={placeholder}", (job_id,))
    
    # Check if max retries exceeded
    cur.execute(f"SELECT retry_count, file_path, category, location_id, printer FROM print_jobs WHERE id={placeholder}", (job_id,))
    row = cur.fetchone()
    if row and row["retry_count"] >= 3:
        cur.execute(f"UPDATE print_jobs SET status={placeholder}, error_message={placeholder} WHERE id={placeholder}", (JobStatus.FAILED_AGENT, error, job_id))
        
        # 🔹 ALERT: Critical failure
        alert_deduplicated(f"job_failed_{job_id}",
          f"Print Job Failed: JOB{str(job_id).zfill(3)}",
          f"<p>Job <b>JOB{str(job_id).zfill(3)}</b> failed permanently after {row['retry_count']} retries.<br>Category: {row['category']}<br>Location: {row['location_id']}<br>Last error: {error}</p>")
        
        # 🔹 CLEANUP: Upload file after failure exhaustion
        safe_delete(row["file_path"])
    else:
        # Release for retry
        cur.execute(f"UPDATE print_jobs SET status={placeholder}, locked_by=NULL, error_message={placeholder} WHERE id={placeholder}", (JobStatus.PENDING_AGENT, None, job_id))
        
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/agent/job/{job_id}/file")
def get_agent_job_file(job_id: int, agent_id: str, token: str):
    conn = get_connection()
    cur = get_cursor(conn)
    if settings.db_type == "sqlite":
        cur.execute("BEGIN IMMEDIATE")
    placeholder = get_placeholder()
    # 🔹 1. Validate Agent Token & Job Ownership
    cur.execute(f"""
        SELECT a.location_id, j.file_path, j.locked_by 
        FROM agents a, print_jobs j
        WHERE a.agent_id={placeholder} AND a.token={placeholder} AND j.id={placeholder}
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
    cur = get_cursor(conn)
    if settings.db_type == "sqlite":
        cur.execute("BEGIN IMMEDIATE")
    placeholder = get_placeholder()
    
    # 1. Token Check
    cur.execute(f"SELECT token FROM agents WHERE agent_id={placeholder}", (agent_id,))
    agent = cur.fetchone()
    if agent:
        if agent["token"] != token:
            conn.close()
            raise HTTPException(401, "Invalid agent token")
        # Update
        cur.execute(f"UPDATE agents SET last_seen={placeholder}, status='Online', hostname={placeholder} WHERE agent_id={placeholder}", (utcnow(), hostname, agent_id))
        if location_id:
            cur.execute(f"UPDATE agents SET location_id={placeholder} WHERE agent_id={placeholder}", (location_id, agent_id))
    else:
        # Register
        cur.execute(f"INSERT INTO agents (agent_id, location_id, status, last_seen, token, hostname) VALUES ({placeholder}, {placeholder}, 'Online', {placeholder}, {placeholder}, {placeholder})",
                    (agent_id, location_id, utcnow(), token, hostname))
    
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/agents")
def get_agents(user: dict = Depends(get_current_user)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"""
        SELECT agent_id, location_id, status, last_seen, hostname
        FROM agents
        ORDER BY last_seen DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.delete("/agents/{agent_id}")
def delete_agent(agent_id: str, current_user: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT agent_id FROM agents WHERE agent_id={placeholder}", (agent_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(404, "Agent not found")
    cur.execute(f"DELETE FROM agents WHERE agent_id={placeholder}", (agent_id,))
    conn.commit()
    conn.close()
    log_audit(current_user.get("sub", "unknown"), "user", "DELETE_AGENT",
              details={"agent_id": agent_id})
    return {"status": "deleted"}


@app.get("/admin/activation-codes")
def list_activation_codes(current_user: dict = Depends(require_admin)):
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"""
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
    cur.execute(f"SELECT used, code, location_id FROM activation_codes WHERE id={placeholder}", (code_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Code not found")

    cur.execute(f"DELETE FROM activation_codes WHERE id={placeholder}", (code_id,))
    conn.commit()
    conn.close()
    used = get_row_value(row, "used", 0)
    action = "DELETE_USED_ACTIVATION_CODE" if used else "REVOKE_ACTIVATION_CODE"
    log_audit(current_user.get("sub", "unknown"), "user", action,
              details={"code_id": code_id, "location_id": get_row_value(row, "location_id", "")})
    return {"status": "deleted"}


@app.post("/admin/activation-codes")
@limiter.limit("30/hour")
def create_activation_code(request: Request, location_id: str, admin: dict = Depends(require_admin)):
    # Note: admin_token check removed as require_admin already validates admin identity via JWT
    code = secrets.token_hex(4).upper()
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"""
        INSERT INTO activation_codes (code, location_id, used, created_at)
        VALUES ({placeholder}, {placeholder}, 0, {placeholder})
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    
    # Validate activation code
    cur.execute(f"SELECT * FROM activation_codes WHERE code={placeholder} AND used=0", (activation_code,))
    row = cur.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(403, "Invalid or already used activation code")
        
    location_id = row["location_id"]
    agent_id = f"agent_{secrets.token_hex(6)}"
    token = secrets.token_hex(24)
    
    # Create agent
    cur.execute(f"""
        INSERT INTO agents (agent_id, location_id, status, last_seen, token, hostname)
        VALUES ({placeholder}, {placeholder}, 'Online', {placeholder}, {placeholder}, {placeholder})
    """, (agent_id, location_id, utcnow(), token, hostname))
    
    # Mark code as used
    cur.execute(f"""
        UPDATE activation_codes 
        SET used=1, agent_id={placeholder}, used_at={placeholder} 
        WHERE code={placeholder}
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
    cur = get_cursor(conn)
    if settings.db_type == "sqlite":
        cur.execute("BEGIN IMMEDIATE")
    placeholder = get_placeholder()
    
    # 1. Token Check / Registration
    cur.execute(f"SELECT token FROM agents WHERE agent_id={placeholder}", (agent_id,))
    agent = cur.fetchone()
    if agent:
        if agent["token"] != token:
            conn.close()
            raise HTTPException(401, "Invalid agent token")
    else:
        # First contact registration
        cur.execute(f"INSERT INTO agents (agent_id, location_id, status, last_seen, token) VALUES ({placeholder}, {placeholder}, 'Online', {placeholder}, {placeholder})",
                    (agent_id, location_id, utcnow(), token))
        conn.commit()

    # 2. Get location_id if not provided
    if not location_id:
        cur.execute(f"SELECT location_id FROM agents WHERE agent_id={placeholder}", (agent_id,))
        agent_row = cur.fetchone()
        location_id = agent_row["location_id"] if agent_row else None

    # 3. Get all USB printers mapped to this location
    if not location_id:
        conn.close()
        return {"printers": []}

    cur.execute(f"""
        SELECT p.name 
        FROM printers p
        JOIN mapping m ON (
            m.a4Primary = p.name OR 
            m.a4Secondary = p.name OR 
            m.barPrimary = p.name OR 
            m.barSecondary = p.name
        )
        WHERE m.external_id={placeholder} AND p.connection_type='USB'
    """, (location_id,))
    printers = [r["name"] for r in cur.fetchall()]
    conn.close()
    return {"printers": list(set(printers))}

@app.post("/agent/confirm")
def confirm_agent_job(job_id: int, agent_id: str, token: str):
    conn = get_connection()
    cur = get_cursor(conn)
    if settings.db_type == "sqlite":
        cur.execute("BEGIN IMMEDIATE")
    placeholder = get_placeholder()

    try:
        # ── 1. Security ──────────────────────────────────────────────────────────
        cur.execute(f"SELECT id FROM agents WHERE agent_id={placeholder} AND token={placeholder}", (agent_id, token))
        if not cur.fetchone():
            conn.close()
            raise HTTPException(401)

        # ── 2. Fetch job ─────────────────────────────────────────────────────────
        cur.execute(f"SELECT printer, file_path, category, locked_by FROM print_jobs WHERE id={placeholder}", (job_id,))
        job = cur.fetchone()
        if not job:
            conn.close()
            raise HTTPException(404, "Job not found")

        # ── Ownership: allow if locked_by matches OR is NULL (spooler fallback) ──
        if job["locked_by"] is not None and job["locked_by"] != agent_id:
            conn.close()
            raise HTTPException(403, "Job owned by another agent or lease expired")

        # ── 3. Fetch printer ─────────────────────────────────────────────────────
        cur.execute(f"SELECT status, last_updated, last_update_source FROM printers WHERE name={placeholder}", (job["printer"],))
        printer = cur.fetchone()

        if not printer:
            logger.error(f"[CONFIRM REJECTED] Job {job_id}: Printer not found. Marking Failed.")
            cur.execute(f"UPDATE print_jobs SET status={placeholder} WHERE id={placeholder}", (JobStatus.FAILED, job_id))
            conn.commit()
            conn.close()
            return {"status": "error", "message": "Printer not found"}

        # ── Gate A: Printer must be Online ────────────────────────────────────────
        if printer["status"] != "Online":
            logger.error(f"[CONFIRM REJECTED] Job {job_id}: Printer is '{printer['status']}'. Marking Failed.")
            cur.execute(f"UPDATE print_jobs SET status={placeholder} WHERE id={placeholder}", (JobStatus.FAILED, job_id))
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
                    cur.execute(f"UPDATE print_jobs SET status={placeholder} WHERE id={placeholder}", (JobStatus.FAILED, job_id))
                    conn.commit()
                    conn.close()
                    return {"status": "error", "message": "Printer status stale"}
        except Exception as e:
            logger.warning(f"[GATE B] Timestamp parse error for job {job_id}: {e} — skipping gate")

        # ── Gate C: Minimum duration (skip if locked_at is missing) ──────────────
        try:
            cur.execute(f"SELECT locked_at FROM print_jobs WHERE id={placeholder}", (job_id,))
            locked_row = cur.fetchone()
            locked_at_str = locked_row["locked_at"] if locked_row else None
            if locked_at_str:
                duration = datetime.now(timezone.utc).timestamp() - float(locked_at_str)
                if duration < 0.05:
                    logger.error(f"[CONFIRM REJECTED] Job {job_id}: Instant completion ({duration:.2f}s). Marking Failed.")
                    cur.execute(f"UPDATE print_jobs SET status={placeholder} WHERE id={placeholder}", (JobStatus.FAILED, job_id))
                    conn.commit()
                    conn.close()
                    return {"status": "error", "message": "Instant completion detected"}
        except Exception as e:
            logger.warning(f"[GATE C] Duration check error for job {job_id}: {e} — skipping gate")

        # ── Gate D: Source must be from Agent ─────────────────────────────────────
        source = str(printer["last_update_source"] or "")
        if not source.startswith("Agent"):
            logger.error(f"[CONFIRM REJECTED] Job {job_id}: Untrusted source '{source}'. Marking Failed.")
            cur.execute(f"UPDATE print_jobs SET status={placeholder} WHERE id={placeholder}", (JobStatus.FAILED, job_id))
            conn.commit()
            conn.close()
            return {"status": "error", "message": "Untrusted status source"}

        # ── Success ───────────────────────────────────────────────────────────────
        logger.info(f"[CONFIRM ACCEPTED] Job {job_id}: Marking Completed.")
        cur.execute(f"UPDATE print_jobs SET status={placeholder}, completed_at={placeholder} WHERE id={placeholder} AND status!={placeholder}",
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT id FROM agents WHERE agent_id={placeholder} AND token={placeholder}", (agent_id, token))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(401)
        
    printer_name = data.get("printer_name")
    new_status = data.get("status")
    
    if printer_name and new_status:
        # 🔹 STRICT OWNERSHIP: ONLY USB PRINTERS
        cur.execute(f"SELECT id, status, connection_type FROM printers WHERE name={placeholder}", (printer_name,))
        printer = cur.fetchone()
        
        if not printer:
            logger.warning(f"Agent {agent_id} reported unknown printer: {printer_name}")
        elif printer["connection_type"] != "USB":
            logger.warning(f"CONFLICT: Agent {agent_id} tried to update IP printer '{printer_name}'. REJECTED.")
        else:
            old_status = printer["status"]
            # 🔹 Always update last_updated even if status unchanged
            cur.execute(f"""
                UPDATE printers 
                SET status={placeholder}, last_updated={placeholder}, last_update_source={placeholder} 
                WHERE id={placeholder}
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT id, name, ip, status, category, connection_type, last_updated, last_update_source FROM printers")
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    # Calculate threshold based on current time
    threshold_dt = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = threshold_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Logs use utcnow() which is formatted string. We need to handle comparison.
    # Simplified: DELETE WHERE time < (current_time - days)
    # Using python date functions ensures polymorphic compatibility.
    cur.execute(f"DELETE FROM print_logs WHERE time < {placeholder}", (cutoff_str,))
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
                cur = get_cursor(conn)
                placeholder = get_placeholder()
                cur.execute(f"SELECT status FROM print_jobs WHERE id={placeholder}", (job['job_id'],))
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
                    raw_payload = job["payload"]
                    if isinstance(raw_payload, bytes):
                        # Fresh job: payload is ZPL bytes — save to disk
                        barcode_file = f"uploads/barcode_{job['job_id']}.zpl"
                        logger.info("[ZPL DEBUG]\n" + raw_payload.decode(errors='ignore'))
                        with open(barcode_file, "wb") as f:
                            f.write(raw_payload)
                        conn = get_connection()
                        cur = get_cursor(conn)
                        placeholder = get_placeholder()
                        cur.execute(f"UPDATE print_jobs SET file_path={placeholder} WHERE id={placeholder}", (barcode_file, job['job_id']))
                        conn.commit()
                        conn.close()
                    else:
                        # Recovery case: payload is already a file path — use as-is,
                        # never overwrite the file or the file_path column.
                        barcode_file = raw_payload
                    job["payload"] = barcode_file

                future = executor.submit(print_with_failover, job["job_id"], job["location_id"], job["category"], job["payload"])
                try:
                    future.result(timeout=60)
                    broadcast_sync("job_update", {"job_id": job["job_id"]})
                    broadcast_sync("dashboard_refresh", {})
                except concurrent.futures.TimeoutError:
                    logger.error(f"Worker-{worker_id} job {job['job_id']} TIMED OUT after 60s")
                    broadcast_sync("job_update", {"job_id": job["job_id"]})

        except Exception as e:
            if "RETRY" in str(e) and job_item:
                logger.warning(f"Worker-{worker_id} retrying job {job_item['job_id']} in 2s")
                time.sleep(2)
                print_queue.put((2, job_item))
                broadcast_sync("job_update", {"job_id": job_item["job_id"]})
            else:
                logger.error(f"Worker-{worker_id} error: {e}")
                if job_item:
                    broadcast_sync("job_update", {"job_id": job_item["job_id"]})
        finally:
            if job_item:
                print_queue.task_done()

# 🔹 Uvicorn server startup
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)


# 🔹 BACKGROUND TASKS: Monitoring & Maintenance
def monitor_loop():
    logger.info("Background Monitoring Thread started")
    while True:
        conn = None
        try:
            conn = get_connection()
            cur = get_cursor(conn)
            placeholder = get_placeholder()
            
            # 1. HEARTBEAT ENFORCEMENT (Mark agents Offline if > threshold)
            stale_cutoff = (datetime.now(timezone.utc) - timedelta(seconds=settings.stale_threshold_seconds)).strftime("%Y-%m-%d %H:%M:%S UTC")
            cur.execute(f"SELECT agent_id, hostname, location_id FROM agents WHERE status='Online' AND last_seen < {placeholder}", (stale_cutoff,))
            dead_agents = cur.fetchall()
            for agent in dead_agents:
                logger.warning(f"Agent {agent['agent_id']} TIMED OUT. Marking Offline.")
                cur.execute(f"UPDATE agents SET status='Offline' WHERE agent_id={placeholder}", (agent["agent_id"],))
                broadcast_sync("agent_update", {"agent_id": agent["agent_id"], "status": "Offline"})
                # 🔹 ALERT: Agent disconnected
                alert_deduplicated(f"agent_offline_{agent['agent_id']}",
                  f"Agent Offline: {agent['hostname']}",
                  f"<p>Print agent <b>{agent['hostname']}</b> (ID: {agent['agent_id']}) at location <b>{agent['location_id']}</b> stopped heartbeating.</p>")

            # 2. USB PRINTER TIMEOUT FALLBACK (Every 60s)
            cur.execute(f"""
                SELECT name, location_id FROM printers 
                WHERE connection_type='USB' AND status='Online'
                AND last_updated < {placeholder}
            """, (stale_cutoff,))
            timed_out = cur.fetchall()
            for p in timed_out:
                logger.warning(f"TIMEOUT: USB Printer '{p['name']}' stale (>45s). Marking Offline.")
                cur.execute(f"UPDATE printers SET status='Offline', last_update_source='Server:USBTimeout' WHERE name={placeholder}", (p["name"],))
                broadcast_sync("printer_update", {"name": p["name"], "status": "Offline"})
                # 🔹 ALERT: Printer offline
                alert_deduplicated(f"printer_offline_{p['name']}",
                  f"Printer Offline: {p['name']}",
                  f"<p>Printer <b>{p['name']}</b> at location <b>{p['location_id']}</b> went offline at {utcnow()}.</p>")
                
            # 3. IP PRINTER MONITORING (Every 60s)
            cur.execute(f"SELECT id, name, ip, status FROM printers WHERE connection_type='IP' AND ip IS NOT NULL AND ip != ''")
            ip_printers = cur.fetchall()
            from services.printer_service import check_printer
            for p in ip_printers:
                is_alive = check_printer(p["ip"], timeout=2)
                new_status = "Online" if is_alive else "Offline"

                if p["status"] != new_status:
                    logger.info(f"STATUS UPDATE: '{p['name']}' [IP] | Source: Server | {p['status']} -> {new_status}")
                    cur.execute(f"""
                        UPDATE printers
                        SET status={placeholder}, last_updated={placeholder}, last_update_source={placeholder}
                        WHERE id={placeholder}
                    """, (new_status, utcnow(), "Server:IPMonitor", p["id"]))
                    broadcast_sync("printer_update", {"name": p["name"], "status": new_status})
                    if new_status == "Offline":
                        alert_deduplicated(
                            f"printer_offline_{p['name']}",
                            f"IP Printer Offline: {p['name']}",
                            f"<p>Network printer <b>{p['name']}</b> ({p['ip']}) is unreachable on port 9100.</p>"
                        )
                
            # 4. AUTOMATED LOG CLEANUP (Daily)
            placeholder = get_placeholder()
            thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
            cur.execute(f"DELETE FROM print_logs WHERE time < {placeholder}", (thirty_days_ago,))
            
            conn.commit()
            if dead_agents or timed_out:
                broadcast_sync("dashboard_refresh", {})

        except Exception as e:
            logger.error(f"Monitoring Loop error: {e}")
        finally:
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

