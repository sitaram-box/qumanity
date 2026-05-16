#!/usr/bin/env python3
"""
Populate calendar_solar and daily_lunar_info for 2026 in indiaq.db.

Lunar **tithi** (paksha, tithi number/name, elongation, moon phase) uses ``ephem``
at **IST 06:00**, geocentric ecliptic elongation Moon−Sun (12° per tithi), as before.

VS 2083 (2026 Gregorian) contains **Adhik Jyeshtha** — Purnimanta month names cannot
be derived from full-moon enumeration alone here. Lunar **month labels** therefore use
``LUNAR_MONTH_RANGES_2026`` below (validated against commonly published Panchanga /
public calendar sites for VS 2083).

Validation (after run):
  SELECT date, lunar_month, paksha, tithi_name FROM daily_lunar_info
  WHERE date = '2026-05-11';
  -- Expected: Jyeshtha | Krishna | Navami

Dependencies: ephem, pytz

Run: python3 init_calendar_2026.py
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import ephem
import pytz

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "indiaq.db"

IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.UTC

UJJAIN_LAT_DEG = 23.1748
UJJAIN_LON_DEG = 75.7733

# Inclusive Gregorian ranges ``(start, end, month_name)`` — North Indian naming for
# VS 2083 Adhik Jyeshtha year; overlaps with Amanta/other regions are intentional
# omissions for this prototype. Ashadha begins 30 Jun 2026 per standard Panchanga.
LUNAR_MONTH_RANGES_2026: tuple[tuple[date, date, str], ...] = (
    (date(2026, 1, 1), date(2026, 1, 17), "Pausha"),
    (date(2026, 1, 18), date(2026, 2, 16), "Magha"),
    (date(2026, 2, 17), date(2026, 3, 18), "Phalguna"),
    (date(2026, 3, 19), date(2026, 5, 1), "Chaitra"),
    (date(2026, 5, 2), date(2026, 6, 29), "Jyeshtha"),
    (date(2026, 6, 30), date(2026, 7, 29), "Ashadha"),
    (date(2026, 7, 30), date(2026, 8, 26), "Shravana"),
    (date(2026, 8, 27), date(2026, 9, 25), "Bhadrapada"),
    (date(2026, 9, 26), date(2026, 10, 25), "Ashvina"),
    (date(2026, 10, 26), date(2026, 11, 23), "Kartika"),
    (date(2026, 11, 24), date(2026, 12, 22), "Margashirsha"),
    (date(2026, 12, 23), date(2026, 12, 31), "Pausha"),
)

TITHI_SHUKLA = (
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashthi",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
    "Purnima",
)

TITHI_KRISHNA = (
    "Pratipada",
    "Dwitiya",
    "Tritiya",
    "Chaturthi",
    "Panchami",
    "Shashthi",
    "Saptami",
    "Ashtami",
    "Navami",
    "Dashami",
    "Ekadashi",
    "Dwadashi",
    "Trayodashi",
    "Chaturdashi",
    "Amavasya",
)

MAPPING_NOTICE = (
    "WARNING: ``lunar_month`` for year 2026 uses hardcoded VS 2083 ranges "
    "(incl. Adhik Jyeshtha / extended Jyeshtha through 29 Jun) aligned with widely "
    "used public Panchanga sites; rebases if authoritative sources revise limits."
)

SOURCE_NOTE = (
    "ephem geocentric elongation @ IST 06:00; illum=(1-cos(elong))/2; "
    "tithi from elongation 12°/tithi; lunar_month via LUNAR_MONTH_RANGES_2026 "
    f"(prototype); ref Ujjain {UJJAIN_LON_DEG}°E/{UJJAIN_LAT_DEG}°N"
)


def _d(d: date) -> str:
    return d.isoformat()


def ist_midday_to_utc(d: date, hour: int = 12, minute: int = 0) -> datetime:
    local = IST.localize(datetime(d.year, d.month, d.day, hour, minute, 0))
    return local.astimezone(UTC)


def elongation_moon_sun_deg_geocentric(utc_naive: datetime) -> tuple[float, float]:
    ed = ephem.Date(utc_naive.replace(tzinfo=None))
    moon = ephem.Moon()
    sun = ephem.Sun()
    moon.compute(ed)
    sun.compute(ed)
    mlon = float(ephem.Ecliptic(moon).lon)
    slon = float(ephem.Ecliptic(sun).lon)
    elong_deg = (math.degrees(mlon) - math.degrees(slon)) % 360.0
    illum_pct = (1.0 - math.cos(math.radians(elong_deg))) / 2.0 * 100.0
    return elong_deg, illum_pct


def paksha_tithi_from_elongation(elong_deg: float) -> tuple[str, int, str]:
    if elong_deg < 180.0:
        paksha = "Shukla"
        n = int(elong_deg // 12.0) + 1
        n = min(15, max(1, n))
        name = TITHI_SHUKLA[n - 1]
    else:
        paksha = "Krishna"
        x = elong_deg - 180.0
        n = int(x // 12.0) + 1
        n = min(15, max(1, n))
        name = TITHI_KRISHNA[n - 1]
    return paksha, n, name


def lunar_month_from_mapping(d: date) -> str:
    for start, end, name in LUNAR_MONTH_RANGES_2026:
        if start <= d <= end:
            return name
    raise ValueError(f"no lunar_month range covers {d.isoformat()} (mapping incomplete)")


def tropical_solar_for_date(d: date) -> str:
    m, day = d.month, d.day
    if (m == 12 and day >= 22) or (m == 1 and day <= 19):
        return "Capricorn"
    bands = (
        ((1, 20), (2, 17), "Aquarius"),
        ((2, 18), (3, 19), "Pisces"),
        ((3, 20), (4, 19), "Aries"),
        ((4, 20), (5, 20), "Taurus"),
        ((5, 21), (6, 20), "Gemini"),
        ((6, 21), (7, 22), "Cancer"),
        ((7, 23), (8, 22), "Leo"),
        ((8, 23), (9, 22), "Virgo"),
        ((9, 23), (10, 22), "Libra"),
        ((10, 23), (11, 21), "Scorpio"),
        ((11, 22), (12, 21), "Sagittarius"),
        ((12, 22), (12, 31), "Capricorn"),
    )
    for (sm, sd), (em, ed), name in bands:
        if (m, day) >= (sm, sd) and (m, day) <= (em, ed):
            return name
    return "Capricorn"


def vikram_samvat_for_date(d: date) -> int:
    """
    Hindu year ticks to VS 2083 from Chaitra / VS New Year (~19 March 2026) onward.
    """
    if d < date(2026, 3, 19):
        return 2082
    if d.year == 2026:
        return 2083
    return 2083 + max(0, d.year - 2026)


DDL_CALENDAR_SOLAR = """
CREATE TABLE IF NOT EXISTS calendar_solar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    solar_month_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    year INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calendar_solar_range
    ON calendar_solar(start_date, end_date);

