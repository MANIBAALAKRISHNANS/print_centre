import sqlite3
import os
from datetime import datetime, timezone

def utcnow() -> str:
    """Return current UTC time as ISO 8601 string. Used for all timestamps."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

# ✅ CONSISTENT JOB STATUS CONSTANTS
class JobStatus:
    QUEUED     = "Queued"
    PRINTING   = "Printing"
    COMPLETED  = "Completed"
    FAILED     = "Failed"
    RETRYING   = "Retrying"

VALID_STATUSES = {JobStatus.QUEUED, JobStatus.PRINTING, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.RETRYING}

def get_connection():
    db_path = os.environ.get("PRINTCENTER_DB_PATH", "printcenter.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ✅ PRINT JOBS (ONLY ONCE)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS print_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT,
        category TEXT,
        printer TEXT,
        status TEXT,
        type TEXT,
        time TEXT,
        
        patient_name TEXT,
        age TEXT,
        gender TEXT,
        patient_id TEXT,
        tube_type TEXT
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

    # ✅ MAPPING
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mapping (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location TEXT UNIQUE,
        a4Primary TEXT,
        a4Secondary TEXT,
        barPrimary TEXT,
        barSecondary TEXT
    )
    """)

    # ✅ CATEGORIES
    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )
    """)

    # ✅ PRINTERS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS printers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        ip TEXT,
        category TEXT,
        status TEXT
    )
    """)
    # ✅ ADD LANGUAGE COLUMN (SAFE MIGRATION)
    try:
      cur.execute("ALTER TABLE printers ADD COLUMN language TEXT DEFAULT 'PS'")
    except Exception as e:
       if "duplicate column name" not in str(e).lower():
          print("DB Error:", e)

    # ✅ ADD PRINT_JOBS COLUMNS (SAFE MIGRATION)
    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN file_path TEXT")
    except Exception as e:
        pass
    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN file_type TEXT")
    except Exception as e:
        pass
    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN retry_count INTEGER DEFAULT 0")
    except Exception as e:
        pass
    try:
        cur.execute("ALTER TABLE print_jobs ADD COLUMN pages INTEGER DEFAULT 1")
    except Exception as e:
        pass

    # ✅ LOCATIONS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    """)

    # ✅ INDEXES — Added for high-frequency query columns
    # These are safe to run repeatedly (IF NOT EXISTS)
    indexes = [
        # print_jobs: status filter (dashboard + /print-jobs?status=)
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON print_jobs(status)",
        # print_jobs: retry filter (/print-jobs?retried=true)
        "CREATE INDEX IF NOT EXISTS idx_jobs_retry ON print_jobs(retry_count)",
        # print_jobs: printer analytics (GROUP BY printer)
        "CREATE INDEX IF NOT EXISTS idx_jobs_printer ON print_jobs(printer)",
        # print_jobs: patient dedup check
        "CREATE INDEX IF NOT EXISTS idx_jobs_patient_id ON print_jobs(patient_id)",
        # print_logs: per-job log lookup (GET /print-logs/{job_id})
        "CREATE INDEX IF NOT EXISTS idx_logs_job_id ON print_logs(job_id)",
        # print_logs: status filter in log modal
        "CREATE INDEX IF NOT EXISTS idx_logs_status ON print_logs(status)",
    ]
    for idx_sql in indexes:
        try:
            cur.execute(idx_sql)
        except Exception as e:
            print(f"[DB] Index warning: {e}")

    conn.commit()
    conn.close()
