#!/usr/bin/env python3
"""Manually trigger zodiac election automation for testing."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import election_automation

DEFAULT_DB = ROOT / "indiaq.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="Test election automation")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--year", type=int, default=date.today().year)
    parser.add_argument("--month", type=int, default=date.today().month)
    parser.add_argument(
        "--village-only",
        action="store_true",
        help="Run village elections only (skip hierarchy)",
    )
    parser.add_argument(
        "--level",
        default="village",
        help="level_type for single-location run",
    )
    parser.add_argument("--location-id", help="Run one location election")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if args.location_id:
            sign = election_automation.sun_sign_for_date(
                date(args.year, args.month, 15)
            )
            result = election_automation.run_election_for_location(
                conn,
                args.level,
                args.location_id,
                sign,
                args.year,
                args.month,
                simulate=True,
            )
            print(result)
        else:
            summary = election_automation.run_monthly_election_job(
                conn,
                today=date(args.year, args.month, 1),
                simulate=True,
                include_hierarchy=not args.village_only,
            )
            print(summary)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
