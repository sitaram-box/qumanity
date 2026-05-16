"""
Quantum Box — Flask prototype.
Geography reads from indiaq.db; app users live in the same database `users` table.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import string
import time
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any

import bcrypt

import calendar_time
import election_scheduler
import social_core
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "indiaq.db"

PATH_PREFIX = "0.राम|"
_GEO_CHILD_TABLES = frozenset({"district", "tehsil", "village"})

ZODIAC_SIGNS_ORDER = (
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

GENDER_OPTIONS = (
    "Male",
    "Female",
    "Male born female",
    "Female born male",
)

ELEMENT_BY_SIGN = {
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

SIGNS_BY_ELEMENT: dict[str, tuple[str, str, str]] = {
    "Fire": ("Aries", "Leo", "Sagittarius"),
    "Earth": ("Taurus", "Virgo", "Capricorn"),
    "Air": ("Gemini", "Libra", "Aquarius"),
    "Water": ("Cancer", "Scorpio", "Pisces"),
}

# Legacy registration IDs (U-XXXXXXXX); login accepts any stored private_id shape.
PRIVATE_ID_RE = re.compile(r"^\s*(U-[A-Za-z0-9]{8})\s*$", re.I)
PRIVATE_ID_LOGIN_RE = re.compile(r"^[\w./|\-]{3,190}$")

USER_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    private_id TEXT UNIQUE NOT NULL,
    public_id TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    gender TEXT NOT NULL CHECK(
        gender IN ('Male', 'Female', 'Male born female', 'Female born male')
    ),
    date_of_birth TEXT NOT NULL,
    birth_time TEXT NOT NULL,
    age INTEGER NOT NULL,
    age_group TEXT NOT NULL,
    sun_sign TEXT NOT NULL,
    moon_sign TEXT NOT NULL,
    element TEXT NOT NULL,
    birth_location_id TEXT,
    current_location_id TEXT,
    birth_continent_id TEXT,
    birth_country_id TEXT,
    current_continent_id TEXT,
    current_country_id TEXT,
    country TEXT NOT NULL DEFAULT 'India',
    email TEXT,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    account_type TEXT NOT NULL DEFAULT 'H_U',
    mentor_level INTEGER NOT NULL DEFAULT 0,
    manager_level INTEGER NOT NULL DEFAULT 0,
    leader_level INTEGER NOT NULL DEFAULT 0,
    agent_level INTEGER NOT NULL DEFAULT 0,
    is_admin INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_users_current_loc ON users(current_location_id);
CREATE INDEX IF NOT EXISTS idx_users_birth_loc ON users(birth_location_id);
CREATE INDEX IF NOT EXISTS idx_users_private_id ON users(private_id);
CREATE INDEX IF NOT EXISTS idx_users_public_id ON users(public_id);
CREATE INDEX IF NOT EXISTS idx_users_sun_sign ON users(sun_sign);
CREATE INDEX IF NOT EXISTS idx_users_element ON users(element);
CREATE INDEX IF NOT EXISTS idx_users_gender ON users(gender);
CREATE INDEX IF NOT EXISTS idx_users_age_group ON users(age_group);
CREATE INDEX IF NOT EXISTS idx_users_current_country ON users(current_country_id);
CREATE INDEX IF NOT EXISTS idx_users_current_continent ON users(current_continent_id);
"""

POST_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    location_id TEXT,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    current_level TEXT NOT NULL DEFAULT 'personal',
    level_start_time TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'live',
    total_score INTEGER NOT NULL DEFAULT 0,
    previous_levels TEXT,
    origin_village_id TEXT,
    origin_tehsil_id TEXT,
    origin_district_id TEXT,
    origin_state_id TEXT,
    origin_country_id TEXT,
    origin_continent_id TEXT,
    freeze_level TEXT,
    qoins_settled INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_posts_user_private_id ON posts(user_private_id);
CREATE INDEX IF NOT EXISTS idx_posts_location_id ON posts(location_id);
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at);
CREATE INDEX IF NOT EXISTS idx_posts_level_status ON posts(current_level, status);
CREATE INDEX IF NOT EXISTS idx_posts_status_location ON posts(status, location_id);
CREATE INDEX IF NOT EXISTS idx_posts_level_start_time ON posts(level_start_time);
CREATE INDEX IF NOT EXISTS idx_posts_freeze_level ON posts(freeze_level);
CREATE INDEX IF NOT EXISTS idx_posts_origin_village ON posts(origin_village_id);
"""

CONNECTION_REQUESTS_SQL = """
CREATE TABLE IF NOT EXISTS connection_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_private_id TEXT NOT NULL,
    to_user_private_id TEXT NOT NULL,
    request_type TEXT NOT NULL,
    relationship TEXT,
    is_dead INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(from_user_private_id, to_user_private_id, request_type)
);
CREATE INDEX IF NOT EXISTS idx_connection_requests_to ON connection_requests(to_user_private_id, status);
CREATE INDEX IF NOT EXISTS idx_connection_requests_from ON connection_requests(from_user_private_id, status);
"""

# --- Family profile / members (Personal Account → Family tab) ---
FAMILY_PROFILE_SQL = """
CREATE TABLE IF NOT EXISTS family_profile (
    user_private_id TEXT PRIMARY KEY,
    form_data TEXT,
    form_completed INTEGER NOT NULL DEFAULT 0,
    relationship_status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
"""

FAMILY_MEMBERS_SQL = """
CREATE TABLE IF NOT EXISTS family_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    member_name TEXT NOT NULL,
    relationship TEXT NOT NULL,
    gender TEXT,
    age INTEGER,
    age_modifier TEXT,
    is_close_family INTEGER NOT NULL DEFAULT 0,
    is_dead INTEGER NOT NULL DEFAULT 0,
    is_placeholder INTEGER NOT NULL DEFAULT 0,
    member_type TEXT NOT NULL DEFAULT 'nuclear',
    account_public_id TEXT,
    source TEXT NOT NULL DEFAULT 'form',
    parent_link TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_family_members_user ON family_members(user_private_id);
CREATE INDEX IF NOT EXISTS idx_family_members_user_close ON family_members(user_private_id, is_close_family);
"""

# Graph edges: ``source_id`` / ``target_id`` reference ``family_members.id`` (and the
# account-holder row with ``source = 'self'``). ``relation_type`` is one of
# parent | child | spouse | sibling (stored lowercase).
FAMILY_RELATIONSHIPS_SQL = """
CREATE TABLE IF NOT EXISTS family_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    target_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_family_rel_src ON family_relationships(source_id);
CREATE INDEX IF NOT EXISTS idx_family_rel_tgt ON family_relationships(target_id);
CREATE INDEX IF NOT EXISTS idx_family_rel_pair ON family_relationships(
    source_id, target_id, relation_type
);
"""

# Legacy sentinel kept for a few API checks; the tree uses the real ``self`` row id.
VIEWER_GRAPH_MEMBER_ID = -1

# Relationships that belong to the "close family" tree (lowercase, canonical).
CLOSE_FAMILY_RELATIONSHIPS = frozenset(
    {
        "father",
        "mother",
        "spouse",
        "husband",
        "wife",
        "son",
        "daughter",
        "child",
        "children",
        "brother",
        "sister",
        "sibling",
        "real brother/sister",
        "paternal grandfather",
        "paternal grandmother",
        "maternal grandfather",
        "maternal grandmother",
        "grandfather",
        "grandmother",
        "grandparent",
        # Form-collected extended close family (married / single-parent users):
        "son-in-law",
        "daughter-in-law",
        "child's spouse",
        "grandson",
        "granddaughter",
        "grandchild",
        "grandchildren",
        "father-in-law",
        "mother-in-law",
        "spouse's father",
        "spouse's mother",
        # UI menu spellings / hyphen variants (normalised via _normalize_relationship_menu)
        "self",
    }
)


def _normalize_relationship(rel: str | None) -> str:
    return (rel or "").strip().lower()


def _normalize_relationship_menu(rel: str | None) -> str:
    """Map nested-menu labels (incl. Spouse-Father) to canonical lowercase tokens."""
    if not rel:
        return ""
    key = (
        (rel or "")
        .strip()
        .lower()
        .replace("\u2011", "-")
        .replace(" ", "")
        .replace("_", "")
    )
    aliases: dict[str, str] = {
        "paternalgrandfather": "paternal grandfather",
        "paternalgrandmother": "paternal grandmother",
        "maternalgrandfather": "maternal grandfather",
        "maternalgrandmother": "maternal grandmother",
        "grandfather(paternal)": "paternal grandfather",
        "grandfather(maternal)": "maternal grandfather",
        "grandmother(paternal)": "paternal grandmother",
        "grandmother(maternal)": "maternal grandmother",
        "spousefather": "father-in-law",
        "spousemother": "mother-in-law",
    }
    if key in aliases:
        return aliases[key]
    return _normalize_relationship(rel)


_LINEAGE_REFERENCE_RELS = frozenset(
    {"son", "daughter", "child", "children", "grandson", "granddaughter", "grandchild", "grandchildren"}
)


def _relationship_title_from_menu(rel: str | None) -> str:
    """Trimmed menu label for ``family_members.relationship`` / requests."""
    return (rel or "").strip()


def _is_close_family_relationship(rel: str | None) -> bool:
    return _normalize_relationship_menu(rel) in CLOSE_FAMILY_RELATIONSHIPS

# Life stages (age bands) for stats, registration, and cohort charts.
LIFE_STAGE_ORDER = ("Balak", "Yuvak", "Vridh", "Sanyas")

# Legacy DB labels (pre–life-stage migration) for display account codes only.
LEGACY_NUMERIC_AGE_GROUP_ORDER = (
    "1-9",
    "10-19",
    "20-29",
    "30-39",
    "40-49",
    "50-59",
    "60-69",
    "70-79",
    "80-89",
    "90-100+",
)

MESSAGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE NOT NULL,
    sender_id TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',
    parent_message_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP,
    is_draft INTEGER NOT NULL DEFAULT 0,
    is_deleted_by_sender INTEGER NOT NULL DEFAULT 0,
    is_deleted_by_recipient INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id, is_draft, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id, is_draft, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(message_id);
"""

SUN_ELEMENT_ORDER = ("Fire", "Earth", "Air", "Water")

SUN_SIGN_TWO_LETTER: dict[str, str] = {
    "Aries": "Ar",
    "Taurus": "Ta",
    "Gemini": "Ge",
    "Cancer": "Ca",
    "Leo": "Le",
    "Virgo": "Vi",
    "Libra": "Li",
    "Scorpio": "Sc",
    "Sagittarius": "Sa",
    "Capricorn": "Cp",
    "Aquarius": "Aq",
    "Pisces": "Pi",
}

ELEMENT_ACCOUNT_CODE = {
    "Fire": "FI",
    "Earth": "EA",
    "Air": "AI",
    "Water": "WA",
}

# Corner layout: TL=Fire, TR=Earth, BR=Air, BL=Water
ELEMENT_CORNER_POSITION = {"Fire": "tl", "Earth": "tr", "Air": "br", "Water": "bl"}

GEO_ROUTE_TABLE: dict[str, str] = {
    "earth": "earth",
    "continent": "continent",
    "country": "country",
    "zone": "zone",
    "state": "state",
    "district": "district",
    "tehsil": "tehsil",
    "village": "village",
}

GEO_ROUTE_ORDER = (
    "earth",
    "continent",
    "country",
    "zone",
    "state",
    "district",
    "tehsil",
    "village",
)

# Search hits: prefer higher-level units so “Delhi” surfaces the state before villages.
GEO_SEARCH_KIND_ORDER = ("state", "district", "tehsil", "village", "zone")


def _geo_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def build_geo_public_url(kind: str, gid: str) -> str:
    gid = gid.strip()
    if kind == "earth":
        return url_for("location_earth", earth_id=gid)
    if kind == "continent":
        return url_for("location_continent", continent_id=gid)
    if kind == "country":
        return url_for("location_country", country_id=gid)
    if kind == "zone":
        return url_for("location_zone", zone_id=gid)
    if kind == "state":
        return url_for("location_state", state_id=gid)
    if kind == "district":
        return url_for("location_district", district_id=gid)
    if kind == "tehsil":
        return url_for("location_tehsil", tehsil_id=gid)
    if kind == "village":
        return url_for("location_village", village_id=gid)
    abort(404)

app = Flask(__name__)
# Session signing: set SECRET_KEY or QUANTUM_BOX_SECRET in production.
app.config["SECRET_KEY"] = (
    os.environ.get("SECRET_KEY")
    or os.environ.get("QUANTUM_BOX_SECRET")
    or "dev"
)
app.secret_key = app.config["SECRET_KEY"]

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)
_last_escalation_check = 0.0


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc: BaseException | None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def ensure_users_table(conn: sqlite3.Connection) -> None:
    conn.executescript(USER_TABLE_SQL)
    conn.executescript(POST_TABLE_SQL)
    conn.commit()


def geography_has_relational_fks(conn: sqlite3.Connection) -> bool:
    """Use JOIN-based queries when FK columns exist; else resolve via ID paths."""

    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(village)")}
    return "tehsil_id" in cols


def raw_path(full_id: str) -> str:
    fid = (full_id or "").strip()
    if fid.startswith(PATH_PREFIX):
        return fid[len(PATH_PREFIX) :]
    return fid


def full_id_from_raw(raw: str) -> str:
    return PATH_PREFIX + raw


def path_parent_suffix(path: str) -> str | None:
    """Drop last `.segment` chunk (digits or letters — matches varied indiaq layouts)."""

    if "." not in path:
        return None
    parts = path.split(".")
    if len(parts) < 2:
        return None
    return ".".join(parts[:-1])


def state_raw_to_district_base(state_raw: str) -> str:
    if "." not in state_raw:
        return state_raw
    head, tail = state_raw.rsplit(".", 1)
    return f"{head}/{tail}"


def district_base_to_state_path(base: str) -> str:
    if base.count("/") < 2:
        return base
    head, tail = base.rsplit("/", 1)
    letters = "".join(ch for ch in tail if ch.isalpha())
    return f"{head}.{letters}"


def path_to_residual_base(path: str) -> str:
    p = path
    while True:
        nxt = path_parent_suffix(p)
        if nxt is None:
            break
        p = nxt
    return p


def geo_path_to_state_path(any_geo_path: str) -> str:
    return district_base_to_state_path(path_to_residual_base(any_geo_path))


def fetch_direct_children_geo_path(
    conn: sqlite3.Connection, table: str, parent_raw_path: str
) -> list[dict[str, str]]:
    if table not in _GEO_CHILD_TABLES:
        raise ValueError("invalid geography table")
    pfx_full = full_id_from_raw(parent_raw_path)
    pat = re.compile("^" + re.escape(parent_raw_path) + r"\.([^.]+)$")
    cur = conn.execute(
        f"SELECT id, name FROM {table} WHERE id LIKE ?",
        (pfx_full + ".%",),
    )
    rows: list[dict[str, str]] = []
    for r in cur:
        rid = str(r["id"])
        raw = raw_path(rid)
        if pat.match(raw):
            rows.append({"id": rid, "name": str(r["name"])})
    rows.sort(key=lambda x: x["name"].casefold())
    return rows


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def ensure_users_country_column(conn: sqlite3.Connection) -> None:
    """Optional country for cohorting; defaults to India for existing rows."""
    cols = _table_columns(conn, "users")
    if "country" in cols:
        return
    conn.execute(
        "ALTER TABLE users ADD COLUMN country TEXT NOT NULL DEFAULT 'India'"
    )
    conn.execute(
        "UPDATE users SET country = 'India' "
        "WHERE country IS NULL OR TRIM(country) = ''"
    )
    conn.commit()


