#!/usr/bin/env python3
"""
Populate zodiac_sign and element on geography tables (zone → village).

Uses SHA-256 digest of UTF-8 `id` (deterministic across runs and machines),
then index = int(digest, 16) % 12 mapped to tropical sign order:

  Aries, Taurus, Gemini, Cancer, Leo, Virgo, Libra,
  Scorpio, Sagittarius, Capricorn, Aquarius, Pisces.

Element derives from ELEMENT_BY_SIGN (same mapping as users).

Usage (from quantum_box directory):
    python3 assign_zodiac_to_geography.py [--db path/to/indiaq.db]

Default DB: ./indiaq.db — updates in place.

Note: builtin hash() is *not* used (not stable across interpreters); sha256 is.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from pathlib import Path
from typing import Iterable

GEO_TABLES: tuple[str, ...] = ("zone", "state", "district", "tehsil", "village")

ZODIAC_SIGNS_ORDER: tuple[str, ...] = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

ELEMENT_BY_SIGN: dict[str, str] = {
    "Aries": "Fire",
    "Leo": "Fire",
    "Sagittarius": "Fire",
    "Taurus": "Earth",
    "Virgo": "Earth",
    "Capricorn": "Earth",
    "Gemini": "Air",
    "Libra": "Air",
    "Aquarius": "Air",
    "Cancer": "Water",
    "Scorpio": "Water",
    "Pisces": "Water",
}


def zodiac_index_deterministic(geo_id: str) -> int:
    digest = hashlib.sha256(geo_id.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % 12


def sign_and_element_for_id(geo_id: str) -> tuple[str, str]:
    idx = zodiac_index_deterministic(geo_id)
    sign = ZODIAC_SIGNS_ORDER[idx]
    return sign, ELEMENT_BY_SIGN[sign]


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def ensure_column(
    conn: sqlite3.Connection, table: str, name: str, sql_type: str
) -> bool:
    if name in table_columns(conn, table):
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
    return True


def iter_ids(conn: sqlite3.Connection, table: str) -> Iterable[tuple[str]]:
    cur = conn.execute(f"SELECT id FROM {table}")
    for r in cur:
        yield (str(r[0]),)


def main() -> None:
    ap = argparse.ArgumentParser(description="Assign zodiac/element geography columns")
    ap.add_argument(
        "--db",
        type=Path,
        default=Path(__file__).resolve().parent / "indiaq.db",
        help="Path to SQLite geography database",
    )
    args = ap.parse_args()

    if not args.db.is_file():
        raise SystemExit(f"Database file not found: {args.db.resolve()}")

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys = ON")
    total_sign_counts: dict[str, int] = {s: 0 for s in ZODIAC_SIGNS_ORDER}
    total_el_counts = {"Fire": 0, "Earth": 0, "Air": 0, "Water": 0}
    rows_per_table: dict[str, int] = {}

    try:
        for tbl in GEO_TABLES:
            if tbl not in {
                str(r[0])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }:
                print(f"Skipping missing table: {tbl}")
                continue
            ensure_column(conn, tbl, "zodiac_sign", "TEXT")
            ensure_column(conn, tbl, "element", "TEXT")
            conn.commit()

            nupd = 0
            for (geo_id,) in iter_ids(conn, tbl):
                sign, element = sign_and_element_for_id(geo_id)
                conn.execute(
                    f"UPDATE {tbl} SET zodiac_sign = ?, element = ? WHERE id = ?",
                    (sign, element, geo_id),
                )
                total_sign_counts[sign] += 1
                total_el_counts[element] += 1
                nupd += 1
            rows_per_table[tbl] = nupd
            conn.commit()
            print(f"{tbl}: assigned {nupd} rows.")

        total_rows = sum(rows_per_table.values())
        print()
        print("=== Summary — count by zodiac_sign (all geography rows) ===")
        for sign in ZODIAC_SIGNS_ORDER:
            print(f"  {sign:12s}: {total_sign_counts[sign]}")
        print()
        print("=== Summary — count by element ===")
        for el in ("Fire", "Earth", "Air", "Water"):
            print(f"  {el:12s}: {total_el_counts[el]}")
        print()
        print(f"Grand total geography rows touched: {total_rows}")
        print(f"Database updated at {args.db.resolve()}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
