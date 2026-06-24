#!/usr/bin/env python3
"""Migrate QSI (Quantum Spiritual Interface) tables and seed 12 Naam services.

Run from project root:
  python3 migrations/migrate_qsi.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db_path import resolve_database_path, ensure_database_parent

import qsi_core


def run_migration() -> int:
    path = resolve_database_path(ROOT)
    ensure_database_parent(path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        qsi_core.migrate_qsi_schema(conn)
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM qsi_service_categories"
        ).fetchone()["n"]
        print(f"QSI migration complete — {count} services seeded at {path}")
        return 0
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"QSI migration failed: {exc}")
        return 1
    finally:
        conn.close()


def main() -> None:
    raise SystemExit(run_migration())


if __name__ == "__main__":
    main()