def migrate_users_app_extensions(conn: sqlite3.Connection) -> None:
    """Add account roles, admin flag, and messaging support columns to ``users``."""
    cols = _table_columns(conn, "users")
    additions: list[tuple[str, str]] = [
        ("account_type", "TEXT NOT NULL DEFAULT 'H_U'"),
        ("mentor_level", "INTEGER NOT NULL DEFAULT 0"),
        ("manager_level", "INTEGER NOT NULL DEFAULT 0"),
        ("leader_level", "INTEGER NOT NULL DEFAULT 0"),
        ("agent_level", "INTEGER NOT NULL DEFAULT 0"),
        ("is_admin", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col_name, decl in additions:
        if col_name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {decl}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def migrate_messages_table(conn: sqlite3.Connection) -> None:
    conn.executescript(MESSAGES_TABLE_SQL)
    conn.commit()


def migrate_connection_requests_table(conn: sqlite3.Connection) -> None:
    conn.executescript(CONNECTION_REQUESTS_SQL)
    cols = _table_columns(conn, "connection_requests")
    if "relationship" not in cols:
        try:
            conn.execute("ALTER TABLE connection_requests ADD COLUMN relationship TEXT")
        except sqlite3.OperationalError:
            pass
    if "is_dead" not in cols:
        try:
            conn.execute(
                "ALTER TABLE connection_requests ADD COLUMN is_dead INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
    conn.commit()


FAMILY_REMOVAL_REQUESTS_SQL = """
CREATE TABLE IF NOT EXISTS family_removal_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    target_source TEXT NOT NULL,
    target_member_id INTEGER NOT NULL,
    target_member_name TEXT,
    target_relationship TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by TEXT,
    admin_comment TEXT
);
CREATE INDEX IF NOT EXISTS idx_fam_remreq_user ON family_removal_requests(user_private_id);
CREATE INDEX IF NOT EXISTS idx_fam_remreq_status ON family_removal_requests(status);
"""

LINK_REQUESTS_SQL = """
CREATE TABLE IF NOT EXISTS link_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_private_id TEXT NOT NULL,
    to_user_private_id TEXT NOT NULL,
    family_member_id INTEGER NOT NULL,
    relationship_label TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    reject_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_link_requests_to ON link_requests(to_user_private_id, status);
CREATE INDEX IF NOT EXISTS idx_link_requests_from ON link_requests(from_user_private_id, status);
CREATE INDEX IF NOT EXISTS idx_link_requests_member ON link_requests(family_member_id);
"""

USER_FAMILY_SETUP_SQL = """
CREATE TABLE IF NOT EXISTS user_family_setup (
    user_private_id TEXT PRIMARY KEY,
    completed INTEGER NOT NULL DEFAULT 0,
    answers_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
"""

USER_EDUCATION_SQL = """
CREATE TABLE IF NOT EXISTS user_education (
    user_private_id TEXT PRIMARY KEY,
    education_level TEXT NOT NULL DEFAULT 'Uneducated',
    school_class_passed TEXT,
    school_year INTEGER,
    school_institution TEXT,
    college_degree_type TEXT,
    college_status_passed INTEGER NOT NULL DEFAULT 0,
    college_status_dropout INTEGER NOT NULL DEFAULT 0,
    college_year INTEGER,
    college_institution TEXT,
    updated_at TIMESTAMP
);
"""

USER_WORK_SQL = """
CREATE TABLE IF NOT EXISTS user_work (
    user_private_id TEXT PRIMARY KEY,
    work_status TEXT NOT NULL DEFAULT 'Unemployed',
    unemployed_sub TEXT,
    employee_workplace TEXT,
    employee_experience TEXT,
    employer_org_type TEXT,
    employer_company_name TEXT,
    employer_location TEXT,
    employer_years INTEGER,
    employer_months INTEGER,
    employer_business_name TEXT,
    updated_at TIMESTAMP
);
"""


# Constants for time-based action windows
POST_AUTHOR_DELETE_HOURS = 24
FAMILY_DIRECT_REMOVAL_DAYS = 2
# "From" identifier for system-generated messages (post deletion notices,
# admin removal-request decisions, etc.). Stored verbatim in messages.sender_id.
SYSTEM_SENDER_ID = "SYSTEM"


def migrate_family_removal_requests_table(conn: sqlite3.Connection) -> None:
    conn.executescript(FAMILY_REMOVAL_REQUESTS_SQL)
    conn.commit()


def migrate_link_requests_table(conn: sqlite3.Connection) -> None:
    conn.executescript(LINK_REQUESTS_SQL)
    conn.commit()


def migrate_user_family_setup_table(conn: sqlite3.Connection) -> None:
    conn.executescript(USER_FAMILY_SETUP_SQL)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_family_setup (user_private_id, completed, answers_json)
            SELECT user_private_id, 1, '{}'
              FROM family_profile
             WHERE COALESCE(form_completed, 0) = 1
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO user_family_setup (user_private_id, completed, answers_json)
            SELECT DISTINCT fm.user_private_id, 1, '{}'
              FROM family_members fm
             WHERE fm.source != 'self'
               AND COALESCE(fm.is_placeholder, 0) = 0
            """
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()


def migrate_user_education_table(conn: sqlite3.Connection) -> None:
    conn.executescript(USER_EDUCATION_SQL)
    conn.commit()


def migrate_user_work_table(conn: sqlite3.Connection) -> None:
    conn.executescript(USER_WORK_SQL)
    conn.commit()


def migrate_connection_requests_life_stage(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "connection_requests")
    if "request_member_life_stage" in cols:
        return
    try:
        conn.execute(
            "ALTER TABLE connection_requests ADD COLUMN request_member_life_stage TEXT"
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()


def migrate_posts_deletion_columns(conn: sqlite3.Connection) -> None:
    """Soft-delete bookkeeping columns on the posts table.

    A post is now "live" iff ``status = 'live'`` AND ``deleted_at IS NULL``.
    The migration is idempotent and never drops data.
    """
    cols = _table_columns(conn, "posts")
    additions: list[tuple[str, str]] = [
        ("deleted_at", "TIMESTAMP"),
        ("deleted_by", "TEXT"),
        ("delete_reason", "TEXT"),
    ]
    for col_name, decl in additions:
        if col_name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {decl}")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_posts_deleted_at ON posts(deleted_at)"
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()


def migrate_connection_requests_accepted_at(conn: sqlite3.Connection) -> None:
    """Track when a family/social request was accepted (for 2-day removal window)."""
    cols = _table_columns(conn, "connection_requests")
    if "accepted_at" in cols:
        return
    try:
        conn.execute(
            "ALTER TABLE connection_requests ADD COLUMN accepted_at TIMESTAMP"
        )
    except sqlite3.OperationalError:
        pass
    # Backfill: any row already accepted gets created_at as accepted_at so the
    # 2-day window calculation has something to anchor on.
    try:
        conn.execute(
            """
            UPDATE connection_requests
               SET accepted_at = created_at
             WHERE status = 'accepted' AND accepted_at IS NULL
            """
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()


def migrate_connection_requests_family_member_type(conn: sqlite3.Connection) -> None:
    """Nuclear vs general family classification for accepted/pending family requests."""
    cols = _table_columns(conn, "connection_requests")
    if "family_member_type" in cols:
        return
    try:
        conn.execute(
            "ALTER TABLE connection_requests ADD COLUMN family_member_type TEXT"
        )
    except sqlite3.OperationalError:
        pass
    # Legacy rows: treat as nuclear if the relationship is in the close-family set.
    try:
        cur = conn.execute(
            """
            SELECT id, relationship FROM connection_requests
             WHERE request_type = 'family' AND family_member_type IS NULL
            """
        )
        for row in cur:
            rid = int(row["id"])
            rel = str(row["relationship"] or "")
            fmt = "nuclear" if _is_close_family_relationship(rel) else "general"
            conn.execute(
                "UPDATE connection_requests SET family_member_type = ? WHERE id = ?",
                (fmt, rid),
            )
    except sqlite3.OperationalError:
        pass
    conn.commit()


def migrate_connection_requests_request_member_profile(conn: sqlite3.Connection) -> None:
    """Optional display profile on pending family connection requests."""
    cols = _table_columns(conn, "connection_requests")
    for col_name, decl in (
        ("request_member_name", "TEXT"),
        ("request_member_age", "INTEGER"),
        ("request_member_gender", "TEXT"),
    ):
        if col_name in cols:
            continue
        try:
            conn.execute(
                f"ALTER TABLE connection_requests ADD COLUMN {col_name} {decl}"
            )
        except sqlite3.OperationalError:
            pass
    conn.commit()


def send_system_message(
    conn: sqlite3.Connection,
    recipient_private_id: str,
    subject: str,
    body: str,
) -> str:
    """Insert a system-authored message into the user's inbox.

    Returns the allocated ``message_id``. The sender is recorded as
    :data:`SYSTEM_SENDER_ID` so the inbox can render it distinctively and the
    notification bell can pick it up without a real user account behind it.
    """
    mid = allocate_message_id(conn)
    conn.execute(
        """
        INSERT INTO messages (
            message_id, sender_id, recipient_id, subject, body, status,
            parent_message_id, is_draft
        ) VALUES (?, ?, ?, ?, ?, 'sent', NULL, 0)
        """,
        (mid, SYSTEM_SENDER_ID, str(recipient_private_id), subject, body),
    )
    return mid


def is_admin_user(user_row: sqlite3.Row | None) -> bool:
    if user_row is None:
        return False
    try:
        return bool(int(user_row["is_admin"] or 0))
    except (KeyError, TypeError, ValueError):
        return False


def admin_required(view):
    """Decorator: 403 unless ``g.current_user.is_admin`` is truthy. Implies login."""
    @wraps(view)
    @login_required
    def _wrap(*args: Any, **kwargs: Any):
        if not is_admin_user(getattr(g, "current_user", None)):
            return jsonify({"error": "Admin only"}), 403
        return view(*args, **kwargs)
    return _wrap


def migrate_family_tables(conn: sqlite3.Connection) -> None:
    """Create family_profile + family_members tables (no destructive changes)."""
    conn.executescript(FAMILY_PROFILE_SQL)
    conn.executescript(FAMILY_MEMBERS_SQL)
    cols_profile = _table_columns(conn, "family_profile")
    if "relationship_status" not in cols_profile:
        try:
            conn.execute(
                "ALTER TABLE family_profile ADD COLUMN relationship_status TEXT"
            )
        except sqlite3.OperationalError:
            pass
    cols_member = _table_columns(conn, "family_members")
    member_additions: list[tuple[str, str]] = [
        ("gender", "TEXT"),
        ("age", "INTEGER"),
        ("age_modifier", "TEXT"),
        ("is_close_family", "INTEGER NOT NULL DEFAULT 0"),
        ("is_dead", "INTEGER NOT NULL DEFAULT 0"),
        ("is_placeholder", "INTEGER NOT NULL DEFAULT 0"),
        ("member_type", "TEXT NOT NULL DEFAULT 'nuclear'"),
        ("account_public_id", "TEXT"),
        ("source", "TEXT NOT NULL DEFAULT 'form'"),
        ("parent_link", "TEXT"),
    ]
    for col_name, decl in member_additions:
        if col_name in cols_member:
            continue
        try:
            conn.execute(f"ALTER TABLE family_members ADD COLUMN {col_name} {decl}")
        except sqlite3.OperationalError:
            pass
    cols_member = _table_columns(conn, "family_members")
    for col_name, decl in (
        ("tree_mother_member_id", "INTEGER"),
        ("tree_father_member_id", "INTEGER"),
        ("tree_spouse_member_id", "INTEGER"),
        ("tree_child_of_member_id", "INTEGER"),
        ("tree_mother_connection_request_id", "INTEGER"),
        ("tree_father_connection_request_id", "INTEGER"),
        ("reference_relation", "TEXT"),
        ("tree_child_of_connection_request_id", "INTEGER"),
    ):
        if col_name in cols_member:
            continue
        try:
            conn.execute(f"ALTER TABLE family_members ADD COLUMN {col_name} {decl}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def migrate_family_relationships_table(conn: sqlite3.Connection) -> None:
    """Create or migrate ``family_relationships`` to integer edge columns."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='family_relationships'"
    ).fetchone()
    new_cols = {"source_id", "target_id", "relation_type"}
    if row:
        try:
            cols = _table_columns(conn, "family_relationships")
        except sqlite3.OperationalError:
            cols = set()
        if new_cols.issubset(cols):
            return
        legacy = {"source_private_id", "target_private_id", "relationship_type"}
        if legacy.issubset(cols):
            conn.execute(
                "ALTER TABLE family_relationships RENAME TO family_relationships_legacy_edges"
            )
            conn.executescript(FAMILY_RELATIONSHIPS_SQL)
            try:
                cur = conn.execute(
                    """
                    SELECT source_private_id, target_private_id, relationship_type
                      FROM family_relationships_legacy_edges
                    """
                )
                for r in cur:
                    try:
                        s = int(str(r["source_private_id"]).strip())
                        t = int(str(r["target_private_id"]).strip())
                    except (TypeError, ValueError):
                        continue
                    rt = str(r["relationship_type"] or "").strip().lower()
                    if rt not in {"parent", "child", "spouse", "sibling"}:
                        continue
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO family_relationships (
                            source_id, target_id, relation_type
                        ) VALUES (?, ?, ?)
                        """,
                        (s, t, rt),
                    )
            except sqlite3.OperationalError:
                pass
            conn.execute("DROP TABLE IF EXISTS family_relationships_legacy_edges")
        else:
            conn.execute("DROP TABLE IF EXISTS family_relationships")
            conn.executescript(FAMILY_RELATIONSHIPS_SQL)
    else:
        conn.executescript(FAMILY_RELATIONSHIPS_SQL)
    conn.commit()


def state_table_has_zone_fk(conn: sqlite3.Connection) -> bool:
    return "zone_id" in _table_columns(conn, "state")


def infer_state_raw_from_geography_raw(path_raw: str) -> str | None:
    """
    Recover state row raw path IND/ZX.AB from descendants or identity.
    Handles state itself (IND/CS.AN), and deeper rows (IND/CS/AN.1…).
    """
    pr = (path_raw or "").strip()
    if not pr.startswith("IND"):
        return None
    parts = [p for p in pr.split("/") if p != ""]
    if len(parts) < 2:
        return None
    if len(parts) == 2 and "." in parts[1]:
        return pr
    if len(parts) >= 3:
        zcode = parts[1]
        token = parts[2].split(".")[0]
        return f"IND/{zcode}.{token}"
    return None


def zone_full_id_from_state_raw(state_raw: str) -> str | None:
    """Map IND/CS.AN → prefixed IND.CS zone id."""
    sr = infer_state_raw_from_geography_raw(state_raw) or state_raw
    if not sr or "/" not in sr:
        return None
    _country, rest = sr.split("/", 1)
    if "." not in rest:
        return None
    zone_letters_chunk = rest.split(".", 1)[0]
    letters_only = "".join(ch for ch in zone_letters_chunk if ch.isalpha())
    if not letters_only:
        return None
    return full_id_from_raw(f"IND.{letters_only}")


def zone_like_prefix_full(zone_full_id: str) -> str:
    """IND.CS prefixed rows match villages IND/CS/…"""
    raw = raw_path(zone_full_id.strip())
    if "." not in raw:
        swapped = raw
    else:
        swapped = raw.replace(".", "/", 1)
    return full_id_from_raw(swapped)


def user_location_predicate_fk(scope: str, full_id: str) -> tuple[str, tuple]:
    fid = full_id.strip()
    if scope == "village":
        return "(u.current_location_id = ?)", (fid,)
    if scope == "tehsil":
        return (
            "(u.current_location_id IN "
            "(SELECT id FROM village WHERE tehsil_id = ?))",
            (fid,),
        )
    if scope == "district":
        return (
            "(u.current_location_id IN ("
            "SELECT v.id FROM village v "
            "JOIN tehsil t ON v.tehsil_id = t.id "
            "WHERE t.district_id = ?))",
            (fid,),
        )
    if scope == "state":
        return (
            "(u.current_location_id IN ("
            "SELECT v.id FROM village v "
            "JOIN tehsil t ON v.tehsil_id = t.id "
            "JOIN district d ON t.district_id = d.id "
            "WHERE d.state_id = ?))",
            (fid,),
        )
    if scope == "zone":
        raise ValueError("zone predicate needs connection check")
    raise ValueError(scope)


def _indian_users_predicate(conn: sqlite3.Connection) -> tuple[str, tuple]:
    """SQL fragment (with alias u) for users tied to India (path or users.country)."""
    cols = _table_columns(conn, "users")
    has_country = "country" in cols
    path_clause = (
        "(INSTR(TRIM(u.current_location_id), 'IND/') > 0 "
        "OR INSTR(TRIM(u.current_location_id), 'IND.') > 0)"
    )
    if geography_has_relational_fks(conn):
        join_clause = """EXISTS (
            SELECT 1 FROM village v
            INNER JOIN tehsil t ON v.tehsil_id = t.id
            INNER JOIN district d ON t.district_id = d.id
            INNER JOIN state s ON d.state_id = s.id
            WHERE v.id = u.current_location_id
        )"""
        loc_clause = f"({join_clause} OR {path_clause})"
    else:
        loc_clause = path_clause

    if has_country:
        country_clause = "LOWER(TRIM(COALESCE(u.country, ''))) = 'india'"
        where_sql = f"({country_clause} OR {loc_clause})"
    else:
        where_sql = loc_clause
    return where_sql, ()


def user_location_predicate(
    conn: sqlite3.Connection, scope: str, full_id: str | None
) -> tuple[str, tuple]:
    if scope == "earth":
        return "1=1", ()

    if scope == "continent":
        cont = (full_id or "").strip().upper()
        if cont == "AS":
            return _indian_users_predicate(conn)
        return "1=0", ()

    if scope == "country":
        ctry = (full_id or "").strip().upper()
        if ctry == "IND":
            return _indian_users_predicate(conn)
        cols_zone = _table_columns(conn, "zone")
        if (
            "country_id" in cols_zone
            and geography_has_relational_fks(conn)
            and state_table_has_zone_fk(conn)
        ):
            return (
                "(u.current_location_id IN ("
                "SELECT v.id FROM village v "
                "JOIN tehsil t ON v.tehsil_id = t.id "
                "JOIN district d ON t.district_id = d.id "
                "JOIN state s ON d.state_id = s.id "
                "JOIN zone z ON s.zone_id = z.id "
                "WHERE z.country_id = ?))",
                (ctry,),
            )
        return "1=0", ()

    if scope == "india":
        return "1=1", ()

    fid = (full_id or "").strip()
    if geography_has_relational_fks(conn):
        if scope == "zone" and state_table_has_zone_fk(conn):
            return (
                "(u.current_location_id IN ("
                "SELECT v.id FROM village v "
                "JOIN tehsil t ON v.tehsil_id = t.id "
                "JOIN district d ON t.district_id = d.id "
                "JOIN state s ON d.state_id = s.id "
                "WHERE s.zone_id = ?))",
                (fid,),
            )
        if scope == "zone":
            pref = zone_like_prefix_full(fid)
            return (
                "(u.current_location_id = ? OR u.current_location_id LIKE ?)",
                (fid, pref + ".%"),
            )
        return user_location_predicate_fk(scope, fid)

    if scope == "zone":
        pref = zone_like_prefix_full(fid)
        return (
            "(u.current_location_id = ? OR u.current_location_id LIKE ?)",
            (fid, pref + ".%"),
        )
    if scope == "state":
        dist_pref = full_id_from_raw(state_raw_to_district_base(raw_path(fid)))
        return (
            "(u.current_location_id = ? OR u.current_location_id LIKE ?)",
            (fid, dist_pref + ".%"),
        )
    if scope in {"district", "tehsil"}:
        return (
            "(u.current_location_id = ? OR u.current_location_id LIKE ?)",
            (fid, fid + ".%"),
        )
    if scope == "village":
        return "(u.current_location_id = ?)", (fid,)
    raise ValueError(scope)


def _geo_row_optional_meta(
    conn: sqlite3.Connection, table: str, geo_id: str
) -> dict[str, str | None]:
    cols = _table_columns(conn, table)
    qid = (geo_id or "").strip()
    if "zodiac_sign" in cols:
        row = conn.execute(
            f"SELECT name, zodiac_sign, element FROM {table} WHERE id = ?",
            (qid,),
        ).fetchone()
        if row:
            return {
                "name": str(row["name"]),
                "zodiac_sign": str(row["zodiac_sign"]),
                "element": str(row["element"]),
            }
    row = conn.execute(f"SELECT name FROM {table} WHERE id = ?", (qid,)).fetchone()
    if row:
        return {"name": str(row["name"]), "zodiac_sign": None, "element": None}
    return {"name": geo_id or "", "zodiac_sign": None, "element": None}


def _percent(part: float, whole: float) -> float:
    if not whole:
        return 0.0
    return round(100.0 * part / whole, 1)


def cohort_breakdown_ordered(
    conn: sqlite3.Connection,
    where_sql: str,
    params: tuple,
    column: str,
    ordered_labels: tuple[str, ...],
    denominator: int,
) -> list[dict[str, float | int | str]]:
    q = (
        f"SELECT u.{column} AS lbl, COUNT(*) AS c FROM users u WHERE ({where_sql}) "
        f"GROUP BY u.{column}"
    )
    cur = conn.execute(q, params)
    raw = {str(r["lbl"]): int(r["c"]) for r in cur.fetchall()}
    out = []
    for lab in ordered_labels:
        ct = raw.get(lab, 0)
        out.append(
            {
                "label": lab,
                "count": ct,
                "pct": _percent(float(ct), float(denominator)),
            }
        )
    return out


def cohort_gender_male_female_only(
    conn: sqlite3.Connection,
    where_sql: str,
    params: tuple,
    denominator: int,
) -> list[dict[str, float | int | str]]:
    q = (
        f"SELECT u.gender AS lbl, COUNT(*) AS c FROM users u "
        f"WHERE ({where_sql}) AND u.gender IN ('Male', 'Female') GROUP BY u.gender"
    )
    cur = conn.execute(q, params)
    raw = {str(r["lbl"]): int(r["c"]) for r in cur.fetchall()}
    out: list[dict[str, float | int | str]] = []
    for lab in ("Male", "Female"):
        ct = raw.get(lab, 0)
        out.append(
            {
                "label": lab,
                "count": ct,
                "pct": _percent(float(ct), float(denominator)),
            }
        )
    return out


def cohort_life_stage_from_age_column(
    conn: sqlite3.Connection,
    where_sql: str,
    params: tuple,
    denominator: int,
) -> list[dict[str, float | int | str]]:
    """Life stage buckets from ``u.age`` (not stored ``age_group`` text)."""
    life_sql = (
        "CASE "
        "WHEN u.age BETWEEN 0 AND 24 THEN 'Balak' "
        "WHEN u.age BETWEEN 25 AND 49 THEN 'Yuvak' "
        "WHEN u.age BETWEEN 50 AND 75 THEN 'Vridh' "
        "ELSE 'Sanyas' END"
    )
    q = (
        f"SELECT {life_sql} AS lbl, COUNT(*) AS c FROM users u "
        f"WHERE ({where_sql}) GROUP BY lbl"
    )
    cur = conn.execute(q, params)
    raw = {str(r["lbl"]): int(r["c"]) for r in cur.fetchall()}
    out: list[dict[str, float | int | str]] = []
    for lab in LIFE_STAGE_ORDER:
        ct = raw.get(lab, 0)
        out.append(
            {
                "label": lab,
                "count": ct,
                "pct": _percent(float(ct), float(denominator)),
            }
        )
    return out


def sun_sign_counts_by_element(
    conn: sqlite3.Connection,
    where_sql: str,
    params: tuple,
) -> list[dict[str, Any]]:
    cur = conn.execute(
        f"SELECT u.sun_sign AS s, COUNT(*) AS c FROM users u WHERE ({where_sql}) GROUP BY u.sun_sign",
        params,
    )
    raw: dict[str, int] = {}
    for r in cur.fetchall():
        raw[str(r["s"])] = int(r["c"])
    out: list[dict[str, Any]] = []
    for el in SUN_ELEMENT_ORDER:
        signs = SIGNS_BY_ELEMENT[el]
        sign_rows = [{"label": z, "count": raw.get(z, 0)} for z in signs]
        out.append({"element": el, "signs": sign_rows})
    return out


def location_statistics_bundle(
    conn: sqlite3.Connection,
    scope: str,
    geo_id: str | None,
) -> dict:
    """Aggregates keyed for JSON + Chart.js."""
    pred, tup = user_location_predicate(conn, scope, geo_id)
    total_row = conn.execute(
        f"SELECT COUNT(*) AS c FROM users u WHERE ({pred})",
        tup,
    ).fetchone()
    total = int(total_row["c"]) if total_row else 0

    gender_rows = cohort_gender_male_female_only(conn, pred, tup, total)
    age_rows = cohort_life_stage_from_age_column(conn, pred, tup, total)
    sign_rows = cohort_breakdown_ordered(
        conn, pred, tup, "sun_sign", ZODIAC_SIGNS_ORDER, total
    )
    el_rows = cohort_breakdown_ordered(
        conn, pred, tup, "element", SUN_ELEMENT_ORDER, total
    )
    zodiac_by_element = sun_sign_counts_by_element(conn, pred, tup)

    return {
        "total_users": total,
        "gender": gender_rows,
        "age_group": age_rows,
        "sun_element": el_rows,
        "sun_sign": sign_rows,
        "zodiac_by_element": zodiac_by_element,
    }


def build_location_breadcrumbs(
    conn: sqlite3.Connection,
    scope: str,
    full_id: str | None,
) -> list[dict[str, str | None]]:
    """Earth → … → India → zone → … when global tables exist; else legacy India-only trail."""
    if not _geo_table_exists(conn, "earth"):
        return _build_location_breadcrumbs_legacy(conn, scope, full_id)

    if scope == "earth":
        eid = (full_id or "0").strip()
        nm = _geo_row_optional_meta(conn, "earth", eid)["name"]
        return [{"label": nm, "url": None}]

    if scope == "continent":
        assert full_id is not None
        cid = full_id.strip()
        cmeta = _geo_row_optional_meta(conn, "continent", cid)
        enm = _geo_row_optional_meta(conn, "earth", "0")["name"]
        return [
            {"label": enm, "url": url_for("location_earth", earth_id="0")},
            {"label": cmeta["name"], "url": None},
        ]

    if scope == "country":
        assert full_id is not None
        cid = full_id.strip()
        row = conn.execute(
            "SELECT c.name AS cn, c.continent_id FROM country c WHERE c.id = ?",
            (cid,),
        ).fetchone()
        enm = _geo_row_optional_meta(conn, "earth", "0")["name"]
        if not row:
            return [
                {"label": enm, "url": url_for("location_earth", earth_id="0")},
                {"label": cid, "url": None},
            ]
        cont_id = str(row["continent_id"])
        cou_nm = str(row["cn"])
        con_nm = _geo_row_optional_meta(conn, "continent", cont_id)["name"]
        return [
            {"label": enm, "url": url_for("location_earth", earth_id="0")},
            {"label": con_nm, "url": url_for("location_continent", continent_id=cont_id)},
            {"label": cou_nm, "url": None},
        ]

    crumbs: list[dict[str, str | None]] = []
    enm = _geo_row_optional_meta(conn, "earth", "0")["name"]
    as_nm = _geo_row_optional_meta(conn, "continent", "AS")["name"]
    ind_nm = _geo_row_optional_meta(conn, "country", "IND")["name"]
    crumbs.extend(
        [
            {"label": enm, "url": url_for("location_earth", earth_id="0")},
            {"label": as_nm, "url": url_for("location_continent", continent_id="AS")},
            {"label": ind_nm, "url": url_for("location_country", country_id="IND")},
        ]
    )
    if scope == "india":
        crumbs[-1]["url"] = None
        return crumbs

    assert full_id is not None
    rp = raw_path(full_id.strip())

    if scope == "zone":
        meta = _geo_row_optional_meta(conn, "zone", full_id)
        crumbs.append({"label": meta["name"], "url": None})
        return crumbs

    inferred_state = infer_state_raw_from_geography_raw(rp)
    if inferred_state:
        sf = full_id_from_raw(inferred_state)
        zid = zone_full_id_from_state_raw(inferred_state)
        if zid:
            zmeta = _geo_row_optional_meta(conn, "zone", zid)
            crumbs.append(
                {
                    "label": zmeta["name"],
                    "url": url_for("location_zone", zone_id=zid),
                }
            )
        smeta = _geo_row_optional_meta(conn, "state", sf)
        if scope == "state":
            crumbs.append({"label": smeta["name"], "url": None})
            return crumbs
        crumbs.append(
            {"label": smeta["name"], "url": url_for("location_state", state_id=sf)}
        )

    if scope == "district":
        dmeta = _geo_row_optional_meta(conn, "district", full_id)
        crumbs.append({"label": dmeta["name"], "url": None})
        return crumbs

    if scope == "tehsil":
        traw = rp
        draw = path_parent_suffix(traw) if traw else None
        if draw:
            dfull = full_id_from_raw(draw)
            dmeta = _geo_row_optional_meta(conn, "district", dfull)
            crumbs.append(
                {
                    "label": dmeta["name"],
                    "url": url_for("location_district", district_id=dfull),
                }
            )
        tmeta = _geo_row_optional_meta(conn, "tehsil", full_id)
        crumbs.append({"label": tmeta["name"], "url": None})
        return crumbs

    if scope == "village":
        vraw = rp
        traw = path_parent_suffix(vraw) if vraw else None
        draw = path_parent_suffix(traw) if traw else None
        if draw:
            dfull = full_id_from_raw(draw)
            dmeta = _geo_row_optional_meta(conn, "district", dfull)
            crumbs.append(
                {
                    "label": dmeta["name"],
                    "url": url_for("location_district", district_id=dfull),
                }
            )
        if traw:
            tfull = full_id_from_raw(traw)
            tmeta = _geo_row_optional_meta(conn, "tehsil", tfull)
            crumbs.append(
                {
                    "label": tmeta["name"],
                    "url": url_for("location_tehsil", tehsil_id=tfull),
                }
            )
        vmeta = _geo_row_optional_meta(conn, "village", full_id)
        crumbs.append({"label": vmeta["name"], "url": None})
        return crumbs

    crumbs.append({"label": full_id, "url": None})
    return crumbs


def _build_location_breadcrumbs_legacy(
    conn: sqlite3.Connection,
    scope: str,
    full_id: str | None,
) -> list[dict[str, str | None]]:
    """India → zone → … when earth/continent/country tables are not present."""
    crumbs: list[dict[str, str | None]] = []
    crumbs.append({"label": "India", "url": url_for("location_india")})
    if scope == "india":
        return crumbs

    assert full_id is not None
    rp = raw_path(full_id.strip())

    if scope == "zone":
        meta = _geo_row_optional_meta(conn, "zone", full_id)
        crumbs.append({"label": meta["name"], "url": None})
        return crumbs

    inferred_state = infer_state_raw_from_geography_raw(rp)
    if inferred_state:
        sf = full_id_from_raw(inferred_state)
        zid = zone_full_id_from_state_raw(inferred_state)
        if zid:
            zmeta = _geo_row_optional_meta(conn, "zone", zid)
            crumbs.append(
                {
                    "label": zmeta["name"],
                    "url": url_for("location_zone", zone_id=zid),
                }
            )
        smeta = _geo_row_optional_meta(conn, "state", sf)
        if scope == "state":
            crumbs.append({"label": smeta["name"], "url": None})
            return crumbs
        crumbs.append(
            {"label": smeta["name"], "url": url_for("location_state", state_id=sf)}
        )

    if scope == "district":
        dmeta = _geo_row_optional_meta(conn, "district", full_id)
        crumbs.append({"label": dmeta["name"], "url": None})
        return crumbs

    if scope == "tehsil":
        traw = rp
        draw = path_parent_suffix(traw) if traw else None
        if draw:
            dfull = full_id_from_raw(draw)
            dmeta = _geo_row_optional_meta(conn, "district", dfull)
            crumbs.append(
                {
                    "label": dmeta["name"],
                    "url": url_for("location_district", district_id=dfull),
                }
            )
        tmeta = _geo_row_optional_meta(conn, "tehsil", full_id)
        crumbs.append({"label": tmeta["name"], "url": None})
        return crumbs

    if scope == "village":
        vraw = rp
        traw = path_parent_suffix(vraw) if vraw else None
        draw = path_parent_suffix(traw) if traw else None
        if draw:
            dfull = full_id_from_raw(draw)
            dmeta = _geo_row_optional_meta(conn, "district", dfull)
            crumbs.append(
                {
                    "label": dmeta["name"],
                    "url": url_for("location_district", district_id=dfull),
                }
            )
        if traw:
            tfull = full_id_from_raw(traw)
            tmeta = _geo_row_optional_meta(conn, "tehsil", tfull)
            crumbs.append(
                {
                    "label": tmeta["name"],
                    "url": url_for("location_tehsil", tehsil_id=tfull),
                }
            )
        vmeta = _geo_row_optional_meta(conn, "village", full_id)
        crumbs.append({"label": vmeta["name"], "url": None})
        return crumbs

    crumbs.append({"label": full_id, "url": None})
    return crumbs


def _escape_sql_like(pat: str) -> str:
    return (
        pat.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )


def geo_search(conn: sqlite3.Connection, needle: str, limit: int = 35) -> list[dict]:
    needle_clean = needle.strip()
    if not needle_clean:
        return []
    pat = "%" + _escape_sql_like(needle_clean) + "%"

    tbl_names = {
        str(r[0])
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    hits: list[dict] = []
    for kind in GEO_SEARCH_KIND_ORDER:
        tbl = GEO_ROUTE_TABLE[kind]
        if tbl not in tbl_names:
            continue
        cur = conn.execute(
            f"SELECT id, name FROM {tbl} WHERE name LIKE ? ESCAPE '\\' COLLATE NOCASE LIMIT ?",
            (pat, limit),
        )
        for r in cur.fetchall():
            hits.append({"kind": kind, "id": str(r["id"]), "name": str(r["name"])})
            if len(hits) >= limit:
                return hits
    return hits


def parse_date_iso(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_age(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return max(0, years)


def life_stage_from_age(age: int) -> str:
    """Balak 0–24, Yuvak 25–49, Vridh 50–75, Sanyas 76+."""
    if age <= 24:
        return "Balak"
    if age <= 49:
        return "Yuvak"
    if age <= 75:
        return "Vridh"
    return "Sanyas"


def age_group_from_age(age: int) -> str:
    return life_stage_from_age(age)


def sun_sign_for_date(d: date) -> str:
    """Western tropical Sun sign using common calendar boundaries (prototype)."""

    m, day = d.month, d.day
    # Capricorn / Aquarius wrap New Year — check first.
    if (m == 12 and day >= 22) or (m == 1 and day <= 19):
        return "Capricorn"
    if (m == 1 and day >= 20) or (m == 2 and day <= 18):
        return "Aquarius"
    if (m == 2 and day >= 19) or (m == 3 and day <= 20):
        return "Pisces"
    if (m == 3 and day >= 21) or (m == 4 and day <= 19):
        return "Aries"
    if (m == 4 and day >= 20) or (m == 5 and day <= 20):
        return "Taurus"
    if (m == 5 and day >= 21) or (m == 6 and day <= 20):
        return "Gemini"
    if (m == 6 and day >= 21) or (m == 7 and day <= 22):
        return "Cancer"
    if (m == 7 and day >= 23) or (m == 8 and day <= 22):
        return "Leo"
    if (m == 8 and day >= 23) or (m == 9 and day <= 22):
        return "Virgo"
    if (m == 9 and day >= 23) or (m == 10 and day <= 22):
        return "Libra"
    if (m == 10 and day >= 23) or (m == 11 and day <= 21):
        return "Scorpio"
    return "Sagittarius"


def moon_sign_simplified(d: date) -> str:
    doy = int(d.strftime("%j"))
    return ZODIAC_SIGNS_ORDER[(doy - 1) % 12]


def element_for_sun(sun_sign: str) -> str:
    return ELEMENT_BY_SIGN[sun_sign]


def _digest_to_alphanumeric8(digest_hex: str) -> str:
    out: list[str] = []
    for ch in digest_hex:
        if ch.isalnum():
            out.append(ch.upper())
        if len(out) >= 8:
            break
    while len(out) < 8:
        out.append("0")
    return "".join(out[:8])


def allocate_private_id(
    conn: sqlite3.Connection,
    first_name: str,
    dob: str,
    birth_time: str,
    birth_location_id: str | None,
    birth_country_id: str | None = None,
    birth_continent_id: str | None = None,
) -> str:
    salt = 0
    fname = first_name.strip()
    loc_key = (birth_location_id or "").strip()
    if not loc_key:
        loc_key = (
            f"{(birth_country_id or '').strip()}|{(birth_continent_id or '').strip()}|nogeoid"
        )
    while salt < 50_000:
        payload = f"{loc_key}|{fname}|{dob}|{birth_time}|{salt}"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        code = _digest_to_alphanumeric8(digest)
        pid = f"U-{code}"
        row = conn.execute(
            "SELECT 1 AS x FROM users WHERE private_id = ? COLLATE NOCASE",
            (pid,),
        ).fetchone()
        if row is None:
            return pid
        salt += 1
    raise RuntimeError("Could not allocate a unique private_id")


def allocate_public_id(conn: sqlite3.Connection) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(50_000):
        suffix = "".join(secrets.choice(alphabet) for _ in range(8))
        pub = f"A-{suffix}"
        row = conn.execute(
            "SELECT 1 FROM users WHERE public_id = ?",
            (pub,),
        ).fetchone()
        if row is None:
            return pub
    raise RuntimeError("Could not allocate a unique public_id")


def village_exists(conn: sqlite3.Connection, vid: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM village WHERE id = ?",
        ((vid or "").strip(),),
    ).fetchone()
    return row is not None


def _location_display_label_join(conn: sqlite3.Connection, village_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT v.name AS village,
               t.name AS tehsil,
               d.name AS district,
               s.name AS state
          FROM village v
          JOIN tehsil t ON v.tehsil_id = t.id
          JOIN district d ON t.district_id = d.id
          JOIN state s ON d.state_id = s.id
         WHERE v.id = ?
        """,
        ((village_id or "").strip(),),
    ).fetchone()
    if not row:
        return None
    return "{village}, {tehsil}, {district}, {state}".format(
        village=str(row["village"]),
        tehsil=str(row["tehsil"]),
        district=str(row["district"]),
        state=str(row["state"]),
    )


def _location_display_label_path(conn: sqlite3.Connection, village_full_id: str) -> str:
    vf = (village_full_id or "").strip()
    vraw = raw_path(vf)
    traw = path_parent_suffix(vraw)
    draw = path_parent_suffix(traw) if traw else None
    sraw = geo_path_to_state_path(vraw)

    def nm(table: str, full_key: str | None) -> str | None:
        if not full_key:
            return None
        row = conn.execute(
            f"SELECT name FROM {table} WHERE id = ?",
            (full_key,),
        ).fetchone()
        return str(row["name"]) if row else None

    parts = [
        nm("village", vf),
        nm("tehsil", full_id_from_raw(traw) if traw else None),
        nm("district", full_id_from_raw(draw) if draw else None),
        nm("state", full_id_from_raw(sraw)),
    ]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else vf


def location_display_label(conn: sqlite3.Connection, village_id: str) -> str:
    if geography_has_relational_fks(conn):
        joined = _location_display_label_join(conn, village_id)
        if joined is not None:
            return joined
    return _location_display_label_path(conn, village_id)


def _users_per_state_join(conn: sqlite3.Connection) -> tuple[list[str], list[int]]:
    cur = conn.execute(
        """
        SELECT s.name AS state_name, COUNT(u.id) AS cnt
          FROM users u
          INNER JOIN village v ON u.current_location_id = v.id
          INNER JOIN tehsil t ON v.tehsil_id = t.id
          INNER JOIN district d ON t.district_id = d.id
          INNER JOIN state s ON d.state_id = s.id
         GROUP BY s.id, s.name
         ORDER BY cnt DESC, s.name COLLATE NOCASE ASC
        """
    )
    labels: list[str] = []
    values: list[int] = []
    for r in cur.fetchall():
        labels.append(str(r["state_name"]))
        values.append(int(r["cnt"]))
    return labels, values


def _users_per_state_path(conn: sqlite3.Connection) -> tuple[list[str], list[int]]:
    cur = conn.execute("SELECT current_location_id FROM users")
    counts: dict[str, int] = {}
    for r in cur.fetchall():
        vid = str(r["current_location_id"] or "").strip()
        if not vid:
            continue
        sraw = geo_path_to_state_path(raw_path(vid))
        sfull = full_id_from_raw(sraw)
        nrow = conn.execute("SELECT name FROM state WHERE id = ?", (sfull,)).fetchone()
        if not nrow:
            continue
        name = str(nrow["name"])
        counts[name] = counts.get(name, 0) + 1
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].casefold()))
    labels = [k for k, _ in items]
    values = [v for _, v in items]
    return labels, values


def users_per_state_from_current_location(
    conn: sqlite3.Connection,
) -> tuple[list[str], list[int]]:
    if geography_has_relational_fks(conn):
        return _users_per_state_join(conn)
    return _users_per_state_path(conn)


def count_registered_users(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
    return int(row["c"]) if row else 0


def count_users_in_india(conn: sqlite3.Connection) -> int:
    """
    Users tied to India: country is India, or current_location_id matches Indian
    geography (village→state join when relational, else IND path in the id string).
    """
    where_sql, params = _indian_users_predicate(conn)
    row = conn.execute(
        f"SELECT COUNT(*) AS c FROM users u WHERE ({where_sql})",
        params,
    ).fetchone()
    return int(row["c"]) if row else 0


def count_homepage_india_users(conn: sqlite3.Connection) -> int:
    """Users with current country India, plus legacy rows with IND paths only."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM users u
        WHERE TRIM(COALESCE(u.current_country_id, '')) = 'IND'
           OR (
                (u.current_country_id IS NULL OR TRIM(u.current_country_id) = '')
                AND (
                    INSTR(TRIM(u.current_location_id), 'IND/') > 0
                    OR INSTR(TRIM(u.current_location_id), 'IND.') > 0
                )
           )
        """
    ).fetchone()
    return int(row["c"]) if row else 0


def count_homepage_asia_users(conn: sqlite3.Connection) -> int:
    """Users whose current country maps to Asia, plus legacy India-path users."""
    if not _geo_table_exists(conn, "country"):
        return count_users_in_india(conn)
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM users u
        LEFT JOIN country c ON TRIM(COALESCE(u.current_country_id, '')) = c.id
        WHERE c.continent_id = 'AS'
           OR (
                (u.current_country_id IS NULL OR TRIM(u.current_country_id) = '')
                AND (
                    INSTR(TRIM(u.current_location_id), 'IND/') > 0
                    OR INSTR(TRIM(u.current_location_id), 'IND.') > 0
                )
           )
        """
    ).fetchone()
    return int(row["c"]) if row else 0


def explorer_user_counts(
    conn: sqlite3.Connection, continent_id: str, country_id: str
) -> dict[str, str | int]:
    """Validated continent/country pair with user counts for the homepage explorer."""
    cont = (continent_id or "AS").strip().upper()
    cid = (country_id or "IND").strip().upper()
    if not _geo_table_exists(conn, "continent"):
        return {
            "continent_id": "AS",
            "country_id": "IND",
            "continent_name": "Asia",
            "country_name": "India",
            "continent_users": count_homepage_asia_users(conn),
            "country_users": count_homepage_india_users(conn),
        }
    cr = conn.execute("SELECT name FROM continent WHERE id = ?", (cont,)).fetchone()
    if not cr:
        cont = "AS"
        cr = conn.execute("SELECT name FROM continent WHERE id = ?", (cont,)).fetchone()
    ur = conn.execute(
        "SELECT name, continent_id FROM country WHERE id = ?", (cid,)
    ).fetchone()
    if not ur or str(ur["continent_id"]) != cont:
        cid = "IND"
        ur = conn.execute(
            "SELECT name, continent_id FROM country WHERE id = ?", (cid,)
        ).fetchone()
    cont_name = str(cr["name"])
    cou_name = str(ur["name"])

    row_c = conn.execute(
        """
        SELECT COUNT(*) AS c FROM users u
        JOIN country c ON TRIM(COALESCE(u.current_country_id, '')) = c.id
        WHERE c.continent_id = ?
        """,
        (cont,),
    ).fetchone()
    continent_users = int(row_c["c"]) if row_c else 0
    if cont == "AS":
        row_l = conn.execute(
            """
            SELECT COUNT(*) AS c FROM users u
            WHERE (u.current_country_id IS NULL OR TRIM(u.current_country_id) = '')
              AND (
                  INSTR(TRIM(u.current_location_id), 'IND/') > 0
                  OR INSTR(TRIM(u.current_location_id), 'IND.') > 0
              )
            """
        ).fetchone()
        continent_users += int(row_l["c"]) if row_l else 0

    row_co = conn.execute(
        """
        SELECT COUNT(*) AS c FROM users u
        WHERE TRIM(COALESCE(u.current_country_id, '')) = ?
        """,
        (cid,),
    ).fetchone()
    country_users = int(row_co["c"]) if row_co else 0
    if cid == "IND":
        row_lc = conn.execute(
            """
            SELECT COUNT(*) AS c FROM users u
            WHERE (u.current_country_id IS NULL OR TRIM(u.current_country_id) = '')
              AND (
                  INSTR(TRIM(u.current_location_id), 'IND/') > 0
                  OR INSTR(TRIM(u.current_location_id), 'IND.') > 0
              )
            """
        ).fetchone()
        country_users += int(row_lc["c"]) if row_lc else 0

    return {
        "continent_id": cont,
        "country_id": cid,
        "continent_name": cont_name,
        "country_name": cou_name,
        "continent_users": continent_users,
        "country_users": country_users,
    }


def load_user(conn: sqlite3.Connection, pk: int) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (pk,))
    return cur.fetchone()


def _user_text_country_is_india(user_row: sqlite3.Row) -> bool:
    try:
        return str(user_row["country"] or "").strip().lower() == "india"
    except (KeyError, IndexError):
        return False


def _current_location_suggests_india(conn: sqlite3.Connection, cloc: str) -> bool:
    """Indian path prefix or a village row in this geography (prototype DB is India-first)."""
    t = cloc.strip()
    if not t:
        return False
    tu = t.upper()
    if "IND/" in tu or "IND." in tu:
        return True
    if geography_has_relational_fks(conn):
        row = conn.execute("SELECT 1 FROM village WHERE id = ?", (t,)).fetchone()
        return row is not None
    return False


def user_has_full_dashboard(
    conn: sqlite3.Connection | None, user_row: sqlite3.Row
) -> bool:
    """
    India dashboard (stats, posts) vs limited global viewer.

    Mirrors ``_indian_users_predicate`` intent: honour explicit non-Indian
    ``current_country_id``, but treat ``country='India'`` and Indian village paths
    or FK lookups as qualifying when codes are missing or stale.
    """
    cc = ""
    if "current_country_id" in user_row.keys():
        raw = user_row["current_country_id"]
        if raw is not None:
            cc = str(raw).strip().upper()

    cloc = ""
    if user_row["current_location_id"] is not None:
        cloc = str(user_row["current_location_id"]).strip()

    # Registration selected a non-India current country — no override.
    if cc and cc != "IND":
        return False

    if cc == "IND":
        return True

    if _user_text_country_is_india(user_row):
        return True

    if conn is not None and _current_location_suggests_india(conn, cloc):
        return True

    # Backward-compat: path-only installs without FK columns when conn not passed.
    if conn is None and cloc:
        cu = cloc.upper()
        return "IND/" in cu or "IND." in cu

    return False


def gender_letter_account(gender: str | None) -> str:
    g = (gender or "").strip()
    if g == "Male":
        return "M"
    if g == "Female":
        return "F"
    return "O"


def age_category_account_code(age_group: str | None) -> str:
    ag = (age_group or "").strip()
    life_map = {"Balak": "A1", "Yuvak": "A2", "Vridh": "A3", "Sanyas": "A4"}
    if ag in life_map:
        return life_map[ag]
    try:
        idx = LEGACY_NUMERIC_AGE_GROUP_ORDER.index(ag)
    except ValueError:
        return "AX"
    return f"A{idx + 1}"


def compute_user_account_id(user_row: sqlite3.Row) -> str:
    """Display ID: initials + gender-age-element-sun + timeline + placeholder boxes."""

    first = str(user_row["first_name"] or "").strip()
    last = str(user_row["last_name"] or "").strip()
    f1 = (first[:1].upper() or "?")
    l1 = (last[:1].upper() or "?")
    gchr = gender_letter_account(user_row["gender"])

    age_c = age_category_account_code(user_row["age_group"])
    elt = str(user_row["element"] or "").strip()
    elt_code = ELEMENT_ACCOUNT_CODE.get(elt)
    if not elt_code:
        letters = "".join(c for c in elt.upper() if c.isalpha())
        elt_code = ((letters + "??")[:2]) or "??"

    sun_stripped = str(user_row["sun_sign"] or "").strip()
    sig2 = SUN_SIGN_TWO_LETTER.get(sun_stripped)
    if not sig2:
        letters_s = "".join(c for c in sun_stripped if c.isalpha())
        sig2 = ((letters_s[:2] + "??")[:2]) or "??"

    core = f"{f1}{l1}{gchr}-{age_c}{elt_code}{sig2}"
    return f"{core} [EAR-CON-IND] - [A-B-C-D]"


def active_element_corner(element: str | None) -> str:
    return ELEMENT_CORNER_POSITION.get(str(element or "").strip(), "")


def infer_geo_scope_from_full_id(conn: sqlite3.Connection, full_id: str) -> str | None:
    fid = (full_id or "").strip()
    if not fid:
        return None
    for scope in (
        "village",
        "tehsil",
        "district",
        "state",
        "zone",
        "country",
        "continent",
        "earth",
    ):
        tbl = GEO_ROUTE_TABLE[scope]
        if not _geo_table_exists(conn, tbl):
            continue
        row = conn.execute(f"SELECT 1 FROM {tbl} WHERE id = ?", (fid,)).fetchone()
        if row:
            return scope
    return None


def current_location_hierarchy(
    conn: sqlite3.Connection, village_full_id: str
) -> list[dict[str, str]]:
    """State, District, Tehsil, Village metadata inferred from current village id."""
    vf = (village_full_id or "").strip()
    vraw = raw_path(vf)
    traw = path_parent_suffix(vraw)
    draw = path_parent_suffix(traw) if traw else None
    sraw = geo_path_to_state_path(vraw)

    state_id = full_id_from_raw(sraw) if sraw else ""
    district_id = full_id_from_raw(draw) if draw else ""
    tehsil_id = full_id_from_raw(traw) if traw else ""
    village_id = vf

    def loc(scope: str, fid: str) -> dict[str, str]:
        table = GEO_ROUTE_TABLE[scope]
        safe_id = (fid or "").strip()
        nm = _geo_row_optional_meta(conn, table, safe_id)["name"] if safe_id else "-"
        return {
            "scope": scope,
            "id": safe_id,
            "name": str(nm),
            "url": build_geo_public_url(scope, safe_id) if safe_id else "#",
        }

    return [
        loc("state", state_id),
        loc("district", district_id),
        loc("tehsil", tehsil_id),
        loc("village", village_id),
    ]


def user_public_allowed_location_ids(
    conn: sqlite3.Connection, user_row: sqlite3.Row
) -> set[str]:
    """IDs in the logged-in user's current village hierarchy (State…Village)."""
    cloc = user_row["current_location_id"]
    if cloc is None or str(cloc).strip() == "":
        return set()
    hier = current_location_hierarchy(conn, str(cloc).strip())
    return {str(item["id"]).strip() for item in hier if str(item.get("id") or "").strip()}


def user_effective_country_id(
    conn: sqlite3.Connection, user_row: sqlite3.Row
) -> str | None:
    try:
        cid = str(user_row["current_country_id"] or "").strip().upper()
    except (KeyError, IndexError):
        cid = ""
    if cid:
        return cid
    try:
        cloc = str(user_row["current_location_id"] or "").strip()
    except (KeyError, IndexError):
        cloc = ""
    if _current_location_suggests_india(conn, cloc):
        return "IND"
    return None


def user_dashboard_geo_displays(
    conn: sqlite3.Connection, user_row: sqlite3.Row
) -> dict[str, Any]:
    """Labels and synthetic global path for dashboard timelines."""
    try:
        cloc = str(user_row["current_location_id"] or "").strip()
    except (KeyError, IndexError):
        cloc = ""

    ctry_id = user_effective_country_id(conn, user_row)
    try:
        raw_ctry = str(user_row["current_country_id"] or "").strip().upper()
    except (KeyError, IndexError):
        raw_ctry = ""
    if raw_ctry:
        ctry_id = raw_ctry

    try:
        cont_id = str(user_row["current_continent_id"] or "").strip().upper()
    except (KeyError, IndexError):
        cont_id = ""

    ctry_name: str | None = None
    if ctry_id and _geo_table_exists(conn, "country"):
        crow = conn.execute(
            "SELECT name, continent_id FROM country WHERE id = ?", (ctry_id,)
        ).fetchone()
        if crow:
            ctry_name = str(crow["name"])
            if not cont_id:
                cont_id = str(crow["continent_id"] or "").strip().upper()

    cont_name: str | None = None
    if cont_id and _geo_table_exists(conn, "continent"):
        conr = conn.execute(
            "SELECT name FROM continent WHERE id = ?", (cont_id,)
        ).fetchone()
        if conr:
            cont_name = str(conr["name"])

    if ctry_id == "IND" and not cont_id:
        cont_id = "AS"
        if _geo_table_exists(conn, "continent"):
            conr = conn.execute(
                "SELECT name FROM continent WHERE id = ?", (cont_id,)
            ).fetchone()
            if conr:
                cont_name = str(conr["name"])

    earth_slug = "0"
    if cont_id and ctry_id:
        global_id = f"{PATH_PREFIX}{earth_slug}.{cont_id}.{ctry_id}"
    elif ctry_id:
        global_id = f"{PATH_PREFIX}{earth_slug}.?.{ctry_id}"
    elif cont_id:
        global_id = f"{PATH_PREFIX}{earth_slug}.{cont_id}.?"
    else:
        global_id = f"{PATH_PREFIX}{earth_slug}.?.?"

    show_zone_tab = ctry_id == "IND"

    return {
        "user_current_location_id_display": cloc,
        "user_global_id_display": global_id,
        "user_continent_id": cont_id or None,
        "user_continent_name": cont_name,
        "user_country_id": ctry_id or None,
        "user_country_name": ctry_name,
        "user_show_zone_tab": show_zone_tab,
    }


def _author_display_name(first_name: str, last_name: str) -> str:
    first = (first_name or "").strip()
    last_initial = (last_name or "").strip()[:1]
    if first and last_initial:
        return f"{first} {last_initial}."
    return first or last_initial or "Unknown"


COLLECTIVE_BOARD_LEVELS = (
    "village",
    "tehsil",
    "district",
    "state",
    "country",
    "continent",
    "earth",
)

COLLECTIVE_BOARD_LEVEL_OFFSETS = {
    "personal": 0,
    "village": 7,
    "tehsil": 14,
    "district": 21,
    "state": 28,
    "country": 35,
    "continent": 42,
    "earth": 49,
}


