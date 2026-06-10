#!/usr/bin/env python3
"""
Merge Indian geography into indiaq.db without deleting users, posts, or wallets.

The homepage (/) queries the ``state`` table for the state chart. If geography
tables are missing you get ``sqlite3.OperationalError: no such table: state``.

Run from the project root:
  python3 fix_geography.py
  python3 fix_geography.py --source /path/to/indiaq_backup.db

Then:
  python3 check_db.py
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "indiaq.db"
DEFAULT_SOURCE = BASE_DIR / "indiaq_backup.db"
PREFIX = "0.राम|"

# Parent → child (FK order for inserts).
INDIA_TABLES: tuple[str, ...] = ("zone", "state", "district", "tehsil", "village")

INDIA_ZONE_NAMES: dict[str, str] = {
    "CS": "Central State (UT&North-East)",
    "NS": "North India State",
    "WS": "West India State",
    "SS": "South India State",
    "ES": "East India State",
}

FK_COLUMNS: dict[str, tuple[str, ...]] = {
    "state": ("zone_id",),
    "district": ("state_id",),
    "tehsil": ("district_id",),
    "village": ("tehsil_id",),
}


def table_exists(conn: sqlite3.Connection, table: str, *, schema: str = "main") -> bool:
    row = conn.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str, *, schema: str = "main") -> list[str]:
    if not table_exists(conn, table, schema=schema):
        return []
    return [str(r[1]) for r in conn.execute(f"PRAGMA {schema}.table_info({table})")]


def row_count(conn: sqlite3.Connection, table: str, *, schema: str = "main") -> int:
    if not table_exists(conn, table, schema=schema):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {schema}.[{table}]").fetchone()[0])


def raw_path(full_id: str) -> str:
    fid = (full_id or "").strip()
    if fid.startswith(PREFIX):
        return fid[len(PREFIX) :]
    return fid


def zone_full_id_from_state_raw(state_raw: str) -> str | None:
    """Map IND/CS.DL → prefixed zone id IND.CS."""
    sr = (state_raw or "").strip()
    if not sr.startswith("IND") or "/" not in sr:
        return None
    _country, rest = sr.split("/", 1)
    if "." not in rest:
        return None
    zone_letters = "".join(ch for ch in rest.split(".", 1)[0] if ch.isalpha())
    if not zone_letters:
        return None
    return PREFIX + f"IND.{zone_letters}"


def geography_complete(conn: sqlite3.Connection) -> bool:
    """Every India geography table must exist and contain at least one row."""
    return all(
        table_exists(conn, table) and row_count(conn, table) > 0
        for table in INDIA_TABLES
    )


def seed_zones_from_states(conn: sqlite3.Connection) -> int:
    """Create and fill zone when missing but state rows already exist."""
    if not table_exists(conn, "state") or row_count(conn, "state") == 0:
        return 0
    if not table_exists(conn, "zone"):
        conn.execute(
            """
            CREATE TABLE zone (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
    if row_count(conn, "zone") > 0:
        return 0

    seen: set[str] = set()
    inserted = 0
    for (state_id,) in conn.execute("SELECT id FROM state"):
        zid = zone_full_id_from_state_raw(raw_path(str(state_id)))
        if not zid or zid in seen:
            continue
        code = raw_path(zid).replace("IND.", "", 1)
        name = INDIA_ZONE_NAMES.get(code, f"Zone {code}")
        conn.execute(
            "INSERT OR IGNORE INTO zone (id, name) VALUES (?, ?)",
            (zid, name),
        )
        seen.add(zid)
        inserted += 1

    if inserted == 0:
        for code, name in INDIA_ZONE_NAMES.items():
            zid = PREFIX + f"IND.{code}"
            conn.execute(
                "INSERT OR IGNORE INTO zone (id, name) VALUES (?, ?)",
                (zid, name),
            )
            inserted += 1
    return inserted


def create_table_from_source_ddl(conn: sqlite3.Connection, table: str) -> None:
    if table_exists(conn, table):
        return
    row = conn.execute(
        "SELECT sql FROM src.sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"Source database has no DDL for table {table!r}")
    conn.execute(str(row[0]))
    conn.commit()


def copy_table(conn: sqlite3.Connection, table: str) -> None:
    if not table_exists(conn, table, schema="src"):
        print(f"  {table}: not in source — skipped")
        return

    create_table_from_source_ddl(conn, table)

    existing = row_count(conn, table)
    if existing > 0:
        print(f"  {table}: already has {existing} rows — skipped copy")
        return

    cols = table_columns(conn, table, schema="src")
    if not cols:
        return

    select_parts: list[str] = []
    for col in cols:
        if col == "id" or col in FK_COLUMNS.get(table, ()):
            select_parts.append(
                f"CASE WHEN [{col}] IS NULL OR [{col}] LIKE '{PREFIX}%' "
                f"THEN [{col}] ELSE '{PREFIX}' || [{col}] END"
            )
        else:
            select_parts.append(f"[{col}]")

    col_list = ", ".join(f"[{c}]" for c in cols)
    select_sql = ", ".join(select_parts)
    conn.execute(
        f"INSERT OR IGNORE INTO main.[{table}] ({col_list}) "
        f"SELECT {select_sql} FROM src.[{table}]"
    )
    print(f"  {table}: copied {row_count(conn, table)} rows")


def merge_geography(source_path: Path) -> None:
    if not DB_PATH.is_file():
        raise SystemExit(f"Target database not found: {DB_PATH}")
    if not source_path.is_file():
        raise SystemExit(
            f"Source geography database not found: {source_path}\n\n"
            "Place indiaq_backup.db in the project root, or pass --source PATH.\n"
            "Do NOT run setup_indiaq.py — it replaces the entire indiaq.db."
        )

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("ATTACH DATABASE ? AS src", (str(source_path.resolve()),))

        if geography_complete(conn):
            print("Indian geography tables already populated.")
        else:
            print(f"Merging geography from {source_path} …")
            for table in INDIA_TABLES:
                if not table_exists(conn, table) or row_count(conn, table) == 0:
                    copy_table(conn, table)

        if not table_exists(conn, "zone") or row_count(conn, "zone") == 0:
            n = seed_zones_from_states(conn)
            if n:
                print(f"  zone: seeded {row_count(conn, 'zone')} rows from state data")

        conn.commit()
    finally:
        try:
            conn.execute("DETACH DATABASE src")
        except sqlite3.Error:
            pass
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

    global_script = BASE_DIR / "add_global_geography.py"
    if global_script.is_file():
        print("\nRunning add_global_geography.py …")
        result = subprocess.run(
            [sys.executable, str(global_script)],
            cwd=str(BASE_DIR),
            check=False,
        )
        if result.returncode != 0:
            print(
                "Warning: add_global_geography.py failed — run it manually.",
                file=sys.stderr,
            )
    else:
        print("\nRun add_global_geography.py manually for earth/continent/country tables.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=DEFAULT_SOURCE,
        help=f"Geography source DB (default: {DEFAULT_SOURCE.name})",
    )
    args = parser.parse_args()
    merge_geography(args.source.resolve())

    print("\nDone. Verify with: python3 check_db.py")
    print("Then restart Flask and open http://127.0.0.1:5000/")


if __name__ == "__main__":
    main()
