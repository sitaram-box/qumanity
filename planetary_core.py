"""
Planetary positions — birth chart storage and daily ephemeris (Ākāśa / Space layer).

Uses ``ephem`` when available (sidereal Lahiri); falls back to simplified day-of-year
approximation for prototype.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from zodiac_calendar import SIGN_ELEMENT

try:
    import ephem

    EPHEM_AVAILABLE = True
except ImportError:
    ephem = None  # type: ignore
    EPHEM_AVAILABLE = False

try:
    import pytz

    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    IST = None  # type: ignore

ZODIAC_SIGNS: tuple[str, ...] = (
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

PLANET_NAMES: tuple[str, ...] = (
    "Sun",
    "Moon",
    "Mars",
    "Mercury",
    "Jupiter",
    "Venus",
    "Saturn",
    "Rahu",
    "Ketu",
)

PLANET_SANSKRIT: dict[str, dict[str, str]] = {
    "Sun": {"sanskrit": "सूर्य", "name": "Surya", "symbol": "\u2609"},
    "Moon": {"sanskrit": "चंद्र", "name": "Chandra", "symbol": "\u263d"},
    "Mars": {"sanskrit": "मंगल", "name": "Mangala", "symbol": "\u2642"},
    "Mercury": {"sanskrit": "बुध", "name": "Budha", "symbol": "\u263f"},
    "Jupiter": {"sanskrit": "गुरु", "name": "Guru", "symbol": "\u2643"},
    "Venus": {"sanskrit": "शुक्र", "name": "Shukra", "symbol": "\u2640"},
    "Saturn": {"sanskrit": "शनि", "name": "Shani", "symbol": "\u2644"},
    "Rahu": {"sanskrit": "राहु", "name": "Rahu", "symbol": "\u260a"},
    "Ketu": {"sanskrit": "केतु", "name": "Ketu", "symbol": "\u260b"},
}

PLANET_SYMBOLS: dict[str, str] = {
    k: v["symbol"] for k, v in PLANET_SANSKRIT.items()
}

DEFAULT_LAT = 28.6139
DEFAULT_LON = 77.2090

SPACE_DDL = """
CREATE TABLE IF NOT EXISTS deceased_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_private_id TEXT NOT NULL UNIQUE,
    original_public_id TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    gender TEXT,
    date_of_birth TEXT,
    date_of_death TEXT NOT NULL,
    sun_sign TEXT,
    element TEXT,
    current_location_id TEXT,
    karma_ledger_archive TEXT,
    final_wallet_balance INTEGER,
    wallet_transferred_to TEXT,
    obituary TEXT,
    moved_to_space_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    moved_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_deceased_users_location ON deceased_users(current_location_id);
CREATE INDEX IF NOT EXISTS idx_deceased_users_death ON deceased_users(date_of_death);

CREATE TABLE IF NOT EXISTS akashic_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_type TEXT NOT NULL,
    original_id INTEGER,
    user_private_id TEXT,
    location_id TEXT,
    data TEXT NOT NULL,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_akashic_type ON akashic_records(record_type);
CREATE INDEX IF NOT EXISTS idx_akashic_location ON akashic_records(location_id);
CREATE INDEX IF NOT EXISTS idx_akashic_archived ON akashic_records(archived_at);

CREATE TABLE IF NOT EXISTS planetary_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calculation_date TEXT NOT NULL,
    planet_name TEXT NOT NULL,
    zodiac_sign TEXT NOT NULL,
    element TEXT NOT NULL,
    degree REAL,
    nakshatra TEXT,
    retrograde INTEGER NOT NULL DEFAULT 0,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(calculation_date, planet_name)
);
CREATE INDEX IF NOT EXISTS idx_planetary_date ON planetary_positions(calculation_date);

CREATE TABLE IF NOT EXISTS user_birth_planets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    planet_name TEXT NOT NULL,
    zodiac_sign TEXT NOT NULL,
    element TEXT NOT NULL,
    degree REAL,
    nakshatra TEXT,
    retrograde INTEGER NOT NULL DEFAULT 0,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_private_id, planet_name)
);
CREATE INDEX IF NOT EXISTS idx_user_birth_planets_user ON user_birth_planets(user_private_id);

