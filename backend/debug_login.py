import sys, os
sys.path.insert(0, '.')

print("=== Step 1: DB Connection ===")
from database import get_connection
try:
    conn = get_connection()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print("WAL checkpoint OK")
    cur = conn.cursor()
    cur.execute("SELECT username, role, force_password_change, password_hash FROM users WHERE username='admin'")
    row = cur.fetchone()
    if row:
        print(f"User found: {row['username']} | role: {row['role']} | force_pw: {row['force_password_change']}")
        print(f"Hash prefix: {row['password_hash'][:10]}...")
        pw_hash = row['password_hash']
    else:
        print("ERROR: admin user NOT FOUND in DB")
        sys.exit(1)
    conn.close()
    print("DB connection closed OK")
except Exception as e:
    print(f"DB ERROR: {e}")
    sys.exit(1)

print("\n=== Step 2: Password Verify ===")
try:
    from services.auth import verify_password
    result = verify_password("Admin@PrintHub2026", pw_hash)
    print(f"verify_password result: {result}")
except Exception as e:
    print(f"VERIFY ERROR: {type(e).__name__}: {e}")

print("\n=== Step 3: Token Creation ===")
try:
    from services.auth import create_token
    token = create_token("admin", "admin")
    print(f"Token created OK, length={len(token)}")
except Exception as e:
    print(f"TOKEN ERROR: {type(e).__name__}: {e}")

print("\n=== Step 4: Audit Log Write ===")
try:
    from services.audit import log_audit
    log_audit("admin", "user", "LOGIN_TEST", status="SUCCESS", ip_address="127.0.0.1")
    print("Audit log write OK")
except Exception as e:
    print(f"AUDIT ERROR: {type(e).__name__}: {e}")

print("\n=== Step 5: last_login UPDATE ===")
try:
    from database import utcnow
    conn = get_connection()
    conn.execute("UPDATE users SET last_login=? WHERE username=?", (utcnow(), "admin"))
    conn.commit()
    conn.close()
    print("last_login update OK")
except Exception as e:
    print(f"UPDATE ERROR: {type(e).__name__}: {e}")

print("\n=== ALL DONE ===")
