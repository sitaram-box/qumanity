"""
Sauramana (sidereal solar) zodiac calendar — festivals, lunar events, and solar months.

Static JSON under ``data/`` seeds SQLite tables ``festivals`` and ``lunar_events`` so
event rows can be updated without code changes.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FESTIVALS_JSON = DATA_DIR / "festivals_2026.json"
LUNAR_JSON = DATA_DIR / "lunar_data.json"

VIKRAM_SAMVAT_2026 = 2083

ELEMENT_COLOUR: dict[str, str] = {
    "Fire": "#FF6F61",
    "Earth": "#B0E57C",
    "Air": "#C0C0C0",
    "Water": "#79E0EE",
}

ELEMENT_SYMBOL: dict[str, str] = {
    "Fire": "🔥",
    "Earth": "🌍",
    "Air": "💨",
    "Water": "💧",
}

SIGN_SANSKRIT: dict[str, str] = {
    "Aries": "Mesha",
    "Taurus": "Vrishabha",
    "Gemini": "Mithuna",
    "Cancer": "Karka",
    "Leo": "Simha",
    "Virgo": "Kanya",
    "Libra": "Tula",
    "Scorpio": "Vrishchika",
    "Sagittarius": "Dhanu",
    "Capricorn": "Makara",
    "Aquarius": "Kumbha",
    "Pisces": "Meena",
}

SIGN_ELEMENT: dict[str, str] = {
    "Aries": "Fire",
    "Taurus": "Earth",
    "Gemini": "Air",
    "Cancer": "Water",
    "Leo": "Fire",
    "Virgo": "Earth",
    "Libra": "Air",
    "Scorpio": "Water",
    "Sagittarius": "Fire",
    "Capricorn": "Earth",
    "Aquarius": "Air",
    "Pisces": "Water",
}

# Solar month ingress (Sankranti) dates for VS 2083 / Gregorian 2026–2027 cycle.
SOLAR_INGRESS_2026: tuple[tuple[str, str], ...] = (
    ("Aries", "2026-04-14"),
    ("Taurus", "2026-05-15"),
    ("Gemini", "2026-06-15"),
    ("Cancer", "2026-07-16"),
    ("Leo", "2026-08-17"),
    ("Virgo", "2026-09-17"),
    ("Libra", "2026-10-17"),
    ("Scorpio", "2026-11-16"),
    ("Sagittarius", "2026-12-16"),
    ("Capricorn", "2026-01-14"),
    ("Aquarius", "2026-02-13"),
    ("Pisces", "2026-03-15"),
)

GREGORIAN_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

CALENDAR_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS festivals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT,
    year INTEGER NOT NULL DEFAULT 2026
);
CREATE INDEX IF NOT EXISTS idx_festivals_date ON festivals(date);
CREATE INDEX IF NOT EXISTS idx_festivals_year ON festivals(year);

CREATE TABLE IF NOT EXISTS lunar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    date TEXT NOT NULL,
    paksha TEXT,
    description TEXT,
    event_type TEXT NOT NULL,
    year INTEGER NOT NULL DEFAULT 2026
);
CREATE INDEX IF NOT EXISTS idx_lunar_events_date ON lunar_events(date);
CREATE INDEX IF NOT EXISTS idx_lunar_events_year ON lunar_events(year);
CREATE INDEX IF NOT EXISTS idx_lunar_events_type ON lunar_events(event_type);

CREATE TABLE IF NOT EXISTS festivals_2026 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS lunar_events_2026 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    date TEXT NOT NULL,
    paksha TEXT,
    description TEXT
);
"""


def _parse_iso(d: str) -> date:
    return date.fromisoformat(d)


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
    return int(row["c"]) if row else 0


def get_solar_months_2026() -> list[dict[str, Any]]:
    """Twelve sidereal solar months (Aries → Pisces) with element colours."""
    months: list[dict[str, Any]] = []
    ingress = list(SOLAR_INGRESS_2026)
    for i, (name, start_s) in enumerate(ingress):
        start = _parse_iso(start_s)
        if i + 1 < len(ingress):
            end = _parse_iso(ingress[i + 1][1]) - timedelta(days=1)
        else:
            end = _parse_iso(ingress[0][1]) - timedelta(days=1)
            if end < start:
                end = date(2027, 4, 13)
        element = SIGN_ELEMENT[name]
        months.append(
            {
                "name": name,
                "sanskrit": SIGN_SANSKRIT[name],
                "element": element,
                "element_symbol": ELEMENT_SYMBOL[element],
                "colour_code": ELEMENT_COLOUR[element],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "vikram_samvat": VIKRAM_SAMVAT_2026,
            }
        )
    return months


def _gregorian_month_bounds(year: int, month_name: str) -> tuple[str, str] | None:
    key = month_name.strip().capitalize()
    if key not in GREGORIAN_MONTHS:
        return None
    m = GREGORIAN_MONTHS.index(key) + 1
    start = date(year, m, 1)
    if m == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, m + 1, 1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _solar_month_bounds(month_name: str) -> tuple[str, str] | None:
    for row in get_solar_months_2026():
        if row["name"].lower() == month_name.strip().lower():
            return row["start_date"], row["end_date"]
    return None


