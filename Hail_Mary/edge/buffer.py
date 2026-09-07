"""Local SQLite buffer for occupancy records (M3).

Every record aggregator.py produces is inserted here first so nothing is lost
if the network/server is unreachable. Upload (uplink.py) reads pending rows
and marks them uploaded only after a successful POST.
"""

import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS occupancy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    count INTEGER NOT NULL,
    uploaded_at REAL,
    created_at REAL NOT NULL
)
"""


class LocalBuffer:
    def __init__(self, db_path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def insert(self, record):
        self._conn.execute(
            "INSERT INTO occupancy (zone_id, window_start, window_end, count, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (record["zone_id"], record["window_start"], record["window_end"],
             record["count"], time.time()),
        )
        self._conn.commit()

    def fetch_pending(self, limit=100):
        rows = self._conn.execute(
            "SELECT id, zone_id, window_start, window_end, count FROM occupancy "
            "WHERE uploaded_at IS NULL ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def fetch_all(self):
        rows = self._conn.execute(
            "SELECT id, zone_id, window_start, window_end, count FROM occupancy ORDER BY id",
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_uploaded(self, ids):
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        self._conn.execute(
            f"UPDATE occupancy SET uploaded_at = ? WHERE id IN ({placeholders})",
            (time.time(), *ids),
        )
        self._conn.commit()

    def purge_older_than(self, days):
        cutoff = time.time() - days * 86400
        self._conn.execute(
            "DELETE FROM occupancy WHERE uploaded_at IS NOT NULL AND uploaded_at < ?",
            (cutoff,),
        )
        self._conn.commit()