def _post_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _post_passed_level(previous_levels: str, level: str) -> bool:
    target = level.strip().lower()
    tokens = [
        item.strip().split(":", 1)[0].lower()
        for item in (previous_levels or "").split(",")
        if item.strip()
    ]
    return target in tokens


def _collective_board_progress(post: sqlite3.Row, level: str, state: str) -> dict[str, Any]:
    created_at = _post_datetime(post["created_at"])
    level_start = _post_datetime(post["level_start_time"])
    duration_days = int(social_core.LEVEL_DAYS_BY_LEVEL.get(level, social_core.LEVEL_DAYS))
    if state == "live":
        start_dt = level_start or created_at or datetime.now(timezone.utc)
    elif str(post["status"] or "") == "frozen" and _post_passed_level(str(post["previous_levels"] or ""), level):
        start_dt = level_start or created_at or datetime.now(timezone.utc)
    else:
        base = created_at or level_start or datetime.now(timezone.utc)
        start_dt = base + timedelta(days=COLLECTIVE_BOARD_LEVEL_OFFSETS.get(level, 0))
    end_dt = start_dt + timedelta(days=duration_days)
    now = datetime.now(timezone.utc)
    total_seconds = max(1.0, (end_dt - start_dt).total_seconds())
    elapsed_seconds = (now - start_dt).total_seconds()
    if state == "frozen":
        pct = 100.0
        remaining_days = 0
    else:
        pct = max(0.0, min(100.0, (elapsed_seconds / total_seconds) * 100.0))
        remaining_seconds = max(0.0, (end_dt - now).total_seconds())
        remaining_days = int((remaining_seconds + 86399) // 86400)
    return {
        "start_date": _iso_dt(start_dt),
        "end_date": _iso_dt(end_dt),
        "duration_days": duration_days,
        "percent": round(pct, 1),
        "remaining_days": remaining_days,
    }


def _post_vote_counts(conn: sqlite3.Connection, post_id: int) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT vote_value, COUNT(*) AS c
        FROM post_votes
        WHERE post_id = ?
        GROUP BY vote_value
        """,
        (post_id,),
    ).fetchall()
    counts = {1: 0, 0: 0, -1: 0}
    for row in rows:
        value = int(row["vote_value"])
        if value in counts:
            counts[value] = int(row["c"] or 0)
    return {
        "positive": counts[1],
        "neutral": counts[0],
        "negative": counts[-1],
    }


def _collective_board_post_json(
    r: sqlite3.Row,
    conn: sqlite3.Connection,
    current_user: sqlite3.Row,
    board_level: str,
    board_state: str,
) -> dict[str, Any] | None:
    """Render a post row for a board response.

    Defensive guard: a post whose ``current_level`` is still ``'personal'``
    may appear on the author's PCB or on connected members' PCB (family /
    social / linked nuclear relatives). Such rows must never leak through a
    collective / public geo board response — returning ``None`` skips them.
    """
    raw_level = str(r["current_level"] or "").strip().lower()
    if raw_level.startswith("personal") and board_level != "personal":
        return None
    # Deleted posts never appear anywhere — author-deleted or admin-removed.
    if str(r["status"] or "").strip().lower() == "deleted":
        return None
    d = post_row_to_feed_json(r, conn, current_user)
    user_vote = d["current_user_vote"]
    d["vote_counts"] = _post_vote_counts(conn, int(d["id"]))
    d["has_voted"] = user_vote is not None
    d["can_vote"] = bool(
        board_state == "live"
        and d["status"] == "live"
        and not d["is_own_post"]
        and user_vote is None
        and social_core.user_in_post_vote_scope(conn, r, current_user)
    )
    d["board_level"] = board_level
    d["board_state"] = board_state
    d["progress"] = _collective_board_progress(r, board_level, board_state)
    # Deletion eligibility for the UI. The author can always delete their own
    # post within 24h; an admin can delete any post at any time. When an
    # admin deletes someone else's post we require a reason and notify the
    # author — that's the "with reason" mode. Authors and admins deleting
    # their own posts use the simple confirm-only flow.
    created = social_core._parse_sqlite_datetime(r["created_at"])
    now = datetime.now(timezone.utc)
    within = bool(
        created
        and now <= created + timedelta(hours=POST_AUTHOR_DELETE_HOURS)
    )
    viewer_is_admin = is_admin_user(current_user)
    is_own = d["is_own_post"]
    d["viewer_is_admin"] = viewer_is_admin
    d["can_author_delete"] = bool(
        (is_own and within) or (is_own and viewer_is_admin)
    )
    d["can_admin_delete"] = bool(viewer_is_admin and not is_own)
    return d


def _filter_board_posts(
    rows: list[sqlite3.Row],
    conn: sqlite3.Connection,
    current_user: sqlite3.Row,
    board_level: str,
    board_state: str,
) -> list[dict[str, Any]]:
    """Render board rows skipping any that the JSON helper rejects."""
    posts: list[dict[str, Any]] = []
    for r in rows:
        d = _collective_board_post_json(r, conn, current_user, board_level, board_state)
        if d is None:
            continue
        posts.append(d)
    return posts


def post_row_to_feed_json(
    r: sqlite3.Row,
    conn: sqlite3.Connection | None = None,
    current_user: sqlite3.Row | None = None,
) -> dict[str, Any]:
    d = dict(r)
    current_pid = str(current_user["private_id"]) if current_user is not None else ""
    user_vote = d.get("current_user_vote")
    is_own_post = bool(current_pid and current_pid == str(d.get("user_private_id") or ""))
    can_vote = False
    if conn is not None and current_user is not None:
        can_vote = (
            str(d.get("status") or "") == "live"
            and not is_own_post
            and social_core.user_in_post_vote_scope(conn, r, current_user)
        )
    return {
        "id": int(d["id"]),
        "content": str(d.get("content") or ""),
        "author_public_id": str(d.get("author_public_id") or ""),
        "author_first": str(d.get("author_first") or ""),
        "author_last": str(d.get("author_last") or ""),
        "author_display_name": _author_display_name(
            str(d.get("author_first") or ""),
            str(d.get("author_last") or ""),
        ),
        "author_private_id": str(d.get("user_private_id") or d.get("author_private_id") or ""),
        "author_full_name": (
            f"{str(d.get('author_first') or '').strip()} {str(d.get('author_last') or '').strip()}"
        ).strip(),
        "author_age": int(d["author_age"]) if d.get("author_age") not in (None, "") else None,
        "author_gender": str(d.get("author_gender") or ""),
        "author_location_name": (
            location_display_label(conn, str(d.get("author_current_location_id")))
            if conn is not None and d.get("author_current_location_id")
            else ""
        ),
        "current_level": str(d.get("current_level") or ""),
        "status": str(d.get("status") or ""),
        "total_score": int(d.get("total_score") or 0),
        "created_at": str(d.get("created_at") or ""),
        "current_user_vote": None if user_vote is None else int(user_vote),
        "can_vote": can_vote,
        "is_own_post": is_own_post,
    }


def _session_sync_admin_flag(user: sqlite3.Row | None) -> None:
    if user is None:
        session["is_admin"] = 0
        return
    try:
        session["is_admin"] = 1 if int(user["is_admin"] or 0) else 0
    except (KeyError, TypeError, ValueError):
        session["is_admin"] = 0


def api_global_locations_children_rows(
    conn: sqlite3.Connection, parent_id: str
) -> list[dict[str, str]]:
    pid = (parent_id or "").strip()
    pup = pid.upper()
    if pup == "EARTH":
        if _geo_table_exists(conn, "continent"):
            cur = conn.execute(
                "SELECT id, name FROM continent ORDER BY name COLLATE NOCASE ASC"
            )
            return [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
        return [{"id": "AS", "name": "Asia"}]
    if _geo_table_exists(conn, "country"):
        crow = conn.execute(
            "SELECT 1 FROM continent WHERE id = ?",
            (pid,),
        ).fetchone()
        if crow:
            cur = conn.execute(
                "SELECT id, name FROM country WHERE continent_id = ? "
                "ORDER BY name COLLATE NOCASE ASC",
                (pid,),
            )
            return [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
    if pid.upper() == "IND" and _geo_table_exists(conn, "zone"):
        cur = conn.execute("SELECT id, name FROM zone ORDER BY name COLLATE NOCASE ASC")
        return [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
    return []


def _unauthorized_api_response():
    """Return JSON (never HTML) for unauthenticated API requests."""
    return jsonify({"error": "Unauthorized"}), 401


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        pk = session.get("user_pk")
        if not pk:
            if (request.path or "").startswith("/api/"):
                return _unauthorized_api_response()
            return redirect(url_for("login", next=request.path))
        conn = get_db()
        user = load_user(conn, int(pk))
        if not user:
            session.clear()
            if (request.path or "").startswith("/api/"):
                return _unauthorized_api_response()
            return redirect(url_for("login"))
        g.current_user = user
        _session_sync_admin_flag(user)
        return view(*args, **kwargs)

    return wrapped


@app.before_request
def _before_request() -> None:
    """
    Schema/bootstrap only — no authentication gate here (403 never comes from this hook).
    Skips DB work for static assets and the lightweight /debug/check diagnostic.
    """
    if request.endpoint and str(request.endpoint).startswith("static"):
        return
    # Public diagnostic — no DB so /debug/check works even if migrations fail.
    if request.path == "/debug/check":
        return
    conn = get_db()
    ensure_users_table(conn)
    ensure_users_country_column(conn)
    migrate_users_app_extensions(conn)
    migrate_messages_table(conn)
    migrate_connection_requests_table(conn)
    migrate_connection_requests_accepted_at(conn)
    migrate_connection_requests_family_member_type(conn)
    migrate_connection_requests_request_member_profile(conn)
    migrate_family_tables(conn)
    migrate_family_relationships_table(conn)
    migrate_family_removal_requests_table(conn)
    migrate_link_requests_table(conn)
    migrate_user_family_setup_table(conn)
    migrate_user_education_table(conn)
    migrate_user_work_table(conn)
    migrate_connection_requests_life_stage(conn)
    election_scheduler.migrate_election_tables(conn)
    try:
        election_scheduler.process_election_cycles(
            conn, send_system_message_fn=send_system_message
        )
    except sqlite3.Error:
        app.logger.exception("election cycle processing failed")
    social_core.ensure_wallet_and_vote_tables(conn)
    social_core.ensure_posts_escalation_columns(conn)
    migrate_posts_deletion_columns(conn)
    global _last_escalation_check
    now = time.monotonic()
    if now - _last_escalation_check >= 60:
        _last_escalation_check = now
        try:
            social_core.escalate_posts(conn)
        except sqlite3.Error:
            app.logger.exception("post escalation checkpoint failed")


def _geo_statistics_page(scope: str, geo_id: str) -> str:
    conn = get_db()
    tbl = GEO_ROUTE_TABLE[scope]
    row = conn.execute(
        f"SELECT id FROM {tbl} WHERE id = ?", (geo_id.strip(),)
    ).fetchone()
    if row is None:
        abort(404)

    wallet_balance = 0
    wallet_key = ""
    wallet_account_id = ""

    bundle = location_statistics_bundle(conn, scope, geo_id)
    crumbs = build_location_breadcrumbs(conn, scope, geo_id)
    meta = _geo_row_optional_meta(conn, tbl, geo_id.strip())
    wallet_scopes = (
        "village",
        "tehsil",
        "district",
        "state",
        "country",
        "continent",
        "earth",
    )
    if scope in wallet_scopes:
        direct_wallet_id = geo_id.strip()
        direct_wallet_row = conn.execute(
            """
            SELECT balance FROM wallets
            WHERE owner_type = 'location' AND owner_id = ?
            """,
            (direct_wallet_id,),
        ).fetchone()
        wallet_key = (
            direct_wallet_id
            if direct_wallet_row
            else social_core.location_wallet_key(scope, geo_id)
        )
        social_core.ensure_wallet(conn, "location", wallet_key)
        wallet_account_id = direct_wallet_id
        wallet_balance = social_core.get_wallet_balance(
            conn, "location", wallet_key
        )
    chart_prefix = (
        "geo-" + scope + "-" + hashlib.md5(geo_id.encode("utf-8")).hexdigest()[:12]
    )
    admin_members_list_url: str | None = None
    if int(session.get("is_admin") or 0):
        admin_members_list_url = url_for(
            "admin_location_members",
            location_type=scope,
            location_id=geo_id.strip(),
        )
    return render_template(
        "location.html",
        scope=scope,
        location_name=meta["name"],
        breadcrumbs=crumbs,
        stats=bundle,
        geo_meta=meta,
        chart_prefix=chart_prefix,
        wallet_balance=wallet_balance,
        wallet_key=wallet_key,
        wallet_account_id=wallet_account_id,
        signs_by_element=SIGNS_BY_ELEMENT,
        admin_members_list_url=admin_members_list_url,
    )


@app.route("/india")
def location_india():
    conn = get_db()
    if _geo_table_exists(conn, "earth"):
        return redirect(url_for("location_country", country_id="IND"), code=307)
    bundle = location_statistics_bundle(conn, "india", None)
    crumbs = build_location_breadcrumbs(conn, "india", None)
    wallet_key = social_core.location_wallet_key("country", "IND")
    direct_wallet_row = conn.execute(
        """
        SELECT balance FROM wallets
        WHERE owner_type = 'location' AND owner_id = ?
        """,
        ("IND",),
    ).fetchone()
    if direct_wallet_row:
        wallet_key = "IND"
    social_core.ensure_wallet(conn, "location", wallet_key)
    wallet_balance = social_core.get_wallet_balance(conn, "location", wallet_key)
    admin_members_list_url: str | None = None
    if int(session.get("is_admin") or 0):
        admin_members_list_url = url_for(
            "admin_location_members",
            location_type="india",
            location_id="IND",
        )
    return render_template(
        "location.html",
        scope="india",
        location_name="India (national)",
        breadcrumbs=crumbs,
        stats=bundle,
        geo_meta=None,
        chart_prefix="geo-india",
        wallet_balance=wallet_balance,
        wallet_key=wallet_key,
        wallet_account_id="IND",
        signs_by_element=SIGNS_BY_ELEMENT,
        admin_members_list_url=admin_members_list_url,
    )


@app.route("/location/earth/<path:earth_id>")
def location_earth(earth_id: str):
    return _geo_statistics_page("earth", earth_id)


@app.route("/location/continent/<path:continent_id>")
def location_continent(continent_id: str):
    return _geo_statistics_page("continent", continent_id)


@app.route("/location/country/<path:country_id>")
def location_country(country_id: str):
    return _geo_statistics_page("country", country_id)


@app.route("/location/zone/<path:zone_id>")
def location_zone(zone_id: str):
    return _geo_statistics_page("zone", zone_id)


@app.route("/location/state/<path:state_id>")
def location_state(state_id: str):
    return _geo_statistics_page("state", state_id)


@app.route("/location/district/<path:district_id>")
def location_district(district_id: str):
    return _geo_statistics_page("district", district_id)


@app.route("/location/tehsil/<path:tehsil_id>")
def location_tehsil(tehsil_id: str):
    return _geo_statistics_page("tehsil", tehsil_id)


@app.route("/location/village/<path:village_id>")
def location_village(village_id: str):
    return _geo_statistics_page("village", village_id)


@app.route("/api/geo-search")
def api_geo_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify([])
    conn = get_db()
    hits = geo_search(conn, q)
    payload = [
        {
            "kind": h["kind"],
            "id": h["id"],
            "name": h["name"],
            "url": build_geo_public_url(h["kind"], h["id"]),
        }
        for h in hits
    ]
    return jsonify(payload)


@app.get("/api/current_time")
def api_current_time():
    """
    JSON for the global time bar: clock, weekday, solar month, lunar month/paksha/tithi.
    Never raises: on DB/calendar errors returns safe fallback JSON (still HTTP 200).
    """
    try:
        return jsonify(calendar_time.get_current_time_payload(get_db()))
    except Exception:
        app.logger.exception("api_current_time: failed to build calendar payload")
        return jsonify(
            calendar_time.get_current_time_fallback_payload(
                note="Server could not read calendar data."
            )
        )


@app.get("/api/advanced_time")
def api_advanced_time():
    """IST bilingual calendar payload for the dashboard time-box (ephem + DB lunar month)."""
    try:
        return jsonify(calendar_time.get_advanced_time_payload(get_db()))
    except Exception:
        app.logger.exception("api_advanced_time")
        return jsonify({"error": "Could not compute advanced time.", "ephem_available": False}), 500


def escalate_posts(conn: sqlite3.Connection) -> None:
    """
    Advance or finalise live posts and credit Qoins. **Not** called automatically
    on each HTTP request — call from cron, APScheduler, or a one-off script, e.g.::

        import sqlite3
        from pathlib import Path
        from app import DB_PATH, escalate_posts

        c = sqlite3.connect(DB_PATH)
        try:
            escalate_posts(c)
        finally:
            c.close()
    """
    social_core.escalate_posts(conn)


def normalize_zodiac_sign(raw: str) -> str | None:
    s = (raw or "").strip().replace("_", " ")
    if not s:
        return None
    sl = s.casefold()
    for z in ZODIAC_SIGNS_ORDER:
        if z.casefold() == sl:
            return z
    return None


@app.get("/api/zodiac_members/<path:sign>")
def api_zodiac_members(sign: str):
    z = normalize_zodiac_sign(sign.replace("-", " "))
    if not z:
        return jsonify({"error": "Unknown sign"}), 400
    conn = get_db()
    total = conn.execute(
        "SELECT COUNT(*) AS c FROM users WHERE sun_sign = ?", (z,)
    ).fetchone()
    count = int(total["c"]) if total else 0
    cur = conn.execute(
        """
        SELECT first_name, last_name, public_id
        FROM users WHERE sun_sign = ?
        ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE
        """,
        (z,),
    )
    members = [
        {
            "first_name": str(r["first_name"]),
            "last_name": str(r["last_name"]),
            "public_id": str(r["public_id"]),
        }
        for r in cur
    ]
    return jsonify(
        {
            "sign": z,
            "count": count,
            "members": members,
            "council": [],
            "council_message": "No council members yet.",
        }
    )


@app.get("/api/location/count")
@login_required
def api_location_count():
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    location_id = (request.args.get("location_id") or "").strip()
    if not location_id:
        return jsonify({"error": "location_id is required"}), 400

    scope = infer_geo_scope_from_full_id(conn, location_id)
    if not scope:
        return jsonify({"error": "location_id not found"}), 404

    pred, tup = user_location_predicate(conn, scope, location_id)
    row = conn.execute(f"SELECT COUNT(*) AS c FROM users u WHERE ({pred})", tup).fetchone()
    return jsonify({"count": int(row["c"]) if row else 0})


def _api_create_post_core() -> tuple[Any, int]:
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    user_row = g.current_user
    payload = request.get_json(silent=True) or {}
    location_id = str(user_row["current_location_id"] or "").strip()
    content = str(
        payload.get("content") or request.form.get("content") or ""
    ).strip()

    if not location_id:
        return jsonify({"error": "Your current village is required to create a post"}), 400
    if not content:
        return jsonify({"error": "Post content cannot be empty"}), 400
    if len(content) > 500:
        return jsonify({"error": "Post content is too long (max 500 characters)"}), 400
    if infer_geo_scope_from_full_id(conn, location_id) != "village":
        return jsonify({"error": "Your current location must be a village"}), 400

    hier = current_location_hierarchy(conn, location_id)
    origins = social_core.origins_from_hierarchy(
        hier,
        str(user_row["current_country_id"] or "IND"),
        str(user_row["current_continent_id"] or "AS"),
    )
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO posts (
            user_private_id, location_id, content, current_level, level_start_time,
            status, total_score, previous_levels, origin_village_id, origin_tehsil_id, origin_district_id,
            origin_state_id, origin_country_id, origin_continent_id
        ) VALUES (?,?,?,?,?,?,0,?,?,?,?,?,?,?)
        """,
        (
            str(user_row["private_id"]),
            location_id,
            content,
            "personal",
            ts,
            "live",
            "",
            origins["village"],
            origins["tehsil"],
            origins["district"],
            origins["state"],
            origins["country"],
            origins["continent"],
        ),
    )
    post_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    conn.commit()
    # IMPORTANT: Do NOT run escalation here. A brand-new post is < 7 days old
    # and is not eligible for escalation anyway. Calling escalate_posts() at
    # creation time risks reacting to pre-existing stale rows with old
    # level_start_time values (e.g. from earlier test runs) and pushing them
    # onto the Village CVB the instant somebody types a new PCB post — that
    # is the visibility regression the user has been reporting. Escalation
    # still runs on a 60-second cadence from ``_before_request``.
    row = conn.execute(
        """
        SELECT p.*, u.public_id AS author_public_id, u.first_name AS author_first,
               u.last_name AS author_last, u.age AS author_age,
               u.gender AS author_gender, u.current_location_id AS author_current_location_id,
               v.vote_value AS current_user_vote
        FROM posts p
        JOIN users u ON u.private_id = p.user_private_id
        LEFT JOIN post_votes v
          ON v.post_id = p.id AND v.voter_private_id = ?
        WHERE p.id = ?
        """,
        (str(user_row["private_id"]), post_id),
    ).fetchone()
    # The post we just inserted is personal — render it for the author's PCB
    # response using board_level='personal' so the JSON helper does not strip
    # the personal row.
    post = _collective_board_post_json(row, conn, user_row, "personal", "live") if row else None
    return jsonify({"ok": True, "message": "Post saved successfully", "post": post}), 200


@app.post("/api/post/create")
@login_required
def api_post_create():
    body, code = _api_create_post_core()
    return body, code


@app.post("/api/post/delete/<int:post_id>")
@login_required
def api_post_delete(post_id: int):
    """Soft-delete a post.

    * Author may delete within :data:`POST_AUTHOR_DELETE_HOURS` of creation;
      no reason needed.
    * Admin may delete any post at any time. When the admin deletes someone
      else's post, a ``reason`` is required and is delivered to the author
      as a system message in their Private Account Inbox.
    """
    conn = get_db()
    me = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()

    post = conn.execute(
        "SELECT * FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    if not post:
        return jsonify({"error": "Post not found"}), 404

    # Already gone — treat as success so the UI converges.
    if str(post["status"] or "").lower() == "deleted" or post["deleted_at"]:
        return jsonify({"ok": True, "already_deleted": True})

    author_pid = str(post["user_private_id"] or "")
    is_author = (author_pid == me)
    is_admin = is_admin_user(g.current_user)

    created = social_core._parse_sqlite_datetime(post["created_at"])
    now = datetime.now(timezone.utc)
    within_author_window = bool(
        created
        and now <= created + timedelta(hours=POST_AUTHOR_DELETE_HOURS)
    )

    if not is_admin:
        if not is_author:
            return jsonify({"error": "Only the author or an admin can delete this post"}), 403
        if not within_author_window:
            return jsonify({
                "error": (
                    f"Posts can only be deleted by their author within "
                    f"{POST_AUTHOR_DELETE_HOURS} hours of creation."
                )
            }), 403

    # Admin acting on someone else's post must supply a reason and notify them.
    notify_author = bool(is_admin and not is_author)
    if notify_author and not reason:
        return jsonify({"error": "Admin deletions require a reason"}), 400

    now_iso = now.strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE posts
           SET status = 'deleted',
               deleted_at = ?,
               deleted_by = ?,
               delete_reason = ?
         WHERE id = ?
        """,
        (now_iso, me, reason or None, post_id),
    )

    if notify_author:
        author_label = (
            f"{str(g.current_user['first_name'] or '').strip()} "
            f"{str(g.current_user['last_name'] or '').strip()}"
        ).strip() or me
        body = (
            f"An administrator ({author_label}) has removed one of your posts.\n\n"
            f"Reason provided:\n{reason}\n\n"
            f"Original post preview:\n{str(post['content'] or '')[:280]}"
        )
        send_system_message(
            conn,
            author_pid,
            "Your post has been deleted by Admin",
            body,
        )
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/post/vote")
@login_required
def api_post_vote():
    payload = request.get_json(silent=True) or {}
    try:
        post_id = int(payload.get("post_id") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "post_id required"}), 400
    try:
        vote_value = int(payload.get("vote_value"))
    except (TypeError, ValueError):
        return jsonify({"error": "vote_value must be -1, 0, or 1"}), 400
    conn = get_db()
    ok, msg = social_core.user_vote_on_post(
        conn, post_id, str(g.current_user["private_id"]), vote_value
    )
    if not ok:
        return jsonify({"error": msg}), 400
    row = conn.execute(
        "SELECT total_score FROM posts WHERE id = ?", (post_id,)
    ).fetchone()
    ts = int(row["total_score"]) if row else 0
    social_core.escalate_posts(conn)
    return jsonify(
        {
            "ok": True,
            "message": msg,
            "total_score": ts,
            "current_user_vote": vote_value,
            "vote_counts": _post_vote_counts(conn, post_id),
            "has_voted": True,
        }
    )


def _validate_collective_board_request(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
    level: str,
    location_id: str,
) -> tuple[bool, str, str]:
    if level not in COLLECTIVE_BOARD_LEVELS:
        return False, location_id, "level is required"
    if level == "earth":
        return True, location_id or "0", ""
    if not location_id:
        return False, location_id, "location_id is required"

    allowed_profile_locations = user_public_allowed_location_ids(conn, user_row)
    if level in {"village", "tehsil", "district", "state"}:
        if location_id not in allowed_profile_locations:
            return False, location_id, "location_id must be your profile hierarchy"
        scope = infer_geo_scope_from_full_id(conn, location_id)
        if scope != level:
            return False, location_id, "level and location_id do not match"
    elif level == "country":
        user_country = str(user_row["current_country_id"] or "").strip()
        if location_id != user_country:
            return False, location_id, "location_id must match your country"
    elif level == "continent":
        user_continent = str(user_row["current_continent_id"] or "").strip()
        if location_id != user_continent:
            return False, location_id, "location_id must match your continent"
    return True, location_id, ""


def _collective_board_origin_column(level: str) -> str | None:
    return {
        "village": "origin_village_id",
        "tehsil": "origin_tehsil_id",
        "district": "origin_district_id",
        "state": "origin_state_id",
        "country": "origin_country_id",
        "continent": "origin_continent_id",
        "earth": None,
    }.get(level)


def _collective_board_never_personal_sql(alias: str = "p") -> str:
    """SQL fragment: exclude any post still in a personal PCB phase.

    Collective boards (Village CVB and above) must not surface rows whose
    level is ``personal``, ``personal_history``, or legacy ``personal_*``
    prefixes — even if ``current_level = ?`` were mis-bound elsewhere.
    """
    return (
        f" AND (NOT (LOWER(TRIM(COALESCE({alias}.current_level,''))) IN "
        f"('personal','personal_history')) "
        f"AND NOT (LOWER(TRIM(COALESCE({alias}.current_level,''))) "
        f"LIKE 'personal\\_%' ESCAPE '\\'))"
    )


def _posts_not_deleted_sql(conn: sqlite3.Connection, alias: str = "p") -> str:
    if "deleted_at" in _table_columns(conn, "posts"):
        return f" AND ({alias}.deleted_at IS NULL)"
    return ""


def _collective_board_rows(
    conn: sqlite3.Connection,
    level: str,
    location_id: str,
    board_state: str,
    voter_private_id: str,
) -> list[sqlite3.Row]:
    # Hard guard: a Collective Board (Village CVB and above) must NEVER include
    # posts that are still at the 'personal' level — those belong only to the
    # author's Personal Account (PCB) for the first 7 days.
    if level == "personal":
        return []
    col = _collective_board_origin_column(level)
    location_clause = ""
    if col is not None:
        location_clause = f"AND TRIM(p.{col}) = ?"

    never_p = _collective_board_never_personal_sql("p")
    not_del = _posts_not_deleted_sql(conn, "p")
    if board_state == "live":
        query = f"""
            SELECT p.*, u.public_id AS author_public_id, u.first_name AS author_first,
                   u.last_name AS author_last, u.age AS author_age,
                   u.gender AS author_gender, u.current_location_id AS author_current_location_id,
                   v.vote_value AS current_user_vote
            FROM posts p
            JOIN users u ON u.private_id = p.user_private_id
            LEFT JOIN post_votes v
              ON v.post_id = p.id AND v.voter_private_id = ?
            WHERE p.status = 'live'
              AND TRIM(p.current_level) = ?
              AND p.current_level != 'personal'
              AND p.current_level NOT LIKE 'personal\\_%' ESCAPE '\\'
              {never_p}
              {not_del}
              {location_clause}
            ORDER BY datetime(p.created_at) DESC, p.id DESC
            LIMIT 100
        """
        params: list[Any] = [voter_private_id, level]
        if col is not None:
            params.append(location_id.strip())
        return list(conn.execute(query, tuple(params)))

    query = f"""
        SELECT p.*, u.public_id AS author_public_id, u.first_name AS author_first,
               u.last_name AS author_last, u.age AS author_age,
               u.gender AS author_gender, u.current_location_id AS author_current_location_id,
               v.vote_value AS current_user_vote
        FROM posts p
        JOIN users u ON u.private_id = p.user_private_id
        LEFT JOIN post_votes v
          ON v.post_id = p.id AND v.voter_private_id = ?
        WHERE p.status = 'frozen'
          AND p.freeze_level = ?
          AND TRIM(p.current_level) = ?
          AND p.current_level != 'personal'
          AND p.current_level != 'personal_history'
          {never_p}
          {not_del}
          {location_clause}
        ORDER BY datetime(p.created_at) DESC, p.id DESC
        LIMIT 100
    """
    passed_params: list[Any] = [voter_private_id, level, f"{level}_frozen"]
    if col is not None:
        passed_params.append(location_id.strip())
    return list(conn.execute(query, tuple(passed_params)))


def get_connected_user_ids(
    conn: sqlite3.Connection, user_private_id: str
) -> list[str]:
    """Private IDs (excluding self) linked via family connections or social."""
    peers = social_core.connected_peer_private_ids(conn, user_private_id)
    return sorted(peers)


def _personal_board_rows(
    conn: sqlite3.Connection,
    user_private_id: str,
    board_state: str,
) -> list[sqlite3.Row]:
    peers = social_core.connected_peer_private_ids(conn, user_private_id)
    author_ids = [str(user_private_id)] + sorted(peers)
    placeholders = ",".join("?" * len(author_ids))
    base_select = """
        SELECT p.*, u.public_id AS author_public_id, u.first_name AS author_first,
               u.last_name AS author_last, u.age AS author_age,
               u.gender AS author_gender, u.current_location_id AS author_current_location_id,
               v.vote_value AS current_user_vote
        FROM posts p
        JOIN users u ON u.private_id = p.user_private_id
        LEFT JOIN post_votes v
          ON v.post_id = p.id AND v.voter_private_id = ?
    """
    if board_state == "live":
        return list(
            conn.execute(
                base_select
                + f"""
                  WHERE p.user_private_id IN ({placeholders})
                    AND p.status = 'live'
                    AND p.current_level = 'personal'
                  ORDER BY datetime(p.created_at) DESC, p.id DESC
                  LIMIT 100
                """,
                (user_private_id, *author_ids),
            )
        )
    return list(
        conn.execute(
            base_select
            + f"""
              WHERE p.user_private_id IN ({placeholders})
                AND p.current_level != 'personal_history'
                AND (
                  p.status = 'frozen'
                  OR p.previous_levels = 'personal'
                  OR p.previous_levels LIKE 'personal,%'
                  OR p.previous_levels LIKE '%,personal'
                  OR p.previous_levels LIKE '%,personal,%'
                  OR p.previous_levels LIKE 'personal:%'
                  OR p.previous_levels LIKE '%,personal:%'
                )
              ORDER BY datetime(p.created_at) DESC, p.id DESC
              LIMIT 100
            """,
            (user_private_id, *author_ids),
        )
    )


@app.get("/api/personal_board")
@login_required
def api_personal_board():
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    social_core.escalate_posts(conn)

    board_state = (request.args.get("state") or "live").strip().lower()
    if board_state == "freeze":
        board_state = "frozen"
    if board_state not in {"live", "frozen"}:
        return jsonify({"error": "state must be live or frozen"}), 400

    pid = str(g.current_user["private_id"])
    rows = _personal_board_rows(conn, pid, board_state)
    return jsonify(
        {
            "level": "personal",
            "state": board_state,
            "posts": _filter_board_posts(
                rows, conn, g.current_user, "personal", board_state
            ),
        }
    )


@app.get("/api/posts/personal")
@login_required
def api_posts_personal():
    """Alias for :func:`api_personal_board` (PCB feed including connected authors)."""
    return api_personal_board()


def _user_connection_summary(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    loc_id = str(row["current_location_id"] or "").strip()
    item = {
        "private_id": str(row["private_id"]),
        "public_id": str(row["public_id"]),
        "name": f'{row["first_name"]} {row["last_name"]}'.strip(),
        "age": int(row["age"]) if row["age"] is not None else None,
        "gender": str(row["gender"] or ""),
        "location_name": location_display_label(conn, loc_id) if loc_id else "",
    }
    keys = row.keys()
    if "relationship" in keys:
        item["relationship"] = str(row["relationship"] or "")
    if "request_id" in keys and row["request_id"] is not None:
        item["request_id"] = int(row["request_id"])
    return item


@app.get("/api/users/suggest")
@login_required
def api_users_suggest():
    conn = get_db()
    q = (request.args.get("public_id_prefix") or "").strip()
    if len(q) < 2:
        return jsonify({"users": []})
    cur = conn.execute(
        """
        SELECT private_id, public_id, first_name, last_name, age, gender, current_location_id
        FROM users
        WHERE public_id LIKE ? COLLATE NOCASE
          AND private_id != ?
        ORDER BY public_id COLLATE NOCASE
        LIMIT 8
        """,
        (q + "%", str(g.current_user["private_id"])),
    )
    users: list[dict[str, Any]] = []
    for r in cur:
        item = _user_connection_summary(conn, r)
        item["life_stage"] = _life_stage_from_user_row(r)
        users.append(item)
    return jsonify({"users": users})


@app.get("/api/users/lookup")
@login_required
def api_users_lookup():
    """Exact ``public_id`` lookup for family forms (minimal non-sensitive fields)."""
    conn = get_db()
    pub = (request.args.get("public_id") or "").strip()
    if not pub:
        return jsonify({"error": "public_id is required"}), 400
    r = conn.execute(
        """
        SELECT public_id, first_name, last_name, age, gender, age_group
          FROM users
         WHERE public_id = ? COLLATE NOCASE
           AND private_id != ?
        """,
        (pub, str(g.current_user["private_id"])),
    ).fetchone()
    if not r:
        return jsonify({"found": False}), 200
    nm = f'{r["first_name"] or ""} {r["last_name"] or ""}'.strip()
    return jsonify(
        {
            "found": True,
            "public_id": str(r["public_id"] or ""),
            "name": nm,
            "gender": str(r["gender"] or ""),
            "life_stage": _life_stage_from_user_row(r),
            "age": int(r["age"]) if r["age"] is not None else None,
        }
    )


def _connection_status_between(
    conn: sqlite3.Connection,
    me: str,
    target_pid: str,
    request_type: str,
) -> dict[str, Any]:
    """Aggregate the relationship between ``me`` and ``target_pid`` for ``request_type``.

    The unique constraint on ``connection_requests`` is per direction so we may
    have an outgoing row AND an incoming row at the same time. The status the
    UI cares about is, in priority order:
      1. 'accepted'  — either direction has an active connection.
      2. 'pending'   — at least one direction is awaiting approval.
      3. 'rejected'  — every existing row has been rejected (resend allowed).
      4. 'none'      — no row at all.
    """
    accepted = conn.execute(
        """
        SELECT id FROM connection_requests
        WHERE request_type = ? AND status = 'accepted'
          AND ((from_user_private_id = ? AND to_user_private_id = ?)
            OR (from_user_private_id = ? AND to_user_private_id = ?))
        LIMIT 1
        """,
        (request_type, me, target_pid, target_pid, me),
    ).fetchone()
    if accepted:
        return {"status": "accepted", "connection_id": int(accepted["id"])}

    outgoing = conn.execute(
        """
        SELECT id, status FROM connection_requests
        WHERE request_type = ?
          AND from_user_private_id = ? AND to_user_private_id = ?
        """,
        (request_type, me, target_pid),
    ).fetchone()
    incoming = conn.execute(
        """
        SELECT id, status FROM connection_requests
        WHERE request_type = ?
          AND from_user_private_id = ? AND to_user_private_id = ?
        """,
        (request_type, target_pid, me),
    ).fetchone()

    if outgoing and str(outgoing["status"]) == "pending":
        return {
            "status": "pending",
            "direction": "outgoing",
            "connection_id": int(outgoing["id"]),
        }
    if incoming and str(incoming["status"]) == "pending":
        return {
            "status": "pending",
            "direction": "incoming",
            "connection_id": int(incoming["id"]),
        }
    if outgoing and str(outgoing["status"]) == "rejected":
        return {
            "status": "rejected",
            "direction": "outgoing",
            "connection_id": int(outgoing["id"]),
        }
    if incoming and str(incoming["status"]) == "rejected":
        return {
            "status": "rejected",
            "direction": "incoming",
            "connection_id": int(incoming["id"]),
        }
    return {"status": "none"}


def _connection_status_message(state: dict[str, Any], request_type: str) -> str:
    status = str(state.get("status") or "none")
    kind = "Family" if request_type == "family" else "Social"
    if status == "accepted":
        return f"You are already connected ({kind})."
    if status == "pending":
        if state.get("direction") == "outgoing":
            return "Request already sent. Waiting for approval."
        return "This user has already sent you a request — open the notification bell to accept it."
    if status == "rejected":
        return "Previous request was rejected. You may send a new request."
    return "No existing request — you can send a connection request."


@app.get("/api/connection/status")
@login_required
def api_connection_status():
    conn = get_db()
    target_public_id = (request.args.get("target_public_id") or "").strip()
    request_type = (request.args.get("type") or "").strip().lower()
    if request_type not in {"family", "social"}:
        return jsonify({"error": "type must be family or social"}), 400
    if not target_public_id:
        return jsonify({"error": "target_public_id is required"}), 400
    target = conn.execute(
        "SELECT private_id FROM users WHERE public_id = ? COLLATE NOCASE",
        (target_public_id,),
    ).fetchone()
    if not target:
        return jsonify({"error": "Account ID not found"}), 404
    me = str(g.current_user["private_id"])
    target_pid = str(target["private_id"])
    if me == target_pid:
        return jsonify(
            {
                "status": "self",
                "message": "You cannot connect to yourself.",
                "can_send": False,
            }
        )
    state = _connection_status_between(conn, me, target_pid, request_type)
    state["message"] = _connection_status_message(state, request_type)
    state["can_send"] = state["status"] in {"none", "rejected"}
    return jsonify(state)


def _connection_request_apply(
    conn: sqlite3.Connection, from_pid: str, payload: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Shared handler for ``POST /api/connection/request`` and family alias.

    Returns ``(body_dict, http_status)``. On success the caller must
    ``conn.commit()`` — this function does **not** commit.
    """
    target_public_id = str(payload.get("public_id") or "").strip()
    request_type = str(payload.get("request_type") or "").strip().lower()
    relationship = str(payload.get("relationship") or "").strip() or None
    if request_type not in {"family", "social"}:
        return {"error": "request_type must be family or social"}, 400
    family_member_type: str | None = None
    if request_type == "family":
        family_member_type = str(payload.get("family_member_type") or "").strip().lower()
        if family_member_type not in {"nuclear", "general"}:
            return {"error": "family_member_type must be nuclear or general"}, 400
    else:
        relationship = None
    if not target_public_id:
        return {"error": "public_id is required"}, 400
    target = conn.execute(
        "SELECT private_id FROM users WHERE public_id = ? COLLATE NOCASE",
        (target_public_id,),
    ).fetchone()
    if not target:
        return {"error": "Account ID not found"}, 404
    to_pid = str(target["private_id"])
    if from_pid == to_pid:
        return {"error": "You cannot connect to yourself"}, 400

    state = _connection_status_between(conn, from_pid, to_pid, request_type)
    if state["status"] in {"accepted", "pending"}:
        return (
            {
                "error": _connection_status_message(state, request_type),
                "status": state["status"],
            },
            409,
        )

    req_name = str(payload.get("member_name") or payload.get("name") or "").strip() or None
    req_age = _coerce_int(payload.get("age"))
    req_gender = str(payload.get("gender") or "").strip() or None
    req_life = str(payload.get("life_stage") or payload.get("request_member_life_stage") or "").strip() or None
    if request_type != "family":
        family_member_type = None
        req_name = None
        req_age = None
        req_gender = None
        req_life = None

    conn.execute(
        """
        INSERT INTO connection_requests (
            from_user_private_id, to_user_private_id, request_type, relationship,
            status, family_member_type,
            request_member_name, request_member_age, request_member_gender,
            request_member_life_stage
        ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
        ON CONFLICT(from_user_private_id, to_user_private_id, request_type)
        DO UPDATE SET relationship = excluded.relationship,
                      family_member_type = excluded.family_member_type,
                      request_member_name = excluded.request_member_name,
                      request_member_age = excluded.request_member_age,
                      request_member_gender = excluded.request_member_gender,
                      request_member_life_stage = excluded.request_member_life_stage,
                      status = 'pending',
                      created_at = CURRENT_TIMESTAMP
        """,
        (
            from_pid,
            to_pid,
            request_type,
            relationship,
            family_member_type,
            req_name,
            req_age,
            req_gender,
            req_life,
        ),
    )
    return {"ok": True}, 200


@app.post("/api/connection/request")
@login_required
def api_connection_request():
    conn = get_db()
    from_pid = str(g.current_user["private_id"])
    body, code = _connection_request_apply(
        conn, from_pid, request.get_json(silent=True) or {}
    )
    if code < 400:
        conn.commit()
    return jsonify(body), code


@app.post("/api/connection/remove")
@login_required
def api_connection_remove():
    """Delete an accepted connection in either direction.

    Accepts either ``connection_id`` (preferred) or ``target_public_id`` +
    ``type``. The author can only remove a connection they are part of.
    """
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    me = str(g.current_user["private_id"])

    raw_id = payload.get("connection_id")
    try:
        connection_id = int(raw_id) if raw_id is not None and raw_id != "" else 0
    except (TypeError, ValueError):
        connection_id = 0

    if connection_id:
        cur = conn.execute(
            """
            DELETE FROM connection_requests
            WHERE id = ?
              AND status = 'accepted'
              AND (from_user_private_id = ? OR to_user_private_id = ?)
            """,
            (connection_id, me, me),
        )
        if cur.rowcount != 1:
            conn.commit()
            return jsonify({"error": "Connection not found"}), 404
        conn.commit()
        return jsonify({"ok": True})

    target_public_id = str(payload.get("target_public_id") or "").strip()
    request_type = str(payload.get("type") or "").strip().lower()
    if request_type not in {"family", "social"}:
        return jsonify({"error": "type must be family or social"}), 400
    if not target_public_id:
        return jsonify({"error": "connection_id or target_public_id is required"}), 400
    target = conn.execute(
        "SELECT private_id FROM users WHERE public_id = ? COLLATE NOCASE",
        (target_public_id,),
    ).fetchone()
    if not target:
        return jsonify({"error": "Account ID not found"}), 404
    target_pid = str(target["private_id"])
    cur = conn.execute(
        """
        DELETE FROM connection_requests
        WHERE request_type = ?
          AND status = 'accepted'
          AND ((from_user_private_id = ? AND to_user_private_id = ?)
            OR (from_user_private_id = ? AND to_user_private_id = ?))
        """,
        (request_type, me, target_pid, target_pid, me),
    )
    conn.commit()
    if cur.rowcount < 1:
        return jsonify({"error": "Connection not found"}), 404
    return jsonify({"ok": True})


@app.get("/api/connections")
@login_required
def api_connections():
    conn = get_db()
    request_type = (request.args.get("type") or "").strip().lower()
    if request_type not in {"family", "social"}:
        return jsonify({"error": "type must be family or social"}), 400
    me = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT cr.id AS request_id, u.private_id, u.public_id, u.first_name,
               u.last_name, u.age, u.gender, u.current_location_id,
               cr.relationship, cr.created_at
        FROM connection_requests cr
        JOIN users u ON u.private_id = CASE
            WHEN cr.from_user_private_id = ? THEN cr.to_user_private_id
            ELSE cr.from_user_private_id
        END
        WHERE cr.status = 'accepted'
          AND cr.request_type = ?
          AND (cr.from_user_private_id = ? OR cr.to_user_private_id = ?)
        ORDER BY datetime(cr.created_at) DESC
        """,
        (me, request_type, me, me),
    )
    return jsonify({"connections": [_user_connection_summary(conn, r) for r in cur]})


@app.get("/api/requests/incoming")
@login_required
def api_requests_incoming():
    conn = get_db()
    me = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT cr.id, cr.request_type, cr.relationship, cr.status, cr.created_at,
               u.private_id, u.public_id, u.first_name, u.last_name, u.age,
               u.gender, u.current_location_id
        FROM connection_requests cr
        JOIN users u ON u.private_id = cr.from_user_private_id
        WHERE cr.to_user_private_id = ?
          AND cr.status = 'pending'
        ORDER BY datetime(cr.created_at) DESC
        """,
        (me,),
    )
    requests = []
    for row in cur:
        item = _user_connection_summary(conn, row)
        item.update(
            {
                "request_id": int(row["id"]),
                "request_type": str(row["request_type"]),
                "relationship": str(row["relationship"] or ""),
                "status": str(row["status"]),
                "created_at": str(row["created_at"] or ""),
            }
        )
        requests.append(item)
    return jsonify({"requests": requests})


