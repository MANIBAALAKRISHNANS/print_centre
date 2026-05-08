import sqlite3
import os
from datetime import datetime, timezone
from passlib.context import CryptContext

# Security setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    return pwd_context.hash(password)

def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

db_path = "printers.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    username = "admin"
    password = "Admin@PrintHub2026"
    password_hash = hash_password(password)
    
    cur.execute("DELETE FROM users WHERE username=?", (username,))
    cur.execute("""
        INSERT INTO users (username, password_hash, role, created_at, force_password_change)
        VALUES (?, ?, 'admin', ?, 1)
    """, (username, password_hash, utcnow()))
    
    conn.commit()
    conn.close()
    print(f"SUCCESS: User '{username}' created with password '{password}'")
else:
    print("ERROR: Database file not found.")
