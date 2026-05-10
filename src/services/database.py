"""
services/database.py — Database interactions.
Extracted from ``api_window.py``.
"""

import sqlite3

class MetadataDatabase:
    def __init__(self, db_path, logger):
        self.db_path = db_path
        self.logger = logger
        self.init_db()

    def init_db(self):
        """Initialize the database tables if they don't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coords (
                    id INTEGER PRIMARY KEY,
                    lat REAL, lon REAL,
                    stage TEXT, scanned INTEGER DEFAULT 0
                )""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    coord_id INTEGER, pano_id TEXT,
                    FOREIGN KEY(coord_id) REFERENCES coords(id)
                )""")
            conn.commit()
            conn.close()
            self.logger.log_status(f"Database initialized at {self.db_path}")
        except Exception as e:
            self.logger.log_exception(f"Failed to initialize database: {e}")

    def query_results(self, north, south, east, west):
        """Query panorama results from database within bounding box"""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()

            query = """
                SELECT c.lat, c.lon, r.pano_id
                FROM coords c
                JOIN results r ON c.id = r.coord_id
                WHERE c.lat <= ? AND c.lat >= ? AND c.lon <= ? AND c.lon >= ?
            """
            cur.execute(query, (north, south, east, west))
            results = cur.fetchall()
            conn.close()
            self.logger.log_status(f"Found {len(results)} results from database")
            return results
        except Exception as e:
            self.logger.log_exception(f"Database query failed: {e}")
            return []