def _materialize_general_family_member_row(
    conn: sqlite3.Connection, cr: sqlite3.Row
) -> None:
    """After a **general** family connection is accepted, store a ``family_members`` row
    for the requester (tree owner) so the relative appears in All Family Members."""
    if str(cr["request_type"] or "") != "family":
        return
    if str(cr["family_member_type"] or "nuclear").lower() != "general":
        return
    requester = str(cr["from_user_private_id"])
    other_pid = str(cr["to_user_private_id"])
    u = conn.execute("SELECT * FROM users WHERE private_id = ?", (other_pid,)).fetchone()
    if not u:
        return
    pub = str(u["public_id"] or "").strip()
    if not pub:
        return
    rel = str(cr["relationship"] or "Family").strip() or "Family"
    full = (
        f"{str(u['first_name'] or '').strip()} {str(u['last_name'] or '').strip()}"
    ).strip() or pub
    dup = conn.execute(
        """
        SELECT 1 FROM family_members
         WHERE user_private_id = ?
           AND account_public_id = ? COLLATE NOCASE
           AND COALESCE(member_type, 'nuclear') = 'general'
        """,
        (requester, pub),
    ).fetchone()
    if dup:
        return
    conn.execute(
        """
        INSERT INTO family_members (
            user_private_id, member_name, relationship,
            gender, age, age_modifier,
            is_close_family, is_dead, is_placeholder, account_public_id, source,
            parent_link, member_type
        ) VALUES (?, ?, ?, ?, ?, NULL, 0, 0, 0, ?, 'general', NULL, 'general')
        """,
        (
            requester,
            full,
            rel,
            str(u["gender"] or ""),
            u["age"],
            pub,
        ),
    )


@app.post("/api/request/accept/<int:request_id>")
@login_required
def api_request_accept(request_id: int):
    conn = get_db()
    me = str(g.current_user["private_id"])
    row = conn.execute(
        """
        SELECT * FROM connection_requests
         WHERE id = ? AND to_user_private_id = ? AND status = 'pending'
        """,
        (request_id, me),
    ).fetchone()
    if not row:
        return jsonify({"error": "Request not found"}), 404
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        """
        UPDATE connection_requests
           SET status = 'accepted',
               accepted_at = ?
         WHERE id = ? AND to_user_private_id = ? AND status = 'pending'
        """,
        (now_iso, request_id, me),
    )
    if cur.rowcount != 1:
        return jsonify({"error": "Request not found"}), 404
    try:
        _materialize_general_family_member_row(conn, row)
    except sqlite3.OperationalError:
        app.logger.exception("materialize general family member failed")
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/request/reject/<int:request_id>")
@login_required
def api_request_reject(request_id: int):
    conn = get_db()
    cur = conn.execute(
        """
        UPDATE connection_requests
           SET status = 'rejected'
         WHERE id = ? AND to_user_private_id = ? AND status = 'pending'
        """,
        (request_id, str(g.current_user["private_id"])),
    )
    conn.commit()
    if cur.rowcount != 1:
        return jsonify({"error": "Request not found"}), 404
    return jsonify({"ok": True})


@app.get("/api/notifications/unread")
@login_required
def api_notifications_unread():
    """Aggregated unread notifications: pending connection requests + unread
    inbox messages (including system-authored ones)."""
    conn = get_db()
    me = str(g.current_user["private_id"])

    req_cur = conn.execute(
        """
        SELECT cr.id, cr.request_type, cr.relationship, cr.status, cr.created_at,
               u.private_id, u.public_id, u.first_name, u.last_name, u.age,
               u.gender, u.current_location_id
        FROM connection_requests cr
        JOIN users u ON u.private_id = cr.from_user_private_id
        WHERE cr.to_user_private_id = ?
          AND cr.status = 'pending'
        ORDER BY datetime(cr.created_at) DESC
        """,
        (me,),
    )
    requests_list: list[dict[str, Any]] = []
    for row in req_cur:
        item = _user_connection_summary(conn, row)
        item.update(
            {
                "request_id": int(row["id"]),
                "request_type": str(row["request_type"]),
                "relationship": str(row["relationship"] or ""),
                "status": str(row["status"]),
                "created_at": str(row["created_at"] or ""),
            }
        )
        requests_list.append(item)

    msg_cur = conn.execute(
        """
        SELECT m.message_id, m.subject, m.body, m.created_at, m.sender_id,
               m.status, m.is_draft, m.is_deleted_by_recipient,
               u.first_name AS sender_first, u.last_name AS sender_last,
               u.public_id AS sender_public_id
          FROM messages m
          LEFT JOIN users u ON u.private_id = m.sender_id
         WHERE m.recipient_id = ? COLLATE NOCASE
           AND m.is_draft = 0
           AND m.is_deleted_by_recipient = 0
           AND (m.status IS NULL OR m.status != 'read')
         ORDER BY datetime(m.created_at) DESC
         LIMIT 50
        """,
        (me,),
    )
    messages_list: list[dict[str, Any]] = []
    for row in msg_cur:
        sender_id = str(row["sender_id"] or "")
        sender_name = (
            f"{str(row['sender_first'] or '').strip()} "
            f"{str(row['sender_last'] or '').strip()}"
        ).strip()
        if sender_id == SYSTEM_SENDER_ID:
            sender_name = "Quantum Box (System)"
        elif not sender_name:
            sender_name = sender_id or "Unknown sender"
        messages_list.append(
            {
                "message_id": str(row["message_id"]),
                "subject": str(row["subject"] or ""),
                "preview": str(row["body"] or "")[:240],
                "body": str(row["body"] or ""),
                "created_at": str(row["created_at"] or ""),
                "sender_id": sender_id,
                "sender_public_id": str(row["sender_public_id"] or ""),
                "sender_name": sender_name,
                "is_system": sender_id == SYSTEM_SENDER_ID,
            }
        )

    link_req_list: list[dict[str, Any]] = []
    for lr in conn.execute(
        """
        SELECT lr.id, lr.family_member_id, lr.relationship_label, lr.created_at,
               u.first_name, u.last_name, u.public_id
          FROM link_requests lr
          JOIN users u ON u.private_id = lr.from_user_private_id
         WHERE lr.to_user_private_id = ? AND lr.status = 'pending'
         ORDER BY datetime(lr.created_at) DESC
        """,
        (me,),
    ):
        nm = (
            f'{lr["first_name"] or ""} {lr["last_name"] or ""}'.strip()
            or str(lr["public_id"] or "")
        )
        link_req_list.append(
            {
                "link_request_id": int(lr["id"]),
                "family_member_id": int(lr["family_member_id"]),
                "relationship_label": str(lr["relationship_label"] or ""),
                "created_at": str(lr["created_at"] or ""),
                "from_name": nm,
                "from_public_id": str(lr["public_id"] or ""),
            }
        )

    return jsonify(
        {
            "requests": requests_list,
            "messages": messages_list,
            "link_requests": link_req_list,
            "total_unread": len(requests_list)
            + len(messages_list)
            + len(link_req_list),
        }
    )


@app.post("/api/notifications/read_message/<path:message_id>")
@login_required
def api_notifications_read_message(message_id: str):
    """Mark a system / inbox message as read so it drops off the bell list."""
    conn = get_db()
    me = str(g.current_user["private_id"])
    mid = message_id.strip()
    row = conn.execute(
        "SELECT * FROM messages WHERE message_id = ?", (mid,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Message not found"}), 404
    if str(row["recipient_id"]).casefold() != me.casefold():
        return jsonify({"error": "Forbidden"}), 403
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE messages SET status = 'read', read_at = ? WHERE message_id = ?",
        (now, mid),
    )
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/notifications/accept/<int:request_id>")
@login_required
def api_notifications_accept(request_id: int):
    return api_request_accept(request_id)


@app.post("/api/notifications/reject/<int:request_id>")
@login_required
def api_notifications_reject(request_id: int):
    return api_request_reject(request_id)


# ---------------------------------------------------------------------------
# Quantum Punch — zodiac village council elections
# ---------------------------------------------------------------------------


def _election_user_location_match(user_row: sqlite3.Row) -> bool:
    return (
        str(user_row["current_location_id"] or "").strip()
        == election_scheduler.TARGET_VILLAGE_ID
    )


def _election_cycle_row_for_today(
    conn: sqlite3.Connection,
) -> tuple[sqlite3.Row | None, tuple[str, date, date] | None]:
    today = date.today()
    active = election_scheduler.sun_sign_for_election_day(today)
    if not active:
        return None, None
    sign, p_start, _p_end = active
    row = conn.execute(
        """
        SELECT * FROM election_cycles
        WHERE village_id = ? AND zodiac_sign = ? AND start_date = ?
        """,
        (election_scheduler.TARGET_VILLAGE_ID, sign, p_start.isoformat()),
    ).fetchone()
    return row, active


def _election_candidate_public(
    conn: sqlite3.Connection, cycle_id: int
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cur = conn.execute(
        """
        SELECT c.id AS candidate_row_id,
               c.candidate_private_id,
               c.gender,
               c.manifest,
               c.status,
               u.first_name,
               u.last_name,
               u.public_id
        FROM election_candidates c
        JOIN users u ON u.private_id = c.candidate_private_id
        WHERE c.election_cycle_id = ?
          AND c.status IN ('approved', 'pending')
        ORDER BY c.gender, c.id
        """,
        (cycle_id,),
    )
    for r in cur:
        mid = r["manifest"] or ""
        manifest = election_scheduler.parse_manifest(str(mid))
        vote_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM election_votes
            WHERE election_cycle_id = ? AND candidate_private_id = ?
            """,
            (cycle_id, str(r["candidate_private_id"])),
        ).fetchone()
        out.append(
            {
                "id": int(r["candidate_row_id"]),
                "candidate_private_id": str(r["candidate_private_id"]),
                "gender": str(r["gender"]),
                "manifest": manifest,
                "status": str(r["status"]),
                "first_name": str(r["first_name"] or ""),
                "last_name": str(r["last_name"] or ""),
                "public_id": str(r["public_id"] or ""),
                "vote_count": int(vote_count["n"]) if vote_count else 0,
            }
        )
    return out


@app.get("/api/election/status")
@login_required
def api_election_status():
    conn = get_db()
    user = g.current_user
    uid = str(user["private_id"])
    in_village = _election_user_location_match(user)
    sun = str(user["sun_sign"] or "")
    cycle_row, active_period = _election_cycle_row_for_today(conn)
    eligible = bool(
        in_village and active_period and sun == str(active_period[0])
    )
    payload: dict[str, Any] = {
        "target_village_id": election_scheduler.TARGET_VILLAGE_ID,
        "user_in_target_village": in_village,
        "user_sun_sign": sun,
        "eligible_for_current_cycle": eligible,
        "active_period": None,
        "cycle": None,
        "phase": None,
        "candidates": [],
        "votes_for_user": {"Male": None, "Female": None},
        "user_is_candidate": False,
    }
    if active_period:
        sign, p_start, p_end = active_period
        payload["active_period"] = {
            "zodiac_sign": sign,
            "start": p_start.isoformat(),
            "end": p_end.isoformat(),
        }
    if not cycle_row:
        return jsonify(payload)

    cid = int(cycle_row["id"])
    payload["cycle"] = {
        "id": cid,
        "zodiac_sign": str(cycle_row["zodiac_sign"]),
        "status": str(cycle_row["status"]),
        "nomination_start": str(cycle_row["nomination_start"]),
        "nomination_end": str(cycle_row["nomination_end"]),
        "voting_start": str(cycle_row["voting_start"]),
        "voting_end": str(cycle_row["voting_end"]),
        "male_winner_private_id": cycle_row["male_winner_private_id"],
        "female_winner_private_id": cycle_row["female_winner_private_id"],
    }
    payload["phase"] = str(cycle_row["status"])
    payload["candidates"] = _election_candidate_public(conn, cid)
    for vr in conn.execute(
        """
        SELECT gender, candidate_private_id FROM election_votes
        WHERE election_cycle_id = ? AND voter_private_id = ?
        """,
        (cid, uid),
    ):
        gslot = str(vr["gender"])
        if gslot in payload["votes_for_user"]:
            payload["votes_for_user"][gslot] = str(vr["candidate_private_id"])
    cand_self = conn.execute(
        """
        SELECT 1 FROM election_candidates
        WHERE election_cycle_id = ? AND candidate_private_id = ?
        """,
        (cid, uid),
    ).fetchone()
    payload["user_is_candidate"] = cand_self is not None
    return jsonify(payload)


@app.post("/api/election/nominate")
@login_required
def api_election_nominate():
    conn = get_db()
    user = g.current_user
    if not _election_user_location_match(user):
        return jsonify({"error": "Elections are for Rohini Sector-24 residents only"}), 403
    bucket = election_scheduler.election_bucket_gender(str(user["gender"] or ""))
    if not bucket:
        return jsonify(
            {"error": "Only Male or Female cohort candidates can stand in this prototype"}
        ), 400
    cycle_row, active = _election_cycle_row_for_today(conn)
    if not cycle_row or not active:
        return jsonify({"error": "No active election cycle"}), 400
    if str(user["sun_sign"] or "") != str(active[0]):
        return jsonify({"error": "Your sun sign does not match this cycle"}), 403
    st = str(cycle_row["status"] or "")
    if st != "nomination":
        return jsonify({"error": "Nominations are closed"}), 400
    payload = request.get_json(silent=True) or {}
    why = str(payload.get("why_stand") or "").strip()
    changes = str(payload.get("changes") or "").strip()
    if not why or not changes:
        return jsonify({"error": "Both manifest fields are required"}), 400
    cid = int(cycle_row["id"])
    exists = conn.execute(
        """
        SELECT 1 FROM election_candidates
        WHERE election_cycle_id = ? AND candidate_private_id = ?
        """,
        (cid, str(user["private_id"])),
    ).fetchone()
    if exists:
        return jsonify({"error": "You are already a candidate"}), 400
    manifest = json.dumps({"why_stand": why, "changes": changes}, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO election_candidates (
            election_cycle_id, candidate_private_id, gender, manifest, status
        ) VALUES (?, ?, ?, ?, 'approved')
        """,
        (cid, str(user["private_id"]), bucket, manifest),
    )
    conn.commit()
    return jsonify({"ok": True, "election_cycle_id": cid})


@app.post("/api/election/vote")
@login_required
def api_election_vote():
    conn = get_db()
    user = g.current_user
    uid = str(user["private_id"])
    if not _election_user_location_match(user):
        return jsonify({"error": "Only village residents may vote"}), 403
    cycle_row, active = _election_cycle_row_for_today(conn)
    if not cycle_row or not active:
        return jsonify({"error": "No active election cycle"}), 400
    if str(user["sun_sign"] or "") != str(active[0]):
        return jsonify({"error": "Your sun sign does not match this cycle"}), 403
    if str(cycle_row["status"] or "") != "voting":
        return jsonify({"error": "Voting is not open"}), 400
    payload = request.get_json(silent=True) or {}
    cand_pid = str(payload.get("candidate_private_id") or "").strip()
    gender_slot = str(payload.get("gender") or "").strip()
    if gender_slot not in ("Male", "Female"):
        return jsonify({"error": "gender must be Male or Female"}), 400
    if not cand_pid:
        return jsonify({"error": "candidate_private_id required"}), 400
    cid = int(cycle_row["id"])
    target = conn.execute(
        """
        SELECT * FROM election_candidates
        WHERE election_cycle_id = ? AND candidate_private_id = ?
          AND status IN ('approved', 'pending')
        """,
        (cid, cand_pid),
    ).fetchone()
    if not target:
        return jsonify({"error": "Candidate not found"}), 404
    if str(target["gender"]) != gender_slot:
        return jsonify({"error": "Candidate gender mismatch"}), 400
    cand_loc = conn.execute(
        "SELECT current_location_id, sun_sign FROM users WHERE private_id = ?",
        (cand_pid,),
    ).fetchone()
    if not cand_loc:
        return jsonify({"error": "Candidate user missing"}), 400
    if (
        str(cand_loc["current_location_id"] or "").strip()
        != election_scheduler.TARGET_VILLAGE_ID
        or str(cand_loc["sun_sign"] or "") != str(active[0])
    ):
        return jsonify({"error": "Invalid candidate for this cycle"}), 400
    existing = conn.execute(
        """
        SELECT 1 FROM election_votes
        WHERE election_cycle_id = ? AND voter_private_id = ? AND gender = ?
        """,
        (cid, uid, gender_slot),
    ).fetchone()
    if existing:
        return jsonify({"error": "You already voted for this gender slot"}), 400
    conn.execute(
        """
        INSERT INTO election_votes (
            election_cycle_id, voter_private_id, candidate_private_id, gender
        ) VALUES (?, ?, ?, ?)
        """,
        (cid, uid, cand_pid, gender_slot),
    )
    conn.commit()
    return jsonify({"ok": True})


@app.get("/api/election/results")
@login_required
def api_election_results():
    conn = get_db()
    cur = conn.execute(
        """
        SELECT id, zodiac_sign, start_date, end_date, status,
               male_winner_private_id, female_winner_private_id,
               nomination_start, nomination_end, voting_start, voting_end
        FROM election_cycles
        WHERE village_id = ? AND status = 'closed'
        ORDER BY date(start_date) DESC
        LIMIT 24
        """,
        (election_scheduler.TARGET_VILLAGE_ID,),
    )
    results: list[dict[str, Any]] = []
    for r in cur:
        results.append(
            {
                "id": int(r["id"]),
                "zodiac_sign": str(r["zodiac_sign"]),
                "start_date": str(r["start_date"]),
                "end_date": str(r["end_date"]),
                "male_winner_private_id": r["male_winner_private_id"],
                "female_winner_private_id": r["female_winner_private_id"],
            }
        )
    return jsonify({"cycles": results})


@app.get("/api/election/council")
@login_required
def api_election_council():
    conn = get_db()
    today = date.today()
    active = election_scheduler.sun_sign_for_election_day(today)
    current_sign = str(active[0]) if active else None
    cur = conn.execute(
        """
        SELECT vc.zodiac_sign,
               vc.male_head_private_id,
               vc.female_head_private_id,
               vc.election_cycle_id,
               um.first_name AS m_first,
               um.last_name AS m_last,
               um.public_id AS m_pub,
               uf.first_name AS f_first,
               uf.last_name AS f_last,
               uf.public_id AS f_pub
        FROM village_council vc
        LEFT JOIN users um ON um.private_id = vc.male_head_private_id
        LEFT JOIN users uf ON uf.private_id = vc.female_head_private_id
        WHERE vc.village_id = ?
        ORDER BY vc.zodiac_sign
        """,
        (election_scheduler.TARGET_VILLAGE_ID,),
    )
    members: list[dict[str, Any]] = []
    king = None
    queen = None
    for r in cur:
        sign = str(r["zodiac_sign"])
        entry = {
            "zodiac_sign": sign,
            "male": _election_council_face(r, "m"),
            "female": _election_council_face(r, "f"),
            "is_current_king": bool(current_sign and sign == current_sign),
            "is_current_queen": bool(current_sign and sign == current_sign),
        }
        if entry["is_current_king"] and entry["male"]:
            king = dict(entry["male"])
            king["zodiac_sign"] = sign
        if entry["is_current_queen"] and entry["female"]:
            queen = dict(entry["female"])
            queen["zodiac_sign"] = sign
        members.append(entry)
    upcoming = None
    if active:
        _sign, _ps, pend = active
        nxt_start = pend + timedelta(days=1)
        nxt = election_scheduler.sun_sign_for_election_day(nxt_start)
        if nxt:
            upcoming = {
                "zodiac_sign": nxt[0],
                "period_start": nxt[1].isoformat(),
                "days_until": max(0, (nxt[1] - today).days),
            }
    return jsonify(
        {
            "village_id": election_scheduler.TARGET_VILLAGE_ID,
            "current_zodiac_sign": current_sign,
            "king": king,
            "queen": queen,
            "members": members,
            "upcoming_election": upcoming,
        }
    )


def _election_council_face(row: sqlite3.Row, prefix: str) -> dict[str, Any] | None:
    if prefix == "m":
        pid = row["male_head_private_id"]
        fn_key, ln_key, pub_key = "m_first", "m_last", "m_pub"
    else:
        pid = row["female_head_private_id"]
        fn_key, ln_key, pub_key = "f_first", "f_last", "f_pub"
    if not pid:
        return None
    fn = str(row[fn_key] or "").strip()
    ln = str(row[ln_key] or "").strip()
    return {
        "private_id": str(pid),
        "name": (fn + " " + ln).strip() or str(pid),
        "public_id": str(row[pub_key] or ""),
    }


# ---------------------------------------------------------------------------
# Family form / tree / member management
# ---------------------------------------------------------------------------

def _family_profile_row(conn: sqlite3.Connection, user_pid: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT user_private_id, form_data, form_completed, relationship_status, "
        "       created_at, updated_at "
        "FROM family_profile WHERE user_private_id = ?",
        (user_pid,),
    ).fetchone()


def _family_profile_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {
            "form_completed": False,
            "relationship_status": "",
            "form_data": {},
        }
    raw = row["form_data"] or ""
    data: dict[str, Any] = {}
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = parsed
        except (TypeError, ValueError):
            data = {}
    return {
        "form_completed": bool(int(row["form_completed"] or 0)),
        "relationship_status": str(row["relationship_status"] or "")
        or str(data.get("relationship_status") or ""),
        "form_data": data,
        "updated_at": str(row["updated_at"] or "") if row["updated_at"] else "",
    }


def _user_initial_setup_row(
    conn: sqlite3.Connection, user_pid: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM user_family_setup WHERE user_private_id = ?",
        (user_pid,),
    ).fetchone()


def _user_needs_initial_family_setup(
    conn: sqlite3.Connection, user_pid: str, profile: dict[str, Any]
) -> bool:
    if profile.get("form_completed"):
        return False
    r = _user_initial_setup_row(conn, user_pid)
    if r and int(r["completed"] or 0) == 1:
        return False
    return True


def _initial_setup_meta(conn: sqlite3.Connection, user_pid: str) -> dict[str, Any]:
    r = _user_initial_setup_row(conn, user_pid)
    if not r:
        return {"completed": False, "answers": {}}
    try:
        ans = json.loads(str(r["answers_json"] or "{}") or "{}")
        if not isinstance(ans, dict):
            ans = {}
    except (TypeError, ValueError):
        ans = {}
    return {"completed": bool(int(r["completed"] or 0)), "answers": ans}


def _life_stage_from_age(age: int | None) -> str:
    if age is None:
        return ""
    if age <= 24:
        return "Balak"
    if age <= 49:
        return "Yuvak"
    if age <= 75:
        return "Vridh"
    return "Sanyas"


def _life_stage_from_user_row(user_row: sqlite3.Row) -> str:
    ag = str(_urow_get(user_row, "age_group") or "").strip()
    if ag in {"Balak", "Yuvak", "Vridh", "Sanyas"}:
        return ag
    return _life_stage_from_age(_coerce_int(_urow_get(user_row, "age")))


def _wipe_placeholder_family_graph(conn: sqlite3.Connection, user_pid: str) -> None:
    cur = conn.execute(
        "SELECT id FROM family_members WHERE user_private_id = ? AND source != 'self'",
        (user_pid,),
    )
    for row in cur.fetchall():
        mid = int(row["id"])
        conn.execute(
            "DELETE FROM family_relationships WHERE source_id = ? OR target_id = ?",
            (mid, mid),
        )
    conn.execute(
        "DELETE FROM family_members WHERE user_private_id = ? AND source != 'self'",
        (user_pid,),
    )


def _seed_family_from_initial_setup(
    conn: sqlite3.Connection, user_pid: str, self_id: int, setup: dict[str, Any]
) -> None:
    rs = str(setup.get("relationship_status") or "").strip().lower().replace("_", "-")
    has_children = bool(setup.get("has_children"))
    n_children = max(0, min(10, int(setup.get("children_count") or 0)))
    has_siblings = bool(setup.get("has_siblings"))
    n_bro = max(0, min(20, int(setup.get("brothers_count") or 0)))
    n_sis = max(0, min(20, int(setup.get("sisters_count") or 0)))

    fn = str(setup.get("father_name") or "").strip()
    mn = str(setup.get("mother_name") or "").strip()
    father_name = fn if fn else "Father"
    mother_name = mn if mn else "Mother"

    brother_names_raw = setup.get("brother_names") or []
    sister_names_raw = setup.get("sister_names") or []
    brother_names: list[str] = (
        brother_names_raw if isinstance(brother_names_raw, list) else []
    )
    sister_names: list[str] = (
        sister_names_raw if isinstance(sister_names_raw, list) else []
    )

    father = _ins_placeholder(conn, user_pid, father_name, "Father", "")
    mother = _ins_placeholder(conn, user_pid, mother_name, "Mother", "")
    _graph_apply_pair(conn, father, self_id, "parent")
    _graph_apply_pair(conn, mother, self_id, "parent")

    if rs == "married":
        sp = _ins_placeholder(conn, user_pid, "Add", "Spouse", "")
        _graph_apply_pair(conn, sp, self_id, "spouse")

    child_statuses = {"married", "single-parent", "widowed"}
    if has_children and n_children > 0 and rs in child_statuses:
        for _ in range(n_children):
            ch = _ins_placeholder(conn, user_pid, "Add", "Child", "")
            _graph_apply_pair(conn, self_id, ch, "parent")

    if has_siblings:
        for i in range(n_bro):
            raw = ""
            if i < len(brother_names):
                raw = str(brother_names[i] or "").strip()
            label = raw if raw else f"Brother {i + 1}"
            s = _ins_placeholder(conn, user_pid, label, "Sibling", "")
            _graph_apply_pair(conn, s, self_id, "sibling")
        for j in range(n_sis):
            raw = ""
            if j < len(sister_names):
                raw = str(sister_names[j] or "").strip()
            label = raw if raw else f"Sister {j + 1}"
            s2 = _ins_placeholder(conn, user_pid, label, "Sibling", "")
            _graph_apply_pair(conn, s2, self_id, "sibling")


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _family_member_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys() if hasattr(row, "keys") else []
    parent_link = ""
    if "parent_link" in keys and row["parent_link"]:
        parent_link = str(row["parent_link"])
    created_at = str(row["created_at"] or "") if row["created_at"] else ""
    rel_raw = str(row["relationship"] or "")
    is_ph = bool(int(row["is_placeholder"] or 0)) if "is_placeholder" in keys else False
    mt = "nuclear"
    if "member_type" in keys and row["member_type"]:
        mt = str(row["member_type"]).strip().lower() or "nuclear"
    out: dict[str, Any] = {
        "id": int(row["id"]),
        "member_name": str(row["member_name"] or ""),
        "relationship": rel_raw,
        "relationship_to_user": rel_raw,
        "relationship_label": rel_raw,
        "member_type": mt,
        "gender": str(row["gender"] or "") if row["gender"] is not None else "",
        "age": int(row["age"]) if row["age"] is not None else None,
        "age_modifier": str(row["age_modifier"] or "") if row["age_modifier"] is not None else "",
        "is_close_family": bool(int(row["is_close_family"] or 0)),
        "is_dead": bool(int(row["is_dead"] or 0)),
        "is_placeholder": is_ph,
        "is_self": str(row["source"] or "") == "self",
        "account_public_id": str(row["account_public_id"] or "")
        if row["account_public_id"]
        else "",
        "source": str(row["source"] or "form"),
        "parent_link": parent_link,
        "created_at": created_at,
        # The "added_at" anchor for the 2-day direct-removal window; for form
        # rows this is when the row was inserted.
        "added_at": created_at,
    }
    for col in (
        "tree_mother_member_id",
        "tree_father_member_id",
        "tree_spouse_member_id",
        "tree_child_of_member_id",
        "tree_mother_connection_request_id",
        "tree_father_connection_request_id",
        "tree_child_of_connection_request_id",
    ):
        if col in keys and row[col] is not None:
            try:
                out[col] = int(row[col])
            except (TypeError, ValueError):
                out[col] = None
        else:
            out[col] = None
    if "reference_relation" in keys and row["reference_relation"]:
        out["reference_relation"] = str(row["reference_relation"]).strip()
    else:
        out["reference_relation"] = ""
    return out


def _family_member_within_direct_removal_window(added_at: str) -> bool:
    """True if a family member was added within the last
    :data:`FAMILY_DIRECT_REMOVAL_DAYS` days."""
    added = social_core._parse_sqlite_datetime(added_at)
    if added is None:
        return False
    return (
        datetime.now(timezone.utc)
        <= added + timedelta(days=FAMILY_DIRECT_REMOVAL_DAYS)
    )


def _pending_removal_requests_for_user(
    conn: sqlite3.Connection, user_pid: str
) -> dict[tuple[str, int], int]:
    """Map of (source, target_member_id) → removal_request id for pending rows."""
    cur = conn.execute(
        """
        SELECT id, target_source, target_member_id
          FROM family_removal_requests
         WHERE user_private_id = ? AND status = 'pending'
        """,
        (user_pid,),
    )
    out: dict[tuple[str, int], int] = {}
    for r in cur:
        try:
            out[(str(r["target_source"]), int(r["target_member_id"]))] = int(
                r["id"]
            )
        except (TypeError, ValueError):
            continue
    return out


def _annotate_member_removal_state(
    member: dict[str, Any],
    pending_map: dict[tuple[str, int], int],
    viewer_is_admin: bool,
) -> dict[str, Any]:
    """Stamp ``removal_*`` keys onto a member dict so the UI knows the button
    state to render."""
    src = str(member.get("source") or "form")
    try:
        mid = int(member.get("id"))
    except (TypeError, ValueError):
        mid = 0
    pending_request_id = pending_map.get((src, mid))
    member["removal_pending"] = pending_request_id is not None
    member["removal_request_id"] = pending_request_id or 0
    member["within_direct_removal_window"] = (
        _family_member_within_direct_removal_window(
            str(member.get("added_at") or member.get("created_at") or "")
        )
    )
    member["can_remove_directly"] = bool(
        not member["removal_pending"]
        and (viewer_is_admin or member["within_direct_removal_window"])
    )
    return member


def _replace_form_family_members(
    conn: sqlite3.Connection,
    user_pid: str,
    members: list[dict[str, Any]],
) -> None:
    """Wipe and reinsert form-entered family rows for this user.

    Some members reference a ``parent_link_key`` so they can later be
    associated with another newly-inserted row (e.g. a grandchild pointing
    back to its parent child). We resolve those keys into the actual
    ``family_members.id`` and persist it in the ``parent_link`` column.
    """
    conn.execute(
        "DELETE FROM family_members WHERE user_private_id = ? AND source = 'form'",
        (user_pid,),
    )
    key_to_id: dict[str, int] = {}
    pending_parent_resolution: list[tuple[int, str]] = []
    for member in members:
        name = str(member.get("member_name") or "").strip()
        rel = str(member.get("relationship") or "").strip()
        if not name or not rel:
            continue
        gender = str(member.get("gender") or "").strip()
        age = _coerce_int(member.get("age"))
        age_modifier = str(member.get("age_modifier") or "").strip().lower()
        if age_modifier not in {"older", "younger", ""}:
            age_modifier = ""
        is_close = 1 if _is_close_family_relationship(rel) else 0
        is_dead = 1 if _coerce_bool(member.get("is_dead")) else 0
        conn.execute(
            """
            INSERT INTO family_members (
                user_private_id, member_name, relationship,
                gender, age, age_modifier,
                is_close_family, is_dead, account_public_id, source,
                parent_link
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'form', NULL)
            """,
            (
                user_pid,
                name,
                rel,
                gender,
                age,
                age_modifier,
                is_close,
                is_dead,
            ),
        )
        new_id = int(
            conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        )
        local_key = str(member.get("local_key") or "").strip()
        if local_key:
            key_to_id[local_key] = new_id
        plk = str(member.get("parent_link_key") or "").strip()
        if plk:
            pending_parent_resolution.append((new_id, plk))
    for new_id, plk in pending_parent_resolution:
        target = key_to_id.get(plk)
        if not target:
            continue
        conn.execute(
            "UPDATE family_members SET parent_link = ? WHERE id = ?",
            (str(target), new_id),
        )


def _build_form_member_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate the Family form JSON into normalized family_members rows."""
    rows: list[dict[str, Any]] = []
    status = (str(payload.get("relationship_status") or "")).strip().lower()

    father = payload.get("father") or {}
    if (father.get("name") or "").strip():
        rows.append(
            {
                "member_name": father.get("name"),
                "relationship": "Father",
                "gender": "Male",
                "age": father.get("age"),
                "is_dead": father.get("is_dead"),
            }
        )
    mother = payload.get("mother") or {}
    if (mother.get("name") or "").strip():
        rows.append(
            {
                "member_name": mother.get("name"),
                "relationship": "Mother",
                "gender": "Female",
                "age": mother.get("age"),
                "is_dead": mother.get("is_dead"),
            }
        )

    for gp in payload.get("grandparents") or []:
        if not isinstance(gp, dict):
            continue
        if not (gp.get("name") or "").strip():
            continue
        rel = str(gp.get("relationship") or "").strip().title() or "Grandparent"
        rows.append(
            {
                "member_name": gp.get("name"),
                "relationship": rel,
                "gender": gp.get("gender"),
                "age": gp.get("age"),
                "is_dead": gp.get("is_dead"),
            }
        )

    for sib in payload.get("siblings") or []:
        if not isinstance(sib, dict):
            continue
        if not (sib.get("name") or "").strip():
            continue
        rows.append(
            {
                "member_name": sib.get("name"),
                "relationship": "Sibling",
                "gender": sib.get("gender"),
                "age": sib.get("age"),
                "age_modifier": sib.get("age_modifier"),
                "is_dead": sib.get("is_dead"),
            }
        )

    if status == "married":
        spouse = payload.get("spouse") or {}
        if (spouse.get("name") or "").strip():
            rows.append(
                {
                    "member_name": spouse.get("name"),
                    "relationship": "Spouse",
                    "gender": spouse.get("gender"),
                    "age": spouse.get("age"),
                    "is_dead": spouse.get("is_dead"),
                    "local_key": "spouse",
                }
            )

    # Spouse's parents (parents-in-law) for married OR single-parent users.
    if status in {"married", "single-parent", "single_parent"}:
        spf = payload.get("spouse_father") or {}
        if (spf.get("name") or "").strip():
            rows.append(
                {
                    "member_name": spf.get("name"),
                    "relationship": "Father-in-law",
                    "gender": "Male",
                    "is_dead": spf.get("is_dead"),
                }
            )
        spm = payload.get("spouse_mother") or {}
        if (spm.get("name") or "").strip():
            rows.append(
                {
                    "member_name": spm.get("name"),
                    "relationship": "Mother-in-law",
                    "gender": "Female",
                    "is_dead": spm.get("is_dead"),
                }
            )

    # Children + their spouses + grandchildren.
    # For married users we honour the explicit ``has_children`` flag; single-
    # parent users always have children by definition.
    has_children = _coerce_bool(payload.get("has_children"))
    if status in {"single-parent", "single_parent"} or (
        status == "married" and has_children
    ):
        for idx, child in enumerate(payload.get("children") or []):
            if not isinstance(child, dict):
                continue
            child_name = (child.get("name") or "").strip()
            if not child_name:
                continue
            gender = (child.get("gender") or "").strip()
            rel = "Son" if gender.lower() == "male" else (
                "Daughter" if gender.lower() == "female" else "Child"
            )
            child_key = f"child-{idx}"
            rows.append(
                {
                    "member_name": child_name,
                    "relationship": rel,
                    "gender": gender,
                    "age": child.get("age"),
                    "is_dead": child.get("is_dead"),
                    "local_key": child_key,
                }
            )
            cspouse = child.get("spouse") or {}
            if _coerce_bool(child.get("is_married")) and (
                cspouse.get("name") or ""
            ).strip():
                cs_gender = (cspouse.get("gender") or "").strip()
                cs_rel = (
                    "Daughter-in-law"
                    if cs_gender.lower() == "female"
                    else (
                        "Son-in-law"
                        if cs_gender.lower() == "male"
                        else "Child's Spouse"
                    )
                )
                rows.append(
                    {
                        "member_name": cspouse.get("name"),
                        "relationship": cs_rel,
                        "gender": cs_gender,
                        "age": cspouse.get("age"),
                        "is_dead": cspouse.get("is_dead"),
                        "parent_link_key": child_key,
                    }
                )
            for gc in child.get("grandchildren") or []:
                if not isinstance(gc, dict):
                    continue
                if not (gc.get("name") or "").strip():
                    continue
                gc_gender = (gc.get("gender") or "").strip()
                gc_rel = (
                    "Grandson"
                    if gc_gender.lower() == "male"
                    else (
                        "Granddaughter"
                        if gc_gender.lower() == "female"
                        else "Grandchild"
                    )
                )
                rows.append(
                    {
                        "member_name": gc.get("name"),
                        "relationship": gc_rel,
                        "gender": gc_gender,
                        "age": gc.get("age"),
                        "is_dead": gc.get("is_dead"),
                        "parent_link_key": child_key,
                    }
                )

    return rows


@app.get("/api/family/profile")
@login_required
def api_family_profile():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    row = _family_profile_row(conn, pid)
    pr = _family_profile_to_dict(row)
    pr["initial_setup"] = _initial_setup_meta(conn, pid)
    pr["needs_initial_setup"] = _user_needs_initial_family_setup(conn, pid, pr)
    return jsonify(pr)


@app.post("/api/family/initial_setup")
@login_required
def api_family_initial_setup():
    """First-time family questionnaire: saves answers and seeds the nuclear tree."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    fp = _family_profile_to_dict(_family_profile_row(conn, pid))
    if fp.get("form_completed"):
        return jsonify({"error": "Legacy family form already completed"}), 400
    if _initial_setup_meta(conn, pid)["completed"]:
        return jsonify({"error": "Initial setup already completed"}), 400

    payload = request.get_json(silent=True) or {}
    rs = str(payload.get("relationship_status") or "").strip().lower().replace("_", "-")
    allowed = {"unmarried", "married", "single-parent", "widowed"}
    if rs not in allowed:
        return jsonify({"error": "relationship_status is required"}), 400
    if rs == "single_parent":
        rs = "single-parent"

    child_eligible = rs in {"married", "single-parent", "widowed"}
    has_children = bool(payload.get("has_children")) if child_eligible else False
    children_count = max(0, min(10, int(payload.get("children_count") or 0)))
    has_siblings = bool(payload.get("has_siblings"))
    brothers_count = max(0, min(20, int(payload.get("brothers_count") or 0)))
    sisters_count = max(0, min(20, int(payload.get("sisters_count") or 0)))

    def _str_list(key: str) -> list[str]:
        raw = payload.get(key)
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, list):
            return [str(x or "").strip() for x in raw]
        return []

    brother_names = _str_list("brother_names")[:brothers_count] if has_siblings else []
    sister_names = _str_list("sister_names")[:sisters_count] if has_siblings else []
    while len(brother_names) < brothers_count:
        brother_names.append("")
    while len(sister_names) < sisters_count:
        sister_names.append("")

    father_name_opt = str(payload.get("father_name") or "").strip()
    mother_name_opt = str(payload.get("mother_name") or "").strip()

    blob = {
        "relationship_status": rs,
        "father_name": father_name_opt,
        "mother_name": mother_name_opt,
        "has_children": has_children,
        "children_count": children_count,
        "has_siblings": has_siblings,
        "brothers_count": brothers_count,
        "sisters_count": sisters_count,
        "brother_names": brother_names,
        "sister_names": sister_names,
    }
    if rs == "unmarried" and has_children:
        return jsonify({"error": "Unmarried profile cannot include children"}), 400
    if has_children and children_count < 1:
        return jsonify({"error": "children_count must be 1–10 when you have children"}), 400
    if has_siblings and brothers_count + sisters_count < 1:
        return jsonify({"error": "Enter at least one sibling when siblings is Yes"}), 400

    _wipe_placeholder_family_graph(conn, pid)
    self_id = _ensure_account_self_row(conn, pid, g.current_user)
    _seed_family_from_initial_setup(conn, pid, self_id, blob)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    j = json.dumps(blob, ensure_ascii=False)
    ex = conn.execute(
        "SELECT user_private_id FROM user_family_setup WHERE user_private_id = ?",
        (pid,),
    ).fetchone()
    if ex:
        conn.execute(
            """
            UPDATE user_family_setup
               SET completed = 1, answers_json = ?, updated_at = ?
             WHERE user_private_id = ?
            """,
            (j, now_iso, pid),
        )
    else:
        conn.execute(
            """
            INSERT INTO user_family_setup (
                user_private_id, completed, answers_json, created_at, updated_at
            ) VALUES (?, 1, ?, ?, ?)
            """,
            (pid, j, now_iso, now_iso),
        )

    prow = _family_profile_row(conn, pid)
    if prow:
        conn.execute(
            """
            UPDATE family_profile
               SET relationship_status = ?, updated_at = ?
             WHERE user_private_id = ?
            """,
            (rs, now_iso, pid),
        )
    else:
        conn.execute(
            """
            INSERT INTO family_profile (
                user_private_id, form_data, form_completed, relationship_status, updated_at
            ) VALUES (?, '{}', 0, ?, ?)
            """,
            (pid, rs, now_iso),
        )

    conn.commit()
    return jsonify({"ok": True, **_family_tree_graph_payload(conn, pid)})


