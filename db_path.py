"""Resolve SQLite database path for local development and Railway volumes."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent


def resolve_database_path(base_dir: Path | None = None) -> Path:
    """
    Path to indiaq.db.

    Priority:
      1. DATABASE_PATH — full file path (e.g. /data/indiaq.db on Railway volume)
      2. RAILWAY_VOLUME_MOUNT_PATH/indiaq.db — Railway persistent volume mount
      3. <project_root>/indiaq.db — local development
    """
    root = base_dir or BASE_DIR
    explicit = (os.environ.get("DATABASE_PATH") or "").strip()
    if explicit:
        return Path(explicit)
    volume = (os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
    if volume:
        return Path(volume) / "indiaq.db"
    return root / "indiaq.db"


def ensure_database_parent(db_path: Path) -> None:
    parent = db_path.parent
    if str(parent) and not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)


def configure_sqlite_connection(conn: sqlite3.Connection) -> None:
    """Configure SQLite connection with recommended PRAGMAs."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -20000")


def execute_with_retry(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple | list = (),
    *,
    retries: int = 5,
    delay: float = 0.1,
):
    """Run conn.execute with exponential backoff on database lock errors."""
    import sqlite3 as _sqlite3
    import time

    last_exc: _sqlite3.OperationalError | None = None
    for attempt in range(retries):
        try:
            return conn.execute(sql, params)
        except _sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= retries - 1:
                raise
            last_exc = exc
            time.sleep(delay * (attempt + 1))
    if last_exc:
        raise last_exc
    raise RuntimeError("execute_with_retry failed without exception")


DB_PATH = resolve_database_path()
