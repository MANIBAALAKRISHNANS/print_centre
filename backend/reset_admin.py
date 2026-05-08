import sqlite3
import os

db_path = "printers.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE username='admin'")
    conn.commit()
    conn.close()
    print("Admin user cleared successfully.")
else:
    print("Database file not found.")
