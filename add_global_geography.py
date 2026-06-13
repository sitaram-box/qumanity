#!/usr/bin/env python3
"""
One-off migration for indiaq.db: global geography above zone.

Creates earth, continent, country; loads ISO 3166-1 alpha-3 rows from bundled
data/iso3166_countries.json when present, otherwise a built-in minimal list;
seeds global_core tables (states_global, countries_global); adds zone.country_id.

Run from the project root:
    python3 add_global_geography.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from db_path import ensure_database_parent, resolve_database_path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = resolve_database_path(BASE_DIR)
ensure_database_parent(DB_PATH)
JSON_PATH = BASE_DIR / "data" / "iso3166_countries.json"

CONTINENTS: tuple[tuple[str, str], ...] = (
    ("AS", "Asia"),
    ("AF", "Africa"),
    ("EU", "Europe"),
    ("NA", "North America"),
    ("SA", "South America"),
    ("OC", "Australia & Oceania"),
    ("AN", "Antarctica"),
)

PREFIX = "0.राम|"

INDIA_ZONE_NAMES: dict[str, str] = {
    "CS": "Central State (UT&North-East)",
    "NS": "North India State",
    "WS": "West India State",
    "SS": "South India State",
    "ES": "East India State",
}

FALLBACK_COUNTRIES: tuple[tuple[str, str, str], ...] = (
    ("IND", "India", "AS"),
    ("USA", "United States", "NA"),
    ("CAN", "Canada", "NA"),
    ("GBR", "United Kingdom", "EU"),
    ("DEU", "Germany", "EU"),
    ("FRA", "France", "EU"),
    ("AUS", "Australia", "OC"),
    ("JPN", "Japan", "AS"),
    ("CHN", "China", "AS"),
    ("SGP", "Singapore", "AS"),
    ("ARE", "United Arab Emirates", "AS"),
    ("BRA", "Brazil", "SA"),
    ("ZAF", "South Africa", "AF"),
    ("NGA", "Nigeria", "AF"),
    ("MEX", "Mexico", "NA"),
    ("NPL", "Nepal", "AS"),
    ("PAK", "Pakistan", "AS"),
    ("BGD", "Bangladesh", "AS"),
    ("LKA", "Sri Lanka", "AS"),
)


def log(msg: str) -> None:
    print(msg, flush=True)


def map_un_region_to_continent_id(
    alpha3: str,
    region: str | None,
    sub: str | None,
    inter: str | None,
) -> str:
    """Map UN statistical region fields to continent id (AS, AF, EU, NA, SA, OC, AN)."""
    a3 = (alpha3 or "").strip().upper()
    if a3 == "ATA":
        return "AN"
    if not region:
        if a3 == "TWN":
            return "AS"
        return "AN"
    if region == "Antarctica":
        return "AN"
    if region == "Asia":
        return "AS"
    if region == "Africa":
        return "AF"
    if region == "Europe":
        return "EU"
    if region == "Oceania":
        return "OC"
    if region == "Americas":
        blob = f"{sub or ''} {inter or ''}"
        if "South America" in blob:
            return "SA"
        return "NA"
    return "AS"


def load_country_rows_from_json() -> list[tuple[str, str, str]]:
    raw = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, str]] = []
    for row in raw:
        a3 = str(row.get("alpha-3") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        if len(a3) != 3 or not name:
            continue
        cid = map_un_region_to_continent_id(
            a3,
            row.get("region"),
            row.get("sub-region"),
            row.get("intermediate-region"),
        )
        rows.append((a3, name, cid))
    rows.sort(key=lambda t: t[0])
    return rows


def load_country_rows() -> list[tuple[str, str, str]]:
    if JSON_PATH.is_file():
        log(f"Loading countries from {JSON_PATH.name} …")
        return load_country_rows_from_json()
    log("iso3166_countries.json not found — using built-in country list.")
    return list(FALLBACK_COUNTRIES)


def column_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    if not table_exists(conn, table):
        return False
    cur = conn.execute(f"PRAGMA table_info({table})")
    return col in {str(r[1]) for r in cur.fetchall()}


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def row_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0])


def raw_path(full_id: str) -> str:
    fid = (full_id or "").strip()
    if fid.startswith(PREFIX):
        return fid[len(PREFIX) :]
    return fid


def zone_full_id_from_state_raw(state_raw: str) -> str | None:
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


def ensure_zone_table(conn: sqlite3.Connection) -> None:
    """Create ``zone`` and seed rows if the table is missing (required for country_id)."""
    if not table_exists(conn, "zone"):
        log("Creating table zone (if missing) …")
        conn.execute(
            """
            CREATE TABLE zone (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
    if row_count(conn, "zone") > 0:
        return

    if table_exists(conn, "state") and row_count(conn, "state") > 0:
        log("Seeding zone rows from state geography …")
        seen: set[str] = set()
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
        if row_count(conn, "zone") > 0:
            return

    log("Seeding default Indian zone rows …")
    for code, name in INDIA_ZONE_NAMES.items():
        conn.execute(
            "INSERT OR IGNORE INTO zone (id, name) VALUES (?, ?)",
            (PREFIX + f"IND.{code}", name),
        )


def seed_global_core_tables(conn: sqlite3.Connection) -> None:
    import global_core

    log("Migrating global_core schema (states_global, countries_global, …) …")
    global_core.migrate_global_location_schema(conn)
    n = global_core.seed_continents(conn)
    log(f"  continents (global_core): {n} rows seeded/updated")
    n = global_core.seed_countries_from_meta(conn)
    log(f"  countries_global from meta: {n} rows")
    n = global_core.seed_countries_from_existing_table(conn)
    log(f"  countries_global from country table: {n} rows")
    n = global_core.seed_states_from_json(conn)
    log(f"  states_global from JSON: {n} rows")


def verify(conn: sqlite3.Connection) -> bool:
    ok = True
    for table in ("continent", "country", "earth"):
        n = row_count(conn, table)
        log(f"  {table}: {n} rows")
        if table == "continent" and n == 0:
            ok = False
    if table_exists(conn, "states_global"):
        log(f"  states_global: {row_count(conn, 'states_global')} rows")
    return ok


def main() -> int:
    if not DB_PATH.is_file():
        log(f"ERROR: database not found: {DB_PATH}")
        log("Run init_db.py first.")
        return 1

    log(f"Connecting to {DB_PATH} …")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        log("Creating table earth (if missing) …")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS earth (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO earth (id, name) VALUES ('0', 'Earth')"
        )

        log("Creating table continent (if missing) …")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS continent (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
            """
        )
        for cid, cname in CONTINENTS:
            conn.execute(
                "INSERT OR IGNORE INTO continent (id, name) VALUES (?, ?)",
                (cid, cname),
            )

        log("Creating table country (if missing) …")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS country (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                continent_id TEXT NOT NULL,
                FOREIGN KEY (continent_id) REFERENCES continent(id)
            )
            """
        )

        country_rows = load_country_rows()
        log(f"Inserting {len(country_rows)} country rows …")
        conn.executemany(
            """
            INSERT OR IGNORE INTO country (id, name, continent_id)
            VALUES (?, ?, ?)
            """,
            country_rows,
        )

        ensure_zone_table(conn)

        if not column_exists(conn, "zone", "country_id"):
            log("Adding zone.country_id (NOT NULL DEFAULT 'IND') …")
            conn.execute(
                """
                ALTER TABLE zone ADD COLUMN country_id TEXT NOT NULL DEFAULT 'IND'
                    REFERENCES country(id)
                """
            )
        else:
            log("Column zone.country_id already exists — skipping ALTER.")

        log("Setting country_id = 'IND' for all zones (idempotent) …")
        conn.execute(
            "UPDATE zone SET country_id = 'IND' "
            "WHERE country_id IS NULL OR TRIM(country_id) = ''"
        )

        seed_global_core_tables(conn)

        conn.commit()
        log("Verification:")
        if not verify(conn):
            log("ERROR: continent table is still empty.")
            return 1
        log("Done. Global geography tables are ready.")
    except Exception as exc:
        conn.rollback()
        log(f"ERROR: {exc}")
        return 1
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
