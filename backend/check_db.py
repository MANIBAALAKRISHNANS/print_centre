import sqlite3
import os

db_path = 'printer_centre.db'
if not os.path.exists(db_path):
    print(f"File not found: {db_path}")
    # Try the one from settings
    db_path = 'printcenter.db'
    if not os.path.exists(db_path):
        print(f"File not found: {db_path}")
        exit(1)

print(f"Checking DB: {db_path}")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"Tables: {tables}")
conn.close()
