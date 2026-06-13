#!/usr/bin/env python3
"""Database connectivity diagnostic for Qumanity.

Read-only: never creates or modifies the database.

Run:
    python3 check_db.py
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from db_path import resolve_database_path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = resolve_database_path(BASE_DIR)


def main() -> None:
    print("=== Qumanity — Database Diagnostic ===\n")

    print(f"Current directory: {os.getcwd()}")
    print(f"Script directory:  {BASE_DIR}")
    print(f"DATABASE_PATH env: {os.environ.get('DATABASE_PATH', '(not set)')}")
    print(f"RAILWAY_VOLUME_MOUNT_PATH: {os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '(not set)')}")
    print(f"Resolved DB path:  {DB_PATH}")

    if DB_PATH.exists():
        size = DB_PATH.stat().st_size
        print(f"   File exists ({size:,} bytes)")
    else:
        print("   File NOT found — run init_db.py first.")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        version = cur.execute("SELECT sqlite_version();").fetchone()[0]
        tables = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        conn.close()
        print(f"\nSQLite version: {version}")
        print(f"Tables ({len(tables)}):")
        for (name,) in tables:
            print(f"  - {name}")

        geo_tables = ("continent", "country", "states_global", "state", "village")
        print("\nGeography row counts:")
        conn = sqlite3.connect(DB_PATH)
        for table in geo_tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
                print(f"  {table}: {n}")
            except sqlite3.OperationalError:
                print(f"  {table}: (missing)")
        conn.close()
    except sqlite3.Error as exc:
        print(f"\nERROR connecting: {exc}")


if __name__ == "__main__":
    main()
