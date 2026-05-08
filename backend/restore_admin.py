from database import get_connection
conn = get_connection()
conn.execute("UPDATE users SET role='admin' WHERE username='admin'")
conn.commit()
conn.close()
print("Admin role restored successfully")
