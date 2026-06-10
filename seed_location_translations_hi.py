#!/usr/bin/env python3
"""Seed / refresh Hindi rows in location_translations for all geography tables.

Run after init_db or when adding new villages:
  python3 seed_location_translations_hi.py

Safe to re-run: uses UPSERT on (location_id, language_code).
"""

from __future__ import annotations

import sqlite3
import sys

from app import BASE_DIR, DB_PATH
import language_core


def main() -> None:
    if not DB_PATH.is_file():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        raise SystemExit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        language_core.migrate_language_tables(conn)
        language_core.seed_state_languages(conn)
        language_core.seed_state_location_translations(conn)
        language_core.seed_hindi_geography_translations(conn)
        conn.commit()
        counts = {}
        for table in language_core.GEO_TABLES_FOR_I18N:
            n = conn.execute(
                """
                SELECT COUNT(*) FROM location_translations
                WHERE location_type = ? AND language_code = 'hi'
                """,
                (table,),
            ).fetchone()[0]
            counts[table] = int(n)
        print("Hindi location_translations seeded:", counts)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
