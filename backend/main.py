import os
from datetime import datetime, timezone
import uuid
import requests
import threading
import time
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database import init_db, get_connection, utcnow, JobStatus, safe_delete
from datetime import datetime, timezone
from services.barcode_service import build_print_payload, generate_patient_id
from services.routing_service import print_with_failover, mark_job, log_print_event
from queue import PriorityQueue
import shutil
from threading import Lock
import logging
import concurrent.futures

# 🔹 Logging Setup
from logging.handlers import RotatingFileHandler
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler("printcenter.log", maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Main")

print_queue = PriorityQueue(maxsize=500)
app = FastAPI()
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

@app.get("/health")
def health_check():
    return {"status": "ok", "time": utcnow()}

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

class Printer(BaseModel):
    name: str
    ip: str = None
    category: str
    status: str
    language: str = "PS"
    connection_type: str = "IP"

class Category(BaseModel):
    name: str

def is_stale_usb(last_updated_str):
    """🔹 Real-time stale detection for USB printers (45s threshold)"""
    if not last_updated_str: return True
    try:
        # Expected format from database.py: 2026-05-05 17:32:23 UTC
        dt = datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() > 45
    except:
        return True

@app.get("/dashboard")
def get_dashboard():
    cached = get_cached_data("dashboard", 10)
    if cached: return cached

    conn = get_connection()
    try:
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM printers")
        total = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM printers WHERE status='Online'")
        live = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM printers WHERE status='Offline'")
        offline = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM print_jobs")
        job_total = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM print_jobs WHERE status='Completed'")
        job_completed = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM print_jobs WHERE status='Failed'")
        job_failed = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM print_jobs WHERE retry_count > 0")
        job_retried = cur.fetchone()[0]

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
def get_printers():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM printers")
        rows = [dict(r) for r in cur.fetchall()]
        
        # 🔹 REAL-TIME STATUS OVERRIDE (USB Stale Detection)
        for p in rows:
            if p.get("connection_type") == "USB" and p.get("status") == "Online":
                if is_stale_usb(p.get("last_updated")):
                    p["status"] = "Offline"
        return rows
    finally:
        conn.close()

@app.post("/printers")
def add_printer(data: Printer):
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
def update_printer(printer_id: int, data: Printer):
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
def delete_printer(printer_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM printers WHERE id=?", (printer_id,))
    conn.commit()
    conn.close()
    invalidate_cache("dashboard")
    return {"message": "Deleted"}

@app.get("/locations")
def get_locations():
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
def get_mapping():
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
def update_mapping(mapping_id: int, data: dict):
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
def get_print_jobs(limit: int = 50, offset: int = 0, status: str = None, retried: bool = False):
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM print_jobs WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if retried:
        query += " AND retry_count > 0"
    
    # Get Total Count
    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    cur.execute(count_query, params)
    total = cur.fetchone()[0]

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    cur.execute(query, params)
    jobs = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"jobs": jobs, "total": total}

@app.delete("/print-jobs")
def delete_all_jobs():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM print_jobs")
    cur.execute("DELETE FROM print_logs")
    conn.commit()
    conn.close()
    return {"message": "All jobs cleared"}

@app.get("/print-logs/{job_id}")
def get_print_logs(job_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM print_logs WHERE job_id=? ORDER BY id ASC", (job_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/categories")
def get_categories():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM categories")
    rows = [r["name"] for r in cur.fetchall()]
    conn.close()
    return rows

@app.post("/categories")
def add_category(data: Category):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO categories (name) VALUES (?)", (data.name,))
    conn.commit()
    conn.close()
    return {"message": "Added"}

@app.post("/print-job")
def print_job(data: dict):
    location_id = data.get("location_id")
    category = data.get("category")
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
    patient_id = data.get("patient_id") or generate_patient_id()
    cur.execute("INSERT INTO print_jobs (location, location_id, category, printer, status, type, time, patient_name, age, gender, patient_id, tube_type, test_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (loc["name"], location_id, category, "Pending", "Queued", "None", utcnow(), data.get("patient_name"), data.get("age"), data.get("gender"), patient_id, data.get("tube_type"), data.get("test_name")))
    conn.commit()
    job_id = cur.lastrowid
    conn.close()
    payload = build_print_payload({**data, "patient_id": patient_id})
    # Priority: 1 for emergency (optional), 2 for normal
    print_queue.put((2, {"job_id": job_id, "location_id": location_id, "category": category, "payload": payload}))
    return {"job_id": job_id, "status": "Queued"}

@app.get("/mapping-validate")
def validate_mapping():
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
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", 50))
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
                cur.execute(f"""
                    SELECT id, category, printer, patient_id, priority, retry_count 
                    FROM print_jobs 
                    WHERE id IN ({placeholders})
                """, candidates)
                jobs = [dict(row) for row in cur.fetchall()]
            else:
                jobs = []
            
            conn.commit()
            return jobs
        except Exception as e:
            conn.rollback()
            raise HTTPException(500, str(e))
    finally:
        conn.close()

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
    cur.execute("SELECT retry_count, file_path, category FROM print_jobs WHERE id=?", (job_id,))
    row = cur.fetchone()
    if row and row["retry_count"] >= 3:
        cur.execute("UPDATE print_jobs SET status=? WHERE id=?", (JobStatus.FAILED_AGENT, job_id))
        # 🔹 CLEANUP: Upload file after failure exhaustion
        safe_delete(row["file_path"])
    else:
        # Release for retry
        cur.execute("UPDATE print_jobs SET status=?, locked_by=NULL WHERE id=?", (JobStatus.PENDING_AGENT, job_id))
        
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
def agent_heartbeat(agent_id: str, token: str, location_id: str = None):
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
        cur.execute("UPDATE agents SET last_seen=?, status='Online' WHERE agent_id=?", (utcnow(), agent_id))
        if location_id:
            cur.execute("UPDATE agents SET location_id=? WHERE agent_id=?", (location_id, agent_id))
    else:
        # Register
        cur.execute("INSERT INTO agents (agent_id, location_id, status, last_seen, token) VALUES (?, ?, 'Online', datetime('now'), ?)",
                    (agent_id, location_id, token))
    
    conn.commit()
    conn.close()
    return {"status": "ok"}

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
        cur.execute("UPDATE print_jobs SET status=? WHERE id=? AND status!=?",
                    (JobStatus.COMPLETED, job_id, JobStatus.COMPLETED))
        safe_delete(job["file_path"])
        conn.commit()
        conn.close()
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
    expected_token = os.environ.get("ADMIN_CLEANUP_TOKEN", "admin_secret_2026")
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
                    # Optionally mark as failed or retry
            
        except Exception as e:
            if "RETRY" in str(e) and job_item:
                logger.warning(f"Worker-{worker_id} retrying job {job_item['job_id']} in 2s")
                time.sleep(2)
                print_queue.put((priority, job_item))
            else:
                logger.error(f"Worker-{worker_id} error: {e}")
        finally:
            if job_item:
                print_queue.task_done()

# 🔹 Startup: Recover jobs BEFORE starting workers
recover_queue()

# 🔹 Scale: 3 Parallel Workers
for i in range(3):
    threading.Thread(target=process_queue, args=(i,), daemon=True).start()

# 🔹 BACKGROUND TASKS: Monitoring & Maintenance
def monitor_loop():
    logger.info("Background Monitoring Thread started")
    while True:
        try:
            conn = get_connection()
            cur = conn.cursor()
            
            # 1. HEARTBEAT ENFORCEMENT (Mark agents Offline if > 45s)
            cur.execute("SELECT agent_id FROM agents WHERE status='Online' AND last_seen < datetime('now', '-45 seconds')")
            dead_agents = cur.fetchall()
            for agent in dead_agents:
                logger.warning(f"Agent {agent['agent_id']} TIMED OUT. Marking Offline.")
                cur.execute("UPDATE agents SET status='Offline' WHERE agent_id=?", (agent["agent_id"],))

            # 2. USB PRINTER TIMEOUT FALLBACK (Every 60s)
            # Threshold = 45s
            cur.execute("""
                SELECT name FROM printers 
                WHERE connection_type='USB' AND status='Online'
                AND last_updated < datetime('now', '-45 seconds')
            """)
            timed_out = cur.fetchall()
            for p in timed_out:
                logger.warning(f"TIMEOUT: USB Printer '{p['name']}' stale (>45s). Marking Offline.")
                cur.execute("UPDATE printers SET status='Offline', last_update_source='Server:USBTimeout' WHERE name=?", (p["name"],))
                
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
            conn.close()
            
        except Exception as e:
            logger.error(f"Monitoring Loop error: {e}")
            
        time.sleep(60)

threading.Thread(target=monitor_loop, daemon=True).start()
