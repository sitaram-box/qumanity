"""
Zodiac-planet mappings and country-specific mother-tongue languages.
"""

from __future__ import annotations

import sqlite3
from typing import Any

import global_core

ELEMENT_DDL = """
CREATE TABLE IF NOT EXISTS zodiac_planets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    zodiac_sign TEXT NOT NULL,
    planet_name TEXT NOT NULL,
    planet_sanskrit TEXT NOT NULL,
    planet_symbol TEXT NOT NULL,
    is_ruling_planet INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_zodiac_planets_sign ON zodiac_planets(zodiac_sign);

CREATE TABLE IF NOT EXISTS country_languages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_id TEXT NOT NULL,
    language_code TEXT NOT NULL,
    language_name TEXT NOT NULL,
    language_name_local TEXT,
    is_primary INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(country_id, language_code)
);
CREATE INDEX IF NOT EXISTS idx_country_languages_country ON country_languages(country_id);
"""

ZODIAC_SANSKRIT: dict[str, str] = {
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

ZODIAC_PLANETS_SEED: tuple[tuple[str, str, str, str, int], ...] = (
    ("Aries", "Mars", "Mangala", "♂", 1),
    ("Aries", "Sun", "Surya", "☉", 0),
    ("Taurus", "Venus", "Shukra", "♀", 1),
    ("Gemini", "Mercury", "Budha", "☿", 1),
    ("Cancer", "Moon", "Chandra", "☽", 1),
    ("Leo", "Sun", "Surya", "☉", 1),
    ("Virgo", "Mercury", "Budha", "☿", 1),
    ("Libra", "Venus", "Shukra", "♀", 1),
    ("Scorpio", "Mars", "Mangala", "♂", 1),
    ("Scorpio", "Pluto", "Yama", "♇", 0),
    ("Sagittarius", "Jupiter", "Guru", "♃", 1),
    ("Capricorn", "Saturn", "Shani", "♄", 1),
    ("Aquarius", "Saturn", "Shani", "♄", 1),
    ("Aquarius", "Uranus", "Indra", "⛢", 0),
    ("Pisces", "Jupiter", "Guru", "♃", 1),
    ("Pisces", "Neptune", "Varuna", "♆", 0),
)

# ISO alpha-3 country ids (matching ``country`` table).
COUNTRY_LANGUAGES_SEED: tuple[tuple[str, str, str, str | None, int], ...] = (
    ("IND", "hi", "Hindi", "हिन्दी", 1),
    ("IND", "en", "English", "English", 0),
    ("IND", "bn", "Bengali", "বাংলা", 0),
    ("IND", "te", "Telugu", "తెలుగు", 0),
    ("IND", "mr", "Marathi", "मराठी", 0),
    ("IND", "ta", "Tamil", "தமிழ்", 0),
    ("IND", "ur", "Urdu", "اردو", 0),
    ("IND", "gu", "Gujarati", "ગુજરાતી", 0),
    ("IND", "kn", "Kannada", "ಕನ್ನಡ", 0),
    ("IND", "ml", "Malayalam", "മലയാളം", 0),
    ("IND", "or", "Odia", "ଓଡ଼ିଆ", 0),
    ("IND", "pa", "Punjabi", "ਪੰਜਾਬੀ", 0),
    ("IND", "as", "Assamese", "অসমীয়া", 0),
    ("FRA", "fr", "French", "Français", 1),
    ("FRA", "en", "English", "English", 0),
    ("DEU", "de", "German", "Deutsch", 1),
    ("DEU", "en", "English", "English", 0),
    ("ITA", "it", "Italian", "Italiano", 1),
    ("ITA", "en", "English", "English", 0),
    ("ESP", "es", "Spanish", "Español", 1),
    ("ESP", "en", "English", "English", 0),
    ("GBR", "en", "English", "English", 1),
    ("JPN", "ja", "Japanese", "日本語", 1),
    ("JPN", "en", "English", "English", 0),
    ("CHN", "zh", "Chinese", "中文", 1),
    ("CHN", "en", "English", "English", 0),
    ("KOR", "ko", "Korean", "한국어", 1),
    ("KOR", "en", "English", "English", 0),
    ("RUS", "ru", "Russian", "Русский", 1),
    ("RUS", "en", "English", "English", 0),
    ("BRA", "pt", "Portuguese", "Português", 1),
    ("BRA", "en", "English", "English", 0),
    ("ARG", "es", "Spanish", "Español", 1),
    ("ARG", "en", "English", "English", 0),
    ("MEX", "es", "Spanish", "Español", 1),
    ("MEX", "en", "English", "English", 0),
    ("CAN", "en", "English", "English", 1),
    ("CAN", "fr", "French", "Français", 0),
    ("USA", "en", "English", "English", 1),
    ("USA", "es", "Spanish", "Español", 0),
    ("AUS", "en", "English", "English", 1),
    ("ARE", "ar", "Arabic", "العربية", 1),
    ("ARE", "en", "English", "English", 0),
    ("SAU", "ar", "Arabic", "العربية", 1),
    ("SAU", "en", "English", "English", 0),
    ("IDN", "id", "Indonesian", "Bahasa Indonesia", 1),
    ("IDN", "en", "English", "English", 0),
    ("NZL", "en", "English", "English", 1),
    ("ZAF", "en", "English", "English", 1),
    ("ZAF", "af", "Afrikaans", "Afrikaans", 0),
    ("NGA", "en", "English", "English", 1),
    ("PER", "es", "Spanish", "Español", 1),
    ("PER", "en", "English", "English", 0),
)


def migrate_element_core_schema(conn: sqlite3.Connection) -> None:
    """Create zodiac_planets / country_languages and seed when empty."""
    conn.executescript(ELEMENT_DDL)
    seed_zodiac_planets(conn)
    seed_country_languages(conn)


def seed_zodiac_planets(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS c FROM zodiac_planets").fetchone()
    if row and int(row["c"] if isinstance(row, sqlite3.Row) else row[0]) > 0:
        return
    conn.executemany(
        """
        INSERT INTO zodiac_planets (
            zodiac_sign, planet_name, planet_sanskrit, planet_symbol, is_ruling_planet
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ZODIAC_PLANETS_SEED,
    )


def seed_country_languages(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS c FROM country_languages").fetchone()
    if row and int(row["c"] if isinstance(row, sqlite3.Row) else row[0]) > 0:
        return
    conn.executemany(
        """
        INSERT OR IGNORE INTO country_languages (
            country_id, language_code, language_name, language_name_local, is_primary
        ) VALUES (?, ?, ?, ?, ?)
        """,
        COUNTRY_LANGUAGES_SEED,
    )


def get_planets_for_sign(conn: sqlite3.Connection, sign: str) -> list[dict[str, str]]:
    cur = conn.execute(
        """
        SELECT planet_name, planet_sanskrit, planet_symbol
        FROM zodiac_planets
        WHERE zodiac_sign = ?
        ORDER BY is_ruling_planet DESC, id ASC
        """,
        (sign,),
    )
    return [
        {
            "name": str(r["planet_name"]),
            "sanskrit": str(r["planet_sanskrit"]),
            "symbol": str(r["planet_symbol"]),
        }
        for r in cur.fetchall()
    ]


def get_element_popup_data(
    conn: sqlite3.Connection,
    *,
    element: str,
    location_id: str | None = None,
    location_type: str | None = None,
    tab: str = "private",
) -> dict[str, Any]:
    """Popup payload: total members, per-sign counts, and planets per sign."""
    el = str(element or "Fire").strip().title()
    signs = global_core.ELEMENT_SIGNS.get(el, global_core.ELEMENT_SIGNS["Fire"])
    scope_sql, scope_params = global_core._user_scope_sql(location_id, location_type, tab=tab)

    deceased_clause = ""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "is_deceased" in cols:
        deceased_clause = " AND COALESCE(u.is_deceased, 0) = 0"

    result: dict[str, Any] = {"element": el, "total": 0, "signs": []}
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
        result["signs"].append(
            {
                "name_en": sign,
                "name_sa": ZODIAC_SANSKRIT.get(sign, sign),
                "count": count,
                "planets": get_planets_for_sign(conn, sign),
            }
        )
        result["total"] += count
    return result


def get_country_languages(conn: sqlite3.Connection, country_id: str) -> list[dict[str, Any]]:
    cid = str(country_id or "").strip().upper()
    cur = conn.execute(
        """
        SELECT language_code, language_name, language_name_local, is_primary
        FROM country_languages
        WHERE country_id = ?
        ORDER BY is_primary DESC, language_name COLLATE NOCASE ASC
        """,
        (cid,),
    )
    rows = cur.fetchall()
    if not rows:
        return [
            {
                "code": "en",
                "name": "English",
                "name_local": "English",
                "is_primary": 1,
            }
        ]
    return [
        {
            "code": str(r["language_code"]),
            "name": str(r["language_name"]),
            "name_local": str(r["language_name_local"] or r["language_name"]),
            "is_primary": int(r["is_primary"] or 0),
        }
        for r in rows
    ]


def mother_tongue_allowed(
    conn: sqlite3.Connection,
    country_id: str,
    language_code: str,
) -> tuple[bool, str | None]:
    """Return (ok, display_name) for a mother-tongue code under a birth country."""
    cid = str(country_id or "").strip().upper()
    code = str(language_code or "").strip().lower()
    if not code:
        return True, None
    row = conn.execute(
        """
        SELECT language_name FROM country_languages
        WHERE country_id = ? AND language_code = ?
        """,
        (cid, code),
    ).fetchone()
    if row:
        return True, str(row["language_name"])
    if code == "en":
        return True, "English"
    return False, None