def get_festivals_for_month(
    conn: sqlite3.Connection, year: int, month: str
) -> list[dict[str, Any]]:
    """Festivals overlapping the given Gregorian or solar month name."""
    bounds = _gregorian_month_bounds(year, month) or _solar_month_bounds(month)
    if not bounds:
        return []
    start, end = bounds
    rows = conn.execute(
        """
        SELECT name, date, description
        FROM festivals
        WHERE date >= ? AND date <= ?
        ORDER BY date
        """,
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def get_lunar_events_for_month(
    conn: sqlite3.Connection, year: int, month: str
) -> list[dict[str, Any]]:
    bounds = _gregorian_month_bounds(year, month) or _solar_month_bounds(month)
    if not bounds:
        return []
    start, end = bounds
    rows = conn.execute(
        """
        SELECT event_name, date, paksha, description, event_type
        FROM lunar_events
        WHERE date >= ? AND date <= ?
        ORDER BY date
        """,
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def events_for_solar_month(
    conn: sqlite3.Connection, start_date: str, end_date: str
) -> dict[str, list[dict[str, Any]]]:
    festivals = conn.execute(
        """
        SELECT name, date, description FROM festivals
        WHERE date >= ? AND date <= ?
        ORDER BY date
        """,
        (start_date, end_date),
    ).fetchall()
    lunar = conn.execute(
        """
        SELECT event_name, date, paksha, description, event_type
        FROM lunar_events
        WHERE date >= ? AND date <= ?
        ORDER BY date
        """,
        (start_date, end_date),
    ).fetchall()
    return {
        "festivals": [dict(r) for r in festivals],
        "lunar_events": [dict(r) for r in lunar],
    }


def user_birthday_in_range(dob: str, start_date: str, end_date: str) -> bool:
    """True if month-day of dob falls within [start_date, end_date] (any year)."""
    try:
        b = _parse_iso(dob[:10])
        start = _parse_iso(start_date)
        end = _parse_iso(end_date)
    except ValueError:
        return False
    for y in range(start.year, end.year + 1):
        try:
            candidate = date(y, b.month, b.day)
        except ValueError:
            continue
        if start <= candidate <= end:
            return True
    return False


def _row_val(user: sqlite3.Row | dict[str, Any], key: str, default: Any = "") -> Any:
    if isinstance(user, sqlite3.Row):
        try:
            return user[key]
        except (KeyError, IndexError):
            return default
    return user.get(key, default)


def get_user_birthday_payload(user: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    dob = str(_row_val(user, "date_of_birth"))[:10]
    first = str(_row_val(user, "first_name"))
    last = str(_row_val(user, "last_name"))
    try:
        b = _parse_iso(dob)
        month_num, day_num = b.month, b.day
    except ValueError:
        month_num, day_num = None, None
    return {
        "date": dob,
        "name": f"{first} {last}".strip(),
        "month": month_num,
        "day": day_num,
    }


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _seed_from_json(conn: sqlite3.Connection) -> None:
    if FESTIVALS_JSON.is_file():
        festivals = _load_json(FESTIVALS_JSON)
        if _table_count(conn, "festivals") == 0:
            conn.executemany(
                """
                INSERT INTO festivals (name, date, description, year)
                VALUES (?, ?, ?, 2026)
                """,
                [
                    (f["name"], f["date"], f.get("description", ""))
                    for f in festivals
                ],
            )
        if _table_count(conn, "festivals_2026") == 0:
            conn.executemany(
                """
                INSERT INTO festivals_2026 (name, date, description)
                VALUES (?, ?, ?)
                """,
                [
                    (f["name"], f["date"], f.get("description", ""))
                    for f in festivals
                ],
            )

    if LUNAR_JSON.is_file():
        lunar = _load_json(LUNAR_JSON)
        rows: list[tuple[str, str, str, str, str]] = []
        legacy: list[tuple[str, str, str, str]] = []
        for event_type, key in (
            ("Purnima", "purnima"),
            ("Amavasya", "amavasya"),
            ("Ekadashi", "ekadashi"),
        ):
            for item in lunar.get(key, []):
                rows.append(
                    (
                        item["name"],
                        item["date"],
                        item.get("paksha", ""),
                        item.get("description", ""),
                        event_type,
                    )
                )
                legacy.append(
                    (
                        item["name"],
                        item["date"],
                        item.get("paksha", ""),
                        item.get("description", ""),
                    )
                )
        if _table_count(conn, "lunar_events") == 0 and rows:
            conn.executemany(
                """
                INSERT INTO lunar_events
                    (event_name, date, paksha, description, event_type, year)
                VALUES (?, ?, ?, ?, ?, 2026)
                """,
                rows,
            )
        if _table_count(conn, "lunar_events_2026") == 0 and legacy:
            conn.executemany(
                """
                INSERT INTO lunar_events_2026 (event_name, date, paksha, description)
                VALUES (?, ?, ?, ?)
                """,
                legacy,
            )


def migrate_calendar_event_tables(conn: sqlite3.Connection) -> None:
    """Ensure festival / lunar tables exist and seed from JSON when empty."""
    conn.executescript(CALENDAR_TABLES_SQL)
    _seed_from_json(conn)
    conn.commit()
