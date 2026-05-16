"""
Calendar helpers for ``/api/current_time`` and ``/api/advanced_time``.

Uses ``ephem`` for geocentric longitudes and elongation; reads ``daily_lunar_info``
when present for Purnimanta lunar month labels (see ``init_calendar_2026.py``).
"""

from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any

try:
    import ephem
except ImportError:  # pragma: no cover
    ephem = None  # type: ignore

try:
    import pytz
except ImportError:  # pragma: no cover
    pytz = None  # type: ignore

IST = pytz.timezone("Asia/Kolkata") if pytz else None

_log = logging.getLogger(__name__)

EPHEM_AVAILABLE = ephem is not None

# --- Western tropical signs (ecliptic longitude 0° = start of Aries) ---
WEST_SIGN_ORDER_EN = (
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

# Sidereal rāśi (Lahiri): Mesha … Mīna (Sanskrit nominative masculine singular style)
VEDIC_RASHI_SA = (
    "मेषः",
    "वृषभः",
    "मिथुनः",
    "कर्कटः",
    "सिंहः",
    "कन्या",
    "तुला",
    "वृश्चिकः",
    "धनुः",
    "मकरः",
    "कुम्भः",
    "मीनः",
)

VEDIC_RASHI_EN = WEST_SIGN_ORDER_EN

# 27 Nakṣatra names (Sanskrit, nominative / commonly cited spellings)
NAKSHATRA_SA = (
    "अश्विनी",
    "भरणी",
    "कृत्तिका",
    "रोहिणी",
    "मृगशिरा",
    "आर्द्रा",
    "पुनर्वसु",
    "पुष्य",
    "आश्लेषा",
    "मघा",
    "पूर्वफाल्गुनी",
    "उत्तरफाल्गुनी",
    "हस्ता",
    "चित्रा",
    "स्वाती",
    "विशाखा",
    "अनुराधा",
    "ज्येष्ठा",
    "मूला",
    "पूर्वाषाढा",
    "उत्तराषाढा",
    "श्रवणः",
    "धनिष्ठा",
    "शतभिषः",
    "पूर्वभाद्रपदा",
    "उत्तरभाद्रपदा",
    "रेवती",
)

WEEKDAY_EN = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)

# Weekday in Sanskrit (Monday … Sunday)
WEEKDAY_SA = (
    "सोमवारम्",
    "मंगलवारम्",
    "बुधवारम्",
    "गुरुवारम्",
    "शुक्रवारम्",
    "शनिवारम्",
    "रविवारम्",
)

# Note: Python Monday=0; many Indian enumerations use Sunday first — we map by name.

LUNAR_MONTH_EN_TO_SA = {
    "Chaitra": "चैत्रः",
    "Vaishakha": "वैशाखः",
    "Jyeshtha": "ज्येष्ठः",
    "Ashadha": "आषाढः",
    "Shravana": "श्रावणः",
    "Bhadrapada": "भाद्रपदः",
    "Ashvina": "आश्विनः",
    "Kartika": "कार्तिकः",
    "Margashirsha": "मार्गशीर्षः",
    "Pausha": "पौषः",
    "Magha": "माघः",
    "Phalguna": "फाल्गुनः",
}

TITHI_EN_TO_SA = {
    "Pratipada": "प्रथमा",
    "Dwitiya": "द्वितीया",
    "Tritiya": "तृतीया",
    "Chaturthi": "चतुर्थी",
    "Panchami": "पञ्चमी",
    "Shashthi": "षष्ठी",
    "Saptami": "सप्तमी",
    "Ashtami": "अष्टमी",
    "Navami": "नवमी",
    "Dashami": "दशमी",
    "Ekadashi": "एकादशी",
    "Dwadashi": "द्वादशी",
    "Trayodashi": "त्रयोदशी",
    "Chaturdashi": "चतुर्दशी",
    "Purnima": "पूर्णिमा",
    "Amavasya": "अमावास्या",
}

PAKSHA_EN_TO_SA = {
    "Shukla": "शुक्लः",
    "Krishna": "कृष्णः",
}

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


def now_ist() -> datetime:
    if IST is not None:
        return datetime.now(IST)
    return datetime.utcnow() + timedelta(hours=5, minutes=30)


