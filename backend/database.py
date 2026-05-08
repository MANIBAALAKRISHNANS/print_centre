import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor

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
def get_row_value(row, key, index=0):
    """🔹 Helper to extract a value from a row regardless of DB type (dict or tuple)"""
    if row is None:
        return None
    if isinstance(row, dict):
        # Case insensitive check for Postgres vs SQLite keys
        val = row.get(key)
        if val is None:
            val = row.get(key.lower())
        if val is None:
            val = row.get(key.upper())
        return val
    try:
        return row[index]
    except:
        return None

def get_connection():
    if settings.db_type == "postgresql":
        try:
            conn = psycopg2.connect(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                dbname=settings.db_name
            )
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
            
    db_path = settings.database_path
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn

def get_cursor(conn):
    if settings.db_type == "postgresql":
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn.cursor()

def get_placeholder():
    return "%s" if settings.db_type == "postgresql" else "?"



def init_db():
    conn = get_connection()
    
    # SQLite specific checkpointing
    if settings.db_type == "sqlite":
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.info("WAL checkpoint completed on startup.")
        except Exception as e:
            logger.warning(f"WAL checkpoint failed (non-fatal): {e}")
    
    cur = get_cursor(conn)
    pk_type = "SERIAL PRIMARY KEY" if settings.db_type == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # PRINT JOBS
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS print_jobs (
        id {pk_type},
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

    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS print_logs (
        id {pk_type},
        job_id INTEGER,
        printer TEXT,
        status TEXT,
        message TEXT,
        time TEXT
    )
    """)

    # MAPPING (STRICT ID-FIRST)
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS mapping (
        id {pk_type},
        location TEXT,
        external_id TEXT UNIQUE,
        a4Primary TEXT,
        a4Secondary TEXT,
        barPrimary TEXT,
        barSecondary TEXT
    )
    """)

    # CATEGORIES
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS categories (
        id {pk_type},
        name TEXT
    )
    """)

    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS printers (
        id {pk_type},
        name TEXT UNIQUE,
        ip TEXT,
        category TEXT,
        status TEXT DEFAULT 'Offline',
        language TEXT DEFAULT 'PS',
        connection_type TEXT DEFAULT 'IP',
        last_updated TEXT,
        last_update_source TEXT,
        location_id TEXT
    )
    """)

    # LOCATIONS (STRICT ID-FIRST)
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS locations (
        id {pk_type},
        name TEXT,
        block TEXT,
        external_id TEXT UNIQUE
    )
    """)

    # AGENTS
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS agents (
        id {pk_type},
        agent_id TEXT UNIQUE,
        location_id TEXT,
        status TEXT,
        last_seen TEXT,
        token TEXT
    )
    """)

    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS activation_codes (
        id {pk_type},
        code TEXT UNIQUE NOT NULL,
        location_id TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        agent_id TEXT,
        created_at TEXT,
        used_at TEXT
    )
    """)

    # AUDIT LOG (HIPAA)
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS audit_log (
        id {pk_type},
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
    cur.execute(f"""
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
    
    # Print logs
    cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_job_id ON print_logs(job_id)")
    
    # Agents
    cur.execute("CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_agents_last_seen ON agents(last_seen)")

    # Audit log
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)")

    # Activation codes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_codes_used ON activation_codes(used)")

    # USERS
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS users (
        id {pk_type},
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
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    cur.execute(f"SELECT COUNT(*) FROM users WHERE username={placeholder}", (username,))
    row = cur.fetchone()
    count = get_row_value(row, 'count', 0) or 0
    if count == 0:
        cur.execute(f"""
            INSERT INTO users (username, password_hash, role, created_at)
            VALUES ({placeholder}, {placeholder}, 'admin', {placeholder})
        """, (username, password_hash, utcnow()))
        conn.commit()
    conn.close()


def archive_old_jobs(days_to_keep: int = 30):
    """Move completed/failed jobs to archive to keep print_jobs table lean."""
    conn = get_connection()
    cur = get_cursor(conn)
    placeholder = get_placeholder()
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # 1. Copy to archive
        cur.execute(f"""
            INSERT INTO archived_jobs 
            SELECT *, {placeholder} FROM print_jobs 
            WHERE status IN ('Completed', 'Failed', 'Failed Agent')
            AND time < {placeholder}
        """, (utcnow(), cutoff))
        
        deleted = cur.rowcount
        
        # 2. Delete from active table
        cur.execute(f"""
            DELETE FROM print_jobs 
            WHERE status IN ('Completed', 'Failed', 'Failed Agent')
            AND time < {placeholder}
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
