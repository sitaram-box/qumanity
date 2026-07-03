"""In-app feedback storage and admin review."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

FEEDBACK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS app_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT,
    page_path TEXT NOT NULL,
    category TEXT,
    rating INTEGER,
    message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_app_feedback_created ON app_feedback(created_at);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(FEEDBACK_SCHEMA_SQL)


def submit_feedback(
    conn: sqlite3.Connection,
    *,
    page_path: str,
    rating: int | None = None,
    message: str = "",
    category: str = "",
    user_private_id: str | None = None,
) -> int:
    ensure_schema(conn)
    cur = conn.execute(
        """
        INSERT INTO app_feedback (user_private_id, page_path, category, rating, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_private_id,
            (page_path or "/").strip()[:500],
            (category or "").strip()[:120],
            rating,
            (message or "").strip()[:500],
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    return int(cur.lastrowid or 0)


def list_feedback(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT id, page_path, category, rating, message, created_at, user_private_id
        FROM app_feedback
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]
