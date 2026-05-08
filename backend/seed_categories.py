from database import get_connection
conn = get_connection()
cur = conn.cursor()

# Categories to seed
default_categories = ["A4", "Barcode"]

for cat in default_categories:
    cur.execute("SELECT id FROM categories WHERE name=?", (cat,))
    if not cur.fetchone():
        cur.execute("INSERT INTO categories (name) VALUES (?)", (cat,))
        print(f"Seeded category: {cat}")

conn.commit()
conn.close()
print("Category seeding complete")