CREATE TABLE IF NOT EXISTS location_coordinates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL,
    location_type TEXT NOT NULL,
    location_name TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    timezone TEXT DEFAULT 'Asia/Kolkata',
    UNIQUE(location_id, location_type)
);
CREATE INDEX IF NOT EXISTS idx_location_coordinates_lookup
    ON location_coordinates(location_id, location_type);
"""

# Indian state centroids (location_id = state code)
INDIAN_STATE_COORDINATES: tuple[tuple[str, str, float, float], ...] = (
    ("DL", "Delhi", 28.6139, 77.2090),
    ("UP", "Uttar Pradesh", 26.8467, 80.9462),
    ("MH", "Maharashtra", 19.7515, 75.7139),
    ("TN", "Tamil Nadu", 11.1271, 78.6569),
    ("KA", "Karnataka", 15.3173, 75.7139),
    ("KL", "Kerala", 10.8505, 76.2711),
    ("GJ", "Gujarat", 22.2587, 71.1924),
    ("RJ", "Rajasthan", 27.0238, 74.2179),
    ("WB", "West Bengal", 22.9868, 87.8550),
    ("BR", "Bihar", 25.0961, 85.3131),
    ("MP", "Madhya Pradesh", 22.9734, 78.6569),
    ("PB", "Punjab", 31.1471, 75.3412),
    ("HR", "Haryana", 29.0588, 76.0856),
    ("AS", "Assam", 26.2006, 92.9376),
    ("OR", "Odisha", 20.9517, 85.0985),
    ("TG", "Telangana", 18.1124, 79.0193),
    ("JH", "Jharkhand", 23.6102, 85.2799),
    ("UK", "Uttarakhand", 30.0668, 79.0193),
    ("CG", "Chhattisgarh", 21.2787, 81.8661),
    ("GA", "Goa", 15.2993, 74.1240),
)

GLOBAL_LOCATION_COORDINATES: tuple[tuple[str, str, str, float, float], ...] = (
    ("0", "earth", "Earth", 20.0, 0.0),
    ("earth", "earth", "Earth", 20.0, 0.0),
    ("ASIA", "continent", "Asia", 34.0479, 100.6197),
    ("AFR", "continent", "Africa", 1.0, 20.0),
    ("EUR", "continent", "Europe", 54.0, 15.0),
    ("NAM", "continent", "North America", 45.0, -100.0),
    ("SAM", "continent", "South America", -15.0, -60.0),
    ("OCE", "continent", "Oceania", -25.0, 140.0),
    ("IND", "country", "India", 21.0, 78.0),
    ("USA", "country", "United States", 39.8283, -98.5795),
    ("zone", "zone", "India Zone", 23.0, 79.0),
)


def migrate_space_schema(conn: sqlite3.Connection) -> None:
    """Create Space / planetary tables and extend users for deceased workflow."""
    conn.executescript(SPACE_DDL)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col, ddl in (
        ("is_deceased", "INTEGER NOT NULL DEFAULT 0"),
        ("date_of_death", "TEXT"),
        ("deceased_archived", "INTEGER NOT NULL DEFAULT 0"),
        ("wallet_frozen", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
    seed_location_coordinates(conn)


def seed_location_coordinates(conn: sqlite3.Connection) -> None:
    """Idempotent seed for Indian state and global location centroids."""
    for code, name, lat, lon in INDIAN_STATE_COORDINATES:
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
            (code, name, lat, lon),
        )
    for lid, ltype, name, lat, lon in GLOBAL_LOCATION_COORDINATES:
        conn.execute(
            """
            INSERT INTO location_coordinates (
                location_id, location_type, location_name, latitude, longitude
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(location_id, location_type) DO UPDATE SET
                location_name = excluded.location_name,
                latitude = excluded.latitude,
                longitude = excluded.longitude
            """,
            (lid, ltype, name, lat, lon),
        )


def _normalize_location_type(location_type: str | None) -> str:
    return str(location_type or "").strip().lower()


def extract_state_code(location_id: str) -> str | None:
    """Extract 2-letter state code from a geography id path."""
    raw = str(location_id or "").strip().upper()
    if not raw:
        return None
    if "|" in raw:
        raw = raw.split("|", 1)[1]
    m = re.search(r"(?:/|\.)CS(?:/|\.)([A-Z]{2})", raw)
    if m:
        return m.group(1)
    m = re.search(r"(?:^|[/.])([A-Z]{2})(?:[/.]|$)", raw)
    if m and m.group(1) in {c[0] for c in INDIAN_STATE_COORDINATES}:
        return m.group(1)
    return None


def resolve_location_coordinates(
    conn: sqlite3.Connection,
    location_id: str | None,
    location_type: str | None,
) -> tuple[float, float]:
    """
    Resolve lat/lon for a geography unit. Falls back to state centroid, then Delhi.
    """
    migrate_space_schema(conn)
    lid = str(location_id or "").strip()
    ltype = _normalize_location_type(location_type)

    if lid:
        row = conn.execute(
            """
            SELECT latitude, longitude FROM location_coordinates
            WHERE location_id = ? AND location_type = ?
            """,
            (lid, ltype),
        ).fetchone()
        if row:
            return float(row["latitude"]), float(row["longitude"])

        if "." in lid and not lid.startswith("0."):
            row = conn.execute(
                """
                SELECT latitude, longitude FROM location_coordinates
                WHERE location_id = ? AND location_type = 'state'
                """,
                (lid,),
            ).fetchone()
            if row:
                return float(row["latitude"]), float(row["longitude"])
            row = conn.execute(
                """
                SELECT latitude, longitude FROM states_global
                WHERE state_id = ?
                """,
                (lid,),
            ).fetchone()
            if row and row["latitude"] is not None and row["longitude"] is not None:
                return float(row["latitude"]), float(row["longitude"])

        row = conn.execute(
            """
            SELECT latitude, longitude FROM location_coordinates
            WHERE location_id = ? COLLATE NOCASE
            ORDER BY CASE location_type
                WHEN ? THEN 0
                WHEN 'state' THEN 1
                WHEN 'country' THEN 2
                ELSE 3
            END
            LIMIT 1
            """,
            (lid, ltype),
        ).fetchone()
        if row:
            return float(row["latitude"]), float(row["longitude"])

    state_code = extract_state_code(lid)
    if state_code:
        row = conn.execute(
            """
            SELECT latitude, longitude FROM location_coordinates
            WHERE location_id = ? AND location_type = 'state'
            """,
            (state_code,),
        ).fetchone()
        if row:
            return float(row["latitude"]), float(row["longitude"])

    if ltype == "country":
        row = conn.execute(
            """
            SELECT latitude, longitude FROM location_coordinates
            WHERE location_type = 'country' LIMIT 1
            """
        ).fetchone()
        if row:
            return float(row["latitude"]), float(row["longitude"])

    if ltype == "earth":
        row = conn.execute(
            """
            SELECT latitude, longitude FROM location_coordinates
            WHERE location_type = 'earth' LIMIT 1
            """
        ).fetchone()
        if row:
            return float(row["latitude"]), float(row["longitude"])

    return DEFAULT_LAT, DEFAULT_LON


def get_live_planetary_positions(
    conn: sqlite3.Connection,
    *,
    location_id: str | None = None,
    location_type: str | None = None,
    language: str = "en",
    when: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Calculate current sky positions for a geographic location (ephem / fallback)."""
    lat, lon = resolve_location_coordinates(conn, location_id, location_type)
    ref = when or datetime.now(timezone.utc)
    if IST is not None and ref.tzinfo is None:
        ref = IST.localize(ref)
    positions = compute_all_planets(ref, lat=lat, lon=lon)
    return group_by_element(positions, language=language)


def get_element_from_sign(sign: str) -> str:
    return SIGN_ELEMENT.get(str(sign or "").strip(), "Fire")


def get_planet_symbol(planet_name: str) -> str:
    meta = PLANET_SANSKRIT.get(str(planet_name or "").strip())
    if meta:
        return meta["symbol"]
    return "?"


def get_planet_display(planet_name: str, language: str = "en") -> str:
    """Full Sanskrit/English planet name without astrological symbol."""
    planet = PLANET_SANSKRIT.get(str(planet_name or "").strip())
    if not planet:
        return str(planet_name or "")
    lang = (language or "en").strip().lower()
    if lang == "hi":
        return planet["sanskrit"]
    return planet["name"]


def _lahiri_ayanamsa_deg(julian_ut: float) -> float:
    days_since_j2000 = julian_ut - 2451545.0
    years = days_since_j2000 / 365.25
    return (23.85417 + years * (50.29 / 3600.0)) % 360.0


def _sign_from_longitude(lon_deg: float) -> tuple[str, float]:
    lon = float(lon_deg) % 360.0
    idx = int(lon // 30.0) % 12
    degree_in_sign = lon % 30.0
    return ZODIAC_SIGNS[idx], round(degree_in_sign, 2)


def _parse_birth_datetime(date_of_birth: str, birth_time: str) -> datetime:
    d = date.fromisoformat(str(date_of_birth).strip()[:10])
    raw = str(birth_time or "12:00").strip()
    parts = raw.replace(".", ":").split(":")
    h = int(parts[0]) if parts and parts[0].isdigit() else 12
    m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    if IST is not None:
        return IST.localize(datetime.combine(d, time(h, m)))
    return datetime.combine(d, time(h, m), tzinfo=timezone.utc)


def _ephem_observer(dt: datetime, lat: float, lon: float) -> Any:
    obs = ephem.Observer()
    if IST is not None and dt.tzinfo is not None:
        utc = dt.astimezone(pytz.UTC)
    elif dt.tzinfo is not None:
        utc = dt.astimezone(timezone.utc)
    else:
        utc = dt.replace(tzinfo=timezone.utc)
    obs.date = ephem.Date(utc.replace(tzinfo=None))
    obs.lat = str(lat)
    obs.lon = str(lon)
    return obs


def _tropical_longitude(body: Any, obs: Any) -> float:
    body.compute(obs)
    return math.degrees(float(ephem.Ecliptic(body).lon)) % 360.0


def _mean_rahu_longitude(julian_ut: float) -> float:
    """Approximate mean lunar ascending node (Rahu) in tropical degrees."""
    t = (julian_ut - 2451545.0) / 36525.0
    omega = 125.04452 - 1934.136261 * t
    return omega % 360.0


def calculate_simplified_planet_position(planet: str, when: date) -> str:
    """Prototype fallback — day-of-year modulo per planet orbital period."""
    day_of_year = when.timetuple().tm_yday
    planet_speed = {
        "Sun": 365,
        "Moon": 27,
        "Mars": 687,
        "Mercury": 88,
        "Jupiter": 4333,
        "Venus": 225,
        "Saturn": 10759,
        "Rahu": 6800,
        "Ketu": 6800,
    }
    speed = max(1, planet_speed.get(planet, 365))
    sign_index = (day_of_year // max(1, int(speed / 12))) % 12
    if planet == "Ketu":
        sign_index = (sign_index + 6) % 12
    return ZODIAC_SIGNS[sign_index]


def _compute_planet_row(
    planet: str,
    when: datetime,
    *,
    lat: float,
    lon: float,
) -> dict[str, Any]:
    if EPHEM_AVAILABLE and planet in {
        "Sun",
        "Moon",
        "Mars",
        "Mercury",
        "Jupiter",
        "Venus",
        "Saturn",
    }:
        obs = _ephem_observer(when, lat, lon)
        body_map = {
            "Sun": ephem.Sun,
            "Moon": ephem.Moon,
            "Mars": ephem.Mars,
            "Mercury": ephem.Mercury,
            "Jupiter": ephem.Jupiter,
            "Venus": ephem.Venus,
            "Saturn": ephem.Saturn,
        }
        body = body_map[planet]()
        tropical = _tropical_longitude(body, obs)
        julian_ut = float(obs.date) + 2415020.0
        sidereal = (tropical - _lahiri_ayanamsa_deg(julian_ut)) % 360.0
        sign, deg = _sign_from_longitude(sidereal)
        retro = False
        if planet not in ("Sun", "Moon"):
            try:
                retro = bool(body.retrograde)
            except Exception:
                retro = False
        return {
            "planet_name": planet,
            "zodiac_sign": sign,
            "element": get_element_from_sign(sign),
            "degree": deg,
            "nakshatra": None,
            "retrograde": retro,
        }

    d = when.date() if isinstance(when, datetime) else when
    sign = calculate_simplified_planet_position(planet, d)
    return {
        "planet_name": planet,
        "zodiac_sign": sign,
        "element": get_element_from_sign(sign),
        "degree": None,
        "nakshatra": None,
        "retrograde": False,
    }


def compute_all_planets(
    when: datetime | date,
    *,
    lat: float | None = None,
    lon: float | None = None,
) -> list[dict[str, Any]]:
    lat_f = float(lat if lat is not None else DEFAULT_LAT)
    lon_f = float(lon if lon is not None else DEFAULT_LON)
    if isinstance(when, date) and not isinstance(when, datetime):
        when = datetime.combine(when, time(12, 0))
        if IST is not None:
            when = IST.localize(when)
    rows: list[dict[str, Any]] = []
    for planet in PLANET_NAMES:
        if planet in ("Rahu", "Ketu") and EPHEM_AVAILABLE:
            obs = _ephem_observer(when, lat_f, lon_f)
            julian_ut = float(obs.date) + 2415020.0
            rahu_trop = _mean_rahu_longitude(julian_ut)
            sidereal = (rahu_trop - _lahiri_ayanamsa_deg(julian_ut)) % 360.0
            if planet == "Ketu":
                sidereal = (sidereal + 180.0) % 360.0
            sign, deg = _sign_from_longitude(sidereal)
            rows.append(
                {
                    "planet_name": planet,
                    "zodiac_sign": sign,
                    "element": get_element_from_sign(sign),
                    "degree": deg,
                    "nakshatra": None,
                    "retrograde": True,
                }
            )
        else:
            rows.append(
                _compute_planet_row(planet, when, lat=lat_f, lon=lon_f)
            )
    return rows


def group_by_element(
    positions: list[dict[str, Any]],
    *,
    language: str = "en",
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "Fire": [],
        "Earth": [],
        "Air": [],
        "Water": [],
    }
    for pos in positions:
        el = pos.get("element") or get_element_from_sign(str(pos.get("zodiac_sign") or ""))
        if el not in result:
            el = "Fire"
        pname = pos["planet_name"]
        meta = PLANET_SANSKRIT.get(pname, {})
        result[el].append(
            {
                "name": meta.get("name") or pname,
                "planet_key": pname,
                "symbol": get_planet_symbol(pname),
                "sanskrit": meta.get("sanskrit", ""),
                "display": get_planet_display(pname, language),
                "zodiac_sign": pos.get("zodiac_sign"),
                "degree": pos.get("degree"),
                "retrograde": bool(pos.get("retrograde")),
            }
        )
    return result


def save_user_birth_planets(
    conn: sqlite3.Connection,
    user_private_id: str,
    *,
    date_of_birth: str,
    birth_time: str = "12:00",
    latitude: float | None = None,
    longitude: float | None = None,
) -> None:
    """Calculate and persist birth-chart planets for a user (once at registration)."""
    migrate_space_schema(conn)
    pid = str(user_private_id).strip()
    if not pid:
        return
    existing = conn.execute(
        "SELECT COUNT(*) AS c FROM user_birth_planets WHERE user_private_id = ?",
        (pid,),
    ).fetchone()
    if existing and int(existing["c"] or 0) > 0:
        return
    try:
        when = _parse_birth_datetime(date_of_birth, birth_time)
    except (TypeError, ValueError):
        when = datetime.combine(date.today(), time(12, 0))
    planets = compute_all_planets(
        when, lat=latitude, lon=longitude
    )
    for p in planets:
        conn.execute(
            """
            INSERT INTO user_birth_planets (
                user_private_id, planet_name, zodiac_sign, element,
                degree, nakshatra, retrograde
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_private_id, planet_name) DO UPDATE SET
                zodiac_sign = excluded.zodiac_sign,
                element = excluded.element,
                degree = excluded.degree,
                nakshatra = excluded.nakshatra,
                retrograde = excluded.retrograde,
                calculated_at = CURRENT_TIMESTAMP
            """,
            (
                pid,
                p["planet_name"],
                p["zodiac_sign"],
                p["element"],
                p.get("degree"),
                p.get("nakshatra"),
                1 if p.get("retrograde") else 0,
            ),
        )


def update_daily_planetary_positions(
    conn: sqlite3.Connection,
    *,
    for_date: date | None = None,
) -> dict[str, Any]:
    """Calculate and store today's planetary positions (location pages)."""
    migrate_space_schema(conn)
    today = for_date or date.today()
    today_s = today.isoformat()
    when = datetime.combine(today, time(12, 0))
    if IST is not None:
        when = IST.localize(when)
    all_rows = compute_all_planets(when)
    by_name = {r["planet_name"]: r for r in all_rows}
    for planet in PLANET_NAMES:
        p = by_name.get(planet)
        if not p:
            sign = calculate_simplified_planet_position(planet, today)
            p = {
                "planet_name": planet,
                "zodiac_sign": sign,
                "element": get_element_from_sign(sign),
                "degree": None,
                "nakshatra": None,
                "retrograde": False,
            }
        conn.execute(
            """
            INSERT INTO planetary_positions (
                calculation_date, planet_name, zodiac_sign, element,
                degree, nakshatra, retrograde
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(calculation_date, planet_name) DO UPDATE SET
                zodiac_sign = excluded.zodiac_sign,
                element = excluded.element,
                degree = excluded.degree,
                nakshatra = excluded.nakshatra,
                retrograde = excluded.retrograde,
                calculated_at = CURRENT_TIMESTAMP
            """,
            (
                today_s,
                planet,
                p["zodiac_sign"],
                p["element"],
                p.get("degree"),
                p.get("nakshatra"),
                1 if p.get("retrograde") else 0,
            ),
        )
    return {"date": today_s, "planets": len(PLANET_NAMES)}


def get_current_planetary_positions(
    conn: sqlite3.Connection,
    *,
    language: str = "en",
    location_id: str | None = None,
    location_type: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Current sky grouped by element — live calc when location given, else daily cache."""
    if location_id or location_type:
        return get_live_planetary_positions(
            conn,
            location_id=location_id,
            location_type=location_type,
            language=language,
        )
    migrate_space_schema(conn)
    today = date.today().isoformat()
    rows = conn.execute(
        """
        SELECT planet_name, zodiac_sign, element, degree, retrograde
        FROM planetary_positions
        WHERE calculation_date = ?
        ORDER BY planet_name
        """,
        (today,),
    ).fetchall()
    if not rows:
        update_daily_planetary_positions(conn)
        rows = conn.execute(
            """
            SELECT planet_name, zodiac_sign, element, degree, retrograde
            FROM planetary_positions
            WHERE calculation_date = ?
            ORDER BY planet_name
            """,
            (today,),
        ).fetchall()
    positions = [
        {
            "planet_name": r["planet_name"],
            "zodiac_sign": r["zodiac_sign"],
            "element": r["element"],
            "degree": r["degree"],
            "retrograde": bool(r["retrograde"]),
        }
        for r in rows
    ]
    return group_by_element(positions, language=language)


def get_user_birth_planets_grouped(
    conn: sqlite3.Connection,
    user_private_id: str,
    *,
    language: str = "en",
) -> dict[str, list[dict[str, Any]]]:
    migrate_space_schema(conn)
    pid = str(user_private_id).strip()
    rows = conn.execute(
        """
        SELECT planet_name, zodiac_sign, element, degree, retrograde
        FROM user_birth_planets
        WHERE user_private_id = ?
        ORDER BY planet_name
        """,
        (pid,),
    ).fetchall()
    positions = [
        {
            "planet_name": r["planet_name"],
            "zodiac_sign": r["zodiac_sign"],
            "element": r["element"],
            "degree": r["degree"],
            "retrograde": bool(r["retrograde"]),
        }
        for r in rows
    ]
    return group_by_element(positions, language=language)
