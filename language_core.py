#!/usr/bin/env python3
"""Multi-language support — DB/API stay English; UI and display names are localized."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

from translations import LANGUAGE_META, TRANSLATIONS, get_text

# --- Optional domain-layer naming (experimental; not used in API/DB) -----------------
# upayokta_koda = user private id placeholder for internal experiments only.


STATE_LANGUAGE_DDL = """
CREATE TABLE IF NOT EXISTS state_languages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state_code TEXT NOT NULL UNIQUE,
    state_name TEXT NOT NULL,
    default_language_code TEXT NOT NULL,
    default_language_name TEXT NOT NULL
);
"""

LOCATION_TRANSLATIONS_DDL = """
CREATE TABLE IF NOT EXISTS location_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id TEXT NOT NULL,
    location_type TEXT NOT NULL,
    language_code TEXT NOT NULL,
    translated_name TEXT NOT NULL,
    UNIQUE(location_id, language_code)
);
CREATE INDEX IF NOT EXISTS idx_location_translations_loc
    ON location_translations (location_id, language_code);
"""

# state_code → (state_name_en, default_language_code, default_language_name_en)
INDIAN_STATE_LANGUAGES: list[tuple[str, str, str, str]] = [
    ("AN", "Andaman and Nicobar Islands", "en", "English"),
    ("AP", "Andhra Pradesh", "te", "Telugu"),
    ("AR", "Arunachal Pradesh", "en", "English"),
    ("AS", "Assam", "as", "Assamese"),
    ("BR", "Bihar", "hi", "Hindi"),
    ("CH", "Chandigarh", "hi", "Hindi"),
    ("CT", "Chhattisgarh", "hi", "Hindi"),
    ("DL", "Delhi", "hi", "Hindi"),
    ("GA", "Goa", "kok", "Konkani"),
    ("GJ", "Gujarat", "gu", "Gujarati"),
    ("HP", "Himachal Pradesh", "hi", "Hindi"),
    ("HR", "Haryana", "hi", "Hindi"),
    ("JH", "Jharkhand", "hi", "Hindi"),
    ("JK", "Jammu and Kashmir", "ur", "Urdu"),
    ("KA", "Karnataka", "kn", "Kannada"),
    ("KL", "Kerala", "ml", "Malayalam"),
    ("LA", "Ladakh", "hi", "Hindi"),
    ("LD", "Lakshadweep", "ml", "Malayalam"),
    ("MH", "Maharashtra", "mr", "Marathi"),
    ("ML", "Meghalaya", "en", "English"),
    ("MN", "Manipur", "mni", "Manipuri"),
    ("MP", "Madhya Pradesh", "hi", "Hindi"),
    ("MZ", "Mizoram", "mni", "Manipuri"),
    ("NL", "Nagaland", "en", "English"),
    ("OR", "Odisha", "or", "Odia"),
    ("PB", "Punjab", "pa", "Punjabi"),
    ("PY", "Puducherry", "ta", "Tamil"),
    ("RJ", "Rajasthan", "hi", "Hindi"),
    ("SK", "Sikkim", "en", "English"),
    ("TN", "Tamil Nadu", "ta", "Tamil"),
    ("TS", "Telangana", "te", "Telugu"),
    ("TR", "Tripura", "bn", "Bengali"),
    ("UK", "Uttarakhand", "hi", "Hindi"),
    ("UP", "Uttar Pradesh", "hi", "Hindi"),
    ("WB", "West Bengal", "bn", "Bengali"),
]

# English state name → {lang_code: display name} (seeded when state rows exist)
STATE_NAME_TRANSLATIONS: dict[str, dict[str, str]] = {
    "Andaman and Nicobar Islands": {"en": "Andaman and Nicobar Islands"},
    "Andhra Pradesh": {"te": "ఆంధ్ర ప్రదేశ్", "hi": "आंध्र प्रदेश"},
    "Arunachal Pradesh": {"hi": "अरुणाचल प्रदेश"},
    "Assam": {"as": "অসম", "hi": "असम"},
    "Bihar": {"hi": "बिहार"},
    "Chandigarh": {"hi": "चंडीगढ़"},
    "Chhattisgarh": {"hi": "छत्तीसगढ़"},
    "Delhi": {"hi": "दिल्ली"},
    "Goa": {"hi": "गोआ"},
    "Gujarat": {"gu": "ગુજરાત", "hi": "गुजरात"},
    "Haryana": {"hi": "हरियाणा"},
    "Himachal Pradesh": {"hi": "हिमाचल प्रदेश"},
    "Jammu and Kashmir": {"ur": "جموں و کشمیر", "hi": "जम्मू और कश्मीर"},
    "Jharkhand": {"hi": "झारखंड"},
    "Karnataka": {"kn": "ಕರ್ನಾಟಕ", "hi": "कर्नाटक"},
    "Kerala": {"ml": "കേരളം", "hi": "केरल"},
    "Ladakh": {"hi": "लद्दाख"},
    "Lakshadweep": {"hi": "लक्षद्वीप"},
    "Madhya Pradesh": {"hi": "मध्य प्रदेश"},
    "Maharashtra": {"mr": "महाराष्ट्र", "hi": "महाराष्ट्र"},
    "Manipur": {"hi": "मणिपुर"},
    "Meghalaya": {"hi": "मेघालय"},
    "Mizoram": {"hi": "मिज़ोरम"},
    "Nagaland": {"hi": "नागालैंड"},
    "Odisha": {"or": "ଓଡ଼ିଶା", "hi": "ओडिशा"},
    "Puducherry": {"hi": "पुडुचेरी"},
    "Punjab": {"pa": "ਪੰਜਾਬ", "hi": "पंजाब"},
    "Rajasthan": {"hi": "राजस्थान"},
    "Sikkim": {"hi": "सिक्किम"},
    "Tamil Nadu": {"ta": "தமிழ்நாடு", "hi": "तमिलनाडु"},
    "Telangana": {"te": "తెలంగాణ", "hi": "तेलंगाना"},
    "Tripura": {"hi": "त्रिपुरा"},
    "Uttar Pradesh": {"hi": "उत्तर प्रदेश"},
    "Uttarakhand": {"hi": "उत्तराखंड"},
    "West Bengal": {"bn": "পশ্চিমবঙ্গ", "hi": "पश्चिम बंगाल"},
}

# Exact English geography names → Hindi (pilot + common)
HI_EXACT_LOCATION_NAMES: dict[str, str] = {
    "Delhi": "दिल्ली",
    "North West Delhi": "उत्तर-पश्चिम दिल्ली",
    "North East Delhi": "उत्तर-पूर्व दिल्ली",
    "North Delhi": "उत्तर दिल्ली",
    "South West Delhi": "दक्षिण-पश्चिम दिल्ली",
    "South East Delhi": "दक्षिण-पूर्व दिल्ली",
    "South Delhi": "दक्षिण दिल्ली",
    "East Delhi": "पूर्वी दिल्ली",
    "Central Delhi": "मध्य दिल्ली",
    "New Delhi": "नई दिल्ली",
    "Shahdara": "शाहदरा",
    "Bawana": "बवाना",
    "Rohini": "रोहिणी",
    "Rohini Sector-24": "रोहिणी सेक्टर-24",
    "Rohini Sector-23": "रोहिणी सेक्टर-23",
    "Rohini Sector-25": "रोहिणी सेक्टर-25",
    "Narela": "नरेला",
}

TE_EXACT_LOCATION_NAMES: dict[str, str] = {
    "Telangana": "తెలంగాణ",
    "Hyderabad": "హైదరాబాద్",
    "Warangal": "వరంగల్",
    "Karimnagar": "కరీంనగర్",
    "Nizamabad": "నిజామాబాద్",
    "Khammam": "ఖమ్మం",
    "Nalgonda": "నల్గొండ",
    "Mahbubnagar": "మహబూబ్‌నగర్",
    "Adilabad": "ఆదిలాబాద్",
    "Medak": "మెదక్",
    "Rangareddy": "రంగా రెడ్డి",
    "Ranga Reddy": "రంగా రెడ్డి",
    "Sangareddy": "సంగారెడ్డి",
    "Secunderabad": "సికింద్రాబాద్",
    "Serilingampally": "శేరిలింగంపల్లి",
    "Malkajgiri": "మల్కాజ్గిరి",
    "Uppal": "ఉప్పల్",
    "LB Nagar": "ఎల్‌బి నగర్",
    "Charminar": "చార్మినార్",
    "Golconda": "గోల్కొండ",
    "Banjara Hills": "బంజారా హిల్స్",
    "Jubilee Hills": "జూబిలీ హిల్స్",
}

# Longest-first phrase replacements for Hindi display names
HI_PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("North West", "उत्तर-पश्चिम"),
    ("North East", "उत्तर-पूर्व"),
    ("South West", "दक्षिण-पश्चिम"),
    ("South East", "दक्षिण-पूर्व"),
    ("North", "उत्तर"),
    ("South", "दक्षिण"),
    ("East", "पूर्व"),
    ("West", "पश्चिम"),
    ("Central", "मध्य"),
    ("Rohini Sector-", "रोहिणी सेक्टर-"),
    ("Rohini Sec-", "रोहिणी सेक्टर-"),
    ("Rohini Sec ", "रोहिणी सेक्टर "),
    ("Rohini", "रोहिणी"),
    ("Sector-", "सेक्टर-"),
    ("Sector ", "सेक्टर "),
    ("Colony", "कॉलोनी"),
    ("Village", "गाँव"),
    ("Extension", "विस्तार"),
    ("Extn.", "विस्तार"),
    ("Block-", "ब्लॉक-"),
    ("Nagar", "नगर"),
    ("Mandi", "मंडी"),
    ("Bawana", "बवाना"),
    ("Delhi", "दिल्ली"),
    ("Narela", "नरेला"),
    ("Shahdara", "शाहदरा"),
)

# Longest-first phrase replacements for Telugu display names
TE_PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("North West", "ఉత్తర పశ్చిమ"),
    ("North East", "ఉత్తర తూర్పు"),
    ("South West", "దక్షిణ పశ్చిమ"),
    ("South East", "దక్షిణ తూర్పు"),
    ("North", "ఉత్తర"),
    ("South", "దక్షిణ"),
    ("East", "తూర్పు"),
    ("West", "పశ్చిమ"),
    ("Central", "కేంద్ర"),
    ("Hyderabad", "హైదరాబాద్"),
    ("Warangal", "వరంగల్"),
    ("Nagar", "నగర్"),
    ("Mandi", "మండి"),
    ("Colony", "కాలనీ"),
    ("Village", "గ్రామం"),
    ("Sector-", "సెక్టర్-"),
    ("Sector ", "సెక్టర్ "),
)

GEO_TABLES_FOR_I18N: tuple[str, ...] = ("state", "district", "tehsil", "village")


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def migrate_language_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(STATE_LANGUAGE_DDL + LOCATION_TRANSLATIONS_DDL)
    cols = _table_columns(conn, "users")
    for col_name, decl in (
        ("mother_tongue_code", "TEXT"),
        ("mother_tongue_name", "TEXT"),
    ):
        if col_name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {decl}")
        except sqlite3.OperationalError:
            pass


def seed_state_languages(conn: sqlite3.Connection) -> None:
    for code, name, lang_code, lang_name in INDIAN_STATE_LANGUAGES:
        conn.execute(
            """
            INSERT OR IGNORE INTO state_languages (
                state_code, state_name, default_language_code, default_language_name
            ) VALUES (?, ?, ?, ?)
            """,
            (code, name, lang_code, lang_name),
        )


def seed_state_location_translations(conn: sqlite3.Connection) -> None:
    """Match state rows in geography DB by suffix code (e.g. DL in IND/CS.DL)."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='state'"
    ).fetchone():
        return
    for row in conn.execute("SELECT id, name FROM state"):
        state_id = str(row["id"])
        state_name = str(row["name"])
        state_code = state_code_from_full_id(state_id)
        trans = STATE_NAME_TRANSLATIONS.get(state_name, {})
        if state_code:
            for sl in INDIAN_STATE_LANGUAGES:
                if sl[0] == state_code:
                    trans.setdefault(sl[2], sl[3])
                    break
        for lang_code, translated in trans.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO location_translations (
                    location_id, location_type, language_code, translated_name
                ) VALUES (?, 'state', ?, ?)
                """,
                (state_id, lang_code, translated),
            )


def state_code_from_full_id(state_full_id: str) -> str:
    """Extract short code (e.g. DL) from ``0.x|IND/CS.DL`` style ids."""
    raw = state_full_id.split("|", 1)[-1] if "|" in state_full_id else state_full_id
    if "/" in raw:
        tail = raw.split("/")[-1]
    else:
        tail = raw
    if "." in tail:
        return tail.split(".")[-1].upper()
    return tail.upper()


def state_default_language(conn: sqlite3.Connection, state_code: str) -> dict[str, str] | None:
    if not state_code:
        return None
    row = conn.execute(
        """
        SELECT default_language_code, default_language_name
        FROM state_languages WHERE state_code = ?
        """,
        (state_code.upper(),),
    ).fetchone()
    if not row:
        return None
    return {
        "code": str(row["default_language_code"]),
        "name": str(row["default_language_name"]),
    }


def state_code_from_village_id(
    village_id: str,
    *,
    geo_path_to_state_path: Any,
    raw_path_fn: Any,
) -> str | None:
    """Derive state code (e.g. DL) from a village full id via geography path."""
    cloc = (village_id or "").strip()
    if not cloc:
        return None
    try:
        sraw = geo_path_to_state_path(raw_path_fn(cloc))
        tail = sraw.split("/")[-1] if "/" in sraw else sraw
        if "." in tail:
            return tail.split(".")[-1].upper()
        return tail.upper() if tail else None
    except Exception:
        return None


def state_code_for_user_present(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
    *,
    geo_path_to_state_path: Any,
    raw_path_fn: Any,
) -> str | None:
    try:
        cloc = str(user_row["current_location_id"] or "").strip()
    except (KeyError, IndexError):
        cloc = ""
    return state_code_from_village_id(
        cloc,
        geo_path_to_state_path=geo_path_to_state_path,
        raw_path_fn=raw_path_fn,
    )


def all_language_choices(conn: sqlite3.Connection) -> list[dict[str, str]]:
    """Unique languages from state_languages for registration/profile dropdowns."""
    cur = conn.execute(
        """
        SELECT DISTINCT default_language_code AS code, default_language_name AS name
        FROM state_languages
        ORDER BY default_language_name COLLATE NOCASE
        """
    )
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for r in cur:
        code = str(r["code"]).strip().lower()
        if not code or code in seen:
            continue
        seen.add(code)
        meta = LANGUAGE_META.get(code)
        native = meta[1] if meta else str(r["name"])
        out.append(
            {
                "code": code,
                "name": str(r["name"]),
                "native_label": native,
            }
        )
    if "en" not in seen:
        out.insert(0, {"code": "en", "name": "English", "native_label": "English"})
    return out


def resolve_preferred_language(
    conn: sqlite3.Connection,
    session: dict[str, Any],
    user_row: sqlite3.Row | None,
    *,
    geo_path_to_state_path: Any,
    raw_path_fn: Any,
) -> str:
    """
    Priority: session choice → mother tongue → state default → English.
    """
    chosen = str(session.get("preferred_language") or "").strip().lower()
    if chosen:
        return chosen
    if user_row is not None:
        try:
            mt = str(user_row["mother_tongue_code"] or "").strip().lower()
        except (KeyError, IndexError):
            mt = ""
        if mt:
            return mt
        sc = state_code_for_user_present(
            conn,
            user_row,
            geo_path_to_state_path=geo_path_to_state_path,
            raw_path_fn=raw_path_fn,
        )
        if sc:
            row = state_default_language(conn, sc)
            if row:
                return str(row["code"]).lower()
    return "en"


def ui_language_code(
    conn: sqlite3.Connection | None,
    session: dict[str, Any],
    user_row: sqlite3.Row | None,
    *,
    geo_path_to_state_path: Any | None = None,
    raw_path_fn: Any | None = None,
) -> str:
    """
    Language for UI strings (templates + dashboard.js uiStrings).

    English is the default for everyone — new users, logged-out visitors, and
    anyone who has not set a preference. The UI only switches away from English
    after the user explicitly picks a language from the dropdown
    (``language_user_choice``). Unknown codes fall back to English.
    """
    if session.get("language_user_choice"):
        raw = str(session.get("preferred_language") or "en").strip().lower()
        return raw if raw in TRANSLATIONS else "en"
    return "en"


def ui_language_options() -> list[dict[str, str]]:
    """All languages we have UI translations for, English first (for the dropdown)."""
    codes = ["en"] + [c for c in TRANSLATIONS.keys() if c != "en"]
    return [{"code": c, "label": language_option_label(c)} for c in codes]


def language_option_label(code: str) -> str:
    code = (code or "en").strip().lower()
    meta = LANGUAGE_META.get(code)
    if meta:
        if meta[0] == meta[1] or code == "en":
            return meta[1]
        return f"{meta[1]} ({meta[0]})"
    return code


def build_language_dropdown_options(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row | None,
    *,
    geo_path_to_state_path: Any,
    raw_path_fn: Any,
) -> list[dict[str, str]]:
    """Unique options: state default, mother tongue (if different), English."""
    codes: list[str] = []
    labels: dict[str, str] = {}

    def add(code: str) -> None:
        c = (code or "").strip().lower()
        if not c or c in codes:
            return
        codes.append(c)
        labels[c] = language_option_label(c)

    state_code = None
    if user_row is not None:
        state_code = state_code_for_user_present(
            conn,
            user_row,
            geo_path_to_state_path=geo_path_to_state_path,
            raw_path_fn=raw_path_fn,
        )
        if state_code:
            sd = state_default_language(conn, state_code)
            if sd:
                add(sd["code"])
        try:
            mt = str(user_row["mother_tongue_code"] or "").strip().lower()
        except (KeyError, IndexError):
            mt = ""
        if mt:
            add(mt)
    add("en")
    return [{"code": c, "label": labels[c]} for c in codes]


def _normalize_geo_display_name(name: str) -> str:
    return " ".join((name or "").split())


def heuristic_translate_location_name(name: str, language_code: str) -> str:
    """Common-sense localized labels when no DB row exists (API/DB names stay English)."""
    lang = (language_code or "en").strip().lower()
    if lang == "en":
        return name
    clean = _normalize_geo_display_name(name)
    if not clean:
        return name
    if lang == "hi":
        if clean in HI_EXACT_LOCATION_NAMES:
            return HI_EXACT_LOCATION_NAMES[clean]
        out = clean
        for eng, localized in HI_PHRASE_REPLACEMENTS:
            out = out.replace(eng, localized)
        return out if out != clean else name
    if lang == "te":
        if clean in TE_EXACT_LOCATION_NAMES:
            return TE_EXACT_LOCATION_NAMES[clean]
        out = clean
        for eng, localized in TE_PHRASE_REPLACEMENTS:
            out = out.replace(eng, localized)
        return out if out != clean else name
    return name


def fetch_location_translations_batch(
    conn: sqlite3.Connection,
    location_ids: list[str],
    location_type: str,
    language_code: str,
) -> dict[str, str]:
    """Return ``location_id → translated_name`` for rows present in the DB."""
    lang = (language_code or "en").strip().lower()
    loc_type = (location_type or "").strip().lower()
    ids = [i.strip() for i in location_ids if (i or "").strip()]
    if lang == "en" or not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    cur = conn.execute(
        f"""
        SELECT location_id, translated_name FROM location_translations
        WHERE location_type = ? AND language_code = ?
          AND location_id IN ({placeholders})
        """,
        [loc_type, lang, *ids],
    )
    return {str(r[0]): str(r[1]) for r in cur.fetchall()}


def localize_geo_rows(
    conn: sqlite3.Connection,
    rows: list[dict[str, str]],
    location_type: str,
    language_code: str,
) -> list[dict[str, str]]:
    """
    Apply translated display names to geography API rows.
    Falls back to English original_name when no translation exists.
    """
    lang = (language_code or "en").strip().lower()
    if lang == "en" or not rows:
        return [{"id": str(r["id"]), "name": str(r["name"])} for r in rows]
    loc_type = (location_type or "").strip().lower()
    ids = [str(r["id"]).strip() for r in rows]
    trans_map = fetch_location_translations_batch(conn, ids, loc_type, lang)
    out: list[dict[str, str]] = []
    for row in rows:
        loc_id = str(row["id"]).strip()
        original = _normalize_geo_display_name(str(row.get("name") or ""))
        translated = trans_map.get(loc_id)
        if translated:
            display = translated
        else:
            display = heuristic_translate_location_name(original, lang)
        out.append({"id": loc_id, "name": display or original})
    return out


def import_location_translations_from_csv(
    conn: sqlite3.Connection,
    csv_path: str | Path,
) -> int:
    """
    Batch upsert translations from CSV columns:
    location_id, location_type, language_code, translated_name
    """
    path = Path(csv_path)
    if not path.is_file():
        return 0
    count = 0
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            loc_id = (row.get("location_id") or "").strip()
            loc_type = (row.get("location_type") or "").strip().lower()
            lang = (row.get("language_code") or "").strip().lower()
            translated = (row.get("translated_name") or "").strip()
            if not loc_id or not loc_type or not lang or not translated:
                continue
            _upsert_location_translation(conn, loc_id, loc_type, lang, translated)
            count += 1
    return count


# Prototype samples: English name → {lang_code: translated} per geography level
SAMPLE_LOCATION_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "state": {
        "Telangana": {"te": "తెలంగాణ", "hi": "तेलंगाना"},
        "Tamil Nadu": {"ta": "தமிழ்நாடு", "hi": "तमिलनाडु"},
        "Karnataka": {"kn": "ಕರ್ನಾಟಕ", "hi": "कर्नाटक"},
        "Maharashtra": {"mr": "महाराष्ट्र", "hi": "महाराष्ट्र"},
        "Gujarat": {"gu": "ગુજરાત", "hi": "गुजरात"},
        "West Bengal": {"bn": "পশ্চিমবঙ্গ", "hi": "पश्चिम बंगाल"},
        "Odisha": {"or": "ଓଡ଼ିଶା", "hi": "ओडिशा"},
        "Kerala": {"ml": "കേരളം", "hi": "केरल"},
        "Andhra Pradesh": {"te": "ఆంధ్ర ప్రదేశ్", "hi": "आंध्र प्रदेश"},
        "Bihar": {"hi": "बिहार"},
        "Rajasthan": {"hi": "राजस्थान"},
    },
    "district": {
        "Hyderabad": {"te": "హైదరాబాద్", "hi": "हैदराबाद"},
        "Warangal": {"te": "వరంగల్", "hi": "वारंगल"},
        "Karimnagar": {"te": "కరీంనగర్", "hi": "करीमनगर"},
        "Nizamabad": {"te": "నిజామాబాద్", "hi": "निजामाबाद"},
        "Ranga Reddy": {"te": "రంగా రెడ్డి", "hi": "रंगा रेड्डी"},
        "Rangareddy": {"te": "రంగా రెడ్డి", "hi": "रंगा रेड्डी"},
        "Chennai": {"ta": "சென்னை", "hi": "चेन्नई"},
        "Bengaluru Urban": {"kn": "ಬೆಂಗಳೂರು ನಗರ", "hi": "बेंगलुरु"},
        "Mumbai": {"mr": "मुंबई", "hi": "मुंबई"},
        "Ahmedabad": {"gu": "અમદાવાદ", "hi": "अहमदाबाद"},
        "Kolkata": {"bn": "কলকাতা", "hi": "कोलकाता"},
    },
    "tehsil": {
        "Serilingampally": {"te": "శేరిలింగంపల్లి"},
        "Malkajgiri": {"te": "మల్కాజ్గిరి"},
        "Uppal": {"te": "ఉప్పల్"},
        "LB Nagar": {"te": "ఎల్‌బి నగర్"},
        "Charminar": {"te": "చార్మినార్"},
    },
    "village": {
        "Gachibowli": {"te": "గచ్చిబౌలి"},
        "Madhapur": {"te": "మాధాపూర్"},
        "Hitech City": {"te": "హైటెక్ సిటీ"},
        "Banjara Hills": {"te": "బంజారా హిల్స్"},
        "Jubilee Hills": {"te": "జూబిలీ హిల్స్"},
    },
}


def seed_sample_location_translations(conn: sqlite3.Connection) -> dict[str, int]:
    """
    Match geography rows by English ``name`` and insert prototype translations.
    Safe to re-run (upsert).
    """
    counts: dict[str, int] = {t: 0 for t in GEO_TABLES_FOR_I18N}
    for table in GEO_TABLES_FOR_I18N:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone():
            continue
        name_map = SAMPLE_LOCATION_TRANSLATIONS.get(table, {})
        if not name_map:
            continue
        for row in conn.execute(f"SELECT id, name FROM {table}"):
            ename = _normalize_geo_display_name(str(row["name"]))
            trans = name_map.get(ename)
            if not trans:
                continue
            loc_id = str(row["id"]).strip()
            for lang_code, translated in trans.items():
                _upsert_location_translation(
                    conn, loc_id, table, lang_code, translated
                )
                counts[table] += 1
    return counts


# Pilot phase: each focus state translated into its primary language.
PILOT_STATE_TRANSLATIONS: dict[str, dict[str, str]] = {
    "Delhi": {"hi": "दिल्ली"},
    "Uttar Pradesh": {"hi": "उत्तर प्रदेश"},
    "Maharashtra": {"mr": "महाराष्ट्र"},
    "Tamil Nadu": {"ta": "தமிழ்நாடு"},
    "Karnataka": {"kn": "ಕರ್ನಾಟಕ"},
    "Telangana": {"te": "తెలంగాణ"},
    "Kerala": {"ml": "കേരളം"},
    "Gujarat": {"gu": "ગુજરાત"},
    "West Bengal": {"bn": "পশ্চিমবঙ্গ"},
    "Punjab": {"pa": "ਪੰਜਾਬ"},
}


def seed_pilot_location_translations(conn: sqlite3.Connection) -> int:
    """Guarantee pilot-state names exist in their primary language. Safe to re-run."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='state'"
    ).fetchone():
        return 0
    count = 0
    for row in conn.execute("SELECT id, name FROM state"):
        ename = _normalize_geo_display_name(str(row["name"]))
        trans = PILOT_STATE_TRANSLATIONS.get(ename)
        if not trans:
            continue
        loc_id = str(row["id"]).strip()
        for lang_code, translated in trans.items():
            _upsert_location_translation(conn, loc_id, "state", lang_code, translated)
            count += 1
    return count


