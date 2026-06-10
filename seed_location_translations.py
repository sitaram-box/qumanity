#!/usr/bin/env python3
"""Seed / refresh location_translations for all states (prototype + CSV import).

Run after init_db or when adding new villages:
  python3 seed_location_translations.py
  python3 seed_location_translations.py --csv data/location_translations_sample.csv

Safe to re-run: uses UPSERT on (location_id, language_code).
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from app import DB_PATH
import language_core

DEFAULT_CSV = Path(__file__).resolve().parent / "data" / "location_translations_sample.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed location_translations table")
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV if DEFAULT_CSV.is_file() else None,
        help="Optional CSV: location_id,location_type,language_code,translated_name",
    )
    parser.add_argument(
        "--skip-heuristics",
        action="store_true",
        help="Only run sample/CSV seeds (skip Hindi/Telugu heuristic passes)",
    )
    args = parser.parse_args()

    if not DB_PATH.is_file():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        raise SystemExit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        language_core.migrate_language_tables(conn)
        language_core.seed_state_languages(conn)
        language_core.seed_state_location_translations(conn)

        if not args.skip_heuristics:
            language_core.seed_hindi_geography_translations(conn)
            language_core.seed_telugu_geography_translations(conn)

        sample_counts = language_core.seed_sample_location_translations(conn)

        csv_count = 0
        if args.csv and Path(args.csv).is_file():
            csv_count = language_core.import_location_translations_from_csv(
                conn, args.csv
            )
            print(f"Imported {csv_count} rows from {args.csv}")
        elif args.csv:
            print(f"CSV not found (skipped): {args.csv}", file=sys.stderr)

        conn.commit()

        by_lang: dict[str, dict[str, int]] = {}
        for table in language_core.GEO_TABLES_FOR_I18N:
            rows = conn.execute(
                """
                SELECT language_code, COUNT(*) AS n
                FROM location_translations
                WHERE location_type = ?
                GROUP BY language_code
                """,
                (table,),
            ).fetchall()
            for r in rows:
                lang = str(r["language_code"])
                by_lang.setdefault(lang, {})[table] = int(r["n"])

        print("Sample translations upserted:", sample_counts)
        print("Totals by language:", by_lang)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