def tropical_sign(m: int, d: int) -> str:
    """Western tropical zodiac from calendar month/day (Sun position approximation)."""
    if (m == 12 and d >= 22) or (m == 1 and d <= 19):
        return "Capricorn"
    ranges = (
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
    for (sm, sd), (em, ed), name in ranges:
        if (m, d) >= (sm, sd) and (m, d) <= (em, ed):
            return name
    return "Capricorn"


def lahiri_ayanamsa_deg(julian_ut: float) -> float:
    """
    Approximate Lahiri ayanamsa (degrees) using linear drift from J2000.
    Adequate for nakṣatra / sidereal rāśi slotting in this prototype.
    """
    days_since_j2000 = julian_ut - 2451545.0
    years = days_since_j2000 / 365.25
    return (23.85417 + years * (50.29 / 3600.0)) % 360.0


def moon_sun_ecliptic_deg(
    dt_ist: datetime,
) -> tuple[float, float, float, float, float]:
    """
    Returns (moon_tropical_deg, sun_tropical_deg, elong_deg, julian_ut, illum_pct).
    """
    if not EPHEM_AVAILABLE:
        return 0.0, 0.0, 0.0, 2451545.0, 0.0
    if IST is not None and dt_ist.tzinfo is not None:
        utc_naive = dt_ist.astimezone(pytz.UTC).replace(tzinfo=None)
    elif dt_ist.tzinfo is not None:
        utc_naive = dt_ist.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        utc_naive = dt_ist.replace(tzinfo=None) - timedelta(hours=5, minutes=30)
    ed = ephem.Date(utc_naive)
    # Dublin Julian Day + offset → civil Julian Day (UT)
    julian_ut = float(ed) + 2415020.0
    moon = ephem.Moon()
    sun = ephem.Sun()
    moon.compute(ed)
    sun.compute(ed)
    mlon = float(ephem.Ecliptic(moon).lon)
    slon = float(ephem.Ecliptic(sun).lon)
    moon_lon = math.degrees(mlon) % 360.0
    sun_lon = math.degrees(slon) % 360.0
    elong = (moon_lon - sun_lon) % 360.0
    illum_pct = (1.0 - math.cos(math.radians(elong))) / 2.0 * 100.0
    return moon_lon, sun_lon, elong, julian_ut, illum_pct


def western_sign_from_longitude(ecliptic_lon_deg: float) -> str:
    """Tropical zodiac sign from ecliptic longitude (0° = vernal equinox Aries)."""
    idx = int((ecliptic_lon_deg % 360.0) // 30.0)
    return WEST_SIGN_ORDER_EN[idx % 12]


def sidereal_from_tropical(tropical_deg: float, julian_ut: float) -> float:
    return (tropical_deg - lahiri_ayanamsa_deg(julian_ut)) % 360.0


def get_nakshatra(moon_sidereal_longitude_deg: float) -> tuple[int, str, str]:
    """
    Index 0..26, Sanskrit name, English transliteration label (same as SA for UI).
    Each nakṣatra spans 13°20′ (13 + 1/3 degrees).
    """
    span = 360.0 / 27.0
    lon = moon_sidereal_longitude_deg % 360.0
    idx = int(lon // span)
    idx = min(26, max(0, idx))
    return idx, NAKSHATRA_SA[idx], NAKSHATRA_SA[idx]


def get_vedic_sun_sign(sun_sidereal_longitude_deg: float) -> tuple[str, str]:
    """English rāśi name, Sanskrit name from sidereal solar longitude."""
    idx = int((sun_sidereal_longitude_deg % 360.0) // 30.0)
    idx = idx % 12
    return VEDIC_RASHI_EN[idx], VEDIC_RASHI_SA[idx]


def get_paksha(elongation_deg: float) -> tuple[str, str]:
    """English, Sanskrit for bright/dark half."""
    if elongation_deg < 180.0:
        p = "Shukla"
    else:
        p = "Krishna"
    return p, PAKSHA_EN_TO_SA.get(p, p)


def get_tithi_name(elongation_deg: float) -> tuple[int, str, str, str, str]:
    """
    tithi_number 1..15, English name, Sanskrit name, paksha_en, paksha_sa.
    """
    pak_en, pak_sa = get_paksha(elongation_deg)
    if elongation_deg < 180.0:
        n = int(elongation_deg // 12.0) + 1
        n = min(15, max(1, n))
        name_en = TITHI_SHUKLA[n - 1]
    else:
        x = elongation_deg - 180.0
        n = int(x // 12.0) + 1
        n = min(15, max(1, n))
        name_en = TITHI_KRISHNA[n - 1]
    name_sa = TITHI_EN_TO_SA.get(name_en, name_en)
    return n, name_en, name_sa, pak_en, pak_sa


def get_lunar_month_name(english_month: str | None) -> tuple[str, str]:
    """Map DB English Purnimanta month to (en, sa); fallback Passthrough."""
    if not english_month:
        return "—", "—"
    en = english_month.strip()
    sa = LUNAR_MONTH_EN_TO_SA.get(en, en)
    return en, sa


def get_vikram_samvat(d: date) -> int:
    """
    Hindu civil year (prototype rule): VS advances after ~19 March (Chaitra band).
    """
    if (d.month, d.day) >= (3, 19):
        return d.year + 57
    return d.year + 56


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    try:
        r = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
            (name,),
        ).fetchone()
        return r is not None
    except sqlite3.Error as exc:
        _log.warning("calendar: table_exists failed for %s: %s", name, exc)
        return False


def _weekday_en_from_date(d: date) -> str:
    """Monday = 0 in Python ``date.weekday()``."""
    return WEEKDAY_EN[d.weekday()]


def _payload_core(now: datetime, d: date) -> dict[str, Any]:
    return {
        "date_formatted": now.strftime("%d %b %Y"),
        "time_str": now.strftime("%H:%M:%S"),
        "weekday": _weekday_en_from_date(d),
        "solar_month": tropical_sign(d.month, d.day),
        "lunar_month": "—",
        "paksha": "—",
        "tithi_name": "—",
        "tithi_number": 0,
        "moon_phase_pct": None,
        "vikram_samvat": None,
        "calendar_note": None,
    }


def get_advanced_time_payload(conn: sqlite3.Connection | None) -> dict[str, Any]:
    """
    Full bilingual payload for the dashboard time-box (IST instant).
    Lunar month prefers ``daily_lunar_info`` when the calendar date row exists.
    """
    now = now_ist()
    d = now.date()
    ds = d.isoformat()
    note: str | None = None

    if not EPHEM_AVAILABLE:
        vs = get_vikram_samvat(d)
        weekday_en = _weekday_en_from_date(d)
        return {
            "ist_iso": now.isoformat(),
            "date_iso": ds,
            "date_display_upper": now.strftime("%d %b %Y").upper(),
            "time_hms": now.strftime("%H:%M:%S"),
            "weekday_en": weekday_en,
            "weekday_sa": WEEKDAY_SA[d.weekday()],
            "sun_sign_tropical_en": tropical_sign(d.month, d.day),
            "moon_sign_tropical_en": "—",
            "sun_sign_sidereal_en": "—",
            "sun_sign_sidereal_sa": "—",
            "moon_nakshatra_sa": "—",
            "elongation_deg": None,
            "moon_phase_pct": None,
            "lunar_month_en": "—",
            "lunar_month_sa": "—",
            "paksha_en": "—",
            "paksha_sa": "—",
            "tithi_number": 0,
            "tithi_name_en": "—",
            "tithi_name_sa": "—",
            "vikram_samvat": vs,
            "vikram_samvat_sa": f"विक्रम संवत् {vs}",
            "calendar_note": "Install ephem for sidereal longitudes and tithi.",
            "ephem_available": False,
        }

    moon_lon_t, sun_lon_t, elong, jd_ut, illum = moon_sun_ecliptic_deg(now)
    sun_sid = sidereal_from_tropical(sun_lon_t, jd_ut)
    moon_sid = sidereal_from_tropical(moon_lon_t, jd_ut)

    sun_en, sun_sa = get_vedic_sun_sign(sun_sid)
    moon_west = western_sign_from_longitude(moon_lon_t)
    _nk_i, nk_sa, _nk_en = get_nakshatra(moon_sid)
    tithi_n, tithi_en, tithi_sa, pak_en, pak_sa = get_tithi_name(elong)
    vs = get_vikram_samvat(d)

    lunar_en, lunar_sa = "—", "—"
    pak_db_en, pak_db_sa = pak_en, pak_sa
    tithi_db_n, tithi_db_en, tithi_db_sa = tithi_n, tithi_en, tithi_sa

    if conn is not None and _table_exists(conn, "daily_lunar_info"):
        try:
            row = conn.execute(
                """
                SELECT lunar_month, paksha, tithi_number, tithi_name
                FROM daily_lunar_info WHERE date = ?
                """,
                (ds,),
            ).fetchone()
            if row is not None:
                lunar_en, lunar_sa = get_lunar_month_name(str(row["lunar_month"]))
                pak_db_en = str(row["paksha"])
                pak_db_sa = PAKSHA_EN_TO_SA.get(pak_db_en, pak_db_en)
                tithi_db_n = int(row["tithi_number"])
                tithi_db_en = str(row["tithi_name"])
                tithi_db_sa = TITHI_EN_TO_SA.get(tithi_db_en, tithi_db_en)
        except sqlite3.Error as exc:
            note = f"daily_lunar_info read failed: {exc}"
            _log.warning("%s", note)

    weekday_en = _weekday_en_from_date(d)
    # Python weekday Monday=0 → WEEKDAY_SA index (Monday=0)
    weekday_sa = WEEKDAY_SA[d.weekday()]

    date_upper = now.strftime("%d %b %Y").upper()

    return {
        "ist_iso": now.isoformat(),
        "date_iso": ds,
        "date_display_upper": date_upper,
        "time_hms": now.strftime("%H:%M:%S"),
        "weekday_en": weekday_en,
        "weekday_sa": weekday_sa,
        "sun_sign_tropical_en": tropical_sign(d.month, d.day),
        "moon_sign_tropical_en": moon_west,
        "sun_sign_sidereal_en": sun_en,
        "sun_sign_sidereal_sa": sun_sa,
        "moon_nakshatra_sa": nk_sa,
        "elongation_deg": round(elong, 6),
        "moon_phase_pct": round(illum, 3),
        "lunar_month_en": lunar_en,
        "lunar_month_sa": lunar_sa,
        "paksha_en": pak_db_en,
        "paksha_sa": pak_db_sa,
        "tithi_number": tithi_db_n,
        "tithi_name_en": tithi_db_en,
        "tithi_name_sa": tithi_db_sa,
        "vikram_samvat": vs,
        "vikram_samvat_sa": f"विक्रम संवत् {vs}",
        "calendar_note": note,
        "ephem_available": EPHEM_AVAILABLE,
    }


def get_current_time_fallback_payload(
    note: str | None = None,
) -> dict[str, Any]:
    """No database: IST clock + tropical solar only."""
    now = now_ist()
    d = now.date()
    out = _payload_core(now, d)
    out["weekday"] = _weekday_en_from_date(d)
    if note:
        out["calendar_note"] = note
    return out


def get_current_time_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    """
    JSON for GET /api/current_time (IST calendar date for lunar lookup).

    Reads ``daily_lunar_info`` only.
    """
    now = now_ist()
    d = now.date()
    ds = d.isoformat()
    out = _payload_core(now, d)
    out["weekday"] = _weekday_en_from_date(d)

    try:
        if not _table_exists(conn, "daily_lunar_info"):
            out["calendar_note"] = "daily_lunar_info table missing; run init_calendar_2026.py."
            return out

        row = conn.execute(
            """
            SELECT lunar_month, paksha, tithi_number, tithi_name,
                   moon_phase_pct, vikram_samvat, solar_month_name
            FROM daily_lunar_info
            WHERE date = ?
            """,
            (ds,),
        ).fetchone()

        if row is None:
            empty = conn.execute(
                "SELECT COUNT(*) AS n FROM daily_lunar_info"
            ).fetchone()
            total = int(empty["n"]) if empty else 0
            if total == 0:
                out["calendar_note"] = "daily_lunar_info is empty; run init_calendar_2026.py."
            else:
                out["calendar_note"] = f"No lunar row for {ds}."
            return out

        out["lunar_month"] = str(row["lunar_month"])
        out["paksha"] = str(row["paksha"])
        out["tithi_number"] = int(row["tithi_number"])
        out["tithi_name"] = str(row["tithi_name"])
        out["solar_month"] = str(row["solar_month_name"])
        mpc = row["moon_phase_pct"]
        if mpc is not None:
            out["moon_phase_pct"] = float(mpc)
        vsr = row["vikram_samvat"]
        if vsr is not None:
            out["vikram_samvat"] = int(vsr)
        if out.get("calendar_note") is None:
            out["calendar_note"] = None

    except sqlite3.Error as exc:
        _log.warning("calendar: daily_lunar_info query failed: %s", exc)
        out["calendar_note"] = "calendar table unreadable; using solar estimate only."

    return out


def current_time_api_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    """Deprecated shape; prefer get_current_time_payload."""
    p = get_current_time_payload(conn)
    return {
        "current_time": p["time_str"],
        "day_of_week": p["weekday"],
        "solar_month_name": p["solar_month"],
        "lunar_month_name": p["lunar_month"],
        "paksha": p["paksha"],
        "tithi": p["tithi_name"],
        "date_iso": now_ist().date().isoformat(),
    }


def time_info_payload(conn: sqlite3.Connection) -> dict[str, str]:
    p = get_current_time_payload(conn)
    d_iso = now_ist().date().isoformat()
    return {
        "time_hms": p["time_str"],
        "weekday": p["weekday"],
        "moon_cycle": f'{p["lunar_month"]} – {p["paksha"]} – {p["tithi_name"]}',
        "solar_cycle": f'{p["solar_month"]} {d_iso[:4]}',
        "date_iso": d_iso,
    }
