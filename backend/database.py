import sqlite3

def get_connection():
    conn = sqlite3.connect("printcenter.db")
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
      cur.execute("ALTER TABLE printers ADD COLUMN language TEXT DEFAULT 'ZPL'")
    except Exception as e:
       if "duplicate column name" not in str(e).lower():
          print("DB Error:", e)

    # ✅ LOCATIONS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE
    )
    """)

    conn.commit()
    conn.close()