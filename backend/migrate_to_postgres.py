"""
migrate_to_postgres.py
======================
One-time script: copy all data from the existing SQLite database into PostgreSQL.

Usage (run from the backend/ directory):
    python migrate_to_postgres.py

Requirements:
  - PostgreSQL must be running and the target database must already exist.
  - backend/.env must have DB_TYPE=postgresql and valid PG_* credentials.
  - psycopg2-binary must be installed (already in requirements.txt).

The script:
  1. Runs init_db() to create all tables + indexes in PostgreSQL.
  2. Reads every table from SQLite.
  3. Inserts all rows into PostgreSQL (skipping duplicates via ON CONFLICT DO NOTHING).
  4. Reports row counts per table.
"""

import sqlite3
import sys
import os

# ── Load settings before importing database ──────────────────────────────────
from config import settings

if settings.db_type != "postgresql":
    print("[!] DB_TYPE is not 'postgresql' in .env — aborting.")
    print("    Set DB_TYPE=postgresql then re-run this script.")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("[!] psycopg2 is not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

from database import init_db, init_pool, close_pool

SQLITE_PATH = settings.database_path

TABLES = [
    "users",
    "locations",
    "printers",
    "categories",
    "mapping",
    "agents",
    "activation_codes",
    "print_jobs",
    "archived_jobs",
    "print_logs",
    "audit_log",
]


def pg_connect():
    return psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        dbname=settings.db_name,
    )


def migrate():
    if not os.path.exists(SQLITE_PATH):
        print(f"[!] SQLite database not found at '{SQLITE_PATH}'. Nothing to migrate.")
        sys.exit(1)

    print(f"[*] Source : SQLite  → {SQLITE_PATH}")
    print(f"[*] Target : PostgreSQL → {settings.db_user}@{settings.db_host}:{settings.db_port}/{settings.db_name}")
    print()

    # Step 1 — Create all tables + indexes in PostgreSQL
    print("[1/3] Initialising PostgreSQL schema …")
    init_db()
    print("      Schema ready.\n")

    # Step 2 — Read from SQLite
    print("[2/3] Reading SQLite data …")
    sq = sqlite3.connect(SQLITE_PATH)
    sq.row_factory = sqlite3.Row
    sq_cur = sq.cursor()

    table_data: dict[str, list[dict]] = {}
    for table in TABLES:
        try:
            sq_cur.execute(f"SELECT * FROM {table}")
            rows = [dict(r) for r in sq_cur.fetchall()]
            table_data[table] = rows
            print(f"      {table:20s} — {len(rows):>6} rows")
        except sqlite3.OperationalError:
            print(f"      {table:20s} — not found in SQLite (skipping)")
            table_data[table] = []
    sq.close()
    print()

    # Step 3 — Insert into PostgreSQL
    print("[3/3] Inserting into PostgreSQL …")
    pg = pg_connect()
    pg_cur = pg.cursor()

    total_inserted = 0
    for table in TABLES:
        rows = table_data.get(table, [])
        if not rows:
            continue

        columns = list(rows[0].keys())
        col_str = ", ".join(f'"{c}"' for c in columns)
        val_str = ", ".join(["%s"] * len(columns))

        inserted = 0
        skipped  = 0
        for row in rows:
            values = [row[c] for c in columns]
            try:
                pg_cur.execute(
                    f'INSERT INTO "{table}" ({col_str}) VALUES ({val_str}) ON CONFLICT DO NOTHING',
                    values,
                )
                if pg_cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                pg.rollback()
                print(f"      [WARN] Row skipped in {table}: {e}")

        pg.commit()
        total_inserted += inserted
        print(f"      {table:20s} — {inserted:>6} inserted, {skipped} skipped")

    pg_cur.close()
    pg.close()

    print(f"\n[OK] Migration complete. {total_inserted} total rows inserted into PostgreSQL.")
    print("     You can now start the backend with DB_TYPE=postgresql in .env.")


if __name__ == "__main__":
    migrate()
