"""
Global geography (outside India): continents, countries, states/provinces.

Tables use ISO alpha-3 country codes (matching the existing ``country`` table).
State IDs: ``{ISO3}.{STATE_CODE}`` e.g. ``USA.CA``, ``DEU.BY``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
GLOBAL_STATES_JSON = BASE_DIR / "data" / "global_states.json"

CONTINENTS: tuple[tuple[str, str, str, str], ...] = (
    ("AF", "Africa", "अफ्रीका", "अफ़्रीका"),
    ("AS", "Asia", "एशिया", "एशिया"),
    ("EU", "Europe", "यूरोप", "यूरोप"),
    ("NA", "North America", "उत्तर अमेरिका", "उत्तरी अमेरिका"),
    ("SA", "South America", "दक्षिण अमेरिका", "दक्षिण अमेरिका"),
    ("OC", "Oceania", "ओशिनिया", "ओशिनिया"),
    ("AN", "Antarctica", "अंटार्कटिका", "अंटार्कटिका"),
)

# ISO alpha-3 -> (continent_id, name, lat, lng)
COUNTRY_META: dict[str, tuple[str, str, float, float]] = {
    "USA": ("NA", "United States", 37.0902, -95.7129),
    "CAN": ("NA", "Canada", 56.1304, -106.3468),
    "MEX": ("NA", "Mexico", 23.6345, -102.5528),
    "CHN": ("AS", "China", 35.8617, 104.1954),
    "JPN": ("AS", "Japan", 36.2048, 138.2529),
    "KOR": ("AS", "South Korea", 35.9078, 127.7669),
    "IDN": ("AS", "Indonesia", -0.7893, 113.9213),
    "ARE": ("AS", "United Arab Emirates", 23.4241, 53.8478),
    "SAU": ("AS", "Saudi Arabia", 23.8859, 45.0792),
    "DEU": ("EU", "Germany", 51.1657, 10.4515),
    "GBR": ("EU", "United Kingdom", 55.3781, -3.4360),
    "FRA": ("EU", "France", 46.2276, 2.2137),
    "ITA": ("EU", "Italy", 41.8719, 12.5674),
    "ESP": ("EU", "Spain", 40.4637, -3.7492),
    "BRA": ("SA", "Brazil", -14.2350, -51.9253),
    "ARG": ("SA", "Argentina", -38.4161, -63.6167),
    "PER": ("SA", "Peru", -9.1900, -75.0152),
    "AUS": ("OC", "Australia", -25.2744, 133.7751),
    "NZL": ("OC", "New Zealand", -40.9006, 174.8860),
    "NGA": ("AF", "Nigeria", 9.0820, 8.6753),
    "ZAF": ("AF", "South Africa", -30.5595, 22.9375),
    "KEN": ("AF", "Kenya", -0.0236, 37.9062),
    "EGY": ("AF", "Egypt", 26.8206, 30.8025),
}

GLOBAL_DDL = """
CREATE TABLE IF NOT EXISTS continents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    continent_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    name_sanskrit TEXT,
    name_hindi TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS countries_global (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id TEXT NOT NULL UNIQUE,
    continent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    name_local TEXT,
    iso_code TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_countries_global_iso ON countries_global(iso_code);
CREATE INDEX IF NOT EXISTS idx_countries_global_continent ON countries_global(continent_id);

CREATE TABLE IF NOT EXISTS states_global (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state_id TEXT NOT NULL UNIQUE,
    country_id TEXT NOT NULL,
    name TEXT NOT NULL,
    state_code TEXT,
    latitude REAL,
    longitude REAL,
    population INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (country_id) REFERENCES countries_global(country_id)
);
CREATE INDEX IF NOT EXISTS idx_states_global_country ON states_global(country_id);

CREATE TABLE IF NOT EXISTS districts_global (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    district_id TEXT NOT NULL UNIQUE,
    state_id TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (state_id) REFERENCES states_global(state_id)
);
CREATE INDEX IF NOT EXISTS idx_districts_global_state ON districts_global(state_id);
"""

ELEMENT_SIGNS: dict[str, tuple[str, ...]] = {
    "Fire": ("Aries", "Leo", "Sagittarius"),
    "Earth": ("Taurus", "Virgo", "Capricorn"),
    "Air": ("Gemini", "Libra", "Aquarius"),
    "Water": ("Cancer", "Scorpio", "Pisces"),
}


def migrate_global_location_schema(conn: sqlite3.Connection) -> None:
    """Create global location tables and user columns for global state."""
    conn.executescript(GLOBAL_DDL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col, ddl in (
        ("current_global_state_id", "TEXT"),
        ("birth_global_state_id", "TEXT"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")


def _country_id_for_iso(iso3: str, continent_id: str) -> str:
    """Canonical countries_global.country_id: ``{continent}.{iso2-ish}`` fallback to iso3."""
    iso3 = iso3.strip().upper()
    # Use continent.ISO3 short form for uniqueness (NA.USA, AS.JPN)
    return f"{continent_id}.{iso3}"


def seed_continents(conn: sqlite3.Connection) -> int:
    n = 0
    for cont_id, name_en, name_sa, name_hi in CONTINENTS:
        conn.execute(
            """
            INSERT INTO continents (continent_id, name, name_sanskrit, name_hindi)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(continent_id) DO UPDATE SET
                name = excluded.name,
                name_sanskrit = excluded.name_sanskrit,
                name_hindi = excluded.name_hindi
            """,
            (cont_id, name_en, name_sa, name_hi),
        )
        n += 1
    return n


def seed_countries_from_meta(conn: sqlite3.Connection) -> int:
    n = 0
    for iso3, (cont_id, name, lat, lng) in COUNTRY_META.items():
        cid = _country_id_for_iso(iso3, cont_id)
        conn.execute(
            """
            INSERT INTO countries_global (
                country_id, continent_id, name, iso_code, latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(country_id) DO UPDATE SET
                continent_id = excluded.continent_id,
                name = excluded.name,
                iso_code = excluded.iso_code,
                latitude = excluded.latitude,
                longitude = excluded.longitude
            """,
            (cid, cont_id, name, iso3, lat, lng),
        )
        n += 1
    return n


def seed_countries_from_existing_table(conn: sqlite3.Connection) -> int:
    """Sync rows from legacy ``country`` table (ISO alpha-3 ids)."""
    try:
        rows = conn.execute(
            "SELECT id, name, continent_id FROM country ORDER BY id"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0
    n = 0
    for row in rows:
        iso3 = str(row["id"]).strip().upper()
        if iso3 == "IND":
            continue
        cont_id = str(row["continent_id"] or "AS").strip().upper()
        meta = COUNTRY_META.get(iso3)
        lat = meta[2] if meta else None
        lng = meta[3] if meta else None
        cid = _country_id_for_iso(iso3, cont_id)
        conn.execute(
            """
            INSERT INTO countries_global (
                country_id, continent_id, name, iso_code, latitude, longitude
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(country_id) DO UPDATE SET
                name = excluded.name,
                continent_id = excluded.continent_id
            """,
            (cid, cont_id, str(row["name"]), iso3, lat, lng),
        )
        n += 1
    return n


def _load_states_json() -> dict[str, list[dict[str, Any]]]:
    if not GLOBAL_STATES_JSON.is_file():
        return {}
    raw = json.loads(GLOBAL_STATES_JSON.read_text(encoding="utf-8"))
    return raw.get("states") or {}


def seed_states_from_json(conn: sqlite3.Connection) -> int:
    data = _load_states_json()
    n = 0
    for iso3, states in data.items():
        iso3 = iso3.strip().upper()
        if iso3 == "IND":
            continue
        row = conn.execute(
            "SELECT country_id FROM countries_global WHERE iso_code = ?",
            (iso3,),
        ).fetchone()
        if not row:
            cont = COUNTRY_META.get(iso3, ("AS", iso3, 0.0, 0.0))[0]
            cid = _country_id_for_iso(iso3, cont)
        else:
            cid = str(row["country_id"])
        for st in states:
            code = str(st.get("code") or st.get("state_code") or "").strip().upper()
            name = str(st.get("name") or "").strip()
            if not code or not name:
                continue
            state_id = f"{iso3}.{code}"
            conn.execute(
                """
                INSERT INTO states_global (
                    state_id, country_id, name, state_code, latitude, longitude, population
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(state_id) DO UPDATE SET
                    name = excluded.name,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    population = excluded.population
                """,
                (
                    state_id,
                    cid,
                    name,
                    code,
                    st.get("lat") or st.get("latitude"),
                    st.get("lng") or st.get("longitude"),
                    st.get("population"),
                ),
            )
            n += 1
    return n


def seed_location_coordinates_for_global_states(conn: sqlite3.Connection) -> int:
    """Mirror global state centroids into location_coordinates for planetary calc."""
    try:
        import planetary_core
    except ImportError:
        return 0
    planetary_core.migrate_space_schema(conn)
    n = 0
    for row in conn.execute(
        """
        SELECT state_id, name, latitude, longitude
        FROM states_global
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """
    ):
        conn.execute(
            """
            INSERT INTO location_coordinates (
                location_id, location_type, location_name, latitude, longitude
            ) VALUES (?, 'state', ?, ?, ?)
            ON CONFLICT(location_id, location_type) DO UPDATE SET
                location_name = excluded.location_name,
                latitude = excluded.latitude,
                longitude = excluded.longitude
            """,
            (
                str(row["state_id"]),
                str(row["name"]),
                float(row["latitude"]),
                float(row["longitude"]),
            ),
        )
        n += 1
    return n


def seed_all_global_locations(conn: sqlite3.Connection) -> dict[str, int]:
    migrate_global_location_schema(conn)
    stats = {
        "continents": seed_continents(conn),
        "countries_meta": seed_countries_from_meta(conn),
        "countries_synced": seed_countries_from_existing_table(conn),
        "states": seed_states_from_json(conn),
    }
    stats["coordinates"] = seed_location_coordinates_for_global_states(conn)
    return stats


def list_states_for_country(conn: sqlite3.Connection, country_iso: str) -> list[dict[str, str]]:
    """Return states for ISO alpha-3 country code (e.g. USA, DEU)."""
    migrate_global_location_schema(conn)
    iso = country_iso.strip().upper()
    if iso == "IND":
        return []
    cur = conn.execute(
        """
        SELECT state_id, name, state_code
        FROM states_global
        WHERE state_id LIKE ? ESCAPE '\\'
        ORDER BY name COLLATE NOCASE
        """,
        (f"{iso}.%",),
    )
    return [
        {
            "id": str(r["state_id"]),
            "name": str(r["name"]),
            "code": str(r["state_code"] or ""),
        }
        for r in cur
    ]


def country_has_states(conn: sqlite3.Connection, country_iso: str) -> bool:
    """True when ``states_global`` has rows for this ISO alpha-3 country."""
    migrate_global_location_schema(conn)
    iso = country_iso.strip().upper()
    if not iso or iso == "IND":
        return False
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM states_global
        WHERE state_id LIKE ? ESCAPE '\\'
        """,
        (f"{iso}.%",),
    ).fetchone()
    return bool(row and int(row["c"] or 0) > 0)


def country_states_payload(conn: sqlite3.Connection, country_iso: str) -> dict[str, Any]:
    """API payload: ``has_states`` plus ``states`` list."""
    states = list_states_for_country(conn, country_iso)
    return {
        "country_id": country_iso.strip().upper(),
        "has_states": len(states) > 0,
        "states": states,
    }


def state_display_name(conn: sqlite3.Connection, state_id: str | None) -> str | None:
    if not state_id:
        return None
    row = conn.execute(
        "SELECT name FROM states_global WHERE state_id = ?",
        (str(state_id).strip(),),
    ).fetchone()
    return str(row["name"]) if row else None


def user_global_state_id(user_row: sqlite3.Row) -> str | None:
    try:
        sid = str(user_row["current_global_state_id"] or "").strip()
    except (KeyError, IndexError):
        sid = ""
    return sid or None


def is_global_only_user(user_row: sqlite3.Row) -> bool:
    try:
        birth_ctry = str(user_row["birth_country_id"] or "").strip().upper()
        curr_ctry = str(user_row["current_country_id"] or "").strip().upper()
    except (KeyError, IndexError):
        return False
    return birth_ctry != "IND" and curr_ctry != "IND"


def global_public_hierarchy(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
) -> tuple[list[dict[str, str]], str]:
    """State tab for global users; country-only tab when no state is set."""
    state_id = user_global_state_id(user_row)
    if state_id:
        name = state_display_name(conn, state_id) or state_id
        return [
            {
                "scope": "state",
                "id": state_id,
                "name": name,
                "url": "#",
            }
        ], state_id
    try:
        country_id = str(user_row["current_country_id"] or "").strip().upper()
    except (KeyError, IndexError):
        country_id = ""
    if not country_id:
        return [], ""
    cname = country_id
    row = conn.execute(
        "SELECT name FROM countries_global WHERE iso_code = ?", (country_id,)
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT name FROM country WHERE id = ?", (country_id,)
        ).fetchone()
    if row:
        cname = str(row["name"])
    return [
        {
            "scope": "country",
            "id": country_id,
            "name": cname,
            "url": "#",
        }
    ], country_id


def _user_scope_sql(
    location_id: str | None,
    location_type: str | None,
    *,
    tab: str,
) -> tuple[str, list[Any]]:
    """Build safe WHERE clause for element stats by location scope."""
    lid = str(location_id or "").strip()
    ltype = str(location_type or "").strip().lower()
    params: list[Any] = []

    if tab in ("private", "personal") or not lid:
        return "1=1", params

    if ltype == "village":
        return (
            "(TRIM(COALESCE(u.current_location_id,'')) = ? "
            "OR TRIM(COALESCE(u.current_location_id,'')) LIKE ?)",
            [lid, f"{lid}.%"],
        )
    if ltype == "tehsil":
        return "TRIM(COALESCE(u.current_location_id,'')) LIKE ?", [f"%{lid}%"]
    if ltype == "district":
        return "TRIM(COALESCE(u.current_location_id,'')) LIKE ?", [f"%{lid}%"]
    if ltype == "state":
        if "." in lid and not lid.startswith("0."):
            return "TRIM(COALESCE(u.current_global_state_id,'')) = ?", [lid]
        return "TRIM(COALESCE(u.current_location_id,'')) LIKE ?", [f"%{lid}%"]
    if ltype == "country":
        return "TRIM(COALESCE(u.current_country_id,'')) = ?", [lid]
    if ltype == "continent":
        return "TRIM(COALESCE(u.current_continent_id,'')) = ?", [lid]
    if ltype == "earth":
        return "1=1", []
    if ltype == "zone":
        return "TRIM(COALESCE(u.current_location_id,'')) LIKE ?", [f"%{lid}%"]
    return "1=1", params


def get_element_stats(
    conn: sqlite3.Connection,
    *,
    element: str,
    location_id: str | None = None,
    location_type: str | None = None,
    tab: str = "private",
) -> dict[str, Any]:
    """Count living users per zodiac sign within an element at a location scope."""
    el = str(element or "Fire").strip().title()
    signs = ELEMENT_SIGNS.get(el, ELEMENT_SIGNS["Fire"])
    scope_sql, scope_params = _user_scope_sql(location_id, location_type, tab=tab)

    results: dict[str, int] = {}
    total = 0
    deceased_clause = ""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "is_deceased" in cols:
        deceased_clause = " AND COALESCE(u.is_deceased, 0) = 0"

    for sign in signs:
        params = [sign, *scope_params]
        row = conn.execute(
            f"""
            SELECT COUNT(*) AS c FROM users u
            WHERE TRIM(COALESCE(u.sun_sign,'')) = ?
              AND ({scope_sql})
              {deceased_clause}
            """,
            params,
        ).fetchone()
        count = int(row["c"] or 0) if row else 0
        results[sign] = count
        total += count

    return {"element": el, "total": total, "signs": results}
