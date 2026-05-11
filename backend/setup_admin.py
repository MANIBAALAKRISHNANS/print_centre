import argparse
from database import get_connection, get_cursor, get_placeholder
from services.auth import hash_password

def setup_admin(username, password):
    print(f"[*] Initializing admin user: {username}")
    conn = get_connection()
    cur  = get_cursor(conn)
    p    = get_placeholder()

    hashed = hash_password(password)
    try:
        cur.execute(
            f"INSERT INTO users (username, password_hash, role) VALUES ({p}, {p}, 'admin')",
            (username, hashed),
        )
        conn.commit()
        print("[+] Admin user created successfully.")
    except Exception:
        conn.rollback()
        print(f"[!] User {username} already exists. Updating password...")
        cur.execute(
            f"UPDATE users SET password_hash={p}, role='admin' WHERE username={p}",
            (hashed, username),
        )
        conn.commit()
        print("[+] Admin password updated.")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PrinterCentre Production Admin Setup")
    parser.add_argument("--user",     default="admin", help="Admin username")
    parser.add_argument("--password", required=True,   help="Admin password (min 8 chars)")

    args = parser.parse_args()

    if len(args.password) < 8:
        print("[!] Error: Password must be at least 8 characters long.")
    else:
        setup_admin(args.user, args.password)