def get_location_display_name(
    conn: sqlite3.Connection,
    location_id: str,
    location_type: str,
    language_code: str,
    *,
    original_name: str,
) -> str:
    lang = (language_code or "en").strip().lower()
    original = _normalize_geo_display_name(original_name)
    if lang == "en" or not location_id:
        return original
    row = conn.execute(
        """
        SELECT translated_name FROM location_translations
        WHERE location_id = ? AND location_type = ? AND language_code = ?
        """,
        (location_id.strip(), location_type.strip().lower(), lang),
    ).fetchone()
    if row:
        return str(row["translated_name"])
    return heuristic_translate_location_name(original, lang)


def apply_hierarchy_translations(
    conn: sqlite3.Connection,
    hierarchy: list[dict[str, str]],
    language_code: str,
) -> list[dict[str, str]]:
    lang = (language_code or "en").strip().lower()
    if lang == "en":
        return hierarchy
    out: list[dict[str, str]] = []
    for item in hierarchy:
        copy = dict(item)
        scope = str(copy.get("scope") or "").lower()
        fid = str(copy.get("id") or "").strip()
        if scope in GEO_TABLES_FOR_I18N and fid:
            copy["name"] = get_location_display_name(
                conn,
                fid,
                scope,
                lang,
                original_name=str(copy.get("name") or ""),
            )
        out.append(copy)
    return out


