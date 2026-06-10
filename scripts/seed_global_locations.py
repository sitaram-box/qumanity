#!/usr/bin/env python3
"""Seed global location data (continents, countries, states) into indiaq.db."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import global_core  # noqa: E402

DB_PATH = BASE_DIR / "indiaq.db"


def main() -> int:
    if not DB_PATH.is_file():
        print(f"ERROR: database not found: {DB_PATH}")
        print("Run from project root after init_db.py or start the app once.")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        stats = global_core.seed_all_global_locations(conn)
        conn.commit()
        print("Global location seeding complete:")
        for key, val in stats.items():
            print(f"  {key}: {val}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
