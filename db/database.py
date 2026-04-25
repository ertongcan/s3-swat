"""
db/database.py
SQLite database for persisting scan history and results.
Uses aiosqlite for async compatibility with FastAPI.
"""

import aiosqlite
import json
import os
from typing import List, Optional, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "s3swat.db")


async def init_db():
    """Create the scans table if it doesn't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id              TEXT PRIMARY KEY,
                user_id         TEXT NOT NULL,
                bucket          TEXT NOT NULL,
                region          TEXT NOT NULL,
                health_score    INTEGER DEFAULT 0,
                ghost_data      TEXT DEFAULT '[]',
                network_data    TEXT DEFAULT '[]',
                efficiency_data TEXT DEFAULT '{}',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_scans_user
            ON scans(user_id, created_at DESC)
        """)
        await db.commit()


async def save_scan(
    scan_id: str,
    user_id: str,
    bucket: str,
    region: str,
    health_score: int,
    ghost_data: List[Dict],
    network_data: List[Dict],
    efficiency_data: Dict,
):
    """Persist a completed scan."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO scans (id, user_id, bucket, region, health_score,
                               ghost_data, network_data, efficiency_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_id,
                user_id,
                bucket,
                region,
                health_score,
                json.dumps(ghost_data, default=str),
                json.dumps(network_data, default=str),
                json.dumps(efficiency_data, default=str),
            ),
        )
        await db.commit()


async def get_scan(scan_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single scan by ID, scoped to the requesting user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM scans WHERE id = ? AND user_id = ?",
            (scan_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)


async def list_scans(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """List all scans for a user, newest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM scans WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(row) for row in rows]


async def delete_scan(scan_id: str, user_id: str) -> bool:
    """Delete a scan from history. Returns True if a row was deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM scans WHERE id = ? AND user_id = ?",
            (scan_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0


def _row_to_dict(row) -> Dict[str, Any]:
    """Convert an aiosqlite Row to a plain dict, parsing JSON columns."""
    d = dict(row)
    for json_col in ("ghost_data", "network_data", "efficiency_data"):
        if json_col in d and isinstance(d[json_col], str):
            d[json_col] = json.loads(d[json_col])
    return d
