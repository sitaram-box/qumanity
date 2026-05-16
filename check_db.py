#!/usr/bin/env python3
"""
Quick SQLite sanity check for indiaq.db: list tables and PRAGMA columns.

Usage (from project root):
  python3 check_db.py
  python3 check_db.py /path/to/other.db
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "indiaq.db"


def main() -> None:
    db_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DB
    print(f"Database path: {db_path}")
    if not db_path.is_file():
        print("ERROR: file does not exist.")
        sys.exit(2)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as e:
        print(f"ERROR: could not open database: {e}")
        sys.exit(3)

    try:
        tables = conn.execute(
            """
            SELECT name, type, sql
            FROM sqlite_master
            WHERE type IN ('table', 'view')
            ORDER BY type, name
            """
        ).fetchall()

        print(f"\nFound {len(tables)} table(s)/view(s).\n")
        for row in tables:
            name = row["name"]
            typ = row["type"]
            print(f"=== {typ}: {name} ===")
            if row["sql"]:
                for line in str(row["sql"]).strip().splitlines():
                    print(f"  {line}")
            cols = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
            if cols:
                print("  Columns:")
                for c in cols:
                    cid, cname, ctype, notnull, dflt, pk = (
                        c["cid"],
                        c["name"],
                        c["type"],
                        c["notnull"],
                        c["dflt"],
                        c["pk"],
                    )
                    extra = []
                    if pk:
                        extra.append("PK")
                    if notnull:
                        extra.append("NOT NULL")
                    if dflt is not None:
                        extra.append(f"DEFAULT={dflt!r}")
                    suf = f" ({', '.join(extra)})" if extra else ""
                    print(f"    - {cname}: {ctype}{suf}")
            print()

        # lightweight integrity hint (does not fix DB)
        quick = conn.execute("PRAGMA quick_check").fetchone()
        if quick:
            print("PRAGMA quick_check:", quick[0])

    except sqlite3.Error as e:
        print(f"ERROR while reading schema: {e}")
        sys.exit(4)
    finally:
        conn.close()

    print("Done.")


if __name__ == "__main__":
    main()