def _upsert_location_translation(
    conn: sqlite3.Connection,
    location_id: str,
    location_type: str,
    language_code: str,
    translated_name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO location_translations (
            location_id, location_type, language_code, translated_name
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(location_id, language_code) DO UPDATE SET
            location_type = excluded.location_type,
            translated_name = excluded.translated_name
        """,
        (location_id, location_type, language_code, translated_name),
    )


def seed_hindi_geography_translations(conn: sqlite3.Connection) -> None:
    """Populate Hindi names for all state/district/tehsil/village rows (heuristic + overrides)."""
    for table in GEO_TABLES_FOR_I18N:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone():
            continue
        for row in conn.execute(f"SELECT id, name FROM {table}"):
            loc_id = str(row["id"]).strip()
            ename = _normalize_geo_display_name(str(row["name"]))
            if not loc_id or not ename:
                continue
            hi_name = heuristic_translate_location_name(ename, "hi")
            if hi_name and hi_name != ename:
                _upsert_location_translation(conn, loc_id, table, "hi", hi_name)


def seed_telugu_geography_translations(conn: sqlite3.Connection) -> None:
    """Populate Telugu names using heuristics + exact overrides (prototype)."""
    for table in GEO_TABLES_FOR_I18N:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone():
            continue
        for row in conn.execute(f"SELECT id, name FROM {table}"):
            loc_id = str(row["id"]).strip()
            ename = _normalize_geo_display_name(str(row["name"]))
            if not loc_id or not ename:
                continue
            te_name = heuristic_translate_location_name(ename, "te")
            if te_name and te_name != ename:
                _upsert_location_translation(conn, loc_id, table, "te", te_name)


def migrate_and_seed(conn: sqlite3.Connection) -> None:
    migrate_language_tables(conn)
    seed_state_languages(conn)
    seed_state_location_translations(conn)
    seed_pilot_location_translations(conn)
    seed_hindi_geography_translations(conn)
    seed_telugu_geography_translations(conn)
    seed_sample_location_translations(conn)
    # Corrective: older seeds stored Delhi's Hindi name as the longer
    # "Union Territory" label. Normalize any such rows to just "दिल्ली".
    conn.execute(
        """
        UPDATE location_translations
        SET translated_name = 'दिल्ली'
        WHERE language_code = 'hi'
          AND translated_name = 'दिल्ली केंद्र शासित राज्य'
        """
    )
