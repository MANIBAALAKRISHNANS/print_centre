import sqlite3
import argparse
from services.auth import hash_password
from config import settings

def setup_admin(username, password):
    print(f"[*] Initializing admin user: {username}")
    conn = sqlite3.connect(settings.database_path)
    cur = conn.cursor()
    
    # Ensure users table exists (in case init_db wasn't run yet)
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
    
    hashed = hash_password(password)
    try:
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')", (username, hashed))
        conn.commit()
        print("[+] Admin user created successfully.")
    except sqlite3.IntegrityError:
        print(f"[!] User {username} already exists. Updating password...")
        cur.execute("UPDATE users SET password_hash=?, role='admin' WHERE username=?", (hashed, username))
        conn.commit()
        print("[+] Admin password updated.")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PrinterCentre Production Admin Setup")
    parser.add_argument("--user", default="admin", help="Admin username")
    parser.add_argument("--password", required=True, help="Admin password (min 8 chars)")
    
    args = parser.parse_args()
    
    if len(args.password) < 8:
        print("[!] Error: Password must be at least 8 characters long.")
    else:
        setup_admin(args.user, args.password)
