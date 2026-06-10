#!/usr/bin/env python3
"""Add complete state/province data for countries (extends global_states.json)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import global_core  # noqa: E402

DB_PATH = BASE_DIR / "indiaq.db"
BASE_JSON = BASE_DIR / "data" / "global_states.json"
EXTENDED_JSON = BASE_DIR / "data" / "global_states_extended.json"


def _country_row(conn: sqlite3.Connection, iso3: str) -> str | None:
    iso3 = iso3.strip().upper()
    row = conn.execute(
        "SELECT country_id FROM countries_global WHERE iso_code = ?",
        (iso3,),
    ).fetchone()
    if row:
        return str(row["country_id"])
    meta = global_core.COUNTRY_META.get(iso3)
    if not meta:
        return None
    return global_core._country_id_for_iso(iso3, meta[0])


def _insert_state(
    conn: sqlite3.Connection,
    *,
    iso3: str,
    country_id: str,
    code: str,
    name: str,
    lat: float | None = None,
    lng: float | None = None,
) -> None:
    state_id = f"{iso3}.{code.upper()}"
    conn.execute(
        """
        INSERT INTO states_global (
            state_id, country_id, name, state_code, latitude, longitude
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(state_id) DO UPDATE SET
            name = excluded.name,
            state_code = excluded.state_code,
            latitude = COALESCE(excluded.latitude, states_global.latitude),
            longitude = COALESCE(excluded.longitude, states_global.longitude)
        """,
        (state_id, country_id, name, code.upper(), lat, lng),
    )


def seed_from_json(conn: sqlite3.Connection, path: Path) -> int:
    if not path.is_file():
        return 0
    raw = json.loads(path.read_text(encoding="utf-8"))
    states_map = raw.get("states") or raw
    n = 0
    for iso3, states in states_map.items():
        iso3 = str(iso3).strip().upper()
        if iso3 == "IND" or not isinstance(states, list):
            continue
        cid = _country_row(conn, iso3)
        if not cid:
            continue
        for st in states:
            code = str(st.get("code") or st.get("state_code") or "").strip()
            name = str(st.get("name") or "").strip()
            if not code or not name:
                continue
            _insert_state(
                conn,
                iso3=iso3,
                country_id=cid,
                code=code,
                name=name,
                lat=st.get("lat") or st.get("latitude"),
                lng=st.get("lng") or st.get("longitude"),
            )
            n += 1
    return n


def main() -> int:
    if not DB_PATH.is_file():
        print(f"ERROR: database not found: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        global_core.migrate_global_location_schema(conn)
        global_core.seed_countries_from_meta(conn)
        global_core.seed_countries_from_existing_table(conn)

        n_base = seed_from_json(conn, BASE_JSON)
        n_ext = seed_from_json(conn, EXTENDED_JSON)
        coords = global_core.seed_location_coordinates_for_global_states(conn)
        conn.commit()
        print(f"Seeded {n_base} states from {BASE_JSON.name}")
        print(f"Seeded {n_ext} states from {EXTENDED_JSON.name}")
        print(f"Updated {coords} location_coordinates rows")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
