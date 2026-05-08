import sqlite3
from config import settings
import os
import shutil
import logging
from datetime import datetime, timezone, timedelta

import time

def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

logger = logging.getLogger("Database")

def safe_delete(file_path):
    """🔹 Robust file deletion with retries (Windows safe)"""
    if not file_path or not os.path.exists(file_path):
        return
    for i in range(3):
        try:
            os.remove(file_path)
            return
        except PermissionError:
            time.sleep(1)
        except Exception:
            break

class JobStatus:
    QUEUED     = "Queued"
    PRINTING   = "Printing"
    COMPLETED  = "Completed"
    FAILED     = "Failed"
    RETRYING   = "Retrying"
    PENDING_AGENT = "Pending Agent"
    AGENT_PRINTING = "Agent Printing"
    FAILED_AGENT = "Failed Agent"

class PrinterStatus:
    ONLINE  = "Online"
    OFFLINE = "Offline"
    ERROR   = "Error"

VALID_STATUSES = {PrinterStatus.ONLINE, PrinterStatus.OFFLINE, PrinterStatus.ERROR}

# Future: PostgreSQL migration planned. See db_adapter.py (archived) for DBManager stub.
def get_connection():
    db_path = settings.database_path
    conn = sqlite3.connect(db_path, timeout=30) # 🔹 Increased timeout for WAL
    
    # 🔹 PRODUCTION OPTIMIZATIONS (WAL MODE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")  # 5s busy wait instead of instant fail
    
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    
    # 🔹 CRITICAL: Checkpoint the WAL on startup.
    # If the WAL grows too large (e.g. 2MB+) it causes constant "database is locked"
    # errors. TRUNCATE mode resets the WAL to zero after checkpointing.
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        logger.info("WAL checkpoint completed on startup.")
    except Exception as e:
        logger.warning(f"WAL checkpoint failed (non-fatal): {e}")
    
    cur = conn.cursor()

    # PRINT JOBS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS print_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT,
        location_id TEXT,
        category TEXT,
        printer TEXT,
        status TEXT,
        type TEXT,
        time TEXT,
        patient_name TEXT,
        age TEXT,
        gender TEXT,
        patient_id TEXT,
        tube_type TEXT,
        file_path TEXT,
        file_type TEXT,
        retry_count INTEGER DEFAULT 0,
        pages INTEGER DEFAULT 1,
        locked_at TEXT,
        locked_by TEXT,
        priority INTEGER DEFAULT 2
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS print_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER,
        printer TEXT,
        status TEXT,
        message TEXT,
        time TEXT
    )
    """)

    # MAPPING (STRICT ID-FIRST)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mapping (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT,
        external_id TEXT UNIQUE,
        a4Primary TEXT,
        a4Secondary TEXT,
        barPrimary TEXT,
        barSecondary TEXT
    )
    """)

    # CATEGORIES
    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS printers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        ip TEXT,
        category TEXT,
        status TEXT DEFAULT 'Offline',
        language TEXT DEFAULT 'PS',
        connection_type TEXT CHECK(connection_type IN ('IP', 'USB')) DEFAULT 'IP',
        last_updated TEXT,
        last_update_source TEXT,
        location_id TEXT
    )
    """)

    # SAFE MIGRATIONS
    try: cur.execute("ALTER TABLE printers ADD COLUMN location_id TEXT")
    except: pass

    # LOCATIONS (STRICT ID-FIRST)
    # Ensure name is not unique, external_id is UNIQUE
    try:
        cur.execute("PRAGMA index_list('locations')")
        indices = cur.fetchall()
        for idx in indices:
            cur.execute(f"PRAGMA index_info('{idx['name']}')")
            cols = cur.fetchall()
            if any(c['name'] == 'name' for c in cols) and idx['unique'] == 1:
                cur.execute("DROP TABLE locations")
                break
    except:
        pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        block TEXT,
        external_id TEXT UNIQUE
    )
    """)

    # AGENTS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT UNIQUE,
        location_id TEXT,
        status TEXT,
        last_seen TEXT,
        token TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS activation_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        location_id TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        agent_id TEXT,
        created_at TEXT,
        used_at TEXT
    )
    """)

    # AUDIT LOG (HIPAA)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        actor TEXT NOT NULL,
        actor_type TEXT NOT NULL,
        action TEXT NOT NULL,
        resource_type TEXT,
        resource_id TEXT,
        patient_id TEXT,
        ip_address TEXT,
        status TEXT NOT NULL,
        details TEXT
    )
    """)

    # ARCHIVED JOBS (Production Strategy)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS archived_jobs (
        id INTEGER,
        location TEXT,
        location_id TEXT,
        category TEXT,
        printer TEXT,
        status TEXT,
        type TEXT,
        time TEXT,
        patient_name TEXT,
        age TEXT,
        gender TEXT,
        patient_id TEXT,
        tube_type TEXT,
        file_path TEXT,
        file_type TEXT,
        retry_count INTEGER,
        pages INTEGER,
        locked_at TEXT,
        locked_by TEXT,
        priority INTEGER,
        archived_at TEXT NOT NULL
    )
    """)

    # 🔹 PRODUCTION INDEXES
    # Print jobs
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON print_jobs(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_location ON print_jobs(location_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_printer ON print_jobs(printer)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_location ON print_jobs(status, location_id)")
    
    # Print logs
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_job_id ON print_logs(job_id)")
    
    # Agents
    cur.execute("CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_agents_last_seen ON agents(last_seen DESC)")

    # Audit log
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_patient ON audit_log(patient_id)")

    # Activation codes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_codes_used ON activation_codes(used)")

    # USERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'viewer',
        created_at TEXT,
        last_login TEXT
    )
    """)

    # SAFE MIGRATIONS
    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN location_id TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE agents ADD COLUMN hostname TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN locked_at TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN locked_by TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN completed_at TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN error_message TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN created_by TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN pages INTEGER DEFAULT 1")
    except:
        pass

    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN priority INTEGER DEFAULT 2")
    except:
        pass

    try:
        cur.execute("ALTER TABLE mapping ADD COLUMN external_id TEXT")
    except:
        pass

    try:
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mapping_external_id ON mapping(external_id)")
    except:
        pass

    try:
        cur.execute("ALTER TABLE printers ADD COLUMN connection_type TEXT CHECK(connection_type IN ('IP', 'USB')) DEFAULT 'IP'")
    except:
        pass

    try:
        cur.execute("ALTER TABLE printers ADD COLUMN last_updated TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE printers ADD COLUMN last_update_source TEXT")
    except:
        pass

    try:
        cur.execute("ALTER TABLE users ADD COLUMN force_password_change INTEGER DEFAULT 0")
    except:
        pass

    # 🔹 DATA MIGRATION: Populating connection_type and normalizing status
    cur.execute("UPDATE printers SET connection_type = 'IP' WHERE ip IS NOT NULL AND ip != '' AND connection_type IS NULL")
    cur.execute("UPDATE printers SET connection_type = 'USB' WHERE (ip IS NULL OR ip = '') AND connection_type IS NULL")
    # Default fallback
    cur.execute("UPDATE printers SET connection_type = 'IP' WHERE connection_type IS NULL")
    
    # Normalize status: Live -> Online
    cur.execute("UPDATE printers SET status = 'Online' WHERE status = 'Live'")
    cur.execute("UPDATE printers SET status = 'Offline' WHERE status IS NULL OR status = 'Maintenance'")

    conn.commit()
    conn.close()