@app.post("/api/family/submit_form")
@login_required
def api_family_submit_form():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    status = (str(payload.get("relationship_status") or "")).strip().lower()
    allowed = {"unmarried", "married", "single-parent", "single_parent"}
    if status not in allowed:
        return jsonify({"error": "relationship_status must be unmarried, married, or single-parent"}), 400
    if status == "single_parent":
        status = "single-parent"
    payload["relationship_status"] = status

    existing = _family_profile_row(conn, pid)
    if existing and bool(int(existing["form_completed"] or 0)):
        return jsonify({"error": "Family form already submitted. Contact admin to reset."}), 403

    members = _build_form_member_rows(payload)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    blob = json.dumps(payload, ensure_ascii=False)
    if existing:
        conn.execute(
            """
            UPDATE family_profile
               SET form_data = ?, form_completed = 1,
                   relationship_status = ?, updated_at = ?
             WHERE user_private_id = ?
            """,
            (blob, status, now_iso, pid),
        )
    else:
        conn.execute(
            """
            INSERT INTO family_profile (
                user_private_id, form_data, form_completed,
                relationship_status, updated_at
            ) VALUES (?, ?, 1, ?, ?)
            """,
            (pid, blob, status, now_iso),
        )
    _replace_form_family_members(conn, pid, members)
    conn.commit()
    row = _family_profile_row(conn, pid)
    return jsonify({"ok": True, "profile": _family_profile_to_dict(row)})


def _connection_family_members(
    conn: sqlite3.Connection, user_pid: str
) -> list[dict[str, Any]]:
    """Accepted family connections as 'connection'-sourced family_members rows."""
    cur = conn.execute(
        """
        SELECT cr.id AS request_id, cr.relationship AS relationship,
               cr.is_dead AS is_dead, cr.created_at AS created_at,
               cr.accepted_at AS accepted_at,
               COALESCE(cr.family_member_type, 'nuclear') AS family_member_type,
               u.public_id AS public_id, u.first_name AS first_name,
               u.last_name AS last_name, u.gender AS gender, u.age AS age,
               u.current_location_id AS current_location_id
        FROM connection_requests cr
        JOIN users u ON u.private_id = CASE
            WHEN cr.from_user_private_id = ? THEN cr.to_user_private_id
            ELSE cr.from_user_private_id
        END
        WHERE cr.status = 'accepted'
          AND cr.request_type = 'family'
          AND (cr.from_user_private_id = ? OR cr.to_user_private_id = ?)
          AND NOT (
                COALESCE(cr.family_member_type, 'nuclear') = 'general'
                AND EXISTS (
                    SELECT 1 FROM family_members fm
                     WHERE fm.user_private_id = ?
                       AND fm.account_public_id = u.public_id
                       AND COALESCE(fm.member_type, 'nuclear') = 'general'
                )
              )
        ORDER BY datetime(cr.created_at) DESC
        """,
        (user_pid, user_pid, user_pid, user_pid),
    )
    out: list[dict[str, Any]] = []
    for row in cur:
        full_name = (
            f"{str(row['first_name'] or '').strip()} {str(row['last_name'] or '').strip()}"
        ).strip()
        rel = str(row["relationship"] or "").strip()
        accepted_at = str(row["accepted_at"] or "") if row["accepted_at"] else ""
        out.append(
            {
                "id": int(row["request_id"]),
                "member_name": full_name or str(row["public_id"] or ""),
                "relationship": rel or "Family",
                "relationship_label": rel.title() if rel else "Family",
                "gender": str(row["gender"] or ""),
                "age": int(row["age"]) if row["age"] is not None else None,
                "age_modifier": "",
                "is_close_family": _is_close_family_relationship(rel),
                "is_dead": bool(int(row["is_dead"] or 0)),
                "account_public_id": str(row["public_id"] or ""),
                "source": "connection",
                "created_at": str(row["created_at"] or "") if row["created_at"] else "",
                "accepted_at": accepted_at,
                # "added_at" is what the 2-day window measures against: time
                # of acceptance for connections, falling back to creation if
                # the legacy column was missing.
                "added_at": accepted_at or (
                    str(row["created_at"] or "") if row["created_at"] else ""
                ),
                "family_member_type": str(row["family_member_type"] or "nuclear"),
            }
        )
    return out


def get_relationship_sentence(
    member_name: str,
    member_gender: str | None,
    relationships: list[dict[str, Any]],
) -> str:
    """Build natural-language phrases from structured relationship rows."""
    if not relationships:
        return ""
    gl = (member_gender or "").strip().lower()
    parts: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for rel in relationships:
        role = str(rel.get("role") or "").strip()
        other = str(rel.get("other_name") or "").strip()
        other_is_viewer = bool(rel.get("other_is_viewer"))
        dedupe_key = (role, other, "1" if other_is_viewer else "0")
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        if not other and not other_is_viewer:
            continue
        if role == "parent_of":
            if gl == "male":
                label = "father"
            elif gl == "female":
                label = "mother"
            else:
                label = "parent"
            if other_is_viewer:
                parts.append(f"{member_name} is my {label}")
            else:
                parts.append(f"{member_name} is {label} of {other}")
        elif role == "child_of":
            if gl == "male":
                label = "son"
            elif gl == "female":
                label = "daughter"
            else:
                label = "child"
            if other_is_viewer:
                parts.append(f"{member_name} is my {label}")
            else:
                parts.append(f"{member_name} is {label} of {other}")
        elif role == "spouse_of":
            if other_is_viewer:
                parts.append(f"{member_name} is my spouse")
            else:
                parts.append(f"{member_name} is spouse of {other}")
        elif role == "sibling_of":
            if other_is_viewer:
                parts.append(f"{member_name} is my sibling")
            else:
                parts.append(f"{member_name} is sibling of {other}")
    return " · ".join(parts)


def _graph_parse_member_id(raw: Any) -> int | None:
    if raw in (None, ""):
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    return v


def _graph_member_owned(conn: sqlite3.Connection, user_pid: str, mid: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM family_members WHERE id = ? AND user_private_id = ?",
        (mid, user_pid),
    ).fetchone()
    return row is not None


def _graph_clear_edges_between(conn: sqlite3.Connection, a: int, b: int) -> None:
    conn.execute(
        """
        DELETE FROM family_relationships
         WHERE (source_id = ? AND target_id = ?)
            OR (source_id = ? AND target_id = ?)
        """,
        (a, b, b, a),
    )


def _graph_insert_edge(conn: sqlite3.Connection, src: int, tgt: int, rel_type: str) -> None:
    conn.execute(
        """
        INSERT INTO family_relationships (
            source_id, target_id, relation_type
        ) VALUES (?, ?, ?)
        """,
        (src, tgt, rel_type),
    )


def _graph_apply_pair(
    conn: sqlite3.Connection, m1: int, m2: int, relationship_type: str
) -> None:
    rt = relationship_type.strip().lower()
    if rt == "parent":
        _graph_insert_edge(conn, m1, m2, "parent")
        _graph_insert_edge(conn, m2, m1, "child")
    elif rt == "child":
        _graph_insert_edge(conn, m1, m2, "child")
        _graph_insert_edge(conn, m2, m1, "parent")
    elif rt == "spouse":
        _graph_insert_edge(conn, m1, m2, "spouse")
        _graph_insert_edge(conn, m2, m1, "spouse")
    elif rt == "sibling":
        _graph_insert_edge(conn, m1, m2, "sibling")
        _graph_insert_edge(conn, m2, m1, "sibling")
    else:
        raise ValueError("invalid relationship_type")


def _graph_replace_member_edges(
    conn: sqlite3.Connection,
    mid: int,
    *,
    parent_of: int | None,
    child_of: int | None,
    spouse_of: int | None,
    sibling_of: int | None,
) -> None:
    conn.execute(
        "DELETE FROM family_relationships WHERE source_id = ? OR target_id = ?",
        (mid, mid),
    )
    if parent_of is not None and parent_of != mid:
        _graph_apply_pair(conn, mid, parent_of, "parent")
    if child_of is not None and child_of != mid:
        _graph_apply_pair(conn, mid, child_of, "child")
    if spouse_of is not None and spouse_of != mid:
        _graph_apply_pair(conn, mid, spouse_of, "spouse")
    if sibling_of is not None and sibling_of != mid:
        _graph_apply_pair(conn, mid, sibling_of, "sibling")


def _pick_member_by_relationships(
    conn: sqlite3.Connection,
    user_pid: str,
    rels: tuple[str, ...],
    *,
    exclude_id: int | None = None,
) -> int | None:
    rel_low = tuple(x.strip().lower() for x in rels)
    in_ph = ",".join("?" * len(rel_low))
    sql_parts = [
        "SELECT id FROM family_members",
        "WHERE user_private_id = ?",
        f"AND LOWER(TRIM(relationship)) IN ({in_ph})",
    ]
    args: list[Any] = [user_pid, *rel_low]
    if exclude_id is not None:
        sql_parts.append("AND id != ?")
        args.append(exclude_id)
    sql_parts.append("ORDER BY is_placeholder ASC, id ASC LIMIT 1")
    row = conn.execute(" ".join(sql_parts), tuple(args)).fetchone()
    return int(row["id"]) if row else None


def _graph_autolink_from_relationship(
    conn: sqlite3.Connection,
    user_pid: str,
    self_id: int,
    member_id: int,
    relationship_title: str,
) -> None:
    """Infer canonical edges from a human relationship label (best-effort)."""
    key = _normalize_relationship_menu(relationship_title)
    if key in {"father", "mother"}:
        _graph_apply_pair(conn, member_id, self_id, "parent")
        return
    if key in {"spouse", "husband", "wife"}:
        _graph_apply_pair(conn, member_id, self_id, "spouse")
        return
    if key in {"son", "daughter", "child", "children"}:
        _graph_apply_pair(conn, self_id, member_id, "parent")
        return
    if key in {"sibling", "brother", "sister", "real brother/sister"}:
        _graph_apply_pair(conn, member_id, self_id, "sibling")
        return
    if key in {"paternal grandfather"}:
        p = _pick_member_by_relationships(conn, user_pid, ("father",), exclude_id=member_id)
        if p:
            _graph_apply_pair(conn, member_id, p, "parent")
        return
    if key in {"paternal grandmother"}:
        p = _pick_member_by_relationships(conn, user_pid, ("father",), exclude_id=member_id)
        if p:
            _graph_apply_pair(conn, member_id, p, "parent")
        return
    if key in {"maternal grandfather"}:
        p = _pick_member_by_relationships(conn, user_pid, ("mother",), exclude_id=member_id)
        if p:
            _graph_apply_pair(conn, member_id, p, "parent")
        return
    if key in {"maternal grandmother"}:
        p = _pick_member_by_relationships(conn, user_pid, ("mother",), exclude_id=member_id)
        if p:
            _graph_apply_pair(conn, member_id, p, "parent")
        return


def _family_members_by_id(conn: sqlite3.Connection, user_pid: str) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for r in conn.execute(
        "SELECT * FROM family_members WHERE user_private_id = ? ORDER BY id ASC",
        (user_pid,),
    ):
        d = _family_member_to_dict(r)
        out[int(d["id"])] = d
    return out


def _family_members_nuclear_for_tree(
    conn: sqlite3.Connection, user_pid: str
) -> dict[int, dict[str, Any]]:
    """Members shown in the D3 tree (excludes ``member_type = 'general'``)."""
    out: dict[int, dict[str, Any]] = {}
    for r in conn.execute(
        """
        SELECT * FROM family_members
         WHERE user_private_id = ?
           AND COALESCE(member_type, 'nuclear') = 'nuclear'
         ORDER BY id ASC
        """,
        (user_pid,),
    ):
        d = _family_member_to_dict(r)
        out[int(d["id"])] = d
    return out


def _family_graph_edges_raw(conn: sqlite3.Connection) -> list[tuple[int, int, str]]:
    rows: list[tuple[int, int, str]] = []
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='family_relationships'"
    ).fetchone():
        return rows
    try:
        cols = _table_columns(conn, "family_relationships")
    except sqlite3.OperationalError:
        return rows
    if not {"source_id", "target_id", "relation_type"}.issubset(cols):
        return rows
    try:
        cur = conn.execute(
            "SELECT source_id, target_id, relation_type FROM family_relationships"
        )
    except sqlite3.OperationalError:
        return rows
    for r in cur:
        try:
            s = int(r["source_id"])
            t = int(r["target_id"])
        except (TypeError, ValueError):
            continue
        rows.append((s, t, str(r["relation_type"] or "").strip().lower()))
    return rows


def _sentence_rel_rows_for_subject(
    subject_id: int,
    members_by_id: dict[int, dict[str, Any]],
    edges: list[tuple[int, int, str]],
    viewer_id: int,
    viewer_display: str,
) -> list[dict[str, Any]]:
    rels: list[dict[str, Any]] = []
    for s, t, typ in edges:
        if s != subject_id and t != subject_id:
            continue
        if typ == "parent" and s == subject_id:
            oid = t
            oname = (
                viewer_display
                if oid == viewer_id
                else str(members_by_id.get(oid, {}).get("member_name") or "").strip()
            )
            rels.append(
                {
                    "role": "parent_of",
                    "other_name": oname,
                    "other_is_viewer": oid == viewer_id,
                }
            )
        elif typ == "parent" and t == subject_id:
            oid = s
            oname = (
                viewer_display
                if oid == viewer_id
                else str(members_by_id.get(oid, {}).get("member_name") or "").strip()
            )
            rels.append(
                {
                    "role": "child_of",
                    "other_name": oname,
                    "other_is_viewer": oid == viewer_id,
                }
            )
        elif typ == "child" and s == subject_id:
            oid = t
            oname = (
                viewer_display
                if oid == viewer_id
                else str(members_by_id.get(oid, {}).get("member_name") or "").strip()
            )
            rels.append(
                {
                    "role": "child_of",
                    "other_name": oname,
                    "other_is_viewer": oid == viewer_id,
                }
            )
        elif typ == "child" and t == subject_id:
            oid = s
            oname = (
                viewer_display
                if oid == viewer_id
                else str(members_by_id.get(oid, {}).get("member_name") or "").strip()
            )
            rels.append(
                {
                    "role": "parent_of",
                    "other_name": oname,
                    "other_is_viewer": oid == viewer_id,
                }
            )
        elif typ == "spouse" and s == subject_id:
            oid = t
            oname = (
                viewer_display
                if oid == viewer_id
                else str(members_by_id.get(oid, {}).get("member_name") or "").strip()
            )
            rels.append(
                {
                    "role": "spouse_of",
                    "other_name": oname,
                    "other_is_viewer": oid == viewer_id,
                }
            )
        elif typ == "spouse" and t == subject_id:
            oid = s
            oname = (
                viewer_display
                if oid == viewer_id
                else str(members_by_id.get(oid, {}).get("member_name") or "").strip()
            )
            rels.append(
                {
                    "role": "spouse_of",
                    "other_name": oname,
                    "other_is_viewer": oid == viewer_id,
                }
            )
        elif typ == "sibling" and s == subject_id:
            oid = t
            oname = (
                viewer_display
                if oid == viewer_id
                else str(members_by_id.get(oid, {}).get("member_name") or "").strip()
            )
            rels.append(
                {
                    "role": "sibling_of",
                    "other_name": oname,
                    "other_is_viewer": oid == viewer_id,
                }
            )
        elif typ == "sibling" and t == subject_id:
            oid = s
            oname = (
                viewer_display
                if oid == viewer_id
                else str(members_by_id.get(oid, {}).get("member_name") or "").strip()
            )
            rels.append(
                {
                    "role": "sibling_of",
                    "other_name": oname,
                    "other_is_viewer": oid == viewer_id,
                }
            )
    return rels


def _family_self_member_id(conn: sqlite3.Connection, user_pid: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM family_members WHERE user_private_id = ? AND source = 'self' LIMIT 1",
        (user_pid,),
    ).fetchone()
    if not row:
        return None
    return int(row["id"])


def _urow_get(user_row: sqlite3.Row, key: str, default: Any = None) -> Any:
    try:
        v = user_row[key]
    except (KeyError, TypeError, IndexError):
        return default
    return v if v is not None else default


