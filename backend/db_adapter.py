import sqlite3
import os
import logging

logger = logging.getLogger("DBAdapter")

class DBManager:
    """
    Abstracted Database Manager to support SQLite and future PostgreSQL migration.
    """
    def __init__(self):
        self.db_type = os.environ.get("DB_TYPE", "sqlite")
        self.db_path = os.environ.get("PRINTCENTER_DB_PATH", "printcenter.db")
        
    def get_connection(self):
        if self.db_type == "sqlite":
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.row_factory = sqlite3.Row
            return conn
        else:
            # Placeholder for PostgreSQL or others
            raise NotImplementedError(f"Database type {self.db_type} not supported yet.")

    def execute(self, query, params=(), commit=False):
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(query, params)
            if commit:
                conn.commit()
            return cur
        except Exception as e:
            logger.error(f"Database error: {e} | Query: {query}")
            raise
        finally:
            if not commit:
                conn.close()

db_manager = DBManager()
