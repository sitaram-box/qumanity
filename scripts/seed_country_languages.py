#!/usr/bin/env python3
"""Seed country_languages and zodiac_planets (idempotent)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import element_core
from app import DB_PATH


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        element_core.migrate_element_core_schema(conn)
        conn.commit()
        zp = conn.execute("SELECT COUNT(*) AS c FROM zodiac_planets").fetchone()
        cl = conn.execute("SELECT COUNT(*) AS c FROM country_languages").fetchone()
        print(f"Seeded zodiac_planets: {int(zp['c'])} rows")
        print(f"Seeded country_languages: {int(cl['c'])} rows")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