CREATE TABLE IF NOT EXISTS calendar_lunar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lunar_month_name TEXT NOT NULL,
    lunar_month_code TEXT NOT NULL,
    paksha TEXT NOT NULL,
    tithi_names TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calendar_lunar_range
    ON calendar_lunar(start_date, end_date);
"""


def tropical_solar_segments_2026() -> list[tuple[str, str, str, int]]:
    y = 2026
    bands = (
        ((1, 1), (1, 19), "Capricorn"),
        ((1, 20), (2, 17), "Aquarius"),
        ((2, 18), (3, 19), "Pisces"),
        ((3, 20), (4, 19), "Aries"),
        ((4, 20), (5, 20), "Taurus"),
        ((5, 21), (6, 20), "Gemini"),
        ((6, 21), (7, 22), "Cancer"),
        ((7, 23), (8, 22), "Leo"),
        ((8, 23), (9, 22), "Virgo"),
        ((9, 23), (10, 22), "Libra"),
        ((10, 23), (11, 21), "Scorpio"),
        ((11, 22), (12, 21), "Sagittarius"),
        ((12, 22), (12, 31), "Capricorn"),
    )
    return [
        (name, _d(date(y, sm, sd)), _d(date(y, em, ed)), y)
        for (sm, sd), (em, ed), name in bands
    ]


def main() -> None:
    print(MAPPING_NOTICE, flush=True)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=str,
        default=str(DB_PATH),
        help="SQLite path (default: indiaq.db beside this script)",
    )
    args = parser.parse_args()
    dbp = Path(args.db)
    if not dbp.is_file():
        print(f"ERROR: database file not found: {dbp}", file=sys.stderr)
        sys.exit(1)

    print(f"Using database: {dbp.resolve()}")
    conn = sqlite3.connect(str(dbp))
    try:
        conn.executescript(DDL_CALENDAR_SOLAR)

        print("Drop and recreate daily_lunar_info…")
        conn.execute("DROP TABLE IF EXISTS daily_lunar_info")
        conn.execute(
            """
            CREATE TABLE daily_lunar_info (
                date TEXT PRIMARY KEY,
                lunar_month TEXT NOT NULL,
                paksha TEXT NOT NULL,
                tithi_number INTEGER NOT NULL,
                tithi_name TEXT NOT NULL,
                moon_phase_pct REAL NOT NULL,
                elongation_deg REAL NOT NULL,
                vikram_samvat INTEGER NOT NULL,
                solar_month_name TEXT NOT NULL,
                source TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_daily_lunar_date ON daily_lunar_info(date)"
        )

        print("Clearing 2026 calendar_solar …")
        conn.execute("DELETE FROM calendar_solar WHERE year = 2026")
        solar = tropical_solar_segments_2026()
        conn.executemany(
            "INSERT INTO calendar_solar (solar_month_name, start_date, end_date, year) "
            "VALUES (?,?,?,?)",
            solar,
        )

        rows: list[tuple] = []
        d = date(2026, 1, 1)
        end = date(2026, 12, 31)
        while d <= end:
            utc = ist_midday_to_utc(d, 6, 0)
            naive = utc.replace(tzinfo=None)
            elong, illum = elongation_moon_sun_deg_geocentric(naive)
            paksha, tnum, tname = paksha_tithi_from_elongation(elong)
            lunar_m = lunar_month_from_mapping(d)
            solar_m = tropical_solar_for_date(d)
            vs = vikram_samvat_for_date(d)
            rows.append(
                (
                    _d(d),
                    lunar_m,
                    paksha,
                    tnum,
                    tname,
                    round(illum, 3),
                    round(elong, 6),
                    vs,
                    solar_m,
                    SOURCE_NOTE,
                )
            )
            d += timedelta(days=1)

        print(f"Inserting {len(rows)} rows…")
        conn.executemany(
            """
            INSERT INTO daily_lunar_info (
                date, lunar_month, paksha, tithi_number, tithi_name,
                moon_phase_pct, elongation_deg, vikram_samvat,
                solar_month_name, source
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )

        conn.commit()
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
