from database import get_connection, get_cursor, get_placeholder
conn = get_connection()
cur = get_cursor(conn)
placeholder = get_placeholder()

# Categories to seed
default_categories = ["A4", "Barcode"]

for cat in default_categories:
    cur.execute(f"SELECT id FROM categories WHERE name={placeholder}", (cat,))
    if not cur.fetchone():
        cur.execute(f"INSERT INTO categories (name) VALUES ({placeholder})", (cat,))
        print(f"Seeded category: {cat}")

conn.commit()
conn.close()
print("Category seeding complete")