def seed_admin(username, password_hash):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (username,))
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES (?, ?, 'admin', ?)
        """, (username, password_hash, utcnow()))
        conn.commit()
    conn.close()

def archive_old_jobs(days_to_keep: int = 30):
    """Move completed/failed jobs to archive to keep print_jobs table lean."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Start Transaction
        cur.execute("BEGIN TRANSACTION")
        
        # 1. Copy to archive
        cur.execute("""
            INSERT INTO archived_jobs 
            SELECT *, ? FROM print_jobs 
            WHERE status IN ('Completed', 'Failed', 'Failed Agent')
            AND time < ?
        """, (utcnow(), cutoff))
        
        deleted = cur.rowcount
        
        # 2. Delete from active table
        cur.execute("""
            DELETE FROM print_jobs 
            WHERE status IN ('Completed', 'Failed', 'Failed Agent')
            AND time < ?
        """, (cutoff,))
        
        conn.commit()
        logger.info(f"[ARCHIVE] Successfully moved {deleted} jobs to archived_jobs table.")
        return deleted
    except Exception as e:
        conn.rollback()
        logger.error(f"[ARCHIVE ERROR] {e}")
        return 0
    finally:
        conn.close()

def backup_database():
    """Creates a timestamped backup of the production database."""
    src = settings.database_path
    backup_dir = getattr(settings, "database_backup_path", "./backups/")
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(backup_dir, f"printhub_{timestamp}.db")
    
    try:
        shutil.copy2(src, dst)
        
        # Cleanup: Keep only last 7 backups
        backups = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.startswith("printhub_")])
        if len(backups) > 7:
            for old_backup in backups[:-7]:
                os.remove(old_backup)
                
        logger.info(f"[BACKUP] Database backed up to {dst}")
        return dst
    except Exception as e:
        logger.error(f"[BACKUP ERROR] {e}")
        return None
