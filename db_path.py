"""Resolve SQLite database path for local development and Railway volumes."""

from __future__ import annotations

import os
from pathlib import Path

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
