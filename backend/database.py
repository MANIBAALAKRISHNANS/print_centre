import sqlite3
import os
from datetime import datetime, timezone

import time

def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

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

def get_connection():
    db_path = os.environ.get("PRINTCENTER_DB_PATH", "printcenter.db")
    conn = sqlite3.connect(db_path, timeout=10) # 🔹 Added timeout for concurrency
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
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
        last_update_source TEXT
    )
    """)

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

    # SAFE MIGRATIONS
    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN location_id TEXT")
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