def _ensure_account_self_row(
    conn: sqlite3.Connection, user_pid: str, user_row: sqlite3.Row
) -> int:
    fn = str(_urow_get(user_row, "first_name") or "").strip() or "You"
    gender = str(_urow_get(user_row, "gender") or "")
    age = _urow_get(user_row, "age")
    pub = str(_urow_get(user_row, "public_id") or "")
    existing = conn.execute(
        "SELECT id FROM family_members WHERE user_private_id = ? AND source = 'self' LIMIT 1",
        (user_pid,),
    ).fetchone()
    if existing:
        sid = int(existing["id"])
        conn.execute(
            """
            UPDATE family_members
               SET member_name = ?, gender = ?, age = ?, relationship = 'Self',
                   is_close_family = 1, is_placeholder = 0, is_dead = 0,
                   account_public_id = COALESCE(account_public_id, ?)
             WHERE id = ? AND user_private_id = ?
            """,
            (fn, gender, age, pub or None, sid, user_pid),
        )
        return sid
    conn.execute(
        """
        INSERT INTO family_members (
            user_private_id, member_name, relationship,
            gender, age, age_modifier,
            is_close_family, is_dead, is_placeholder, account_public_id, source,
            parent_link
        ) VALUES (?, ?, 'Self', ?, ?, NULL, 1, 0, 0, ?, 'self', NULL)
        """,
        (user_pid, fn, gender, age, pub or None),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _should_seed_nuclear_placeholders(conn: sqlite3.Connection, user_pid: str) -> bool:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM family_members
         WHERE user_private_id = ?
           AND source NOT IN ('self', 'placeholder')
           AND COALESCE(is_placeholder, 0) = 0
           AND COALESCE(member_type, 'nuclear') = 'nuclear'
        """,
        (user_pid,),
    ).fetchone()
    if row and int(row["c"] or 0) > 0:
        return False
    row2 = conn.execute(
        """
        SELECT COUNT(*) AS c FROM family_members
         WHERE user_private_id = ? AND source = 'placeholder'
        """,
        (user_pid,),
    ).fetchone()
    return not row2 or int(row2["c"] or 0) == 0


def _ins_placeholder(
    conn: sqlite3.Connection,
    user_pid: str,
    member_name: str,
    relationship: str,
    gender: str = "",
) -> int:
    conn.execute(
        """
        INSERT INTO family_members (
            user_private_id, member_name, relationship,
            gender, age, age_modifier,
            is_close_family, is_dead, is_placeholder, account_public_id, source,
            parent_link
        ) VALUES (?, ?, ?, ?, NULL, NULL, 1, 0, 1, NULL, 'placeholder', NULL)
        """,
        (user_pid, member_name, relationship, gender),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def _seed_nuclear_placeholder_graph(
    conn: sqlite3.Connection, user_pid: str, self_id: int
) -> None:
    """Insert default placeholder members and canonical edges (prototype)."""
    father = _ins_placeholder(conn, user_pid, "Add", "Father", "")
    mother = _ins_placeholder(conn, user_pid, "Add", "Mother", "")
    _graph_apply_pair(conn, father, self_id, "parent")
    _graph_apply_pair(conn, mother, self_id, "parent")

    pgf = _ins_placeholder(conn, user_pid, "Add", "Paternal Grandfather", "")
    pgm = _ins_placeholder(conn, user_pid, "Add", "Paternal Grandmother", "")
    _graph_apply_pair(conn, pgf, father, "parent")
    _graph_apply_pair(conn, pgm, father, "parent")
    _graph_apply_pair(conn, pgf, pgm, "spouse")

    mgf = _ins_placeholder(conn, user_pid, "Add", "Maternal Grandfather", "")
    mgm = _ins_placeholder(conn, user_pid, "Add", "Maternal Grandmother", "")
    _graph_apply_pair(conn, mgf, mother, "parent")
    _graph_apply_pair(conn, mgm, mother, "parent")
    _graph_apply_pair(conn, mgf, mgm, "spouse")

    spouse = _ins_placeholder(conn, user_pid, "Add", "Spouse", "")
    _graph_apply_pair(conn, spouse, self_id, "spouse")

    s1 = _ins_placeholder(conn, user_pid, "Add", "Sibling", "")
    s2 = _ins_placeholder(conn, user_pid, "Add", "Sibling", "")
    _graph_apply_pair(conn, s1, self_id, "sibling")
    _graph_apply_pair(conn, s2, self_id, "sibling")

    c1 = _ins_placeholder(conn, user_pid, "Add", "Child", "")
    c2 = _ins_placeholder(conn, user_pid, "Add", "Child", "")
    _graph_apply_pair(conn, self_id, c1, "parent")
    _graph_apply_pair(conn, self_id, c2, "parent")


def _ensure_family_graph_defaults(
    conn: sqlite3.Connection,
    user_pid: str,
    user_row: sqlite3.Row,
    profile: dict[str, Any],
) -> int:
    """Ensure account self row + nuclear placeholder template when appropriate."""
    sid = _ensure_account_self_row(conn, user_pid, user_row)
    if _user_needs_initial_family_setup(conn, user_pid, profile):
        conn.commit()
        return sid
    if _should_seed_nuclear_placeholders(conn, user_pid):
        _seed_nuclear_placeholder_graph(conn, user_pid, sid)
    conn.commit()
    return sid


def _family_tree_graph_payload(conn: sqlite3.Connection, user_pid: str) -> dict[str, Any]:
    profile = _family_profile_to_dict(_family_profile_row(conn, user_pid))
    user_row = g.current_user
    self_id = _ensure_family_graph_defaults(conn, user_pid, user_row, profile)

    def uget(key: str, default: Any = None) -> Any:
        return _urow_get(user_row, key, default)

    fn = str(uget("first_name") or "").strip()
    ln = str(uget("last_name") or "").strip()
    viewer_name = (f"{fn} {ln}".strip() or str(uget("public_id") or "You")).strip()

    members_by_id = _family_members_nuclear_for_tree(conn, user_pid)
    edges = _family_graph_edges_raw(conn)
    allowed = set(members_by_id.keys())
    filtered: list[tuple[int, int, str]] = []
    for s, t, typ in edges:
        if s in allowed and t in allowed:
            filtered.append((s, t, typ))

    members_out: list[dict[str, Any]] = []
    for mid, m in sorted(members_by_id.items(), key=lambda x: x[0]):
        row = dict(m)
        row["is_self"] = mid == self_id
        members_out.append(row)

    rel_json = [
        {"source": s, "target": t, "type": typ} for s, t, typ in filtered
    ]
    sentences: dict[str, str] = {}
    vid = self_id
    for mid in sorted(members_by_id.keys()):
        rel_rows = _sentence_rel_rows_for_subject(
            mid, members_by_id, filtered, vid, "you"
        )
        nm = str(members_by_id[mid].get("member_name") or "").strip()
        gen = members_by_id[mid].get("gender")
        if mid == vid:
            rel_rows = []
            for s, t, typ in filtered:
                if typ != "spouse":
                    continue
                oid = t if s == vid else s
                if oid == vid:
                    continue
                oname = str(members_by_id.get(oid, {}).get("member_name") or "").strip()
                if oname:
                    rel_rows.append(
                        {"role": "spouse_of", "other_name": oname, "other_is_viewer": False}
                    )
            for s, t, typ in filtered:
                if typ != "child":
                    continue
                if t != vid:
                    continue
                oid = s
                oname = str(members_by_id.get(oid, {}).get("member_name") or "").strip()
                gl = (str(uget("gender") or "").lower())
                if gl == "male":
                    lab = "father"
                elif gl == "female":
                    lab = "mother"
                else:
                    lab = "parent"
                if oname:
                    rel_rows.append(
                        {
                            "role": "child_of",
                            "other_name": oname,
                            "other_is_viewer": False,
                            "viewer_parent_label": lab,
                        }
                    )
            parts_v: list[str] = []
            for rr in rel_rows:
                if rr.get("viewer_parent_label") and rr.get("other_name"):
                    parts_v.append(f"You are {rr['viewer_parent_label']} of {rr['other_name']}")
                elif rr.get("role") == "spouse_of" and rr.get("other_name"):
                    parts_v.append(f"{rr['other_name']} is my spouse")
            for s, t, typ in filtered:
                if typ != "parent":
                    continue
                if t != vid:
                    continue
                oid = s
                p = members_by_id.get(oid)
                if not p:
                    continue
                oname = str(p.get("member_name") or "").strip()
                if not oname:
                    continue
                pgl = str(p.get("gender") or "").lower()
                if pgl == "male":
                    lab = "father"
                elif pgl == "female":
                    lab = "mother"
                else:
                    lab = "parent"
                parts_v.append(f"{oname} is my {lab}")
            sentences[str(mid)] = " · ".join(parts_v) if parts_v else "You"
        else:
            sentences[str(mid)] = get_relationship_sentence(nm, str(gen or ""), rel_rows)
    return {
        "members": members_out,
        "relationships": rel_json,
        "viewer": {
            "id": self_id,
            "display_name": viewer_name,
            "public_id": str(uget("public_id") or ""),
        },
        "sentences": sentences,
        "form_completed": profile["form_completed"],
        "relationship_status": profile["relationship_status"],
    }


def _family_tree_graph_fallback_payload() -> dict[str, Any]:
    """Minimal tree JSON so the UI always loads if the full graph builder fails."""
    ur = g.current_user

    def ug(key: str, default: Any = None) -> Any:
        try:
            v = ur[key]
        except (KeyError, TypeError, IndexError):
            return default
        return v if v is not None else default

    fn = str(ug("first_name") or "").strip()
    ln = str(ug("last_name") or "").strip()
    viewer_name = (f"{fn} {ln}".strip() or str(ug("public_id") or "You")).strip()
    vid = VIEWER_GRAPH_MEMBER_ID
    return {
        "members": [
            {
                "id": vid,
                "member_name": viewer_name,
                "gender": str(ug("gender") or ""),
                "age": ug("age"),
                "is_dead": False,
                "source": "viewer",
                "is_self": True,
                "account_public_id": str(ug("public_id") or ""),
            }
        ],
        "relationships": [],
        "viewer": {
            "id": vid,
            "display_name": viewer_name,
            "public_id": str(ug("public_id") or ""),
        },
        "sentences": {str(vid): viewer_name or "You"},
        "form_completed": False,
        "relationship_status": "",
    }


@app.get("/api/family/all_members")
@login_required
def api_family_all_members():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    form_rows = [
        _family_member_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM family_members WHERE user_private_id = ? ORDER BY id ASC",
            (pid,),
        )
    ]
    conn_rows = _connection_family_members(conn, pid)
    pending = _pending_removal_requests_for_user(conn, pid)
    viewer_admin = is_admin_user(g.current_user)
    members = [
        _annotate_member_removal_state(m, pending, viewer_admin)
        for m in (form_rows + conn_rows)
    ]
    return jsonify({"members": members})


@app.get("/api/family/tree")
@login_required
def api_family_tree():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    try:
        payload = _family_tree_graph_payload(conn, pid)
    except Exception:
        app.logger.exception("api_family_tree failed")
        payload = _family_tree_graph_fallback_payload()
    return jsonify(payload)


@app.post("/api/family/edit_relationship")
@login_required
def api_family_edit_relationship():
    """Create / replace a typed edge pair between two owned members (or viewer -1)."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    m1 = _graph_parse_member_id(
        payload.get("member1_private_id") or payload.get("member1_id")
    )
    m2 = _graph_parse_member_id(
        payload.get("member2_private_id") or payload.get("member2_id")
    )
    rt = str(payload.get("relationship_type") or "").strip().lower()
    if m1 is None or m2 is None or m1 == m2:
        return jsonify({"error": "Two distinct member ids are required"}), 400
    if not _graph_member_owned(conn, pid, m1) or not _graph_member_owned(conn, pid, m2):
        return jsonify({"error": "Members must belong to your account"}), 403
    if rt not in {"parent", "child", "spouse", "sibling"}:
        return jsonify({"error": "relationship_type must be parent, child, spouse, or sibling"}), 400
    try:
        _graph_clear_edges_between(conn, m1, m2)
        _graph_apply_pair(conn, m1, m2, rt)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    conn.commit()
    return jsonify({"ok": True, **_family_tree_graph_payload(conn, pid)})


@app.post("/api/family/add_nuclear")
@login_required
def api_family_add_nuclear():
    """Add a **nuclear** (tree) family member; optional ``public_id`` links a registered user."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    self_id = _family_self_member_id(conn, pid)
    if self_id is None:
        self_id = _ensure_account_self_row(conn, pid, g.current_user)
        conn.commit()

    opt_pub = str(payload.get("public_id") or payload.get("account_public_id") or "").strip()
    linked_pub: str | None = None
    if opt_pub:
        ur = conn.execute(
            "SELECT public_id FROM users WHERE public_id = ? COLLATE NOCASE",
            (opt_pub,),
        ).fetchone()
        if not ur:
            return jsonify({"error": "Account ID not found"}), 404
        linked_pub = str(ur["public_id"] or "").strip()

    replace_ph = _coerce_int(payload.get("replace_placeholder_id"))
    name = str(payload.get("member_name") or payload.get("name") or "").strip()
    gender = str(payload.get("gender") or "").strip()
    age = _coerce_int(payload.get("age"))
    is_dead = 1 if _coerce_bool(payload.get("is_dead")) else 0
    rel_raw = str(
        payload.get("relationship_to_user")
        or payload.get("relationship")
        or ""
    ).strip()
    db_rel = _relationship_title_from_menu(rel_raw) if rel_raw else "Family"
    if not _is_close_family_relationship(db_rel):
        return jsonify({"error": "Relationship must be a nuclear family role"}), 400

    parent_of = _graph_parse_member_id(payload.get("parent_of"))
    child_of = _graph_parse_member_id(payload.get("child_of"))
    spouse_of = _graph_parse_member_id(payload.get("spouse_of"))
    sibling_of = _graph_parse_member_id(payload.get("sibling_of"))
    explicit = any(
        x is not None for x in (parent_of, child_of, spouse_of, sibling_of)
    )

    if replace_ph is not None:
        if not name:
            return jsonify({"error": "member_name is required"}), 400
        row = conn.execute(
            "SELECT id, is_placeholder, source FROM family_members "
            "WHERE id = ? AND user_private_id = ?",
            (replace_ph, pid),
        ).fetchone()
        if not row or not int(row["is_placeholder"] or 0):
            return jsonify({"error": "Placeholder not found"}), 404
        is_close = 1 if _is_close_family_relationship(db_rel) else 0
        conn.execute(
            """
            UPDATE family_members
               SET member_name = ?, relationship = ?, gender = ?, age = ?,
                   is_dead = ?, is_placeholder = 0, is_close_family = ?,
                   source = 'manual', member_type = 'nuclear',
                   account_public_id = COALESCE(?, account_public_id)
             WHERE id = ? AND user_private_id = ?
            """,
            (name, db_rel, gender, age, is_dead, is_close, linked_pub, replace_ph, pid),
        )
        conn.commit()
        return jsonify(
            {"ok": True, "id": replace_ph, **_family_tree_graph_payload(conn, pid)}
        )

    if not name:
        return jsonify({"error": "member_name is required"}), 400

    for oid in (parent_of, child_of, spouse_of, sibling_of):
        if oid is not None and not _graph_member_owned(conn, pid, oid):
            return jsonify({"error": "Related member not found"}), 400

    is_close = 1 if _is_close_family_relationship(db_rel) else 0
    conn.execute(
        """
        INSERT INTO family_members (
            user_private_id, member_name, relationship,
            gender, age, age_modifier,
            is_close_family, is_dead, is_placeholder, account_public_id, source,
            parent_link, tree_mother_member_id, tree_father_member_id,
            tree_spouse_member_id, tree_child_of_member_id,
            tree_child_of_connection_request_id, reference_relation, member_type
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, 0, ?, 'manual', NULL,
                  NULL, NULL, NULL, NULL, NULL, NULL, 'nuclear')
        """,
        (pid, name, db_rel, gender, age, is_close, is_dead, linked_pub),
    )
    new_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    if explicit:
        _graph_replace_member_edges(
            conn,
            new_id,
            parent_of=parent_of,
            child_of=child_of,
            spouse_of=spouse_of,
            sibling_of=sibling_of,
        )
    elif rel_raw:
        _graph_autolink_from_relationship(conn, pid, self_id, new_id, db_rel)
    else:
        _graph_replace_member_edges(
            conn,
            new_id,
            parent_of=None,
            child_of=None,
            spouse_of=None,
            sibling_of=None,
        )
    conn.commit()
    return jsonify({"ok": True, "id": new_id, **_family_tree_graph_payload(conn, pid)})


@app.post("/api/family/add_member")
@login_required
def api_family_add_member():
    """Backward-compatible alias for :func:`api_family_add_nuclear`."""
    return api_family_add_nuclear()


@app.post("/api/family/add_general")
@login_required
def api_family_add_general():
    """Send a **general** family connection request (mandatory Account ID)."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    public_id = str(payload.get("public_id") or payload.get("account_public_id") or "").strip()
    if not public_id:
        return jsonify({"error": "public_id is required"}), 400
    kind = str(payload.get("family_member_kind") or payload.get("relationship") or "").strip()
    custom = str(payload.get("custom_relationship") or "").strip()
    if kind.lower() == "other":
        rel = custom or "Family"
    else:
        rel = kind or "Family"
    if not rel:
        return jsonify({"error": "Family member type is required"}), 400
    member_name = str(payload.get("member_name") or payload.get("name") or "").strip()
    if not member_name:
        return jsonify({"error": "member_name is required"}), 400

    body, code = _connection_request_apply(
        conn,
        pid,
        {
            "public_id": public_id,
            "request_type": "family",
            "relationship": rel,
            "family_member_type": "general",
            "member_name": member_name,
            "gender": str(payload.get("gender") or "").strip() or None,
            "life_stage": str(payload.get("life_stage") or "").strip() or None,
        },
    )
    if code < 400:
        conn.commit()
    return jsonify(body), code


@app.post("/api/family/link_account")
@login_required
def api_family_link_account():
    """Create a pending **link request** so the target user can accept linking their
    account to a row on the requester's family tree."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    try:
        mid = int(payload.get("member_id") or payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "member_id is required"}), 400
    public_id = str(payload.get("public_id") or "").strip()
    if not public_id:
        return jsonify({"error": "public_id is required"}), 400

    row = conn.execute(
        "SELECT * FROM family_members WHERE id = ? AND user_private_id = ?",
        (mid, pid),
    ).fetchone()
    if not row:
        return jsonify({"error": "Member not found"}), 404
    if str(row["source"] or "") == "self":
        return jsonify({"error": "Cannot link the account holder row"}), 400

    tgt = conn.execute(
        "SELECT private_id, public_id, first_name, last_name FROM users "
        "WHERE public_id = ? COLLATE NOCASE",
        (public_id,),
    ).fetchone()
    if not tgt:
        return jsonify({"error": "Account ID not found"}), 404
    to_pid = str(tgt["private_id"])
    if to_pid == pid:
        return jsonify({"error": "You cannot link to yourself"}), 400

    if str(row.get("account_public_id") or "").strip():
        return jsonify({"error": "This member is already linked"}), 400

    rel_label = str(
        payload.get("relationship_label") or row["relationship"] or "Family"
    ).strip()

    dup = conn.execute(
        """
        SELECT id FROM link_requests
         WHERE from_user_private_id = ?
           AND family_member_id = ?
           AND status = 'pending'
        """,
        (pid, mid),
    ).fetchone()
    if dup:
        return jsonify({"error": "A pending link request already exists for this member"}), 409

    cur = conn.execute(
        """
        INSERT INTO link_requests (
            from_user_private_id, to_user_private_id, family_member_id,
            relationship_label, status
        ) VALUES (?, ?, ?, ?, 'pending')
        """,
        (pid, to_pid, mid, rel_label),
    )
    lid = int(cur.lastrowid)

    fn = (
        f"{str(g.current_user['first_name'] or '').strip()} "
        f"{str(g.current_user['last_name'] or '').strip()}"
    ).strip() or str(g.current_user.get("public_id") or "A user")
    subj = "Family account link request"
    body_txt = (
        f"{fn} wants to link your account ({str(tgt['public_id'] or '')}) "
        f"as “{rel_label}” in their family tree.\n\n"
        f"Open your notifications (bell) to accept or reject this request."
    )
    send_system_message(conn, to_pid, subj, body_txt)
    conn.commit()
    return jsonify({"ok": True, "link_request_id": lid})


@app.get("/api/family/link_requests")
@login_required
def api_family_link_requests():
    conn = get_db()
    me = str(g.current_user["private_id"])
    inc = []
    for r in conn.execute(
        """
        SELECT lr.id, lr.family_member_id, lr.relationship_label, lr.created_at,
               u.first_name, u.last_name, u.public_id
          FROM link_requests lr
          JOIN users u ON u.private_id = lr.from_user_private_id
         WHERE lr.to_user_private_id = ? AND lr.status = 'pending'
         ORDER BY datetime(lr.created_at) DESC
        """,
        (me,),
    ):
        nm = (
            f"{str(r['first_name'] or '').strip()} {str(r['last_name'] or '').strip()}"
        ).strip() or str(r["public_id"] or "")
        inc.append(
            {
                "link_request_id": int(r["id"]),
                "family_member_id": int(r["family_member_id"]),
                "relationship_label": str(r["relationship_label"] or ""),
                "created_at": str(r["created_at"] or ""),
                "from_name": nm,
                "from_public_id": str(r["public_id"] or ""),
            }
        )
    out = []
    for r in conn.execute(
        """
        SELECT lr.id, lr.family_member_id, lr.relationship_label, lr.status, lr.created_at,
               u.first_name, u.last_name, u.public_id
          FROM link_requests lr
          JOIN users u ON u.private_id = lr.to_user_private_id
         WHERE lr.from_user_private_id = ?
         ORDER BY datetime(lr.created_at) DESC
         LIMIT 30
        """,
        (me,),
    ):
        nm = (
            f"{str(r['first_name'] or '').strip()} {str(r['last_name'] or '').strip()}"
        ).strip() or str(r["public_id"] or "")
        out.append(
            {
                "link_request_id": int(r["id"]),
                "family_member_id": int(r["family_member_id"]),
                "relationship_label": str(r["relationship_label"] or ""),
                "status": str(r["status"] or ""),
                "created_at": str(r["created_at"] or ""),
                "to_name": nm,
                "to_public_id": str(r["public_id"] or ""),
            }
        )
    return jsonify({"incoming": inc, "outgoing": out})


@app.post("/api/family/link_accept")
@login_required
def api_family_link_accept():
    conn = get_db()
    me = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    try:
        lid = int(payload.get("link_request_id") or payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "link_request_id is required"}), 400

    lr = conn.execute(
        """
        SELECT * FROM link_requests
         WHERE id = ? AND to_user_private_id = ? AND status = 'pending'
        """,
        (lid, me),
    ).fetchone()
    if not lr:
        return jsonify({"error": "Request not found"}), 404

    from_pid = str(lr["from_user_private_id"])
    mid = int(lr["family_member_id"])
    my_pub = str(g.current_user["public_id"] or "").strip()
    if not my_pub:
        return jsonify({"error": "Your account has no public_id"}), 400

    row = conn.execute(
        "SELECT id FROM family_members WHERE id = ? AND user_private_id = ?",
        (mid, from_pid),
    ).fetchone()
    if not row:
        conn.execute("UPDATE link_requests SET status = 'rejected' WHERE id = ?", (lid,))
        conn.commit()
        return jsonify({"error": "Family member row no longer exists"}), 409

    conn.execute(
        """
        UPDATE family_members
           SET account_public_id = ?
         WHERE id = ? AND user_private_id = ?
        """,
        (my_pub, mid, from_pid),
    )
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE link_requests
           SET status = 'accepted', resolved_at = ?
         WHERE id = ?
        """,
        (now_iso, lid),
    )
    acc_nm = (
        f"{str(g.current_user['first_name'] or '').strip()} "
        f"{str(g.current_user['last_name'] or '').strip()}"
    ).strip() or my_pub
    send_system_message(
        conn,
        from_pid,
        "Family link accepted",
        f"{acc_nm} accepted your request to link their account as "
        f"“{str(lr['relationship_label'] or 'family')}” on your family tree.",
    )
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/family/link_reject")
@login_required
def api_family_link_reject():
    conn = get_db()
    me = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    try:
        lid = int(payload.get("link_request_id") or payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "link_request_id is required"}), 400
    msg = str(payload.get("message") or "").strip()

    lr = conn.execute(
        """
        SELECT * FROM link_requests
         WHERE id = ? AND to_user_private_id = ? AND status = 'pending'
        """,
        (lid, me),
    ).fetchone()
    if not lr:
        return jsonify({"error": "Request not found"}), 404

    from_pid = str(lr["from_user_private_id"])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE link_requests
           SET status = 'rejected', resolved_at = ?, reject_message = ?
         WHERE id = ?
        """,
        (now_iso, msg[:1500] if msg else None, lid),
    )
    acc_nm = (
        f"{str(g.current_user['first_name'] or '').strip()} "
        f"{str(g.current_user['last_name'] or '').strip()}"
    ).strip() or str(g.current_user.get("public_id") or "User")
    body = f"{acc_nm} declined your family account link request."
    if msg:
        body += f"\n\nThey wrote:\n{msg}"
    send_system_message(conn, from_pid, "Family link declined", body)
    conn.commit()
    return jsonify({"ok": True})


def _education_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if not row:
        return {
            "education_level": "Uneducated",
            "school_class_passed": "",
            "school_year": None,
            "school_institution": "",
            "college_degree_type": "",
            "college_status_passed": False,
            "college_status_dropout": False,
            "college_year": None,
            "college_institution": "",
        }
    return {
        "education_level": str(row["education_level"] or "Uneducated"),
        "school_class_passed": str(row["school_class_passed"] or ""),
        "school_year": int(row["school_year"]) if row["school_year"] is not None else None,
        "school_institution": str(row["school_institution"] or ""),
        "college_degree_type": str(row["college_degree_type"] or ""),
        "college_status_passed": bool(int(row["college_status_passed"] or 0)),
        "college_status_dropout": bool(int(row["college_status_dropout"] or 0)),
        "college_year": int(row["college_year"]) if row["college_year"] is not None else None,
        "college_institution": str(row["college_institution"] or ""),
    }


def _work_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if not row:
        return {
            "work_status": "Unemployed",
            "unemployed_sub": "",
            "employee_workplace": "",
            "employee_experience": "",
            "employer_org_type": "",
            "employer_company_name": "",
            "employer_location": "",
            "employer_years": None,
            "employer_months": None,
            "employer_business_name": "",
        }
    return {
        "work_status": str(row["work_status"] or "Unemployed"),
        "unemployed_sub": str(row["unemployed_sub"] or ""),
        "employee_workplace": str(row["employee_workplace"] or ""),
        "employee_experience": str(row["employee_experience"] or ""),
        "employer_org_type": str(row["employer_org_type"] or ""),
        "employer_company_name": str(row["employer_company_name"] or ""),
        "employer_location": str(row["employer_location"] or ""),
        "employer_years": int(row["employer_years"]) if row["employer_years"] is not None else None,
        "employer_months": int(row["employer_months"]) if row["employer_months"] is not None else None,
        "employer_business_name": str(row["employer_business_name"] or ""),
    }


@app.get("/api/user/private_info")
@login_required
def api_user_private_info():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    edu = conn.execute("SELECT * FROM user_education WHERE user_private_id = ?", (pid,)).fetchone()
    wrk = conn.execute("SELECT * FROM user_work WHERE user_private_id = ?", (pid,)).fetchone()
    return jsonify(
        {
            "education": _education_row_to_dict(edu),
            "work": _work_row_to_dict(wrk),
            "life_stage": _life_stage_from_user_row(g.current_user),
        }
    )


@app.post("/api/user/education")
@login_required
def api_user_education_save():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    level = str(payload.get("education_level") or "Uneducated").strip()
    if level not in {"Uneducated", "School", "College"}:
        return jsonify({"error": "education_level must be Uneducated, School, or College"}), 400
    sch_class = str(payload.get("school_class_passed") or "").strip() or None
    sch_year = _coerce_int(payload.get("school_year"))
    sch_inst = str(payload.get("school_institution") or "").strip() or None
    col_deg = str(payload.get("college_degree_type") or "").strip() or None
    if col_deg and col_deg not in {"Graduation", "Post-Graduation"}:
        return jsonify({"error": "college_degree_type must be Graduation or Post-Graduation"}), 400
    col_pass = 1 if _coerce_bool(payload.get("college_status_passed")) else 0
    col_drop = 1 if _coerce_bool(payload.get("college_status_dropout")) else 0
    col_year = _coerce_int(payload.get("college_year"))
    col_inst = str(payload.get("college_institution") or "").strip() or None
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO user_education (
            user_private_id, education_level,
            school_class_passed, school_year, school_institution,
            college_degree_type, college_status_passed, college_status_dropout,
            college_year, college_institution, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_private_id) DO UPDATE SET
            education_level = excluded.education_level,
            school_class_passed = excluded.school_class_passed,
            school_year = excluded.school_year,
            school_institution = excluded.school_institution,
            college_degree_type = excluded.college_degree_type,
            college_status_passed = excluded.college_status_passed,
            college_status_dropout = excluded.college_status_dropout,
            college_year = excluded.college_year,
            college_institution = excluded.college_institution,
            updated_at = excluded.updated_at
        """,
        (
            pid,
            level,
            sch_class,
            sch_year,
            sch_inst,
            col_deg if level == "College" else None,
            col_pass if level == "College" else 0,
            col_drop if level == "College" else 0,
            col_year if level == "College" else None,
            col_inst if level == "College" else None,
            now_iso,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM user_education WHERE user_private_id = ?", (pid,)).fetchone()
    return jsonify({"ok": True, "education": _education_row_to_dict(row)})


@app.post("/api/user/work")
@login_required
def api_user_work_save():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("work_status") or "Unemployed").strip()
    allowed = {"Unemployed", "Employee", "Employer", "Retired"}
    if status not in allowed:
        return jsonify({"error": "work_status must be Unemployed, Employee, Employer, or Retired"}), 400
    ls = _life_stage_from_user_row(g.current_user)
    if status == "Retired" and ls not in {"Vridh", "Sanyas"}:
        return jsonify(
            {"error": "Retired is only available when your age group is Vridh (50–75) or Sanyas (75+)."}
        ), 400
    un_sub = str(payload.get("unemployed_sub") or "").strip() or None
    if status == "Unemployed" and un_sub and un_sub not in {
        "Not interested in Employment",
        "Searching Employment",
    }:
        return jsonify({"error": "Invalid unemployed_sub value"}), 400
    emp_wp = str(payload.get("employee_workplace") or "").strip() or None
    emp_ex = str(payload.get("employee_experience") or "").strip() or None
    org_type = str(payload.get("employer_org_type") or "").strip() or None
    if org_type and org_type not in {"Organised", "Unorganised"}:
        return jsonify({"error": "employer_org_type must be Organised or Unorganised"}), 400
    co_nm = str(payload.get("employer_company_name") or "").strip() or None
    co_loc = str(payload.get("employer_location") or "").strip() or None
    co_y = _coerce_int(payload.get("employer_years"))
    co_m = _coerce_int(payload.get("employer_months"))
    bus_nm = str(payload.get("employer_business_name") or "").strip() or None
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO user_work (
            user_private_id, work_status, unemployed_sub,
            employee_workplace, employee_experience,
            employer_org_type, employer_company_name, employer_location,
            employer_years, employer_months, employer_business_name, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_private_id) DO UPDATE SET
            work_status = excluded.work_status,
            unemployed_sub = excluded.unemployed_sub,
            employee_workplace = excluded.employee_workplace,
            employee_experience = excluded.employee_experience,
            employer_org_type = excluded.employer_org_type,
            employer_company_name = excluded.employer_company_name,
            employer_location = excluded.employer_location,
            employer_years = excluded.employer_years,
            employer_months = excluded.employer_months,
            employer_business_name = excluded.employer_business_name,
            updated_at = excluded.updated_at
        """,
        (
            pid,
            status,
            un_sub if status == "Unemployed" else None,
            emp_wp if status == "Employee" else None,
            emp_ex if status == "Employee" else None,
            org_type if status == "Employer" else None,
            co_nm if status == "Employer" and org_type == "Organised" else None,
            co_loc if status == "Employer" and org_type == "Organised" else None,
            co_y if status == "Employer" and org_type == "Organised" else None,
            co_m if status == "Employer" and org_type == "Organised" else None,
            bus_nm if status == "Employer" and org_type == "Unorganised" else None,
            now_iso,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM user_work WHERE user_private_id = ?", (pid,)).fetchone()
    return jsonify({"ok": True, "work": _work_row_to_dict(row)})


@app.post("/api/family/unlink_account")
@login_required
def api_family_unlink_account():
    """Clear ``account_public_id`` on a nuclear row, or remove a **general** link
    (deletes the accepted general family connection and the list row)."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    try:
        mid = int(payload.get("member_id") or payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "member_id is required"}), 400
    row = conn.execute(
        "SELECT source, member_type, account_public_id FROM family_members "
        "WHERE id = ? AND user_private_id = ?",
        (mid, pid),
    ).fetchone()
    if not row:
        return jsonify({"error": "Member not found"}), 404
    if str(row["source"] or "") == "self":
        return jsonify({"error": "Cannot unlink the account holder"}), 400
    if str(row["member_type"] or "nuclear").lower() == "general":
        pub = str(row["account_public_id"] or "").strip()
        if not pub:
            conn.execute(
                "DELETE FROM family_members WHERE id = ? AND user_private_id = ?",
                (mid, pid),
            )
            conn.commit()
            return jsonify({"ok": True, **_family_tree_graph_payload(conn, pid)})
        other = conn.execute(
            "SELECT private_id FROM users WHERE public_id = ? COLLATE NOCASE",
            (pub,),
        ).fetchone()
        if other:
            other_pid = str(other["private_id"])
            conn.execute(
                """
                DELETE FROM connection_requests
                 WHERE request_type = 'family'
                   AND COALESCE(family_member_type, 'nuclear') = 'general'
                   AND status = 'accepted'
                   AND (
                        (from_user_private_id = ? AND to_user_private_id = ?)
                     OR (from_user_private_id = ? AND to_user_private_id = ?)
                   )
                """,
                (pid, other_pid, other_pid, pid),
            )
        conn.execute(
            "DELETE FROM family_members WHERE id = ? AND user_private_id = ?",
            (mid, pid),
        )
        conn.commit()
        return jsonify({"ok": True, **_family_tree_graph_payload(conn, pid)})
    conn.execute(
        "UPDATE family_members SET account_public_id = NULL WHERE id = ? AND user_private_id = ?",
        (mid, pid),
    )
    conn.commit()
    return jsonify({"ok": True, **_family_tree_graph_payload(conn, pid)})


@app.post("/api/family/update_member")
@login_required
def api_family_update_member():
    """Update **name / age / gender** for a nuclear ``family_members`` row (no graph changes)."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    try:
        mid = int(payload.get("member_id") or payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "member_id is required"}), 400
    row = conn.execute(
        "SELECT member_type, source FROM family_members WHERE id = ? AND user_private_id = ?",
        (mid, pid),
    ).fetchone()
    if not row:
        return jsonify({"error": "Member not found"}), 404
    if str(row["member_type"] or "nuclear").lower() == "general":
        return jsonify({"error": "General members cannot be edited here"}), 400
    if str(row["source"] or "") == "self":
        return jsonify({"error": "Use your profile settings for your own name"}), 400
    name = str(payload.get("member_name") or "").strip()
    if not name:
        return jsonify({"error": "member_name is required"}), 400
    gender = str(payload.get("gender") or "").strip()
    age = _coerce_int(payload.get("age"))
    conn.execute(
        """
        UPDATE family_members SET member_name = ?, gender = ?, age = ?
         WHERE id = ? AND user_private_id = ?
        """,
        (name, gender, age, mid, pid),
    )
    conn.commit()
    return jsonify({"ok": True, **_family_tree_graph_payload(conn, pid)})


@app.post("/api/family/update_relationships")
@login_required
def api_family_update_relationships():
    """Update profile fields and replace all graph edges touching one member."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    try:
        mid = int(payload.get("member_id") or payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "member_id is required"}), 400
    self_id = _family_self_member_id(conn, pid)
    if self_id is not None and mid == self_id:
        return jsonify({"error": "Cannot rewire the account holder via this endpoint"}), 400
    if not _graph_member_owned(conn, pid, mid):
        return jsonify({"error": "Member not found"}), 404
    mt_row = conn.execute(
        "SELECT COALESCE(member_type, 'nuclear') AS mt FROM family_members "
        "WHERE id = ? AND user_private_id = ?",
        (mid, pid),
    ).fetchone()
    if mt_row and str(mt_row["mt"] or "").lower() == "general":
        return jsonify({"error": "General relatives are not part of the tree graph"}), 400
    name = str(payload.get("member_name") or "").strip()
    if not name:
        return jsonify({"error": "member_name is required"}), 400
    gender = str(payload.get("gender") or "").strip()
    age = _coerce_int(payload.get("age"))
    is_dead = 1 if _coerce_bool(payload.get("is_dead")) else 0
    parent_of = _graph_parse_member_id(payload.get("parent_of"))
    child_of = _graph_parse_member_id(payload.get("child_of"))
    spouse_of = _graph_parse_member_id(payload.get("spouse_of"))
    sibling_of = _graph_parse_member_id(payload.get("sibling_of"))
    for oid in (parent_of, child_of, spouse_of, sibling_of):
        if oid is not None and oid != mid and not _graph_member_owned(conn, pid, oid):
            return jsonify({"error": "Related member not found"}), 400
    conn.execute(
        """
        UPDATE family_members
           SET member_name = ?, gender = ?, age = ?, is_dead = ?
         WHERE id = ? AND user_private_id = ?
        """,
        (name, gender, age, is_dead, mid, pid),
    )
    _graph_replace_member_edges(
        conn,
        mid,
        parent_of=parent_of,
        child_of=child_of,
        spouse_of=spouse_of,
        sibling_of=sibling_of,
    )
    conn.commit()
    return jsonify({"ok": True, **_family_tree_graph_payload(conn, pid)})


@app.post("/api/family/mark_dead")
@login_required
def api_family_mark_dead():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    source = str(payload.get("source") or "form").strip().lower()
    try:
        member_id = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "id is required"}), 400
    if source not in {"form", "manual", "connection", "general"}:
        return jsonify({"error": "source must be form, manual, general, or connection"}), 400
    if source in {"form", "manual", "general"}:
        cur = conn.execute(
            "UPDATE family_members SET is_dead = 1 "
            "WHERE id = ? AND user_private_id = ? "
            "AND COALESCE(is_placeholder, 0) = 0 AND source != 'self'",
            (member_id, pid),
        )
    else:
        cur = conn.execute(
            "UPDATE connection_requests SET is_dead = 1 "
            "WHERE id = ? AND status = 'accepted' "
            "  AND request_type = 'family' "
            "  AND (from_user_private_id = ? OR to_user_private_id = ?)",
            (member_id, pid, pid),
        )
    conn.commit()
    if cur.rowcount != 1:
        return jsonify({"error": "Member not found"}), 404
    return jsonify({"ok": True})


