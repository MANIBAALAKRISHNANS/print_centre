import sqlite3
import os

db_path = "printers.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT username, role, password_hash FROM users WHERE username='admin'")
    row = cur.fetchone()
    if row:
        print(f"User Found: {row['username']} ({row['role']})")
        # I won't print the hash for privacy, but I'll check if it looks valid
        if row['password_hash'].startswith('$2b$') or row['password_hash'].startswith('$2a$'):
             print("Hash format looks like valid bcrypt.")
        else:
             print("Hash format looks unusual.")
    else:
        print("User NOT found.")
    conn.close()
else:
    print("Database file not found.")
