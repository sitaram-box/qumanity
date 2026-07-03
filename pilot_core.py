"""Pilot village program — registration, feedback, metrics."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

PILOT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pilot_villages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id TEXT UNIQUE NOT NULL,
    start_date TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    coordinator_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pilot_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id TEXT NOT NULL,
    citizen_id TEXT,
    category TEXT,
    rating INTEGER,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pilot_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id TEXT NOT NULL,
    metric_date TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    UNIQUE(village_id, metric_date, metric_name)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(PILOT_SCHEMA_SQL)


def register_pilot_village(
    conn: sqlite3.Connection,
    *,
    village_id: str,
    coordinator_name: str = "",
    status: str = "active",
) -> None:
    ensure_schema(conn)
    conn.execute(
        """
        INSERT INTO pilot_villages (village_id, start_date, status, coordinator_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(village_id) DO UPDATE SET
            status = excluded.status,
            coordinator_name = excluded.coordinator_name
        """,
        (
            village_id.strip(),
            datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            status.strip() or "active",
            coordinator_name.strip(),
        ),
    )


def list_pilot_villages(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT village_id, start_date, status, coordinator_name, created_at
        FROM pilot_villages
        ORDER BY datetime(created_at) DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def submit_pilot_feedback(
    conn: sqlite3.Connection,
    *,
    village_id: str,
    category: str = "",
    rating: int | None = None,
    comment: str = "",
    citizen_id: str | None = None,
) -> int:
    ensure_schema(conn)
    cur = conn.execute(
        """
        INSERT INTO pilot_feedback (village_id, citizen_id, category, rating, comment)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            village_id.strip(),
            citizen_id,
            category.strip()[:80],
            rating,
            comment.strip()[:1000],
        ),
    )
    return int(cur.lastrowid or 0)


def get_pilot_metrics(conn: sqlite3.Connection, village_id: str | None = None) -> list[dict[str, Any]]:
    ensure_schema(conn)
    if village_id:
        rows = conn.execute(
            """
            SELECT village_id, metric_date, metric_name, metric_value
            FROM pilot_metrics WHERE village_id = ?
            ORDER BY metric_date DESC, metric_name
            """,
            (village_id.strip(),),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT village_id, metric_date, metric_name, metric_value
            FROM pilot_metrics
            ORDER BY metric_date DESC, metric_name
            """
        ).fetchall()
    return [dict(r) for r in rows]