GRANDPARENT_RELATIONSHIPS = (
    "Paternal Grandfather",
    "Paternal Grandmother",
    "Maternal Grandfather",
    "Maternal Grandmother",
)


@app.post("/api/family/add_grandparent")
@login_required
def api_family_add_grandparent():
    """Insert a grandparent close-family row from the empty tree slot modal."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}

    relationship = str(payload.get("relationship") or "").strip().title()
    if relationship not in GRANDPARENT_RELATIONSHIPS:
        return jsonify({"error": "relationship must be a grandparent slot"}), 400

    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    gender = str(payload.get("gender") or "").strip()
    if not gender:
        gender = "Male" if "grandfather" in relationship.lower() else "Female"
    if gender not in {"Male", "Female"}:
        return jsonify({"error": "gender must be Male or Female"}), 400

    is_dead = 1 if _coerce_bool(payload.get("is_dead")) else 0

    existing = conn.execute(
        """
        SELECT id FROM family_members
        WHERE user_private_id = ?
          AND LOWER(TRIM(relationship)) = LOWER(?)
        LIMIT 1
        """,
        (pid, relationship),
    ).fetchone()
    if existing:
        return (
            jsonify(
                {
                    "error": f"{relationship} is already set. Mark them deceased or contact admin to reset."
                }
            ),
            409,
        )

    conn.execute(
        """
        INSERT INTO family_members (
            user_private_id, member_name, relationship,
            gender, age, age_modifier,
            is_close_family, is_dead, account_public_id, source
        ) VALUES (?, ?, ?, ?, NULL, NULL, 1, ?, NULL, 'form')
        """,
        (pid, name, relationship, gender, is_dead),
    )
    conn.commit()
    return jsonify({"ok": True})


def _optional_same_user_family_member_id(
    conn: sqlite3.Connection, user_pid: str, raw: Any
) -> int | None:
    if raw in (None, "", 0, "0"):
        return None
    try:
        mid = int(raw)
    except (TypeError, ValueError):
        return None
    if mid <= 0:
        return None
    row = conn.execute(
        "SELECT id FROM family_members WHERE id = ? AND user_private_id = ?",
        (mid, user_pid),
    ).fetchone()
    return int(row["id"]) if row else None


def _optional_same_user_nuclear_family_connection_request_id(
    conn: sqlite3.Connection, user_pid: str, raw: Any
) -> int | None:
    """Accepted family ``connection_requests.id`` the user participates in, nuclear only."""
    if raw in (None, "", 0, "0"):
        return None
    try:
        rid = int(raw)
    except (TypeError, ValueError):
        return None
    if rid <= 0:
        return None
    row = conn.execute(
        """
        SELECT cr.id
          FROM connection_requests cr
         WHERE cr.id = ?
           AND cr.status = 'accepted'
           AND cr.request_type = 'family'
           AND (cr.from_user_private_id = ? OR cr.to_user_private_id = ?)
           AND COALESCE(cr.family_member_type, 'nuclear') = 'nuclear'
        """,
        (rid, user_pid, user_pid),
    ).fetchone()
    return int(row["id"]) if row else None


def _nuclear_parent_link_candidates(
    conn: sqlite3.Connection, user_pid: str
) -> list[dict[str, Any]]:
    """Form/manual close-family rows plus accepted nuclear family connections."""
    out: list[dict[str, Any]] = []
    for r in conn.execute(
        """
        SELECT * FROM family_members
         WHERE user_private_id = ? AND is_close_family = 1
         ORDER BY id ASC
        """,
        (user_pid,),
    ):
        d = _family_member_to_dict(r)
        out.append(
            {
                "kind": "member",
                "member_id": d["id"],
                "member_name": d["member_name"],
                "relationship": d["relationship"],
            }
        )
    for m in _connection_family_members(conn, user_pid):
        if not m.get("is_close_family"):
            continue
        if str(m.get("family_member_type") or "nuclear") != "nuclear":
            continue
        out.append(
            {
                "kind": "connection",
                "connection_request_id": int(m["id"]),
                "member_name": m["member_name"],
                "relationship": m["relationship"],
            }
        )
    return out


def _enrich_member_tree_linked_parent_names(
    conn: sqlite3.Connection, user_pid: str, m: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not m:
        return None
    out = dict(m)

    def _name_from_member_id(mid: int) -> str:
        row = conn.execute(
            "SELECT member_name FROM family_members "
            "WHERE id = ? AND user_private_id = ?",
            (mid, user_pid),
        ).fetchone()
        return str(row["member_name"] or "").strip() if row else ""

    def _name_from_connection_request(rid: int) -> str:
        row = conn.execute(
            """
            SELECT u.first_name, u.last_name, u.public_id
              FROM connection_requests cr
              JOIN users u ON u.private_id = CASE
                  WHEN cr.from_user_private_id = ? THEN cr.to_user_private_id
                  ELSE cr.from_user_private_id
              END
             WHERE cr.id = ?
               AND cr.status = 'accepted'
               AND cr.request_type = 'family'
               AND (cr.from_user_private_id = ? OR cr.to_user_private_id = ?)
            """,
            (user_pid, rid, user_pid, user_pid),
        ).fetchone()
        if not row:
            return ""
        full = (
            f"{str(row['first_name'] or '').strip()} {str(row['last_name'] or '').strip()}"
        ).strip()
        return full or str(row["public_id"] or "")

    tm = out.get("tree_mother_member_id")
    tmc = out.get("tree_mother_connection_request_id")
    if tm is not None:
        out["linked_mother_name"] = _name_from_member_id(int(tm))
    elif tmc is not None:
        out["linked_mother_name"] = _name_from_connection_request(int(tmc))
    tf = out.get("tree_father_member_id")
    tfc = out.get("tree_father_connection_request_id")
    if tf is not None:
        out["linked_father_name"] = _name_from_member_id(int(tf))
    elif tfc is not None:
        out["linked_father_name"] = _name_from_connection_request(int(tfc))
    ref = str(out.get("reference_relation") or "").strip()
    tcc = out.get("tree_child_of_connection_request_id")
    tcm = out.get("tree_child_of_member_id")
    if ref and (tcm is not None or tcc is not None):
        other_n = ""
        if tcm is not None:
            other_n = _name_from_member_id(int(tcm))
        elif tcc is not None:
            other_n = _name_from_connection_request(int(tcc))
        if other_n:
            out["natural_lineage_phrase"] = ref + " of " + other_n
    return out


@app.post("/api/family/add_close_manual")
@login_required
def api_family_add_close_manual():
    """Add a close-family row from the dashboard (``source = 'manual'``)."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    choice = str(payload.get("relationship") or "").strip()
    name = str(payload.get("name") or payload.get("member_name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if not choice:
        return jsonify({"error": "relationship is required"}), 400
    if _normalize_relationship_menu(choice) == "self":
        return jsonify({"error": "Self is not a valid row here"}), 400
    gender = str(payload.get("gender") or "").strip()
    age = _coerce_int(payload.get("age"))
    connect_id = _optional_same_user_family_member_id(
        conn, pid, payload.get("connect_to_member_id")
    )
    tree_child_override = _optional_same_user_family_member_id(
        conn, pid, payload.get("tree_child_of_member_id")
    )

    db_rel = choice
    if choice == "Child" or _normalize_relationship_menu(choice) == "child":
        gl = gender.lower()
        if gl == "male":
            db_rel = "Son"
        elif gl == "female":
            db_rel = "Daughter"
        else:
            db_rel = "Child"
    elif choice == "Sibling" or _normalize_relationship_menu(choice) == "sibling":
        db_rel = "Sibling"
    else:
        db_rel = _relationship_title_from_menu(choice)

    if not _is_close_family_relationship(db_rel):
        return jsonify({"error": "Unsupported relationship for close family"}), 400

    tree_child_of: int | None = tree_child_override
    if choice == "Child" and connect_id is not None:
        tree_child_of = connect_id
    elif tree_child_of is None and connect_id is not None:
        tree_child_of = connect_id

    conn.execute(
        """
        INSERT INTO family_members (
            user_private_id, member_name, relationship,
            gender, age, age_modifier,
            is_close_family, is_dead, account_public_id, source,
            parent_link, tree_mother_member_id, tree_father_member_id,
            tree_spouse_member_id, tree_child_of_member_id,
            tree_child_of_connection_request_id, reference_relation
        ) VALUES (?, ?, ?, ?, ?, NULL, 1, 0, NULL, 'manual', NULL,
                  NULL, NULL, NULL, ?, NULL, NULL)
        """,
        (pid, name, db_rel, gender, age, tree_child_of),
    )
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/family/member_sentence_save")
@login_required
def api_family_member_sentence_save():
    """Natural-language editor: ``[Name] is [rel] of [Other]`` (saved rows only)."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    try:
        mid = int(payload.get("member_id") or payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "member_id is required"}), 400
    row = conn.execute(
        "SELECT id, relationship FROM family_members WHERE id = ? AND user_private_id = ?",
        (mid, pid),
    ).fetchone()
    if not row:
        return jsonify({"error": "Member not found"}), 404
    current_rel = str(row["relationship"] or "").strip()
    ref_rel_raw = str(payload.get("reference_relation") or "").strip()
    om = _optional_same_user_family_member_id(conn, pid, payload.get("other_member_id"))
    oc = _optional_same_user_nuclear_family_connection_request_id(
        conn, pid, payload.get("other_connection_request_id")
    )
    if om is not None and oc is not None:
        return jsonify({"error": "Choose one other person (member or account), not both"}), 400
    if om == mid:
        return jsonify({"error": "Cannot reference the same row"}), 400

    if not ref_rel_raw and om is None and oc is None:
        conn.execute(
            """
            UPDATE family_members
               SET reference_relation = NULL,
                   tree_child_of_member_id = NULL,
                   tree_child_of_connection_request_id = NULL
             WHERE id = ? AND user_private_id = ?
            """,
            (mid, pid),
        )
        conn.commit()
        return jsonify({"ok": True})

    if ref_rel_raw and om is None and oc is None:
        return jsonify({"error": "Choose the other family member"}), 400
    if (om is not None or oc is not None) and not ref_rel_raw:
        return jsonify({"error": "reference_relation is required"}), 400

    rnorm = _normalize_relationship_menu(ref_rel_raw)

    merged_rel = current_rel
    if rnorm in _LINEAGE_REFERENCE_RELS and (om is not None or oc is not None):
        merged_rel = current_rel or _relationship_title_from_menu(ref_rel_raw)
    else:
        merged_rel = _relationship_title_from_menu(ref_rel_raw) or current_rel

    conn.execute(
        """
        UPDATE family_members
           SET reference_relation = ?,
               tree_child_of_member_id = ?,
               tree_child_of_connection_request_id = ?,
               tree_mother_member_id = NULL,
               tree_father_member_id = NULL,
               tree_mother_connection_request_id = NULL,
               tree_father_connection_request_id = NULL,
               relationship = ?
         WHERE id = ? AND user_private_id = ?
        """,
        (ref_rel_raw, om, oc, merged_rel, mid, pid),
    )
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/family/dashboard_add")
@login_required
def api_family_dashboard_add():
    """Add Family Member button: name/age/gender + type + optional account ID."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("member_name") or payload.get("name") or "").strip()
    gender = str(payload.get("gender") or "").strip()
    age = _coerce_int(payload.get("age"))
    rel_menu = str(payload.get("relationship") or "").strip()
    fmt = str(payload.get("family_member_type") or "").strip().lower()
    public_id = str(payload.get("public_id") or "").strip()

    if not name:
        return jsonify({"error": "name is required"}), 400
    if not rel_menu:
        return jsonify({"error": "relationship is required"}), 400
    if fmt not in {"nuclear", "general"}:
        return jsonify({"error": "family_member_type must be nuclear or general"}), 400
    if _normalize_relationship_menu(rel_menu) == "self":
        return jsonify({"error": "Self is not valid here"}), 400
    if not _is_close_family_relationship(rel_menu):
        return jsonify({"error": "Unsupported relationship"}), 400
    if fmt == "general" and not public_id:
        return jsonify({"error": "Account ID is required for General Family"}), 400

    db_rel = _relationship_title_from_menu(rel_menu)
    if rel_menu == "Child" or _normalize_relationship_menu(rel_menu) == "child":
        gl = gender.lower()
        if gl == "male":
            db_rel = "Son"
        elif gl == "female":
            db_rel = "Daughter"
        else:
            db_rel = "Child"
    elif rel_menu == "Sibling" or _normalize_relationship_menu(rel_menu) == "sibling":
        db_rel = "Sibling"

    is_close = 1 if fmt == "nuclear" else (1 if _is_close_family_relationship(db_rel) else 0)

    if fmt == "nuclear" and not public_id:
        conn.execute(
            """
            INSERT INTO family_members (
                user_private_id, member_name, relationship,
                gender, age, age_modifier,
                is_close_family, is_dead, account_public_id, source,
                parent_link, tree_mother_member_id, tree_father_member_id,
                tree_spouse_member_id, tree_child_of_member_id,
                tree_child_of_connection_request_id, reference_relation
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, 0, NULL, 'manual', NULL,
                      NULL, NULL, NULL, NULL, NULL, NULL)
            """,
            (pid, name, db_rel, gender, age, is_close),
        )
        conn.commit()
        return jsonify({"ok": True, "mode": "manual_row"})

    target = conn.execute(
        "SELECT private_id FROM users WHERE public_id = ? COLLATE NOCASE",
        (public_id,),
    ).fetchone()
    if not target:
        return jsonify({"error": "Account ID not found"}), 404
    to_pid = str(target["private_id"])
    if to_pid == pid:
        return jsonify({"error": "You cannot connect to yourself"}), 400
    state = _connection_status_between(conn, pid, to_pid, "family")
    if state["status"] in {"accepted", "pending"}:
        return (
            jsonify(
                {
                    "error": _connection_status_message(state, "family"),
                    "status": state["status"],
                }
            ),
            409,
        )
    conn.execute(
        """
        INSERT INTO connection_requests (
            from_user_private_id, to_user_private_id, request_type, relationship,
            status, family_member_type,
            request_member_name, request_member_age, request_member_gender,
            request_member_life_stage
        ) VALUES (?, ?, 'family', ?, 'pending', ?, ?, ?, ?, NULL)
        ON CONFLICT(from_user_private_id, to_user_private_id, request_type)
        DO UPDATE SET relationship = excluded.relationship,
                      family_member_type = excluded.family_member_type,
                      request_member_name = excluded.request_member_name,
                      request_member_age = excluded.request_member_age,
                      request_member_gender = excluded.request_member_gender,
                      request_member_life_stage = excluded.request_member_life_stage,
                      status = 'pending',
                      created_at = CURRENT_TIMESTAMP
        """,
        (pid, to_pid, db_rel, fmt, name, age, gender or None),
    )
    conn.commit()
    return jsonify({"ok": True, "mode": "connection_request"})


@app.get("/api/family/tree_links")
@login_required
def api_family_tree_links():
    """All ``family_members`` rows for manual tree-connection editing."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    rows = [
        _family_member_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM family_members WHERE user_private_id = ? ORDER BY id ASC",
            (pid,),
        )
    ]
    candidates = _nuclear_parent_link_candidates(conn, pid)
    return jsonify({"members": rows, "nuclear_parent_candidates": candidates})


@app.post("/api/family/tree_links/save")
@login_required
def api_family_tree_links_save():
    """Update optional tree FK columns on ``family_members`` rows."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    updates = payload.get("updates")
    if not isinstance(updates, list) or not updates:
        return jsonify({"error": "updates (non-empty list) is required"}), 400
    all_ids = {
        int(r["id"])
        for r in conn.execute(
            "SELECT id FROM family_members WHERE user_private_id = ?",
            (pid,),
        )
    }
    for u in updates:
        if not isinstance(u, dict):
            continue
        try:
            mid = int(u.get("id"))
        except (TypeError, ValueError):
            return jsonify({"error": "Each update needs a numeric id"}), 400
        if mid not in all_ids:
            return jsonify({"error": f"Unknown member id {mid}"}), 400
        cur_row = conn.execute(
            """
            SELECT tree_mother_member_id, tree_father_member_id,
                   tree_mother_connection_request_id, tree_father_connection_request_id,
                   tree_spouse_member_id, tree_child_of_member_id
              FROM family_members
             WHERE id = ? AND user_private_id = ?
            """,
            (mid, pid),
        ).fetchone()
        if not cur_row:
            return jsonify({"error": f"Unknown member id {mid}"}), 400
        cm = cur_row["tree_mother_member_id"]
        cf = cur_row["tree_father_member_id"]
        cmc = cur_row["tree_mother_connection_request_id"]
        cfc = cur_row["tree_father_connection_request_id"]
        csp = cur_row["tree_spouse_member_id"]
        cch = cur_row["tree_child_of_member_id"]

        def _resolve_parent_side(
            u_dict: dict[str, Any],
            key_m: str,
            key_c: str,
            cur_m: Any,
            cur_c: Any,
        ) -> tuple[int | None, int | None]:
            m_in = key_m in u_dict
            c_in = key_c in u_dict
            if m_in and c_in:
                m = _optional_same_user_family_member_id(conn, pid, u_dict.get(key_m))
                creq = _optional_same_user_nuclear_family_connection_request_id(
                    conn, pid, u_dict.get(key_c)
                )
                return m, creq
            if m_in:
                m = _optional_same_user_family_member_id(conn, pid, u_dict.get(key_m))
                if m is not None:
                    return m, None
                creq = _optional_same_user_nuclear_family_connection_request_id(
                    conn, pid, cur_c
                )
                return m, creq
            if c_in:
                creq = _optional_same_user_nuclear_family_connection_request_id(
                    conn, pid, u_dict.get(key_c)
                )
                if creq is not None:
                    return None, creq
                m = _optional_same_user_family_member_id(conn, pid, cur_m)
                return m, creq
            return (
                _optional_same_user_family_member_id(conn, pid, cur_m),
                _optional_same_user_nuclear_family_connection_request_id(conn, pid, cur_c),
            )

        mo, mo_c = _resolve_parent_side(
            u, "tree_mother_member_id", "tree_mother_connection_request_id", cm, cmc
        )
        fa, fa_c = _resolve_parent_side(
            u, "tree_father_member_id", "tree_father_connection_request_id", cf, cfc
        )
        if "tree_spouse_member_id" in u:
            sp = _optional_same_user_family_member_id(conn, pid, u.get("tree_spouse_member_id"))
        else:
            sp = _optional_same_user_family_member_id(conn, pid, csp)
        if "tree_child_of_member_id" in u:
            ch = _optional_same_user_family_member_id(conn, pid, u.get("tree_child_of_member_id"))
        else:
            ch = _optional_same_user_family_member_id(conn, pid, cch)
        if mo is not None and mo_c is not None:
            return (
                jsonify(
                    {
                        "error": "Choose either a linked member or a linked account for mother, not both",
                    }
                ),
                400,
            )
        if fa is not None and fa_c is not None:
            return (
                jsonify(
                    {
                        "error": "Choose either a linked member or a linked account for father, not both",
                    }
                ),
                400,
            )
        if mo is not None and mo == fa:
            return jsonify({"error": "Mother and father cannot be the same member"}), 400
        if mo_c is not None and mo_c == fa_c:
            return jsonify({"error": "Mother and father cannot be the same account"}), 400
        sp = _optional_same_user_family_member_id(conn, pid, u.get("tree_spouse_member_id"))
        ch = _optional_same_user_family_member_id(conn, pid, u.get("tree_child_of_member_id"))
        for x in (mo, fa, sp, ch):
            if x is not None and x not in all_ids:
                return (
                    jsonify({"error": "Linked member must be in your family list"}),
                    400,
                )
        if any(x == mid for x in (mo, fa, sp, ch) if x is not None):
            return jsonify({"error": "Cannot link a member to itself"}), 400
        conn.execute(
            """
            UPDATE family_members
               SET tree_mother_member_id = ?,
                   tree_father_member_id = ?,
                   tree_mother_connection_request_id = ?,
                   tree_father_connection_request_id = ?,
                   tree_spouse_member_id = ?,
                   tree_child_of_member_id = ?
             WHERE id = ? AND user_private_id = ?
            """,
            (mo, fa, mo_c, fa_c, sp, ch, mid, pid),
        )
    conn.commit()
    return jsonify({"ok": True})


@app.get("/api/family/alive_members")
@login_required
def api_family_alive_members():
    """Return living family members (form + connection sources) for the bulk
    "Mark Deceased" modal. The current user is implicitly excluded — they
    cannot appear in their own family table."""
    conn = get_db()
    pid = str(g.current_user["private_id"])
    form_rows = [
        _family_member_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM family_members "
            "WHERE user_private_id = ? AND is_dead = 0 "
            "AND COALESCE(is_placeholder, 0) = 0 "
            "AND source != 'self' "
            "ORDER BY id ASC",
            (pid,),
        )
    ]
    conn_rows = [
        m for m in _connection_family_members(conn, pid) if not m["is_dead"]
    ]
    return jsonify({"members": form_rows + conn_rows})


@app.post("/api/family/mark_deceased")
@login_required
def api_family_mark_deceased():
    """Mark multiple family members deceased in one call.

    Body: ``{"members": [{"id": <int>, "source": "form"|"manual"|"connection"}, ...]}``.
    """
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    members = payload.get("members") or []
    if not isinstance(members, list) or not members:
        return jsonify({"error": "members list is required"}), 400

    updated = 0
    skipped: list[dict[str, Any]] = []
    for entry in members:
        if not isinstance(entry, dict):
            continue
        try:
            member_id = int(entry.get("id"))
        except (TypeError, ValueError):
            continue
        source = str(entry.get("source") or "form").strip().lower()
        if source in {"form", "manual", "general"}:
            cur = conn.execute(
                "UPDATE family_members SET is_dead = 1 "
                "WHERE id = ? AND user_private_id = ? AND is_dead = 0 "
                "AND COALESCE(is_placeholder, 0) = 0 AND source != 'self'",
                (member_id, pid),
            )
        elif source == "connection":
            cur = conn.execute(
                "UPDATE connection_requests SET is_dead = 1 "
                "WHERE id = ? AND status = 'accepted' "
                "  AND request_type = 'family' "
                "  AND is_dead = 0 "
                "  AND (from_user_private_id = ? OR to_user_private_id = ?)",
                (member_id, pid, pid),
            )
        else:
            skipped.append({"id": member_id, "source": source, "reason": "bad-source"})
            continue
        if cur.rowcount == 1:
            updated += 1
        else:
            skipped.append({"id": member_id, "source": source, "reason": "not-found"})
    conn.commit()
    return jsonify(
        {
            "ok": True,
            "updated": updated,
            "skipped": skipped,
            **_family_tree_graph_payload(conn, pid),
        }
    )


@app.post("/api/family/request_connection")
@login_required
def api_family_request_connection():
    """Alias for ``POST /api/connection/request`` (family) using Account ID."""
    conn = get_db()
    from_pid = str(g.current_user["private_id"])
    pl = dict(request.get_json(silent=True) or {})
    if not str(pl.get("public_id") or "").strip() and str(pl.get("account_id") or "").strip():
        pl["public_id"] = str(pl.get("account_id") or "").strip()
    pl.setdefault("request_type", "family")
    body, code = _connection_request_apply(conn, from_pid, pl)
    if code < 400:
        conn.commit()
    return jsonify(body), code


def _lookup_member_added_at(
    conn: sqlite3.Connection, user_pid: str, source: str, member_id: int
) -> tuple[bool, str, dict[str, Any] | None]:
    """Find a family member by (source, id) and return its 'added_at' anchor.

    Returns ``(found, added_at_iso, meta)``. ``meta`` carries human-readable
    bits (name, relationship) for downstream messaging.
    """
    if source in {"form", "manual", "general"}:
        row = conn.execute(
            "SELECT * FROM family_members WHERE id = ? AND user_private_id = ?",
            (member_id, user_pid),
        ).fetchone()
        if not row:
            return False, "", None
        src = str(row["source"] or "form")
        return (
            True,
            str(row["created_at"] or ""),
            {
                "member_name": str(row["member_name"] or ""),
                "relationship": str(row["relationship"] or ""),
                "is_close_family": bool(int(row["is_close_family"] or 0)),
                "member_table_source": src,
            },
        )
    if source == "connection":
        row = conn.execute(
            """
            SELECT cr.*, u.first_name, u.last_name, u.public_id
              FROM connection_requests cr
              JOIN users u ON u.private_id = CASE
                  WHEN cr.from_user_private_id = ? THEN cr.to_user_private_id
                  ELSE cr.from_user_private_id
              END
             WHERE cr.id = ?
               AND cr.status = 'accepted'
               AND cr.request_type = 'family'
               AND (cr.from_user_private_id = ? OR cr.to_user_private_id = ?)
            """,
            (user_pid, member_id, user_pid, user_pid),
        ).fetchone()
        if not row:
            return False, "", None
        added_at = (
            str(row["accepted_at"] or "")
            if row["accepted_at"]
            else str(row["created_at"] or "")
        )
        full = (
            f"{str(row['first_name'] or '').strip()} "
            f"{str(row['last_name'] or '').strip()}"
        ).strip() or str(row["public_id"] or "")
        return (
            True,
            added_at,
            {
                "member_name": full,
                "relationship": str(row["relationship"] or ""),
                "is_close_family": _is_close_family_relationship(
                    str(row["relationship"] or "")
                ),
            },
        )
    return False, "", None


def _delete_family_member(
    conn: sqlite3.Connection, user_pid: str, source: str, member_id: int
) -> bool:
    """Physically remove a family member row regardless of age. Returns True if
    a row was deleted."""
    if source in {"form", "manual", "general"}:
        src_row = conn.execute(
            "SELECT source FROM family_members WHERE id = ? AND user_private_id = ?",
            (member_id, user_pid),
        ).fetchone()
        if not src_row:
            return False
        if str(src_row["source"] or "") == "self":
            return False
        conn.execute(
            "DELETE FROM family_relationships WHERE source_id = ? OR target_id = ?",
            (member_id, member_id),
        )
        cur = conn.execute(
            "DELETE FROM family_members WHERE id = ? AND user_private_id = ?",
            (member_id, user_pid),
        )
        return cur.rowcount == 1
    if source == "connection":
        cur = conn.execute(
            """
            DELETE FROM connection_requests
             WHERE id = ?
               AND status = 'accepted'
               AND request_type = 'family'
               AND (from_user_private_id = ? OR to_user_private_id = ?)
            """,
            (member_id, user_pid, user_pid),
        )
        return cur.rowcount == 1
    return False


@app.post("/api/family/remove_member")
@login_required
def api_family_remove_member():
    """Remove a family member.

    * Admins may delete any member on their own family list immediately.
    * Within :data:`FAMILY_DIRECT_REMOVAL_DAYS` days of adding → delete now
      (including activation-form close family).
    * Beyond that window (non-admin) → 409 with ``requires_admin_approval``.
    """
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    source = str(payload.get("source") or "form").strip().lower()
    try:
        member_id = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "id is required"}), 400
    if source not in {"form", "manual", "connection", "general"}:
        return jsonify({"error": "source must be form, manual, general, or connection"}), 400

    found, added_at, meta = _lookup_member_added_at(conn, pid, source, member_id)
    if not found or meta is None:
        return jsonify({"error": "Member not found"}), 404

    is_admin = is_admin_user(g.current_user)
    if not is_admin and not _family_member_within_direct_removal_window(added_at):
        return (
            jsonify(
                {
                    "error": (
                        f"This member was added more than "
                        f"{FAMILY_DIRECT_REMOVAL_DAYS} days ago. Submit a "
                        "removal request and an admin will review it."
                    ),
                    "requires_admin_approval": True,
                }
            ),
            409,
        )

    if not _delete_family_member(conn, pid, source, member_id):
        return jsonify({"error": "Member not found"}), 404
    conn.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Family removal — admin-approved path (used when a member was added more
# than FAMILY_DIRECT_REMOVAL_DAYS days ago).
# ---------------------------------------------------------------------------


def _notify_admins_new_family_removal_request(
    conn: sqlite3.Connection,
    requester_pid: str,
    target_name: str,
    target_rel: str,
    reason: str,
) -> None:
    """Deliver a system message to every admin except the requester."""
    req = conn.execute(
        "SELECT first_name, last_name, public_id FROM users WHERE private_id = ?",
        (requester_pid,),
    ).fetchone()
    if not req:
        return
    rn = (
        f"{str(req['first_name'] or '').strip()} "
        f"{str(req['last_name'] or '').strip()}"
    ).strip() or str(req["public_id"] or "User")
    body = (
        f"{rn} requested removal of family member "
        f"{target_name or '(unnamed)'} "
        f"({target_rel or 'relative'}).\n\nReason:\n{reason}"
    )
    for row in conn.execute(
        "SELECT private_id FROM users WHERE COALESCE(is_admin, 0) = 1",
    ):
        apid = str(row["private_id"])
        if apid == requester_pid:
            continue
        send_system_message(
            conn,
            apid,
            "New family removal request",
            body,
        )


@app.post("/api/family/request_removal")
@login_required
def api_family_request_removal():
    """Open a removal request that an admin must review.

    Body: ``{"source": "form"|"manual"|"connection", "id": <int>, "reason": "<text>"}``.
    Returns 409 if a pending request already exists for this member.
    """
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    source = str(payload.get("source") or "").strip().lower()
    reason = str(payload.get("reason") or "").strip()
    try:
        member_id = int(payload.get("id"))
    except (TypeError, ValueError):
        return jsonify({"error": "id is required"}), 400
    if source not in {"form", "manual", "connection", "general"}:
        return jsonify({"error": "source must be form, manual, general, or connection"}), 400
    if not reason:
        return jsonify({"error": "Reason for removal is required"}), 400
    if len(reason) > 1500:
        return jsonify({"error": "Reason is too long (max 1500 chars)"}), 400

    found, _added, meta = _lookup_member_added_at(conn, pid, source, member_id)
    if not found or meta is None:
        return jsonify({"error": "Member not found"}), 404

    existing = conn.execute(
        """
        SELECT id FROM family_removal_requests
         WHERE user_private_id = ?
           AND target_source = ?
           AND target_member_id = ?
           AND status = 'pending'
        """,
        (pid, source, member_id),
    ).fetchone()
    if existing:
        return (
            jsonify(
                {
                    "error": "A removal request for this member is already pending.",
                    "request_id": int(existing["id"]),
                }
            ),
            409,
        )

    conn.execute(
        """
        INSERT INTO family_removal_requests (
            user_private_id, target_source, target_member_id,
            target_member_name, target_relationship, reason, status
        ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            pid,
            source,
            member_id,
            meta["member_name"],
            meta["relationship"],
            reason,
        ),
    )
    _notify_admins_new_family_removal_request(
        conn,
        pid,
        str(meta["member_name"] or ""),
        str(meta["relationship"] or ""),
        reason,
    )
    conn.commit()
    return jsonify({"ok": True})


@app.get("/api/admin/family_removal_requests")
@admin_required
def api_admin_family_removal_requests():
    """List removal requests (pending by default; ``?status=all`` for everything)."""
    conn = get_db()
    status_filter = (request.args.get("status") or "pending").strip().lower()
    params: tuple[Any, ...] = ()
    where = ""
    if status_filter == "pending":
        where = "WHERE rr.status = 'pending'"
    elif status_filter in {"approved", "rejected"}:
        where = "WHERE rr.status = ?"
        params = (status_filter,)
    cur = conn.execute(
        f"""
        SELECT rr.*, u.public_id AS user_public_id, u.first_name, u.last_name
          FROM family_removal_requests rr
          JOIN users u ON u.private_id = rr.user_private_id
         {where}
         ORDER BY datetime(rr.created_at) DESC
         LIMIT 200
        """,
        params,
    )
    items: list[dict[str, Any]] = []
    for r in cur:
        items.append(
            {
                "id": int(r["id"]),
                "user_private_id": str(r["user_private_id"]),
                "user_public_id": str(r["user_public_id"] or ""),
                "user_name": (
                    f"{str(r['first_name'] or '').strip()} "
                    f"{str(r['last_name'] or '').strip()}"
                ).strip(),
                "target_source": str(r["target_source"] or ""),
                "target_member_id": int(r["target_member_id"]),
                "target_member_name": str(r["target_member_name"] or ""),
                "target_relationship": str(r["target_relationship"] or ""),
                "reason": str(r["reason"] or ""),
                "status": str(r["status"] or ""),
                "created_at": str(r["created_at"] or ""),
                "reviewed_at": str(r["reviewed_at"] or "") if r["reviewed_at"] else "",
                "reviewed_by": str(r["reviewed_by"] or "") if r["reviewed_by"] else "",
                "admin_comment": str(r["admin_comment"] or ""),
            }
        )
    return jsonify({"requests": items})


def _close_removal_request(
    conn: sqlite3.Connection,
    request_id: int,
    decision: str,
    admin_pid: str,
    admin_comment: str,
) -> tuple[bool, sqlite3.Row | None]:
    """Mark a removal request approved/rejected. Returns (success, row)."""
    row = conn.execute(
        "SELECT * FROM family_removal_requests WHERE id = ?",
        (request_id,),
    ).fetchone()
    if not row or str(row["status"] or "") != "pending":
        return False, row
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE family_removal_requests
           SET status = ?, reviewed_at = ?, reviewed_by = ?, admin_comment = ?
         WHERE id = ?
        """,
        (decision, now_iso, admin_pid, admin_comment or None, request_id),
    )
    return True, row


@app.post("/api/admin/family_removal_requests/<int:request_id>/approve")
@admin_required
def api_admin_family_removal_approve(request_id: int):
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    admin_comment = str(payload.get("admin_comment") or "").strip()
    admin_pid = str(g.current_user["private_id"])
    ok, row = _close_removal_request(
        conn, request_id, "approved", admin_pid, admin_comment
    )
    if not ok:
        conn.commit()
        return jsonify({"error": "Request not found or already reviewed"}), 404
    # Apply the actual removal.
    user_pid = str(row["user_private_id"])
    src = str(row["target_source"])
    try:
        tmid = int(row["target_member_id"])
    except (TypeError, ValueError):
        tmid = 0
    _delete_family_member(conn, user_pid, src, tmid)
    send_system_message(
        conn,
        user_pid,
        "Family removal request approved",
        (
            f"Your request to remove "
            f"{row['target_member_name'] or 'a family member'} "
            f"({row['target_relationship'] or 'relative'}) has been "
            f"approved. The member has been removed from your family.\n\n"
            f"Admin note: {admin_comment or '(none)'}"
        ),
    )
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/admin/family_removal_requests/<int:request_id>/reject")
@admin_required
def api_admin_family_removal_reject(request_id: int):
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    admin_comment = str(payload.get("admin_comment") or "").strip()
    admin_pid = str(g.current_user["private_id"])
    ok, row = _close_removal_request(
        conn, request_id, "rejected", admin_pid, admin_comment
    )
    if not ok:
        conn.commit()
        return jsonify({"error": "Request not found or already reviewed"}), 404
    user_pid = str(row["user_private_id"])
    send_system_message(
        conn,
        user_pid,
        "Family removal request rejected",
        (
            f"Your request to remove "
            f"{row['target_member_name'] or 'a family member'} "
            f"({row['target_relationship'] or 'relative'}) was reviewed and "
            f"rejected by an admin. The member remains in your family list.\n\n"
            f"Admin note: {admin_comment or '(none)'}"
        ),
    )
    conn.commit()
    return jsonify({"ok": True})


@app.get("/api/post_history")
@login_required
def api_post_history():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT id, content, current_level, status, total_score, created_at,
               freeze_level, previous_levels
        FROM posts
        WHERE user_private_id = ?
          AND (
            current_level = 'personal_history'
            OR status = 'completed'
          )
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT 100
        """,
        (pid,),
    )
    return jsonify({"posts": [dict(r) for r in cur]})


@app.get("/api/collective_board")
@login_required
def api_collective_board():
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    social_core.escalate_posts(conn)

    level = (request.args.get("level") or "").strip().lower()
    location_id = (request.args.get("location_id") or "").strip()
    board_state = (request.args.get("state") or "live").strip().lower()
    if board_state == "freeze":
        board_state = "frozen"
    if board_state not in {"live", "frozen"}:
        return jsonify({"error": "state must be live or frozen"}), 400

    # Personal posts are private (PCB only). Refuse to ever expose them via CVB.
    if level == "personal":
        return jsonify({"error": "personal posts are not available on collective boards"}), 400

    ok, location_id, err = _validate_collective_board_request(
        conn, g.current_user, level, location_id
    )
    if not ok:
        status = 400 if "required" in err or "match" in err else 403
        return jsonify({"error": err}), status

    pid = str(g.current_user["private_id"])
    rows = _collective_board_rows(conn, level, location_id, board_state, pid)
    return jsonify(
        {
            "level": level,
            "location_id": location_id,
            "state": board_state,
            "posts": _filter_board_posts(
                rows, conn, g.current_user, level, board_state
            ),
        }
    )


@app.get("/api/posts")
@login_required
def api_posts():
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    social_core.escalate_posts(conn)

    level = (request.args.get("level") or "").strip().lower()
    location_id = (request.args.get("location_id") or "").strip()
    # Personal posts are PCB-only; never expose them through public APIs.
    if level == "personal":
        return jsonify({"posts": []})
    ok, location_id, err = _validate_collective_board_request(
        conn, g.current_user, level, location_id
    )
    if not ok:
        status = 400 if "required" in err or "match" in err else 403
        return jsonify({"error": err}), status

    pid = str(g.current_user["private_id"])
    rows = _collective_board_rows(conn, level, location_id, "live", pid)
    return jsonify(
        {"posts": _filter_board_posts(rows, conn, g.current_user, level, "live")}
    )


@app.get("/api/my_posts")
@login_required
def api_my_posts():
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    pid = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT id, content, current_level, status, total_score, created_at
        FROM posts
        WHERE user_private_id = ?
          AND (
            (status = 'live' AND current_level = 'personal')
            OR (status = 'frozen')
          )
        ORDER BY datetime(created_at) DESC
        LIMIT 80
        """,
        (pid,),
    )
    rows = [dict(r) for r in cur]
    return jsonify({"posts": rows})


@app.get("/debug/check")
def debug_check():
    """Minimal JSON probe — if this works but / fails, the problem is not Flask routing."""
    return jsonify({"status": "ok"})


@app.get("/debug/post_visibility")
@login_required
def debug_post_visibility():
    """Diagnostic helper for the 7-day personal-only post rule.

    Pass ``?post_id=N`` and inspect the JSON. ``current_level`` should be
    ``'personal'`` for new posts and the ``visibility`` block should say
    the post is hidden from village CVB / geo feeds.
    """
    conn = get_db()
    try:
        post_id = int(request.args.get("post_id") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "post_id must be an integer"}), 400
    if not post_id:
        return jsonify({"error": "post_id is required"}), 400
    row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not row:
        return jsonify({"error": "post not found"}), 404
    level = str(row["current_level"] or "").strip().lower()
    status = str(row["status"] or "").strip().lower()
    lst = str(row["level_start_time"] or "")
    cutoff_row = conn.execute(
        "SELECT (CASE WHEN datetime(?) <= datetime('now','-7 days') THEN 1 ELSE 0 END) AS old",
        (lst,),
    ).fetchone()
    return jsonify(
        {
            "post_id": post_id,
            "current_level": level,
            "status": status,
            "level_start_time": lst,
            "older_than_seven_days": bool(int(cutoff_row["old"] or 0)) if cutoff_row else False,
            "visibility": {
                "pcb_live_for_author": level == "personal" and status == "live",
                "village_cvb": level == "village" and status == "live",
                "any_collective_board": level not in {"personal", "personal_history"}
                and status in {"live", "frozen"},
            },
        }
    )


@app.route("/")
def index():
    conn = get_db()
    total_users_earth = count_registered_users(conn)
    total_users_asia = count_homepage_asia_users(conn)
    total_users_india = count_homepage_india_users(conn)
    labels, values = users_per_state_from_current_location(conn)
    chart_states = {"labels": labels, "values": values}

    exp_continent = (request.args.get("explorer_continent") or "AS").strip().upper()
    exp_country = (request.args.get("explorer_country") or "IND").strip().upper()
    explorer = explorer_user_counts(conn, exp_continent, exp_country)
    continents_list: list[dict[str, str]] = []
    countries_list: list[dict[str, str]] = []
    if _geo_table_exists(conn, "continent"):
        continents_list = [
            {"id": str(r["id"]), "name": str(r["name"])}
            for r in conn.execute(
                "SELECT id, name FROM continent ORDER BY name COLLATE NOCASE"
            )
        ]
    if _geo_table_exists(conn, "country"):
        countries_list = [
            {"id": str(r["id"]), "name": str(r["name"])}
            for r in conn.execute(
                "SELECT id, name FROM country WHERE continent_id = ? "
                "ORDER BY name COLLATE NOCASE",
                (explorer["continent_id"],),
            )
        ]

    return render_template(
        "index.html",
        total_users_earth=total_users_earth,
        total_users_asia=total_users_asia,
        total_users_india=total_users_india,
        chart_states=chart_states,
        explorer=explorer,
        continents_list=continents_list,
        countries_list=countries_list,
    )


@app.route("/about-details")
def about_details():
    """Placeholder for the full About story; linked from the home page."""
    return render_template("about_details.html")


@app.route("/about")
def about():
    """Canonical About page."""
    return render_template("about.html")


@app.route("/contact")
def contact():
    """Contact page."""
    return render_template("contact.html")


@app.route("/api/continents")
def api_continents():
    conn = get_db()
    if not _geo_table_exists(conn, "continent"):
        return jsonify([])
    cur = conn.execute(
        "SELECT id, name FROM continent ORDER BY name COLLATE NOCASE ASC"
    )
    return jsonify([{"id": str(r["id"]), "name": str(r["name"])} for r in cur])


@app.route("/api/countries")
def api_countries():
    continent_id = (request.args.get("continent_id") or "").strip().upper()
    if not continent_id:
        return jsonify({"error": "continent_id is required"}), 400
    conn = get_db()
    if not _geo_table_exists(conn, "country"):
        return jsonify([])
    cur = conn.execute(
        "SELECT id, name FROM country WHERE continent_id = ? "
        "ORDER BY name COLLATE NOCASE ASC",
        (continent_id,),
    )
    return jsonify([{"id": str(r["id"]), "name": str(r["name"])} for r in cur])


@app.route("/api/states")
def api_states():
    conn = get_db()
    cur = conn.execute("SELECT id, name FROM state ORDER BY name COLLATE NOCASE ASC")
    return jsonify([{"id": str(r["id"]), "name": str(r["name"])} for r in cur])


@app.route("/api/districts")
def api_districts():
    state_id = (request.args.get("state_id") or "").strip()
    if not state_id:
        return jsonify({"error": "state_id required"}), 400
    conn = get_db()
    if geography_has_relational_fks(conn):
        cur = conn.execute(
            "SELECT id, name FROM district WHERE state_id = ? ORDER BY name COLLATE NOCASE",
            (state_id,),
        )
        return jsonify([{"id": str(r["id"]), "name": str(r["name"])} for r in cur])
    base = state_raw_to_district_base(raw_path(state_id))
    return jsonify(fetch_direct_children_geo_path(conn, "district", base))


@app.route("/api/tehsils")
def api_tehsils():
    district_id = (request.args.get("district_id") or "").strip()
    if not district_id:
        return jsonify({"error": "district_id required"}), 400
    conn = get_db()
    if geography_has_relational_fks(conn):
        cur = conn.execute(
            "SELECT id, name FROM tehsil WHERE district_id = ? ORDER BY name COLLATE NOCASE",
            (district_id,),
        )
        return jsonify([{"id": str(r["id"]), "name": str(r["name"])} for r in cur])
    return jsonify(
        fetch_direct_children_geo_path(conn, "tehsil", raw_path(district_id))
    )


@app.route("/api/villages")
def api_villages():
    tehsil_id = (request.args.get("tehsil_id") or "").strip()
    if not tehsil_id:
        return jsonify({"error": "tehsil_id required"}), 400
    conn = get_db()
    if geography_has_relational_fks(conn):
        cur = conn.execute(
            """
            SELECT id, name FROM village
             WHERE tehsil_id = ?
             ORDER BY name COLLATE NOCASE
            """,
            (tehsil_id,),
        )
        return jsonify([{"id": str(r["id"]), "name": str(r["name"])} for r in cur])
    return jsonify(
        fetch_direct_children_geo_path(conn, "village", raw_path(tehsil_id))
    )


def _message_row_to_dict(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "message_id": str(r["message_id"]),
        "sender_id": str(r["sender_id"]),
        "recipient_id": str(r["recipient_id"]),
        "subject": r["subject"],
        "body": str(r["body"]),
        "status": str(r["status"]),
        "parent_message_id": r["parent_message_id"],
        "created_at": str(r["created_at"]) if r["created_at"] is not None else None,
        "read_at": str(r["read_at"]) if r["read_at"] is not None else None,
        "is_draft": bool(r["is_draft"]),
    }


def allocate_message_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM messages").fetchone()
    seq = int(row["m"] or 0) + 1
    return f"MSG-{100000 + seq}"


def _resolve_geo_entity_id(conn: sqlite3.Connection, pid: str) -> str | None:
    s = (pid or "").strip()
    if not s or s.upper() == "IND":
        return None
    candidates = [s, raw_path(s)]
    fr = raw_path(s)
    if fr:
        candidates.append(full_id_from_raw(fr))
    seen: set[str] = set()
    for tid in candidates:
        if not tid or tid in seen:
            continue
        seen.add(tid)
        if infer_geo_scope_from_full_id(conn, tid):
            return tid
    return None


def api_locations_children_rows(conn: sqlite3.Connection, parent_id: str) -> list[dict[str, str]]:
    pid = (parent_id or "").strip()
    if not pid:
        return []
    if pid.upper() == "IND":
        cur = conn.execute("SELECT id, name FROM state ORDER BY name COLLATE NOCASE ASC")
        return [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]

    norm = _resolve_geo_entity_id(conn, pid)
    if not norm:
        return []
    scope = infer_geo_scope_from_full_id(conn, norm)
    if scope == "state":
        if geography_has_relational_fks(conn):
            cur = conn.execute(
                "SELECT id, name FROM district WHERE state_id = ? ORDER BY name COLLATE NOCASE",
                (norm,),
            )
            return [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
        base = state_raw_to_district_base(raw_path(norm))
        return fetch_direct_children_geo_path(conn, "district", base)
    if scope == "district":
        if geography_has_relational_fks(conn):
            cur = conn.execute(
                "SELECT id, name FROM tehsil WHERE district_id = ? ORDER BY name COLLATE NOCASE",
                (norm,),
            )
            return [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
        return fetch_direct_children_geo_path(conn, "tehsil", raw_path(norm))
    if scope == "tehsil":
        if geography_has_relational_fks(conn):
            cur = conn.execute(
                """
                SELECT id, name FROM village
                 WHERE tehsil_id = ?
                 ORDER BY name COLLATE NOCASE
                """,
                (norm,),
            )
            return [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
        return fetch_direct_children_geo_path(conn, "village", raw_path(norm))
    return []


def location_tab_strip_for_dashboard(
    conn: sqlite3.Connection,
    state_id: str | None,
    district_id: str | None,
    tehsil_id: str | None,
    village_id: str | None,
) -> list[dict[str, str]]:
    vid = (village_id or "").strip()
    if vid and infer_geo_scope_from_full_id(conn, vid) == "village":
        return current_location_hierarchy(conn, vid)

    def one(scope: str, fid: str) -> dict[str, str]:
        table = GEO_ROUTE_TABLE[scope]
        safe = (fid or "").strip()
        if not safe:
            return {"scope": scope, "id": "", "name": "—", "url": "#"}
        meta = _geo_row_optional_meta(conn, table, safe)
        return {
            "scope": scope,
            "id": safe,
            "name": str(meta["name"]),
            "url": build_geo_public_url(scope, safe),
        }

    return [
        one("state", (state_id or "").strip()),
        one("district", (district_id or "").strip()),
        one("tehsil", (tehsil_id or "").strip()),
        one("village", (village_id or "").strip()),
    ]


@app.get("/api/locations/children")
@login_required
def api_locations_children():
    conn = get_db()
    parent_id = (request.args.get("parent_id") or "").strip()
    if not parent_id:
        return jsonify({"error": "parent_id is required"}), 400
    rows = api_locations_children_rows(conn, parent_id)
    return jsonify(rows)


@app.get("/api/locations/stats_link")
@login_required
def api_locations_stats_link():
    """Resolve a geography row id to the canonical statistics page URL."""
    conn = get_db()
    lid = (request.args.get("location_id") or "").strip()
    if not lid:
        return jsonify({"error": "location_id is required"}), 400
    scope = infer_geo_scope_from_full_id(conn, lid)
    if not scope:
        return jsonify({"error": "location not found"}), 404
    return jsonify({"scope": scope, "stats_url": build_geo_public_url(scope, lid)})


@app.get("/api/locations/tab_strip")
@login_required
def api_locations_tab_strip():
    conn = get_db()
    state_id = (request.args.get("state_id") or "").strip() or None
    district_id = (request.args.get("district_id") or "").strip() or None
    tehsil_id = (request.args.get("tehsil_id") or "").strip() or None
    village_id = (request.args.get("village_id") or "").strip() or None
    levels = location_tab_strip_for_dashboard(conn, state_id, district_id, tehsil_id, village_id)
    return jsonify({"levels": levels})


@app.get("/api/locations/global_children")
@login_required
def api_locations_global_children():
    conn = get_db()
    parent_id = (request.args.get("parent_id") or "").strip()
    if not parent_id:
        return jsonify({"error": "parent_id is required"}), 400
    rows = api_global_locations_children_rows(conn, parent_id)
    return jsonify(rows)


@app.get("/api/dashboard/public_stats")
@login_required
def api_dashboard_public_stats():
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    lid = (request.args.get("location_id") or "").strip()
    if not lid:
        return jsonify({"error": "location_id is required"}), 400
    allowed = user_public_allowed_location_ids(conn, g.current_user)
    if lid not in allowed:
        return jsonify({"error": "location_id must be your profile hierarchy"}), 403
    scope = infer_geo_scope_from_full_id(conn, lid)
    if not scope:
        return jsonify({"error": "location not found"}), 404
    bundle = location_statistics_bundle(conn, scope, lid)
    return jsonify(
        {
            "total_users": bundle["total_users"],
            "gender_counts": {str(r["label"]): int(r["count"]) for r in bundle["gender"]},
            "element_counts": {str(r["label"]): int(r["count"]) for r in bundle["sun_element"]},
            "life_stage_counts": {str(r["label"]): int(r["count"]) for r in bundle["age_group"]},
            "stats_url": build_geo_public_url(scope, lid),
            "scope": scope,
        }
    )


@app.get("/api/dashboard/geo_feed")
@login_required
def api_dashboard_geo_feed():
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    lid = (request.args.get("location_id") or "").strip()
    if not lid:
        return jsonify({"error": "location_id is required"}), 400
    allowed = user_public_allowed_location_ids(conn, g.current_user)
    if lid not in allowed:
        return jsonify({"error": "location_id must be your profile hierarchy"}), 403
    scope = infer_geo_scope_from_full_id(conn, lid)
    if not scope:
        return jsonify({"error": "location not found"}), 404
    rows = social_core.posts_for_geo_feed(
        conn, scope, lid, str(g.current_user["private_id"])
    )
    feed: list[dict[str, Any]] = []
    for r in rows:
        # Defensive: personal posts must never leak through a geo feed.
        if str(r["current_level"] or "").strip().lower().startswith("personal"):
            continue
        feed.append(post_row_to_feed_json(r, conn, g.current_user))
    return jsonify({"posts": feed})


@app.get("/api/dashboard/global_stats")
@login_required
def api_dashboard_global_stats():
    conn = get_db()
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Dashboard features are limited to India residents."}), 403
    scope = (request.args.get("scope") or "earth").strip().lower()
    geo_id = (request.args.get("geo_id") or "").strip()

    if scope == "earth":
        eid = geo_id or "0"
        bundle = location_statistics_bundle(conn, "earth", eid)
        url_id = eid
    elif scope == "continent":
        if not geo_id:
            return jsonify({"error": "geo_id is required for continent scope"}), 400
        bundle = location_statistics_bundle(conn, "continent", geo_id)
        url_id = geo_id
    elif scope == "country":
        if not geo_id:
            return jsonify({"error": "geo_id is required for country scope"}), 400
        bundle = location_statistics_bundle(conn, "country", geo_id)
        url_id = geo_id
    elif scope == "zone":
        if not geo_id:
            return jsonify({"error": "geo_id is required for zone scope"}), 400
        bundle = location_statistics_bundle(conn, "zone", geo_id)
        url_id = geo_id
    else:
        return jsonify({"error": "invalid scope"}), 400

    return jsonify(
        {
            "total_users": bundle["total_users"],
            "gender_counts": {str(r["label"]): int(r["count"]) for r in bundle["gender"]},
            "element_counts": {str(r["label"]): int(r["count"]) for r in bundle["sun_element"]},
            "life_stage_counts": {str(r["label"]): int(r["count"]) for r in bundle["age_group"]},
            "stats_url": build_geo_public_url(scope, url_id),
            "scope": scope,
        }
    )


@app.get("/api/messages/inbox")
@login_required
def api_messages_inbox():
    conn = get_db()
    me = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT * FROM messages
         WHERE recipient_id = ? COLLATE NOCASE
           AND is_draft = 0
           AND is_deleted_by_recipient = 0
         ORDER BY datetime(created_at) DESC
         LIMIT 200
        """,
        (me,),
    )
    return jsonify({"messages": [_message_row_to_dict(r) for r in cur]})


@app.get("/api/messages/sent")
@login_required
def api_messages_sent():
    conn = get_db()
    me = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT * FROM messages
         WHERE sender_id = ? COLLATE NOCASE
           AND is_draft = 0
           AND is_deleted_by_sender = 0
         ORDER BY datetime(created_at) DESC
         LIMIT 200
        """,
        (me,),
    )
    return jsonify({"messages": [_message_row_to_dict(r) for r in cur]})


@app.get("/api/messages/drafts")
@login_required
def api_messages_drafts():
    conn = get_db()
    me = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT * FROM messages
         WHERE sender_id = ? COLLATE NOCASE
           AND is_draft = 1
           AND is_deleted_by_sender = 0
         ORDER BY datetime(created_at) DESC
         LIMIT 200
        """,
        (me,),
    )
    return jsonify({"messages": [_message_row_to_dict(r) for r in cur]})


@app.post("/api/messages/send")
@login_required
def api_messages_send():
    conn = get_db()
    me = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    recipient_raw = str(payload.get("recipient_id") or "").strip()
    subject = str(payload.get("subject") or "").strip() or None
    body = str(payload.get("body") or "").strip()
    is_draft = bool(payload.get("is_draft"))
    parent_mid = str(payload.get("parent_message_id") or "").strip() or None

    if not body:
        return jsonify({"error": "Message body is required"}), 400
    if is_draft and not recipient_raw:
        recipient_raw = me
    if not recipient_raw:
        return jsonify({"error": "recipient_id is required"}), 400

    row_r = conn.execute(
        "SELECT private_id FROM users WHERE private_id = ? COLLATE NOCASE",
        (recipient_raw,),
    ).fetchone()
    if not row_r:
        return jsonify({"error": "Recipient Private ID not found"}), 400
    recipient_id = str(row_r["private_id"])

    if not is_draft and recipient_id == me:
        return jsonify({"error": "You cannot send a non-draft message to yourself"}), 400

    mid = allocate_message_id(conn)
    status = "draft" if is_draft else "sent"
    conn.execute(
        """
        INSERT INTO messages (
            message_id, sender_id, recipient_id, subject, body, status,
            parent_message_id, is_draft
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mid,
            me,
            recipient_id,
            subject,
            body,
            status,
            parent_mid,
            1 if is_draft else 0,
        ),
    )
    conn.commit()
    return jsonify({"ok": True, "message_id": mid})


@app.post("/api/messages/read/<path:message_id>")
@login_required
def api_messages_read(message_id: str):
    conn = get_db()
    me = str(g.current_user["private_id"])
    row = conn.execute(
        "SELECT * FROM messages WHERE message_id = ?",
        (message_id.strip(),),
    ).fetchone()
    if not row:
        return jsonify({"error": "Message not found"}), 404
    if str(row["recipient_id"]).casefold() != me.casefold():
        return jsonify({"error": "Forbidden"}), 403
    if row["is_draft"]:
        return jsonify({"error": "Drafts cannot be marked read"}), 400
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE messages
           SET status = 'read', read_at = ?
         WHERE message_id = ?
        """,
        (now, message_id.strip()),
    )
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/messages/delete/<path:message_id>")
@login_required
def api_messages_delete(message_id: str):
    conn = get_db()
    me = str(g.current_user["private_id"])
    row = conn.execute(
        "SELECT * FROM messages WHERE message_id = ?",
        (message_id.strip(),),
    ).fetchone()
    if not row:
        return jsonify({"error": "Message not found"}), 404
    is_sender = str(row["sender_id"]).casefold() == me.casefold()
    is_recipient = str(row["recipient_id"]).casefold() == me.casefold()
    if not is_sender and not is_recipient:
        return jsonify({"error": "Forbidden"}), 403
    if is_sender:
        conn.execute(
            "UPDATE messages SET is_deleted_by_sender = 1 WHERE message_id = ?",
            (message_id.strip(),),
        )
    if is_recipient:
        conn.execute(
            "UPDATE messages SET is_deleted_by_recipient = 1 WHERE message_id = ?",
            (message_id.strip(),),
        )
    conn.commit()
    return jsonify({"ok": True})


def _continent_country_valid(conn: sqlite3.Connection, cont: str, ctry: str) -> bool:
    if not _geo_table_exists(conn, "continent") or not _geo_table_exists(conn, "country"):
        return False
    row = conn.execute(
        "SELECT 1 FROM country WHERE id = ? AND continent_id = ?",
        (ctry.strip().upper(), cont.strip().upper()),
    ).fetchone()
    return row is not None


@app.route("/register", methods=["GET", "POST"])
def register():
    conn = get_db()
    continents_form: list[dict[str, str]] = []
    if _geo_table_exists(conn, "continent"):
        continents_form = [
            {"id": str(r["id"]), "name": str(r["name"])}
            for r in conn.execute(
                "SELECT id, name FROM continent ORDER BY name COLLATE NOCASE"
            )
        ]

    if request.method == "GET":
        return render_template(
            "register.html",
            gender_options=GENDER_OPTIONS,
            continents=continents_form,
            form={},
            errors=None,
            new_private_id=None,
            new_public_id=None,
        )

    form = dict(request.form)
    errors: list[str] = []

    first_name = (form.get("first_name") or "").strip()
    last_name = (form.get("last_name") or "").strip()
    gender = (form.get("gender") or "").strip()
    dob_s = (form.get("date_of_birth") or "").strip()
    birth_time = (form.get("birth_time") or "").strip()
    birth_loc = (form.get("birth_location_id") or "").strip() or None
    curr_loc = (form.get("current_location_id") or "").strip() or None
    birth_cont = (form.get("birth_continent_id") or "").strip().upper()
    birth_ctry = (form.get("birth_country_id") or "").strip().upper()
    curr_cont = (form.get("current_continent_id") or "").strip().upper()
    curr_ctry = (form.get("current_country_id") or "").strip().upper()
    email_raw = (form.get("email") or "").strip() or None
    password = form.get("password") or ""
    confirm = form.get("confirm_password") or ""

    if not first_name:
        errors.append("First name is required.")
    if not last_name:
        errors.append("Last name is required.")

    if gender not in GENDER_OPTIONS:
        errors.append("Please choose a valid gender option.")

    dob_dt = parse_date_iso(dob_s)
    if not dob_dt:
        errors.append("Please enter a valid date of birth.")

    if not birth_time:
        errors.append("Birth time is required.")
    else:
        m_time = re.match(r"^(\d{2}:\d{2})", birth_time)
        if not m_time:
            errors.append("Birth time must be in HH:MM format.")
        else:
            birth_time = m_time.group(1)

    if not birth_cont or not birth_ctry:
        errors.append("Birth continent and country are required.")
    elif not _continent_country_valid(conn, birth_cont, birth_ctry):
        errors.append("Invalid birth continent or country combination.")

    if not curr_cont or not curr_ctry:
        errors.append("Current continent and country are required.")
    elif not _continent_country_valid(conn, curr_cont, curr_ctry):
        errors.append("Invalid current continent or country combination.")

    if birth_ctry == "IND":
        if not birth_loc:
            errors.append("For birth in India, select state through village.")
        elif not village_exists(conn, birth_loc):
            errors.append("Invalid birth village selection.")
    else:
        birth_loc = None

    if curr_ctry == "IND":
        if not curr_loc:
            errors.append("For current residence in India, select state through village.")
        elif not village_exists(conn, curr_loc):
            errors.append("Invalid current village selection.")
    else:
        curr_loc = None

    if password != confirm:
        errors.append("Password and confirmation do not match.")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")

    if dob_dt:
        age = compute_age(dob_dt)
        if age > 130:
            errors.append("Age out of supported range.")

    if errors or not dob_dt:
        return render_template(
            "register.html",
            gender_options=GENDER_OPTIONS,
            continents=continents_form,
            form=form,
            errors=errors,
            new_private_id=None,
            new_public_id=None,
        )

    dob_iso = dob_dt.strftime("%Y-%m-%d")
    age = compute_age(dob_dt)
    agroup = age_group_from_age(age)
    sun = sun_sign_for_date(dob_dt)
    moon = moon_sign_simplified(dob_dt)
    elem = element_for_sun(sun)

    legacy_country_text = "India" if curr_ctry == "IND" else "Other"

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    try:
        private_id = allocate_private_id(
            conn,
            first_name,
            dob_iso,
            birth_time,
            birth_loc,
            birth_country_id=birth_ctry,
            birth_continent_id=birth_cont,
        )
        public_id = allocate_public_id(conn)
        conn.execute(
            """
            INSERT INTO users (
                private_id,
                public_id,
                first_name,
                last_name,
                gender,
                date_of_birth,
                birth_time,
                age,
                age_group,
                sun_sign,
                moon_sign,
                element,
                birth_location_id,
                current_location_id,
                birth_continent_id,
                birth_country_id,
                current_continent_id,
                current_country_id,
                country,
                email,
                password_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                private_id,
                public_id,
                first_name,
                last_name,
                gender,
                dob_iso,
                birth_time,
                age,
                agroup,
                sun,
                moon,
                elem,
                birth_loc,
                curr_loc,
                birth_cont,
                birth_ctry,
                curr_cont,
                curr_ctry,
                legacy_country_text,
                email_raw,
                pw_hash,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        errors.append("Could not create account (collision). Please try again.")
        return render_template(
            "register.html",
            gender_options=GENDER_OPTIONS,
            continents=continents_form,
            form=form,
            errors=errors,
            new_private_id=None,
            new_public_id=None,
        )

    return render_template(
        "register.html",
        gender_options=GENDER_OPTIONS,
        continents=continents_form,
        form={},
        errors=None,
        new_private_id=private_id,
        new_public_id=public_id,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    conn = get_db()

    if request.method == "GET":
        return render_template("login.html", error=None)

    raw_pid = request.form.get("private_id") or ""
    password = request.form.get("password") or ""
    pid_in = raw_pid.strip()
    if not PRIVATE_ID_LOGIN_RE.match(pid_in):
        return render_template(
            "login.html",
            error="Enter a valid Private ID (3–190 characters: letters, digits, _ / . - |).",
        )
    canon = pid_in
    m_legacy = PRIVATE_ID_RE.match(raw_pid)
    if m_legacy:
        canon = m_legacy.group(1).upper()

    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE private_id = ? COLLATE NOCASE",
        (canon,),
    ).fetchone()
    if not row:
        return render_template(
            "login.html",
            error="Invalid Private ID or password.",
        )

    stored = row["password_hash"]
    stored_b = stored.encode("utf-8") if isinstance(stored, str) else stored

    if not bcrypt.checkpw(password.encode("utf-8"), stored_b):
        return render_template(
            "login.html",
            error="Invalid Private ID or password.",
        )

    session.clear()
    session["user_pk"] = int(row["id"])
    full_user = load_user(conn, int(row["id"]))
    _session_sync_admin_flag(full_user)
    flash("You're signed in.", "success")
    dest = request.args.get("next") or ""
    if (
        dest.startswith("/")
        and full_user
        and user_has_full_dashboard(conn, full_user)
    ):
        return redirect(dest)
    if full_user and user_has_full_dashboard(conn, full_user):
        return redirect(url_for("dashboard"))
    return redirect(url_for("global_viewer"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    user_row = g.current_user
    if not user_has_full_dashboard(conn, user_row):
        return redirect(url_for("global_viewer"))

    display_name = f'{user_row["first_name"]} {user_row["last_name"]}'
    cloc = user_row["current_location_id"]
    if cloc:
        current_hierarchy = current_location_hierarchy(conn, str(cloc))
        default_vid = current_hierarchy[3]["id"] if len(current_hierarchy) > 3 else ""
    else:
        current_hierarchy = []
        default_vid = ""

    birth_vid = user_row["birth_location_id"]
    birth_location_label = (
        location_display_label(conn, str(birth_vid)) if birth_vid else None
    )
    current_location_label = (
        location_display_label(conn, str(cloc)) if cloc else None
    )

    social_core.ensure_wallet(conn, "user", str(user_row["private_id"]))
    pid = str(user_row["private_id"])
    wallet_balance = social_core.get_wallet_balance(conn, "user", pid)
    earned_row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS s FROM qoin_transactions
        WHERE user_private_id = ? AND amount > 0
        """,
        (pid,),
    ).fetchone()
    qoins_earned_total = int(earned_row["s"]) if earned_row else 0

    tx_cur = conn.execute(
        """
        SELECT id, amount, reason, created_at
        FROM qoin_transactions
        WHERE user_private_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT 10
        """,
        (pid,),
    )
    qoin_transactions_recent = [dict(r) for r in tx_cur]

    cur_private = conn.execute(
        """
        SELECT id, content, current_level, status, total_score, created_at
        FROM posts
        WHERE user_private_id = ?
          AND current_level = 'personal'
          AND status IN ('live', 'frozen')
        ORDER BY datetime(created_at) DESC
        LIMIT 80
        """,
        (pid,),
    )
    private_posts = [dict(r) for r in cur_private]

    user_village_stats_url = "#"
    if default_vid:
        user_village_stats_url = build_geo_public_url("village", str(default_vid).strip())

    user_life_stage = life_stage_from_age(int(user_row["age"]))

    geo_displays = user_dashboard_geo_displays(conn, user_row)
    dash_client_config: dict[str, Any] = {
        "userHierarchy": [dict(item) for item in current_hierarchy],
        "villageStatsUrl": user_village_stats_url,
        "defaultVillageId": default_vid or "",
        "quantumPunchVillageId": election_scheduler.TARGET_VILLAGE_ID,
        "userContinentId": geo_displays.get("user_continent_id") or "",
        "userContinentName": geo_displays.get("user_continent_name") or "",
        "userCountryId": geo_displays.get("user_country_id") or "",
        "userCountryName": geo_displays.get("user_country_name") or "",
        "userShowZoneTab": bool(geo_displays.get("user_show_zone_tab")),
        "isAdmin": is_admin_user(user_row),
        "userPrivateId": str(user_row["private_id"] or ""),
    }

    return render_template(
        "dashboard.html",
        user=user_row,
        display_name=display_name,
        birth_location_label=birth_location_label,
        current_location_label=current_location_label,
        current_hierarchy=current_hierarchy,
        default_active_location_id=default_vid,
        user_village_stats_url=user_village_stats_url,
        user_life_stage=user_life_stage,
        wallet_balance=wallet_balance,
        qoins_earned_total=qoins_earned_total,
        qoin_transactions_recent=qoin_transactions_recent,
        private_posts=private_posts,
        show_dashboard_post_form=bool(default_vid),
        dash_client_config=dash_client_config,
        **geo_displays,
    )


@app.route("/admin/location_members/<path:location_type>/<path:location_id>")
@login_required
def admin_location_members(location_type: str, location_id: str):
    if not int(session.get("is_admin") or 0):
        abort(403)
    conn = get_db()
    lt = location_type.strip().lower()
    lid = (location_id or "").strip()
    allowed_admin_scopes = frozenset(
        {"earth", "continent", "country", "zone", "state", "district", "tehsil", "village", "india"}
    )
    if lt not in allowed_admin_scopes:
        abort(404)

    if lt == "india":
        if lid.upper() != "IND":
            abort(404)
        pred, tup = _indian_users_predicate(conn)
        page_title = "India (national)"
    else:
        tbl = GEO_ROUTE_TABLE.get(lt)
        if not tbl or not _geo_table_exists(conn, tbl):
            abort(404)
        if conn.execute(f"SELECT 1 FROM {tbl} WHERE id = ?", (lid,)).fetchone() is None:
            abort(404)
        pred, tup = user_location_predicate(conn, lt, lid)
        page_title = str(_geo_row_optional_meta(conn, tbl, lid)["name"])

    cur = conn.execute(
        f"""
        SELECT first_name, last_name, gender, age, sun_sign, private_id, public_id,
               birth_location_id, current_location_id
        FROM users u
        WHERE ({pred})
        ORDER BY COALESCE(last_name, ''), COALESCE(first_name, '')
        """,
        tup,
    )
    members: list[dict[str, Any]] = []
    for r in cur:
        try:
            ag = int(r["age"])
        except (TypeError, ValueError):
            ag = 0
        members.append(
            {
                "full_name": f'{r["first_name"] or ""} {r["last_name"] or ""}'.strip(),
                "gender": str(r["gender"] or ""),
                "age": ag,
                "life_stage": life_stage_from_age(ag),
                "sun_sign": str(r["sun_sign"] or ""),
                "private_id": str(r["private_id"] or ""),
                "public_id": str(r["public_id"] or ""),
                "birth_location_id": str(r["birth_location_id"] or "")
                if r["birth_location_id"]
                else "—",
                "current_location_id": str(r["current_location_id"] or "")
                if r["current_location_id"]
                else "—",
            }
        )
    return render_template(
        "members_list.html",
        location_scope=lt,
        location_id=lid,
        location_title=page_title,
        members=members,
    )


@app.route("/global-viewer")
@login_required
def global_viewer():
    conn = get_db()
    user_row = g.current_user
    if user_has_full_dashboard(conn, user_row):
        return redirect(url_for("dashboard"))
    display_name = f'{user_row["first_name"]} {user_row["last_name"]}'
    return render_template(
        "global_viewer.html",
        user=user_row,
        display_name=display_name,
    )


if __name__ == "__main__":
    # On macOS, AirPlay Receiver may bind to port 5000; browsers then show 403/empty
    # with no Flask log line — avoid 5000 for local dev unless you disable AirPlay Receiver.
    port = int(os.environ.get("FLASK_RUN_PORT", "5001"))
    app.run(debug=True, host="127.0.0.1", port=port)
