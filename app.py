"""
Qumanity — Flask prototype.
Geography reads from indiaq.db; app users live in the same database `users` table.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import string
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
import bcrypt
import click

import admin_bootstrap
import config  # loads .env at import time; single source of truth for settings
from blockchain_adapter import blockchain
from blockchain_core import migrate_blockchain_schema
from db_path import ensure_database_parent, resolve_database_path
import birth_chart
import calendar_time
import election_scheduler
import language_core
import leadership_core
import identity_core
import donation_core
import referral_core
from translations import TRANSLATIONS, get_dashboard_ui_strings, get_text
import qoin_core
import scheduler as qoin_scheduler
import social_core
import sita_platform_core
import varna_core
import planetary_core
import element_core
import global_core
import deceased_core
import zodiac_calendar
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

DATABASE_PATH = str(resolve_database_path(BASE_DIR))
DB_PATH = Path(DATABASE_PATH)
ensure_database_parent(DB_PATH)


def _init_db_if_needed() -> None:
    """Initialize database tables if they don't exist — runs in background."""
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=15)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        )
        if not cursor.fetchone():
            subprocess.run(
                [sys.executable, str(BASE_DIR / "init_db.py")],
                timeout=30,
                capture_output=True,
                cwd=str(BASE_DIR),
            )
            print("Database initialized", flush=True)
        conn.close()
    except Exception as exc:
        print(f"Database init warning: {exc}", flush=True)


threading.Thread(target=_init_db_if_needed, daemon=True).start()

if os.environ.get("ENABLE_BLOCKCHAIN", "false").lower() == "true":
    blockchain.enabled = True

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

UPGRADE_ACCOUNT_TYPES = frozenset(
    {"Volunteer", "Agent", "Manager", "Leader", "Mentor"}
)
COUNCIL_UPGRADE_TYPES = frozenset({"Volunteer", "Agent", "Manager"})
ADMIN_ONLY_UPGRADE_TYPES = frozenset({"Leader", "Mentor"})

DEMO_ACCOUNT_TYPE_PREFIX = "D_U"

# Legacy registration IDs (U-XXXXXXXX); login accepts any stored private_id shape.
PRIVATE_ID_RE = re.compile(r"^\s*(U-[A-Za-z0-9]{8})\s*$", re.I)
# Login: 9-digit numeric Private ID with HU- prefix (e.g. HU-014918240).
PRIVATE_ID_LOGIN_RE = re.compile(r"^\d{9}$")
HU_PRIVATE_ID_LOGIN_RE = re.compile(r"^HU-\d{9}$", re.IGNORECASE)
ADMIN_PRIVATE_ID = "HU-014918240"
ADMIN_PUBLIC_ID = "ADMIN-PUBLIC"
HUMAN_PRIVATE_ID_PREFIX = "HU-"
LEGACY_ADMIN_PRIVATE_ID = "H_U_ADMIN"

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
    -- Levels: personal | village | tehsil | district | state | country | continent | earth
    -- Global users (no Indian village origin) escalate: personal -> country -> continent -> earth
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
    qoins_settled INTEGER NOT NULL DEFAULT 0,
    original_post_id INTEGER,
    frozen_at_level TEXT,
    archived_at_level TEXT,
    level_end_time TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_posts_user_private_id ON posts(user_private_id);
CREATE INDEX IF NOT EXISTS idx_posts_location_id ON posts(location_id);
CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at);
CREATE INDEX IF NOT EXISTS idx_posts_level_status ON posts(current_level, status);
CREATE INDEX IF NOT EXISTS idx_posts_status_location ON posts(status, location_id);
CREATE INDEX IF NOT EXISTS idx_posts_level_start_time ON posts(level_start_time);
CREATE INDEX IF NOT EXISTS idx_posts_freeze_level ON posts(freeze_level);
CREATE INDEX IF NOT EXISTS idx_posts_origin_village ON posts(origin_village_id);
CREATE INDEX IF NOT EXISTS idx_posts_user_status_level ON posts(user_private_id, status, current_level);
CREATE INDEX IF NOT EXISTS idx_posts_original_post_id ON posts(original_post_id);
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

try:
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
except ImportError:
    pass

_migration_startup_status: dict[str, Any] = {
    "running": False,
    "ok": False,
    "admin_exists": False,
    "already_configured": False,
    "message": "pending",
    "admin_private_id": ADMIN_PRIVATE_ID,
}

@app.get("/health")
@app.get("/healthz")
def health():
    """Fast liveness probe for Railway/Docker — always returns 200 when the process is up."""
    payload: dict[str, Any] = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
        payload["database"] = "connected"
    except Exception as exc:
        payload["database"] = "error"
        payload["database_error"] = str(exc)
    return jsonify(payload)


@app.get("/test-admin-login")
def test_admin_login():
    """Public diagnostic — admin account and password status (no secrets)."""
    import admin_login_repair

    conn = get_db()
    heal = admin_login_repair.ensure_admin_healthy(conn, force=True)
    status = admin_login_repair.test_admin_login_status(conn)
    status["self_heal"] = heal
    return jsonify(status)


def _valid_master_key(key: str) -> bool:
    """Validate emergency login key (env MASTER_KEY; dev fallback when unset)."""
    expected = (getattr(config, "MASTER_KEY", "") or "").strip()
    if not expected and config.DEBUG:
        expected = "emergency-key-2024"
    return bool(key and expected and key.strip() == expected)


@app.route("/emergency-login")
def emergency_login():
    """Emergency admin session using MASTER_KEY (set MASTER_KEY on Railway)."""
    import admin_login_repair

    key = (request.args.get("key") or "").strip()
    if not _valid_master_key(key):
        return "Unauthorized", 401

    conn = get_db()
    heal = admin_login_repair.ensure_admin_healthy(conn, force=True)
    if not heal.get("ok"):
        return (
            f"Admin heal failed: {heal.get('error') or heal}",
            500,
        )

    row = _lookup_user_by_private_id(conn, ADMIN_PRIVATE_ID)
    if not row:
        return "Admin not found after heal", 404

    user_pk = _user_pk_for_login_row(conn, row)
    if not user_pk:
        return "Admin user_pk missing after heal", 500

    session.clear()
    session["user_pk"] = user_pk
    full_user = load_user(conn, user_pk)
    _session_sync_admin_flag(full_user)
    app.logger.warning("Emergency login used for admin private_id=%s", ADMIN_PRIVATE_ID)
    return redirect(url_for("dashboard"))


@app.route("/fix-admin-login", methods=["GET", "POST"])
def fix_admin_login_page():
    """Public repair page — resets admin to HU-014918240 / P@y#umans123."""
    import admin_login_repair

    status = admin_login_repair.run_repair(reset_password=True, force=True)
    log = admin_login_repair.format_repair_log(status)
    ok = bool(status.get("ok"))
    title = "Admin login fixed" if ok else "Admin login fix failed"
    return f"""
    <html>
    <head><title>{title}</title></head>
    <body style="font-family: Inter, system-ui, sans-serif; padding: 40px; max-width: 720px; margin: 0 auto; background: #0f172a; color: #f8fafc;">
      <h1>{title}</h1>
      <pre style="background: #1e293b; padding: 20px; border-radius: 8px; white-space: pre-wrap; border: 1px solid #475569;">{log}</pre>
      <p><strong>Login credentials</strong></p>
      <ul>
        <li>OTP digits: <code>014918240</code></li>
        <li>Password: <code>P@y#umans123</code></li>
        <li>Full Private ID: <code>HU-014918240</code></li>
      </ul>
      <a href="{url_for('login')}" style="display:inline-block;background:#f59e0b;color:#000;padding:10px 20px;text-decoration:none;border-radius:6px;font-weight:600;">Go to Login</a>
    </body>
    </html>
    """


@app.route("/api/fix-admin-login", methods=["GET", "POST"])
def api_fix_admin_login():
    """JSON admin login repair."""
    import admin_login_repair

    status = admin_login_repair.run_repair(reset_password=True, force=True)
    status["success"] = bool(status.get("ok"))
    return jsonify(status), (200 if status.get("ok") else 500)


@app.route("/reset-admin", methods=["GET", "POST"])
def reset_admin_page():
    """Delete all admins and create fresh HU-014918240."""
    import admin_login_repair

    status = admin_login_repair.run_reset()
    log = admin_login_repair.format_reset_log(status)
    ok = bool(status.get("ok"))
    title = "Admin reset complete" if ok else "Admin reset failed"
    return f"""
    <html>
    <head><title>{title}</title></head>
    <body style="font-family: Inter, system-ui, sans-serif; padding: 40px; max-width: 720px; margin: 0 auto; background: #0f172a; color: #f8fafc;">
      <h1>{title}</h1>
      <pre style="background: #1e293b; padding: 20px; border-radius: 8px; white-space: pre-wrap; border: 1px solid #475569;">{log}</pre>
      <h3>Credentials</h3>
      <ul>
        <li>Private ID: <code>HU-014918240</code></li>
        <li>OTP digits: <code>014918240</code></li>
        <li>Password: <code>P@y#umans123</code></li>
        <li>Email: <code>sekyorintantra@gmail.com</code></li>
        <li>Phone: <code>8287696616</code></li>
      </ul>
      <a href="{url_for('login')}" style="display:inline-block;background:#f59e0b;color:#000;padding:10px 20px;text-decoration:none;border-radius:6px;font-weight:600;">Go to Login</a>
    </body>
    </html>
    """


@app.route("/api/reset-admin", methods=["GET", "POST"])
def api_reset_admin():
    """JSON admin reset."""
    import admin_login_repair

    status = admin_login_repair.run_reset()
    status["success"] = bool(status.get("ok"))
    return jsonify(status), (200 if status.get("ok") else 500)


@app.route("/debug-admin", methods=["GET"])
def debug_admin_status():
    """Check admin account — always available for ops."""
    import admin_login_repair

    conn = get_db()
    diag = admin_login_repair.diagnose_admin(conn)
    target = diag.get("target")
    login_verified = admin_login_repair.verify_admin_password(conn)
    login_simulated = admin_login_repair.simulate_admin_login(conn)
    null_ids = conn.execute(
        "SELECT COUNT(*) FROM users WHERE id IS NULL"
    ).fetchone()[0]
    return jsonify(
        {
            "exists": target is not None,
            "login_verified": login_verified,
            "login_simulated": login_simulated,
            "users_with_null_id": int(null_ids or 0),
            "expected_private_id": ADMIN_PRIVATE_ID,
            "login_digits": ADMIN_PRIVATE_ID[len("HU-"):],
            "password_hint": "P@y#umans123",
            "admin_details": target,
            "all_admins": diag.get("admins"),
            "legacy_admin": diag.get("legacy"),
            "fix_url": "/fix-admin-login",
            "reset_url": "/reset-admin",
        }
    )

app.config.update(config.as_flask_config())
app.secret_key = app.config["SECRET_KEY"]

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("qumanity")
config.log_warnings()


def _log_payment_env_status() -> None:
    vpa = (os.environ.get("DONATION_UPI_VPA") or config.DONATION_UPI_VPA or "").strip()
    logger.info(
        "Payment env: RAZORPAY_KEY_ID=%s RAZORPAY_KEY_SECRET=%s DONATION_UPI_VPA=%s",
        "set" if config.RAZORPAY_KEY_ID else "MISSING",
        "set" if config.RAZORPAY_KEY_SECRET else "MISSING",
        f"set ({len(vpa)} chars)" if vpa else "MISSING",
    )


_log_payment_env_status()


def _language_geo_helpers() -> dict[str, Any]:
    return {
        "geo_path_to_state_path": geo_path_to_state_path,
        "raw_path_fn": raw_path,
    }


def resolve_user_language(
    conn: sqlite3.Connection, user_row: sqlite3.Row | None
) -> str:
    return language_core.resolve_preferred_language(
        conn, session, user_row, **_language_geo_helpers()
    )


def active_ui_language(
    conn: sqlite3.Connection | None = None,
    user_row: sqlite3.Row | None = None,
) -> str:
    """UI label language — honors explicit dropdown choice over auto-detect."""
    helpers = _language_geo_helpers()
    if conn is None:
        try:
            conn = get_db()
        except Exception:
            conn = None
    if user_row is None and session.get("user_pk") and conn is not None:
        try:
            user_row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (int(session["user_pk"]),),
            ).fetchone()
        except Exception:
            user_row = None
    return language_core.ui_language_code(
        conn, session, user_row, **helpers
    )


def language_dropdown_options(
    conn: sqlite3.Connection, user_row: sqlite3.Row | None
) -> list[dict[str, str]]:
    return language_core.build_language_dropdown_options(
        conn, user_row, **_language_geo_helpers()
    )


@app.template_filter("mask_private_id")
def mask_private_id_filter(private_id: str | None) -> str:
    return sita_platform_core.mask_private_id(str(private_id or ""))


@app.template_filter("tr")
def translate_filter(key: str, language_code: str | None = None) -> str:
    lang = (language_code or getattr(g, "ui_language", None) or "en").strip().lower()
    return get_text(key, lang)


@app.before_request
def _check_allowed_host() -> None:
    """Reject unknown host headers in production (custom domain + Railway fallback)."""
    if not config.IS_PRODUCTION:
        return
    if request.path in ("/health", "/healthz", "/favicon.ico"):
        return
    if request.endpoint and str(request.endpoint).startswith("static"):
        return
    host = (request.host or "").split(":")[0].strip().lower()
    if not host:
        return
    allowed = config.allowed_hosts()
    if host not in allowed:
        app.logger.warning("Blocked request for unknown host: %s", host)
        abort(400, description="Invalid host")


@app.before_request
def _ensure_admin_self_heal() -> None:
    """Lightweight auto-heal for primary + backup admin (throttled)."""
    if request.endpoint and str(request.endpoint).startswith("static"):
        return
    skip = {
        "/health",
        "/healthz",
        "/setup",
        "/logout",
        "/webhook/donation",
        "/debug/check",
        "/test-admin-login",
        "/emergency-login",
    }
    if request.path in skip:
        return
    try:
        import admin_login_repair

        conn = get_db()
        force = request.path in ("/login", "/api/login") and request.method == "POST"
        result = admin_login_repair.ensure_admin_healthy(conn, force=force)
        if result.get("actions") and not result.get("skipped"):
            app.logger.info("Admin self-heal: %s", result.get("actions"))
        if not result.get("ok") and not result.get("skipped"):
            app.logger.warning("Admin self-heal failed: %s", result)
    except Exception:
        app.logger.exception("Admin self-heal error")


@app.before_request
def _prune_invalid_session() -> None:
    """Drop stale session cookies when the user row no longer exists."""
    if request.endpoint and str(request.endpoint).startswith("static"):
        return
    if request.path in ("/health", "/healthz", "/setup", "/logout"):
        return
    pk = session.get("user_pk")
    if not pk:
        return
    try:
        conn = get_db()
        row = conn.execute("SELECT 1 FROM users WHERE id = ?", (int(pk),)).fetchone()
        if not row:
            session.clear()
    except Exception:
        session.clear()


@app.before_request
def _bind_ui_language() -> None:
    if request.path in ("/health", "/healthz"):
        g.ui_language = "en"
        return
    if request.path == "/setup":
        g.ui_language = "en"
        return
    if session.get("language_user_choice"):
        g.ui_language = str(session.get("preferred_language") or "en").strip().lower() or "en"
        return
    try:
        g.ui_language = active_ui_language()
    except Exception:
        g.ui_language = str(session.get("preferred_language") or "en").strip().lower() or "en"


@app.context_processor
def inject_homepage_nav() -> dict[str, bool]:
    """Homepage always shows Login/Register — not Dashboard — even if a session cookie exists."""
    return {"show_public_nav": request.endpoint == "index"}


@app.context_processor
def inject_language_context() -> dict[str, Any]:
    # English is the default for everyone. The dropdown shows ONLY the languages
    # relevant to this user: their state's default language, their mother tongue
    # (if different), and English — never the full list. Logged-out visitors see
    # just English.
    lang = (getattr(g, "ui_language", None) or "en").strip().lower()
    if lang not in TRANSLATIONS:
        lang = "en"
    options: list[dict[str, str]] = [{"code": "en", "label": "English"}]
    try:
        conn = get_db()
        user_row = None
        if session.get("user_pk"):
            user_row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (int(session["user_pk"]),),
            ).fetchone()
        options = language_dropdown_options(conn, user_row)
    except Exception:
        options = [{"code": "en", "label": "English"}]
    # Ensure the active language is always selectable even if it is outside the
    # relevant set (e.g. a user explicitly chose another language earlier).
    if lang not in {o["code"] for o in options}:
        options.append(
            {"code": lang, "label": language_core.language_option_label(lang)}
        )
    return {
        "preferred_language": lang,
        "current_language": lang,
        "language_options": options,
        "is_logged_in": bool(session.get("user_pk")),
    }


@app.context_processor
def inject_council_context() -> dict[str, Any]:
    """Expose council / mentor flags to templates (hamburger menu, Space sections)."""
    try:
        if not session.get("user_pk"):
            return {"is_council_member": False, "is_mentor": False}
        conn = get_db()
        user_row = getattr(g, "current_user", None)
        if user_row is None:
            user_row = conn.execute(
                "SELECT * FROM users WHERE id = ?",
                (int(session["user_pk"]),),
            ).fetchone()
        return {
            "is_council_member": is_council_member(conn, user_row),
            "is_mentor": deceased_core.is_mentor_user(conn, user_row),
            "is_admin": is_admin_user(user_row),
        }
    except Exception:
        return {"is_council_member": False, "is_mentor": False, "is_admin": False}


@app.context_processor
def inject_donation_display() -> dict[str, str]:
    return {
        "donation_bank_name": getattr(config, "DONATION_BANK_NAME", "SITA Foundation"),
        "donation_bank": getattr(config, "DONATION_BANK", "State Bank of India"),
        "donation_upi_display": getattr(config, "DONATION_UPI_DISPLAY", "41711366837@sbi"),
        "donation_bank_account": getattr(config, "DONATION_BANK_ACCOUNT", "41711366837"),
        "donation_ifsc": getattr(config, "DONATION_IFSC", "SBIN0011551"),
    }


app.logger.setLevel(logging.INFO)
_last_escalation_check = 0.0


def _api_json_error(message: str, status: int = 500):
    return jsonify({"error": message}), status


@app.errorhandler(404)
def _handle_api_404(err):
    if (request.path or "").startswith("/api/"):
        return _api_json_error("Not found", 404)
    return err


@app.errorhandler(500)
def _handle_api_500(err):
    if (request.path or "").startswith("/api/"):
        app.logger.exception("Unhandled API error")
        return _api_json_error("Internal server error", 500)
    return err


try:
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def _handle_api_http_exception(err: HTTPException):
        if (request.path or "").startswith("/api/"):
            return jsonify({"error": err.description or err.name}), err.code
        return err
except ImportError:
    pass


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(DB_PATH, timeout=15)
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
        ("is_active", "INTEGER NOT NULL DEFAULT 0"),
        ("registered_by_admin", "INTEGER NOT NULL DEFAULT 0"),
        ("birth_latitude", "REAL"),
        ("birth_longitude", "REAL"),
        ("account_status", "TEXT NOT NULL DEFAULT 'active'"),
        ("temp_access", "INTEGER NOT NULL DEFAULT 0"),
        ("verified_at", "TEXT"),
        ("verification_failed_reason", "TEXT"),
    ]
    for col_name, decl in additions:
        if col_name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {decl}")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute(
            "UPDATE users SET is_active = 1 WHERE COALESCE(is_active, 0) = 0"
        )
    except sqlite3.OperationalError:
        pass
    try:
        import admin_login_repair

        admin_login_repair.repair_null_user_ids(conn)
    except Exception:
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


def migrate_user_education_work_v2(conn: sqlite3.Connection) -> None:
    """Ensure education/work tables exist and have created_at where missing."""
    migrate_user_education_table(conn)
    migrate_user_work_table(conn)
    for table, col in (("user_education", "created_at"), ("user_work", "created_at")):
        cols = _table_columns(conn, table)
        if col in cols:
            continue
        try:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {col} TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )
        except sqlite3.OperationalError:
            pass
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


def is_council_member(conn: sqlite3.Connection, user_row: sqlite3.Row | None) -> bool:
    """True if the user is Admin (Mentor) or holds any filled leadership slot at
    any geographic level (Village → Earth)."""
    if user_row is None:
        return False
    if is_admin_user(user_row):
        return True
    try:
        private_id = str(user_row["private_id"] or "").strip()
    except (KeyError, TypeError):
        private_id = ""
    if not private_id:
        return False
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM leadership_council
            WHERE current_holder_private_id = ? AND status = 'filled'
            """,
            (private_id,),
        ).fetchone()
        return bool(row and int(row["c"] or 0) > 0)
    except sqlite3.Error:
        return False


def user_can_upgrade_to(
    conn: sqlite3.Connection,
    upgrader: sqlite3.Row | None,
    target_type: str,
) -> bool:
    target = str(target_type or "").strip()
    if not target:
        return False
    if is_admin_user(upgrader):
        return target in UPGRADE_ACCOUNT_TYPES
    if is_council_member(conn, upgrader):
        return target in COUNCIL_UPGRADE_TYPES
    return False


def council_or_admin_required(view):
    """Decorator: admin or elected council member. Implies login."""

    @wraps(view)
    @login_required
    def _wrap(*args: Any, **kwargs: Any):
        conn = get_db()
        user = getattr(g, "current_user", None)
        if not is_admin_user(user) and not is_council_member(conn, user):
            return jsonify({"error": "Admin or Council member only"}), 403
        return view(*args, **kwargs)

    return _wrap


def admin_required(view):
    """Decorator: 403 unless ``g.current_user.is_admin`` is truthy. Implies login."""
    @wraps(view)
    @login_required
    def _wrap(*args: Any, **kwargs: Any):
        if not is_admin_user(getattr(g, "current_user", None)):
            return jsonify({"error": "Admin only"}), 403
        return view(*args, **kwargs)
    return _wrap


def admin_page_required(view):
    """HTML admin routes: redirect to dashboard when not admin."""

    @wraps(view)
    @login_required
    def _wrap(*args: Any, **kwargs: Any):
        if not is_admin_user(getattr(g, "current_user", None)):
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
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


INDIA_ZONE_NAMES: dict[str, str] = {
    "CS": "Central State (UT&North-East)",
    "NS": "North India State",
    "WS": "West India State",
    "SS": "South India State",
    "ES": "East India State",
}


def zone_code_from_village_location_id(location_id: str) -> str | None:
    """Extract zone code (e.g. CS) from ``0.राम|IND/CS/DL.5.4.1E``."""
    rp = raw_path((location_id or "").strip())
    if "IND/" not in rp:
        return None
    tail = rp.split("IND/", 1)[1]
    if not tail:
        return None
    head = tail.split("/", 1)[0]
    letters = "".join(ch for ch in head if ch.isalpha())
    return letters.upper() if letters else None


def user_zone_info(
    conn: sqlite3.Connection, user_row: sqlite3.Row
) -> dict[str, str | None]:
    try:
        cloc = str(user_row["current_location_id"] or "").strip()
    except (KeyError, IndexError):
        cloc = ""
    code = zone_code_from_village_location_id(cloc)
    if not code:
        return {"zone_code": None, "zone_id": None, "zone_name": None}
    zid = full_id_from_raw(f"IND.{code}")
    name = INDIA_ZONE_NAMES.get(code, code)
    if _geo_table_exists(conn, "zone"):
        meta = _geo_row_optional_meta(conn, "zone", zid)
        if meta.get("name"):
            name = str(meta["name"])
    return {"zone_code": code, "zone_id": zid, "zone_name": name}


def donation_location_context(
    conn: sqlite3.Connection,
    *,
    village_id: str,
    country_id: str = "IND",
    continent_id: str = "",
) -> dict[str, str]:
    """Resolve wallet IDs for the 8 geographic donation tiers."""
    vid = (village_id or "").strip()
    by_scope: dict[str, str] = {}
    if vid:
        by_scope = {h["scope"]: h["id"] for h in current_location_hierarchy(conn, vid)}
    zone_id = ""
    if vid:
        zc = zone_code_from_village_location_id(vid)
        if zc:
            zone_id = full_id_from_raw(f"IND.{zc}")
    ctry = (country_id or "IND").strip().upper() or "IND"
    cont = (continent_id or "").strip().upper()
    if not cont and ctry == "IND":
        cont = "AS"
    return donation_core.build_location_context(
        village_id=vid,
        country_id=ctry,
        continent_id=cont,
        zone_id=zone_id,
        state_id=by_scope.get("state", ""),
        district_id=by_scope.get("district", ""),
        tehsil_id=by_scope.get("tehsil", ""),
    )


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


def get_countries_by_continent(
    conn: sqlite3.Connection, continent_id: str
) -> list[str]:
    """Return country ids belonging to a continent (from ``country`` table)."""
    cid = (continent_id or "").strip().upper()
    if not cid or not _geo_table_exists(conn, "country"):
        return []
    cur = conn.execute(
        "SELECT id FROM country WHERE continent_id = ? ORDER BY id",
        (cid,),
    )
    return [str(r["id"]).strip() for r in cur if str(r["id"] or "").strip()]


def user_location_predicate(
    conn: sqlite3.Connection, scope: str, full_id: str | None
) -> tuple[str, tuple]:
    if scope == "earth":
        return "1=1", ()

    user_cols = _table_columns(conn, "users")
    has_current_country = "current_country_id" in user_cols

    if scope == "continent":
        cont = (full_id or "").strip().upper()
        if has_current_country and _geo_table_exists(conn, "country"):
            return (
                "TRIM(COALESCE(u.current_country_id, '')) IN "
                "(SELECT id FROM country WHERE continent_id = ?)",
                (cont,),
            )
        if cont == "AS":
            return _indian_users_predicate(conn)
        return "1=0", ()

    if scope == "country":
        ctry = (full_id or "").strip().upper()
        if has_current_country:
            if ctry == "IND":
                ind_pred, ind_params = _indian_users_predicate(conn)
                return (
                    f"(TRIM(COALESCE(u.current_country_id, '')) = ? OR ({ind_pred}))",
                    (ctry,) + ind_params,
                )
            return (
                "TRIM(COALESCE(u.current_country_id, '')) = ?",
                (ctry,),
            )
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


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Minimum 9 chars, upper, lower, digit, special."""
    pw = password or ""
    if len(pw) < 9:
        return False, "Password must be at least 9 characters."
    if not re.search(r"[A-Z]", pw):
        return False, "Password must contain at least one capital letter."
    if not re.search(r"[a-z]", pw):
        return False, "Password must contain at least one small letter."
    if not re.search(r"[0-9]", pw):
        return False, "Password must contain at least one number."
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", pw):
        return False, "Password must contain at least one special character."
    return True, "Valid"


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


def _india_chain_ids_from_village(
    conn: sqlite3.Connection, village_id: str | None
) -> dict[str, str]:
    """State/district/tehsil/village full ids for registration form restore."""
    vid = (village_id or "").strip()
    if not vid:
        return {}
    hier = current_location_hierarchy(conn, vid)
    by_scope = {str(h["scope"]): str(h["id"]) for h in hier}
    return {
        "state_id": by_scope.get("state", ""),
        "district_id": by_scope.get("district", ""),
        "tehsil_id": by_scope.get("tehsil", ""),
        "village_id": by_scope.get("village", vid),
    }


def _enrich_register_form_geo(conn: sqlite3.Connection, form: dict[str, Any]) -> None:
    """Add birth_/current_ state_id… keys from village ids for chained dropdown restore."""
    for prefix, loc_key in (
        ("birth", "birth_location_id"),
        ("current", "current_location_id"),
    ):
        chain = _india_chain_ids_from_village(conn, form.get(loc_key))
        for k, v in chain.items():
            form[f"{prefix}_{k}"] = v

    birth_ctry = str(form.get("birth_country_id") or "").strip().upper()
    curr_ctry = str(form.get("current_country_id") or "").strip().upper()
    if form.get("birth_location_selected") != "1":
        if birth_ctry == "IND" and form.get("birth_location_id"):
            form["birth_location_selected"] = "1"
        elif birth_ctry and birth_ctry != "IND":
            if global_core.country_has_states(conn, birth_ctry):
                if form.get("birth_global_state_id"):
                    form["birth_location_selected"] = "1"
            else:
                form["birth_location_selected"] = "1"
    if form.get("current_location_selected") != "1":
        if curr_ctry == "IND" and form.get("current_location_id"):
            form["current_location_selected"] = "1"
        elif curr_ctry and curr_ctry != "IND":
            if global_core.country_has_states(conn, curr_ctry):
                if form.get("current_global_state_id"):
                    form["current_location_selected"] = "1"
            else:
                form["current_location_selected"] = "1"


def user_in_indian_village(conn: sqlite3.Connection, user_row: sqlite3.Row) -> bool:
    """Village commerce/wallet features only for users at an Indian village location."""
    try:
        cloc = str(user_row["current_location_id"] or "").strip()
    except (KeyError, IndexError):
        return False
    if not cloc or not _current_location_suggests_india(conn, cloc):
        return False
    return village_exists(conn, cloc)


def _qoin_hierarchy_resolver(user_private_id: str) -> list[dict[str, str]]:
    conn = get_db()
    row = conn.execute(
        "SELECT current_location_id FROM users WHERE private_id = ?",
        (user_private_id,),
    ).fetchone()
    if not row or not row["current_location_id"]:
        return []
    return current_location_hierarchy(conn, str(row["current_location_id"]))


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


REGISTRATION_TOTAL_VILLAGES = 620000
REGISTRATION_TOTAL_STATES = 28


def _geo_table_row_count(conn: sqlite3.Connection, table: str) -> int:
    if not _geo_table_exists(conn, table):
        return 0
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
    return int(row["c"]) if row else 0


def registration_stats_bundle(conn: sqlite3.Connection) -> dict[str, int]:
    """Counts for the registration page statistics panel."""
    total_users = count_registered_users(conn)
    india_users = count_homepage_india_users(conn)

    if geography_has_relational_fks(conn) and _geo_table_exists(conn, "village"):
        active_villages, active_tehsils, active_districts, active_states = (
            _active_location_counts_join(conn)
        )
    else:
        active_villages, active_tehsils, active_districts, active_states = (
            _active_location_counts_path(conn)
        )

    total_villages = REGISTRATION_TOTAL_VILLAGES
    total_tehsils = _geo_table_row_count(conn, "tehsil")
    total_districts = _geo_table_row_count(conn, "district")
    state_table_count = _geo_table_row_count(conn, "state")
    total_states = (
        state_table_count if state_table_count > 0 else REGISTRATION_TOTAL_STATES
    )

    return {
        "total_users": total_users,
        "india_users": india_users,
        "active_villages": active_villages,
        "active_tehsils": active_tehsils,
        "active_districts": active_districts,
        "active_states": active_states,
        "total_villages": total_villages,
        "total_tehsils": total_tehsils,
        "total_districts": total_districts,
        "total_states": total_states,
        "empty_villages": max(0, total_villages - active_villages),
        "empty_tehsils": max(0, total_tehsils - active_tehsils),
        "empty_districts": max(0, total_districts - active_districts),
        "empty_states": max(0, total_states - active_states),
    }


def _active_location_counts_join(
    conn: sqlite3.Connection,
) -> tuple[int, int, int, int]:
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT TRIM(u.current_location_id)) AS c
        FROM users u
        INNER JOIN village v ON v.id = TRIM(u.current_location_id)
        """
    ).fetchone()
    active_villages = int(row["c"]) if row else 0

    active_tehsils = 0
    active_districts = 0
    active_states = 0

    if _geo_table_exists(conn, "tehsil"):
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT v.tehsil_id) AS c
            FROM users u
            INNER JOIN village v ON v.id = TRIM(u.current_location_id)
            WHERE TRIM(COALESCE(v.tehsil_id, '')) != ''
            """
        ).fetchone()
        active_tehsils = int(row["c"]) if row else 0

        if _geo_table_exists(conn, "district"):
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT t.district_id) AS c
                FROM users u
                INNER JOIN village v ON v.id = TRIM(u.current_location_id)
                INNER JOIN tehsil t ON t.id = v.tehsil_id
                WHERE TRIM(COALESCE(t.district_id, '')) != ''
                """
            ).fetchone()
            active_districts = int(row["c"]) if row else 0

            if _geo_table_exists(conn, "state"):
                row = conn.execute(
                    """
                    SELECT COUNT(DISTINCT d.state_id) AS c
                    FROM users u
                    INNER JOIN village v ON v.id = TRIM(u.current_location_id)
                    INNER JOIN tehsil t ON t.id = v.tehsil_id
                    INNER JOIN district d ON d.id = t.district_id
                    WHERE TRIM(COALESCE(d.state_id, '')) != ''
                    """
                ).fetchone()
                active_states = int(row["c"]) if row else 0

    return active_villages, active_tehsils, active_districts, active_states


def _active_location_counts_path(
    conn: sqlite3.Connection,
) -> tuple[int, int, int, int]:
    villages: set[str] = set()
    tehsils: set[str] = set()
    districts: set[str] = set()
    states: set[str] = set()

    cur = conn.execute(
        """
        SELECT TRIM(current_location_id) AS loc
        FROM users
        WHERE TRIM(COALESCE(current_location_id, '')) != ''
        """
    )
    for row in cur:
        vid = str(row["loc"] or "").strip()
        if not vid or not village_exists(conn, vid):
            continue
        villages.add(vid)
        raw = raw_path(vid)
        tehsil_raw = path_parent_suffix(raw)
        if tehsil_raw:
            tehsils.add(full_id_from_raw(tehsil_raw))
            district_raw = path_parent_suffix(tehsil_raw)
            if district_raw:
                districts.add(full_id_from_raw(district_raw))
        state_raw = geo_path_to_state_path(raw)
        if state_raw:
            states.add(full_id_from_raw(state_raw))

    return len(villages), len(tehsils), len(districts), len(states)


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


def _row_get(
    row: sqlite3.Row | dict[str, Any] | None,
    key: str,
    default: Any = None,
) -> Any:
    """Read a column from sqlite3.Row or dict without AttributeError."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        val = row[key]
        return default if val is None else val
    except (KeyError, IndexError, TypeError):
        return default


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
    India-associated dashboard features (Public timeline, village posts, etc.).

    Available when the user has India as birth and/or present country (Types A, B, D).
    Type C (global-only) users use Private, Personal, and Global accounts instead.
    """
    _ = conn
    return identity_core.user_birth_in_india(user_row) or identity_core.user_present_in_india(
        user_row
    )


GLOBAL_COLLECTIVE_BOARD_LEVELS = frozenset({"earth", "continent", "country"})


def user_can_access_collective_board(
    conn: sqlite3.Connection | None, user_row: sqlite3.Row, level: str
) -> bool:
    if level in GLOBAL_COLLECTIVE_BOARD_LEVELS:
        return True
    if level == "state" and global_core.is_global_only_user(user_row):
        return bool(global_core.user_global_state_id(user_row))
    return user_has_full_dashboard(conn, user_row)


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
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
    *,
    village_id: str | None = None,
) -> set[str]:
    """IDs in the logged-in user's active village hierarchy (State…Village)."""
    if global_core.is_global_only_user(user_row):
        sid = global_core.user_global_state_id(user_row)
        allowed = set()
        if sid:
            allowed.add(sid)
        try:
            cid = str(user_row["current_country_id"] or "").strip().upper()
        except (KeyError, IndexError):
            cid = ""
        if cid:
            allowed.add(cid)
        return allowed
    cloc = village_id or effective_dashboard_village_id(conn, user_row)
    if cloc is None or str(cloc).strip() == "":
        return set()
    hier = current_location_hierarchy(conn, str(cloc).strip())
    return {str(item["id"]).strip() for item in hier if str(item.get("id") or "").strip()}


def session_location_mode(user_row: sqlite3.Row) -> str:
    mode = session.get("location_mode")
    if mode in ("birth", "present") and identity_core.can_toggle_location(user_row):
        return str(mode)
    return identity_core.default_location_mode(user_row)


def effective_dashboard_village_id(
    conn: sqlite3.Connection, user_row: sqlite3.Row
) -> str:
    mode = session_location_mode(user_row)
    vid = identity_core.active_location_id(user_row, mode)
    return str(vid or "").strip()


def dashboard_hierarchy_for_user(
    conn: sqlite3.Connection, user_row: sqlite3.Row
) -> tuple[list[dict[str, str]], str]:
    vid = effective_dashboard_village_id(conn, user_row)
    if not vid:
        return [], ""
    hier = current_location_hierarchy(conn, vid)
    return hier, vid


def present_village_id(user_row: sqlite3.Row) -> str:
    """User's current (present) village — used for Public Account timeline."""
    return str(user_row["current_location_id"] or "").strip()


def public_hierarchy_for_user(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
    *,
    language_code: str | None = None,
) -> tuple[list[dict[str, str]], str]:
    """Public Account always reflects present location, never birth."""
    if global_core.is_global_only_user(user_row):
        return global_core.global_public_hierarchy(conn, user_row)
    vid = present_village_id(user_row)
    if not vid:
        return [], ""
    hier = current_location_hierarchy(conn, vid)
    lang = language_code or resolve_user_language(conn, user_row)
    return language_core.apply_hierarchy_translations(conn, hier, lang), vid


def user_public_allowed_location_ids_present(
    conn: sqlite3.Connection, user_row: sqlite3.Row
) -> set[str]:
    """IDs in the user's present-village hierarchy (State…Village)."""
    cloc = present_village_id(user_row)
    if not cloc:
        return set()
    hier = current_location_hierarchy(conn, cloc)
    return {str(item["id"]).strip() for item in hier if str(item.get("id") or "").strip()}


def elections_are_enabled() -> bool:
    return bool(getattr(election_scheduler, "ELECTIONS_ENABLED", False))


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

    show_zone_tab = identity_core.user_show_zone_tab(user_row)
    zinfo = user_zone_info(conn, user_row) if show_zone_tab else {
        "zone_code": None,
        "zone_id": None,
        "zone_name": None,
    }

    return {
        "user_current_location_id_display": cloc,
        "user_global_id_display": global_id,
        "user_continent_id": cont_id or None,
        "user_continent_name": cont_name,
        "user_country_id": ctry_id or None,
        "user_country_name": ctry_name,
        "user_show_zone_tab": show_zone_tab,
        "user_zone_code": zinfo.get("zone_code"),
        "user_zone_id": zinfo.get("zone_id"),
        "user_zone_name": zinfo.get("zone_name"),
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
    "zone",
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


def _escalation_label_for_frozen(post: sqlite3.Row | dict[str, Any]) -> str:
    """Human label for a frozen post row (e.g. Escalated to Village)."""
    if isinstance(post, sqlite3.Row):
        d = dict(post)
    else:
        d = post
    frozen_at = str(
        d.get("frozen_at_level") or d.get("freeze_level") or ""
    ).strip().lower()
    if not frozen_at:
        cl = str(d.get("current_level") or "").strip().lower()
        if cl.endswith("_frozen"):
            frozen_at = cl[: -len("_frozen")]
    if not frozen_at:
        return "Frozen"
    try:
        order = social_core.post_level_order(d)
        idx = order.index(frozen_at)
    except ValueError:
        return "Frozen"
    if frozen_at == "earth":
        return "Journey complete"
    if idx + 1 < len(order):
        nxt = order[idx + 1]
        return f"Escalated to {nxt.title()}"
    return "Frozen"


def _archived_level_label(post: sqlite3.Row | dict[str, Any]) -> str:
    if isinstance(post, sqlite3.Row):
        d = dict(post)
    else:
        d = post
    level = str(d.get("archived_at_level") or "").strip().lower()
    if level:
        return f"Archived from {level.title()}"
    return "Previous post"


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
    level_end = _post_datetime(post["level_end_time"]) if "level_end_time" in post.keys() else None
    if state == "frozen" and level_end is not None:
        end_dt = level_end
    else:
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
    if board_state == "frozen":
        d["escalation_label"] = _escalation_label_for_frozen(r)
        d["is_read_only"] = True
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


def _api_handle_errors(view):
    """Wrap API handlers so failures return JSON instead of HTML error pages."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except sqlite3.Error:
            app.logger.exception("Database error in %s", view.__name__)
            return _api_json_error("Database error", 500)
        except Exception as exc:
            app.logger.exception("API error in %s", view.__name__)
            return _api_json_error(str(exc) or "Internal server error", 500)

    return wrapped


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
        try:
            is_active = int(user["is_active"] or 0)
        except (KeyError, TypeError, ValueError):
            is_active = 1
        try:
            is_admin = int(user["is_admin"] or 0)
        except (KeyError, TypeError, ValueError):
            is_admin = 0
        if not is_active and not is_admin:
            allowed = {
                "register_donation",
                "api_register_donate",
            }
            if request.endpoint not in allowed:
                session.clear()
                if (request.path or "").startswith("/api/"):
                    return jsonify({"error": "Account not activated. Complete registration donation."}), 403
                flash("Your account is not active. Complete the registration donation.", "error")
                return redirect(url_for("register_donation"))
        return view(*args, **kwargs)

    return wrapped


def api_login_required(view):
    """Alias for :func:`login_required` — API routes must never redirect to HTML login."""
    return login_required(view)


def _safe_escalate_posts(conn: sqlite3.Connection) -> None:
    try:
        social_core.escalate_posts(conn)
    except sqlite3.Error:
        app.logger.exception("post escalation failed")


@app.before_request
def _before_request() -> None:
    """
    Schema/bootstrap only — no authentication gate here (403 never comes from this hook).
    Skips DB work for static assets and the lightweight /debug/check diagnostic.
    """
    if request.endpoint and str(request.endpoint).startswith("static"):
        return
    if request.path in ("/health", "/healthz"):
        return
    if request.path == "/setup":
        return
    if request.path == "/webhook/donation":
        return
    if request.path == "/logout":
        return
    # Public diagnostic — no DB so /debug/check works even if migrations fail.
    if request.path == "/debug/check":
        return
    if request.path == "/debug-admin":
        return
    if request.path in ("/fix-admin-login", "/api/fix-admin-login", "/reset-admin", "/api/reset-admin"):
        return
    if request.path in ("/test-admin-login", "/emergency-login"):
        return
    try:
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
        migrate_user_education_work_v2(conn)
        migrate_connection_requests_life_stage(conn)
        election_scheduler.migrate_election_tables(conn)
        leadership_core.migrate_leadership_council(conn)
        leadership_core.seed_mentor_slots(conn)
        language_core.migrate_and_seed(conn)
        social_core.ensure_wallet_and_vote_tables(conn)
        qoin_core.migrate_qoin_transactions(conn)
        qoin_core.migrate_cash_donations(conn)
        qoin_core.migrate_qoin_economy_tables(conn)
        zodiac_calendar.migrate_calendar_event_tables(conn)
        import village_platform

        village_platform.migrate_village_platform_tables(conn)
        identity_core.migrate_identity_tables(conn)
        referral_core.migrate_referral_schema(conn)
        donation_core.migrate_donation_schema(conn)
        varna_core.migrate_varna_schema(conn)
        planetary_core.migrate_space_schema(conn)
        global_core.migrate_global_location_schema(conn)
        element_core.migrate_element_core_schema(conn)
        migrate_blockchain_schema(conn)
        sita_platform_core.migrate_sita_platform_schema(conn)
        import qsi_core

        qsi_core.migrate_qsi_schema(conn)
        try:
            qsi_core.process_pending_karma_awards(conn)
        except sqlite3.Error:
            app.logger.exception("qsi karma award processing failed")
        if elections_are_enabled():
            try:
                election_scheduler.process_election_cycles(
                    conn, send_system_message_fn=send_system_message
                )
            except sqlite3.Error:
                app.logger.exception("election cycle processing failed")
        try:
            qoin_scheduler.run_weekly_settlement_if_due(
                conn,
                hierarchy_resolver=_qoin_hierarchy_resolver,
                notify_fn=send_system_message,
            )
        except sqlite3.Error:
            app.logger.exception("weekly qoin settlement failed")
        try:
            qoin_scheduler.run_monthly_varna_recalc_if_due(conn)
        except sqlite3.Error:
            app.logger.exception("monthly varna recalc failed")
        try:
            qoin_scheduler.run_daily_planetary_update_if_due(conn)
        except sqlite3.Error:
            app.logger.exception("daily planetary update failed")
        try:
            qoin_scheduler.run_akashic_archive_jobs_if_due(conn)
        except sqlite3.Error:
            app.logger.exception("akashic archive jobs failed")
        try:
            qoin_scheduler.run_daily_age_category_update_if_due(
                conn,
                life_stage_from_age_fn=life_stage_from_age,
                compute_age_fn=compute_age,
                notify_fn=send_system_message,
            )
        except sqlite3.Error:
            app.logger.exception("daily age category update failed")
        social_core.ensure_wallet_and_vote_tables(conn)
        social_core.ensure_posts_escalation_columns(conn)
        migrate_posts_deletion_columns(conn)
        conn.commit()
        global _last_escalation_check
        now = time.monotonic()
        if now - _last_escalation_check >= 60:
            _last_escalation_check = now
            _safe_escalate_posts(conn)
    except sqlite3.Error:
        app.logger.exception("before_request schema bootstrap failed")
    except Exception:
        app.logger.exception("before_request bootstrap failed")


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
    village_wallet_qoins = 0
    village_wallet_rupees = 0
    if scope == "village":
        vid = geo_id.strip()
        qoin_core.ensure_wallet(conn, "village", vid)
        village_wallet_qoins = qoin_core.wallet_balance(conn, "village", vid)
        village_wallet_rupees = qoin_core.wallet_rupee_total(conn, "village", vid)
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
        village_wallet_qoins=village_wallet_qoins,
        village_wallet_rupees=village_wallet_rupees,
        location_id=geo_id.strip(),
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
        location_id="IND",
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
    user_row = g.current_user
    payload = request.get_json(silent=True) or {}
    content = str(
        payload.get("content") or request.form.get("content") or ""
    ).strip()

    if not content:
        return jsonify({"error": "Post content cannot be empty"}), 400
    if len(content) > 500:
        return jsonify({"error": "Post content is too long (max 500 characters)"}), 400

    situation = identity_core.user_situation_type(user_row)
    is_global_only = situation == "C"

    if is_global_only:
        country_id = str(user_row["current_country_id"] or "").strip().upper()
        continent_id = str(user_row["current_continent_id"] or "").strip().upper()
        state_id = global_core.user_global_state_id(user_row)
        if not country_id:
            return jsonify(
                {"error": "Your current country is required to create a post"}
            ), 400
        if global_core.country_has_states(conn, country_id) and not state_id:
            return jsonify(
                {"error": "Your state/province is required to create a post"}
            ), 400
        origins = social_core.origins_for_global_user(
            country_id, continent_id, state_id=state_id
        )
        location_id = state_id or country_id
    else:
        if not user_has_full_dashboard(conn, user_row):
            return jsonify(
                {"error": "Posting requires an India birth or present location."}
            ), 403
        location_id = str(user_row["current_location_id"] or "").strip()
        if not location_id:
            return jsonify({"error": "Your current village is required to create a post"}), 400
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
    _safe_escalate_posts(conn)
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
        if global_core.is_global_only_user(user_row) and level == "state":
            gs = global_core.user_global_state_id(user_row)
            if gs and location_id == gs:
                return True, location_id, ""
        if location_id not in allowed_profile_locations:
            return False, location_id, "location_id must be your profile hierarchy"
        scope = infer_geo_scope_from_full_id(conn, location_id)
        if scope != level and not (
            level == "state"
            and global_core.is_global_only_user(user_row)
            and location_id == global_core.user_global_state_id(user_row)
        ):
            return False, location_id, "level and location_id do not match"
    elif level == "country":
        if _geo_table_exists(conn, "country"):
            crow = conn.execute(
                "SELECT id FROM country WHERE id = ?", (location_id,)
            ).fetchone()
            if crow:
                return True, location_id, ""
        user_country = str(user_row["current_country_id"] or "").strip()
        if location_id != user_country:
            return False, location_id, "location_id must match your country"
    elif level == "continent":
        if _geo_table_exists(conn, "continent"):
            conr = conn.execute(
                "SELECT id FROM continent WHERE id = ?", (location_id,)
            ).fetchone()
            if conr:
                return True, location_id, ""
        user_continent = str(user_row["current_continent_id"] or "").strip()
        if location_id != user_continent:
            return False, location_id, "location_id must match your continent"
    elif level == "zone":
        zinfo = user_zone_info(conn, user_row)
        user_zone_id = str(zinfo.get("zone_id") or "").strip()
        if not user_zone_id or location_id != user_zone_id:
            return False, location_id, "location_id must match your India zone"
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
    level is ``personal``, ``personal_history``, ``private_history``, or legacy
    ``personal_*`` prefixes — even if ``current_level = ?`` were mis-bound elsewhere.
    """
    return (
        f" AND (NOT (LOWER(TRIM(COALESCE({alias}.current_level,''))) IN "
        f"('personal','personal_history','private_history')) "
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
    if level == "zone":
        zone_pred, zone_params = user_location_predicate(conn, "zone", location_id)
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
                  AND p.current_level != 'personal'
                  AND p.current_level NOT LIKE 'personal\\_%' ESCAPE '\\'
                  AND ({zone_pred})
                  {never_p}
                  {not_del}
                ORDER BY datetime(p.created_at) DESC, p.id DESC
                LIMIT 100
            """
            params: list[Any] = [voter_private_id, *zone_params]
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
              AND p.current_level != 'personal'
              AND p.current_level NOT LIKE 'personal\\_%' ESCAPE '\\'
              AND ({zone_pred})
              {never_p}
              {not_del}
            ORDER BY datetime(p.created_at) DESC, p.id DESC
            LIMIT 100
        """
        return list(conn.execute(query, tuple([voter_private_id, *zone_params])))

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
                AND p.status = 'frozen'
                AND p.current_level = 'personal_frozen'
              ORDER BY datetime(COALESCE(p.level_end_time, p.created_at)) DESC, p.id DESC
              LIMIT 100
            """,
            (user_private_id, *author_ids),
        )
    )


@app.get("/api/personal_board")
@login_required
@_api_handle_errors
def api_personal_board():
    conn = get_db()
    _ = conn
    _safe_escalate_posts(conn)

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
            sender_name = "Qumanity (System)"
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


def _election_active_zodiac_sign(today: date | None = None) -> str | None:
    active = election_scheduler.sun_sign_for_election_day(today or date.today())
    return str(active[0]) if active else None


def _election_user_sun_sign_matches_cycle(
    user_row: sqlite3.Row, zodiac_sign: str | None
) -> bool:
    if not zodiac_sign:
        return False
    return str(user_row["sun_sign"] or "").strip() == str(zodiac_sign).strip()


def _element_for_zodiac_sign(zodiac_sign: str | None) -> str | None:
    if not zodiac_sign:
        return None
    return ELEMENT_BY_SIGN.get(str(zodiac_sign).strip())


def _election_user_element_matches_cycle(
    user_row: sqlite3.Row, zodiac_sign: str | None
) -> bool:
    if not zodiac_sign:
        return False
    cycle_element = _element_for_zodiac_sign(zodiac_sign)
    user_element = str(user_row["element"] or "").strip()
    return bool(cycle_element and user_element == cycle_element)


def _election_user_can_vote(
    user_row: sqlite3.Row, zodiac_sign: str | None = None
) -> bool:
    if not _election_user_location_match(user_row):
        return False
    sign = zodiac_sign if zodiac_sign is not None else _election_active_zodiac_sign()
    if not sign or not _election_user_element_matches_cycle(user_row, sign):
        return False
    try:
        age = int(user_row["age"])
    except (TypeError, ValueError):
        return False
    return age >= 13


def _election_voting_ineligible_message(
    user_row: sqlite3.Row, zodiac_sign: str | None
) -> str:
    element = _element_for_zodiac_sign(zodiac_sign) or "matching"
    if not _election_user_location_match(user_row):
        return "Elections apply to residents of Rohini Sector‑24 only."
    try:
        age = int(user_row["age"])
    except (TypeError, ValueError):
        age = 0
    if age < 13:
        return "You must be at least 13 years old to vote in village elections."
    if zodiac_sign and not _election_user_element_matches_cycle(user_row, zodiac_sign):
        return (
            f"Voting is open only to {element} sign members for this election."
        )
    return "You are not eligible to vote in this election cycle."


def _election_user_can_nominate(
    user_row: sqlite3.Row, zodiac_sign: str | None = None
) -> bool:
    if not _election_user_location_match(user_row):
        return False
    sign = zodiac_sign if zodiac_sign is not None else _election_active_zodiac_sign()
    if not sign or not _election_user_sun_sign_matches_cycle(user_row, sign):
        return False
    if str(user_row["age_group"] or "").strip() != "Yuvak":
        return False
    return election_scheduler.election_bucket_gender(str(user_row["gender"] or "")) is not None


def _user_account_badges(user_row: sqlite3.Row) -> list[str]:
    badges: list[str] = []
    try:
        at = str(user_row["account_type"] or "").strip()
    except (KeyError, IndexError):
        at = "H_U"
    if at in UPGRADE_ACCOUNT_TYPES:
        badges.append(at)
    try:
        if int(user_row["mentor_level"] or 0) > 0 and "Mentor" not in badges:
            badges.append("Mentor")
        if int(user_row["leader_level"] or 0) > 0 and "Leader" not in badges:
            badges.append("Leader")
        if int(user_row["manager_level"] or 0) > 0 and "Manager" not in badges:
            badges.append("Manager")
        if int(user_row["agent_level"] or 0) > 0 and "Agent" not in badges:
            badges.append("Agent")
    except (KeyError, TypeError, ValueError):
        pass
    return badges


def _is_demo_account_type(account_type: str | None) -> bool:
    return str(account_type or "").strip().upper().startswith(DEMO_ACCOUNT_TYPE_PREFIX)


def _validate_agent_public_id(conn: sqlite3.Connection, agent_public_id: str) -> bool:
    return identity_core.validate_cash_recipient_public_id(conn, agent_public_id)


def _user_karma_index(user_row: sqlite3.Row) -> int:
    try:
        return (
            int(user_row["mentor_level"] or 0)
            + int(user_row["manager_level"] or 0)
            + int(user_row["leader_level"] or 0)
            + int(user_row["agent_level"] or 0)
        )
    except (KeyError, TypeError, ValueError):
        return 0


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
               u.public_id,
               u.age,
               u.age_group,
               u.sun_sign,
               u.mentor_level,
               u.manager_level,
               u.leader_level,
               u.agent_level
        FROM election_candidates c
        JOIN users u ON u.private_id = c.candidate_private_id
        WHERE c.election_cycle_id = ?
          AND c.status = 'approved'
        ORDER BY c.gender, c.id
        """,
        (cycle_id,),
    )
    for r in cur:
        mid = r["manifest"] or ""
        manifest = election_scheduler.parse_manifest(str(mid))
        cand_pid = str(r["candidate_private_id"])
        vote_count = conn.execute(
            """
            SELECT COUNT(*) AS n FROM election_votes
            WHERE election_cycle_id = ? AND candidate_private_id = ?
            """,
            (cycle_id, cand_pid),
        ).fetchone()
        social_core.ensure_wallet(conn, "user", cand_pid)
        wallet_balance = social_core.get_wallet_balance(conn, "user", cand_pid)
        try:
            age = int(r["age"])
        except (TypeError, ValueError):
            age = 0
        age_group = str(r["age_group"] or "")
        if not age_group and age:
            age_group = life_stage_from_age(age)
        out.append(
            {
                "id": int(r["candidate_row_id"]),
                "candidate_private_id": cand_pid,
                "gender": str(r["gender"]),
                "manifest": manifest,
                "status": str(r["status"]),
                "first_name": str(r["first_name"] or ""),
                "last_name": str(r["last_name"] or ""),
                "public_id": str(r["public_id"] or ""),
                "age": age,
                "age_group": age_group,
                "sun_sign": str(r["sun_sign"] or ""),
                "karma_index": _user_karma_index(r),
                "wallet_balance": wallet_balance,
                "vote_count": int(vote_count["n"]) if vote_count else 0,
            }
        )
    return out


def _election_format_date_label(iso_date: str, *, end_of_day: bool = False) -> str:
    raw = (iso_date or "").strip()[:10]
    try:
        d = date.fromisoformat(raw)
    except ValueError:
        return raw or "—"
    time_s = "23:59" if end_of_day else "00:00"
    return f"{d.day} {d.strftime('%b %Y')} {time_s}"


def _election_phase_window_label(phase: str, cycle_row: sqlite3.Row) -> str:
    ph = (phase or "").strip().lower()
    if ph == "nomination":
        start = str(cycle_row["nomination_start"] or "")
        end = str(cycle_row["nomination_end"] or "")
        title = "Nomination"
    elif ph == "voting":
        start = str(cycle_row["voting_start"] or "")
        end = str(cycle_row["voting_end"] or "")
        title = "Voting"
    elif ph == "closed":
        start = str(cycle_row["voting_start"] or "")
        end = str(cycle_row["voting_end"] or "")
        title = "Results / closed"
    else:
        start = str(cycle_row["start_date"] or "")
        end = str(cycle_row["end_date"] or "")
        title = ph.capitalize() or "Cycle"
    if not start and not end:
        return title
    return (
        f"{title}: {_election_format_date_label(start)} – "
        f"{_election_format_date_label(end, end_of_day=True)}"
    )


def _election_status_label(phase: str) -> str:
    labels = {
        "nomination": "Nomination open",
        "voting": "Voting open",
        "closed": "Results announced",
        "upcoming": "Upcoming",
    }
    return labels.get((phase or "").strip().lower(), "Election closed")


def _election_display_from_cycle(cycle_row: sqlite3.Row | None) -> dict[str, Any]:
    if not cycle_row:
        return {
            "status_label": "No active election",
            "phase": None,
            "zodiac_sign": None,
            "current_phase_window": "",
            "next_phase_label": "",
            "next_phase_start": "",
        }
    phase = str(cycle_row["status"] or "")
    zodiac = str(cycle_row["zodiac_sign"] or "")
    next_label = ""
    next_start = ""
    if phase == "nomination":
        next_label = "Voting"
        next_start = str(cycle_row["voting_start"] or "")
    elif phase == "voting":
        next_label = "Results"
        next_start = str(cycle_row["voting_end"] or "")
    next_start_display = (
        _election_format_date_label(next_start) if next_start else ""
    )
    return {
        "status_label": _election_status_label(phase),
        "phase": phase,
        "zodiac_sign": zodiac,
        "current_phase_window": _election_phase_window_label(phase, cycle_row),
        "next_phase_label": next_label,
        "next_phase_start": next_start,
        "next_phase_start_display": next_start_display,
    }


def migrate_admin_user_profile(conn: sqlite3.Connection) -> None:
    """One-time correction for the default admin account."""
    row = conn.execute(
        "SELECT 1 FROM users WHERE private_id = ? COLLATE NOCASE",
        (ADMIN_PRIVATE_ID,),
    ).fetchone()
    if not row:
        legacy = conn.execute(
            "SELECT 1 FROM users WHERE private_id = ? COLLATE NOCASE",
            (LEGACY_ADMIN_PRIVATE_ID,),
        ).fetchone()
        if not legacy:
            return
        identity_core.reassign_user_private_id(
            conn,
            LEGACY_ADMIN_PRIVATE_ID,
            ADMIN_PRIVATE_ID,
            new_public_id=ADMIN_PUBLIC_ID,
        )
    dob = date(1990, 7, 30)
    age = compute_age(dob)
    age_group = life_stage_from_age(age)
    sun = sun_sign_for_date(dob)
    moon = moon_sign_simplified(dob)
    elem = element_for_sun(sun)
    conn.execute(
        """
        UPDATE users
        SET date_of_birth = ?,
            birth_time = ?,
            age = ?,
            age_group = ?,
            sun_sign = ?,
            moon_sign = ?,
            element = ?,
            is_active = 1,
            mentor_level = 1,
            leader_level = 1
        WHERE private_id = ? COLLATE NOCASE
        """,
        (
            dob.isoformat(),
            "07:05",
            age,
            age_group,
            sun,
            moon,
            elem,
            ADMIN_PRIVATE_ID,
        ),
    )
    if qoin_core.wallet_balance(conn, "user", ADMIN_PRIVATE_ID) == 0:
        qoin_core.credit_signup_bonus(conn, ADMIN_PRIVATE_ID)


@app.post("/api/set-language")
def api_set_language():
    from translations import LANGUAGE_META, TRANSLATIONS

    data = request.get_json(silent=True) or {}
    lang = str(data.get("language") or "").strip().lower()
    if not lang:
        return jsonify({"error": "language is required"}), 400
    if lang not in TRANSLATIONS and lang not in LANGUAGE_META:
        return jsonify({"error": "unsupported language"}), 400
    session.permanent = True
    session["preferred_language"] = lang
    session["language_user_choice"] = True
    session.modified = True
    return jsonify({"ok": True, "status": "ok", "language": lang})


@app.post("/api/user/mother-tongue")
@login_required
@_api_handle_errors
def api_user_mother_tongue():
    conn = get_db()
    data = request.get_json(silent=True) or {}
    code = str(data.get("mother_tongue_code") or data.get("code") or "").strip().lower()
    name = str(data.get("mother_tongue_name") or data.get("name") or "").strip()
    if not code:
        conn.execute(
            """
            UPDATE users SET mother_tongue_code = NULL, mother_tongue_name = NULL
            WHERE id = ?
            """,
            (int(g.current_user["id"]),),
        )
        conn.commit()
        return jsonify({"ok": True, "mother_tongue_code": None, "mother_tongue_name": None})
    if not name:
        for ch in language_core.all_language_choices(conn):
            if ch["code"] == code:
                name = ch["name"]
                break
    conn.execute(
        """
        UPDATE users SET mother_tongue_code = ?, mother_tongue_name = ?
        WHERE id = ?
        """,
        (code, name or code, int(g.current_user["id"])),
    )
    conn.commit()
    return jsonify({"ok": True, "mother_tongue_code": code, "mother_tongue_name": name})


@app.get("/api/leadership/<level_type>/<path:location_id>")
@login_required
@_api_handle_errors
def api_leadership_get(level_type: str, location_id: str):
    conn = get_db()
    try:
        payload = leadership_core.get_leadership_for_location(
            conn, level_type, location_id
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    payload["is_admin"] = is_admin_user(g.current_user)
    return jsonify(payload)


@app.post("/api/leadership/appoint")
@login_required
@_api_handle_errors
def api_leadership_appoint():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    return jsonify(
        {
            "error": "Appointments are not available in this prototype phase.",
            "ok": False,
        }
    ), 501


@app.get("/api/election/status")
@login_required
@_api_handle_errors
def api_election_status():
    if not elections_are_enabled():
        return jsonify(
            {
                "elections_enabled": False,
                "paused": True,
                "message": (
                    "Elections are currently paused. They will resume during the "
                    "Gemini month. Please check back later."
                ),
                "phase": "paused",
            }
        )
    conn = get_db()
    user = g.current_user
    uid = str(user["private_id"])
    in_village = _election_user_location_match(user)
    sun = str(user["sun_sign"] or "")
    cycle_row, active_period = _election_cycle_row_for_today(conn)
    active_sign = str(active_period[0]) if active_period else None
    eligible_vote = _election_user_can_vote(user, active_sign)
    eligible_nominate = _election_user_can_nominate(user, active_sign)
    cycle_element = _element_for_zodiac_sign(active_sign)
    user_element = str(user["element"] or "")
    payload: dict[str, Any] = {
        "target_village_id": election_scheduler.TARGET_VILLAGE_ID,
        "user_in_target_village": in_village,
        "user_sun_sign": sun,
        "user_element": user_element,
        "cycle_element": cycle_element,
        "user_age": int(user["age"]) if user["age"] is not None else None,
        "user_age_group": str(user["age_group"] or ""),
        "eligible_for_current_cycle": eligible_vote,
        "eligible_to_vote": eligible_vote,
        "eligible_to_nominate": eligible_nominate,
        "voting_ineligible_message": _election_voting_ineligible_message(
            user, active_sign
        ),
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
    payload["election_display"] = _election_display_from_cycle(cycle_row)
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


@app.get("/api/election/history")
@login_required
def api_election_history():
    """Prototype placeholder — past cycles will be listed here later."""
    if not elections_are_enabled():
        return jsonify(
            {
                "paused": True,
                "past_nominations": [],
                "past_voting_results": [],
                "past_winners": [],
                "message": (
                    "Elections are currently paused. They will resume during the "
                    "Gemini month. Please check back later."
                ),
            }
        )
    return jsonify(
        {
            "past_nominations": [],
            "past_voting_results": [],
            "past_winners": [],
            "message": "No data available",
        }
    )


@app.post("/api/election/nominate")
@login_required
def api_election_nominate():
    if not elections_are_enabled():
        return jsonify(
            {
                "error": (
                    "Elections are currently paused. They will resume during the "
                    "Gemini month. Please check back later."
                )
            }
        ), 403
    conn = get_db()
    user = g.current_user
    cycle_row, active = _election_cycle_row_for_today(conn)
    if not cycle_row or not active:
        return jsonify({"error": "No active election cycle"}), 400
    active_sign = str(active[0])
    if not _election_user_can_nominate(user, active_sign):
        if not _election_user_location_match(user):
            return jsonify({"error": "Elections are for Rohini Sector-24 residents only"}), 403
        if str(user["age_group"] or "").strip() != "Yuvak":
            return jsonify(
                {"error": "Only Yuvak residents (ages 25–49) may submit a nomination"}
            ), 403
        if not _election_user_sun_sign_matches_cycle(user, active_sign):
            return jsonify({"error": "Your sun sign does not match this cycle"}), 403
        bucket = election_scheduler.election_bucket_gender(str(user["gender"] or ""))
        if not bucket:
            return jsonify(
                {"error": "Only Male or Female cohort candidates can stand in this prototype"}
            ), 400
        return jsonify({"error": "You are not eligible to nominate in this cycle"}), 403
    bucket = election_scheduler.election_bucket_gender(str(user["gender"] or ""))
    if not bucket:
        return jsonify(
            {"error": "Only Male or Female cohort candidates can stand in this prototype"}
        ), 400
    st = str(cycle_row["status"] or "")
    if st != "nomination":
        return jsonify({"error": "Nominations are closed"}), 400
    payload = request.get_json(silent=True) or {}
    target_role = str(payload.get("target_role") or payload.get("slot_designation") or "").strip().lower()
    if target_role and not varna_core.can_nominate_for_council(
        conn, str(user["private_id"]), target_role
    ):
        return jsonify(
            {
                "error": (
                    "Your Dharma profile suggests other council roles. "
                    "See eligible roles on your Private Account dashboard."
                ),
                "eligible_roles": varna_core.eligible_roles_for_user(
                    conn, str(user["private_id"])
                ),
            }
        ), 403
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
        return jsonify(
            {
                "error": "You have already submitted a nomination for this zodiac cycle. You cannot submit again."
            }
        ), 400
    manifest = json.dumps({"why_stand": why, "changes": changes}, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO election_candidates (
            election_cycle_id, candidate_private_id, gender, manifest, status
        ) VALUES (?, ?, ?, ?, 'pending')
        """,
        (cid, str(user["private_id"]), bucket, manifest),
    )
    conn.commit()
    return jsonify({"ok": True, "election_cycle_id": cid, "status": "pending"})


def _admin_election_cycle_for_management(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """Resolve the election cycle admins manage (current zodiac month)."""
    cycle_row, _active = _election_cycle_row_for_today(conn)
    if cycle_row:
        return cycle_row
    sign = _election_active_zodiac_sign()
    if not sign:
        return None
    return conn.execute(
        """
        SELECT * FROM election_cycles
        WHERE village_id = ? AND zodiac_sign = ?
        ORDER BY start_date DESC
        LIMIT 1
        """,
        (election_scheduler.TARGET_VILLAGE_ID, sign),
    ).fetchone()


def _admin_nomination_row_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    mid = row["manifest"] or ""
    manifest = election_scheduler.parse_manifest(str(mid))
    why = manifest.get("why_stand") or manifest.get("text") or ""
    changes = manifest.get("changes") or ""
    parts = [p for p in (why, changes) if p]
    try:
        age = int(row["age"]) if row["age"] is not None else None
    except (TypeError, ValueError):
        age = None
    age_group = str(row["age_group"] or "")
    if not age_group and age is not None:
        age_group = life_stage_from_age(age)
    return {
        "id": int(row["candidate_row_id"]),
        "election_cycle_id": int(row["election_cycle_id"]),
        "candidate_private_id": str(row["candidate_private_id"]),
        "gender": str(row["gender"] or ""),
        "manifest": manifest,
        "manifest_text": "\n\n".join(parts),
        "why_stand": why,
        "changes": changes,
        "status": str(row["status"] or ""),
        "rejection_reason": str(row["rejection_reason"] or "")
        if row["rejection_reason"]
        else "",
        "first_name": str(row["first_name"] or ""),
        "last_name": str(row["last_name"] or ""),
        "public_id": str(row["public_id"] or ""),
        "sun_sign": str(row["sun_sign"] or ""),
        "zodiac_sign": str(row["cycle_zodiac"] or row["zodiac_sign"] or ""),
        "age": age,
        "age_group": age_group,
        "created_at": str(row["created_at"] or ""),
    }


def _admin_nominations_list_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    cycle_row = _admin_election_cycle_for_management(conn)
    if not cycle_row:
        return {"nominations": [], "cycle": None}
    cid = int(cycle_row["id"])
    status_filter = (request.args.get("status") or "all").strip().lower()
    sql = """
        SELECT c.id AS candidate_row_id, c.election_cycle_id, c.candidate_private_id,
               c.gender, c.manifest, c.status, c.created_at, c.rejection_reason,
               u.first_name, u.last_name, u.public_id, u.age, u.age_group, u.sun_sign,
               ec.zodiac_sign AS cycle_zodiac
        FROM election_candidates c
        JOIN users u ON u.private_id = c.candidate_private_id
        JOIN election_cycles ec ON ec.id = c.election_cycle_id
        WHERE c.election_cycle_id = ?
    """
    params: list[Any] = [cid]
    if status_filter and status_filter != "all":
        sql += " AND c.status = ?"
        params.append(status_filter)
    sql += " ORDER BY c.created_at ASC, c.id ASC"
    cur = conn.execute(sql, tuple(params))
    all_rows = [_admin_nomination_row_dict(conn, r) for r in cur]
    pending = [n for n in all_rows if n["status"] == "pending"]
    approved = [n for n in all_rows if n["status"] == "approved"]
    if status_filter == "pending":
        listed = pending
    elif status_filter == "approved":
        listed = approved
    else:
        listed = pending + approved
    return {
        "cycle": {
            "id": cid,
            "zodiac_sign": str(cycle_row["zodiac_sign"]),
            "status": str(cycle_row["status"]),
        },
        "nominations": listed,
        "pending": pending,
        "approved": approved,
    }


@app.get("/api/admin/nominations/pending")
@app.get("/api/admin/nominations")
@admin_required
def api_admin_nominations_list():
    conn = get_db()
    return jsonify(_admin_nominations_list_payload(conn))


@app.post("/api/admin/nomination/approve/<int:candidate_id>")
@admin_required
def api_admin_nomination_approve(candidate_id: int):
    conn = get_db()
    cycle_row = _admin_election_cycle_for_management(conn)
    if not cycle_row:
        return jsonify({"error": "No active election cycle"}), 400
    cid = int(cycle_row["id"])
    row = conn.execute(
        """
        SELECT * FROM election_candidates
        WHERE id = ? AND election_cycle_id = ? AND status IN ('pending', 'rejected')
        """,
        (candidate_id, cid),
    ).fetchone()
    if not row:
        return jsonify({"error": "Nomination not found or already approved"}), 404
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE election_candidates
        SET status = 'approved', reviewed_at = ?, rejection_reason = NULL
        WHERE id = ?
        """,
        (now, candidate_id),
    )
    cand_pid = str(row["candidate_private_id"])
    zodiac = str(cycle_row["zodiac_sign"] or "")
    body = (
        f"Congratulations! Your nomination for {zodiac} council member has been "
        "approved. You will appear on the voting ballot."
    )
    send_system_message(
        conn, cand_pid, "Your nomination has been approved", body
    )
    conn.commit()
    return jsonify({"ok": True, "candidate_id": candidate_id, "status": "approved"})


@app.post("/api/admin/nomination/reject/<int:candidate_id>")
@admin_required
def api_admin_nomination_reject(candidate_id: int):
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return jsonify({"error": "Rejection reason is required"}), 400
    cycle_row = _admin_election_cycle_for_management(conn)
    if not cycle_row:
        return jsonify({"error": "No active election cycle"}), 400
    cid = int(cycle_row["id"])
    row = conn.execute(
        """
        SELECT * FROM election_candidates
        WHERE id = ? AND election_cycle_id = ? AND status IN ('pending', 'approved')
        """,
        (candidate_id, cid),
    ).fetchone()
    if not row:
        return jsonify({"error": "Nomination not found or already rejected"}), 404
    if str(row["status"] or "") == "rejected":
        return jsonify({"error": "Nomination already rejected"}), 400
    cand_pid = str(row["candidate_private_id"])
    zodiac = str(cycle_row["zodiac_sign"] or "")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        UPDATE election_candidates
        SET status = 'rejected', rejection_reason = ?, reviewed_at = ?
        WHERE id = ?
        """,
        (reason, now, candidate_id),
    )
    body = f"Your nomination was not approved.\n\nReason: {reason}"
    send_system_message(conn, cand_pid, "Nomination Rejected", body)
    conn.commit()
    return jsonify({"ok": True, "candidate_id": candidate_id, "status": "rejected"})


@app.post("/api/admin/nomination/edit_manifest/<int:candidate_id>")
@admin_required
def api_admin_nomination_edit_manifest(candidate_id: int):
    conn = get_db()
    cycle_row = _admin_election_cycle_for_management(conn)
    if not cycle_row:
        return jsonify({"error": "No active election cycle"}), 400
    cid = int(cycle_row["id"])
    row = conn.execute(
        """
        SELECT * FROM election_candidates
        WHERE id = ? AND election_cycle_id = ?
        """,
        (candidate_id, cid),
    ).fetchone()
    if not row:
        return jsonify({"error": "Nomination not found"}), 404
    payload = request.get_json(silent=True) or {}
    why = str(payload.get("why_stand") or payload.get("manifest_why") or "").strip()
    changes = str(payload.get("changes") or payload.get("manifest_changes") or "").strip()
    if not why and not changes:
        existing = election_scheduler.parse_manifest(str(row["manifest"] or ""))
        why = str(existing.get("why_stand") or existing.get("text") or "").strip()
        changes = str(existing.get("changes") or "").strip()
    if not why:
        return jsonify({"error": "Manifest text (why_stand) is required"}), 400
    manifest = json.dumps(
        {"why_stand": why, "changes": changes}, ensure_ascii=False
    )
    conn.execute(
        "UPDATE election_candidates SET manifest = ? WHERE id = ?",
        (manifest, candidate_id),
    )
    conn.commit()
    return jsonify({"ok": True, "candidate_id": candidate_id})


@app.post("/api/admin/nomination/remove/<int:candidate_id>")
@admin_required
def api_admin_nomination_remove(candidate_id: int):
    conn = get_db()
    cycle_row = _admin_election_cycle_for_management(conn)
    if not cycle_row:
        return jsonify({"error": "No active election cycle"}), 400
    cid = int(cycle_row["id"])
    row = conn.execute(
        """
        SELECT * FROM election_candidates
        WHERE id = ? AND election_cycle_id = ?
        """,
        (candidate_id, cid),
    ).fetchone()
    if not row:
        return jsonify({"error": "Nomination not found"}), 404
    payload = request.get_json(silent=True) or {}
    notify = payload.get("notify", True) is not False
    cand_pid = str(row["candidate_private_id"])
    zodiac = str(cycle_row["zodiac_sign"] or "")
    conn.execute("DELETE FROM election_candidates WHERE id = ?", (candidate_id,))
    if notify:
        body = (
            f"Your nomination for the {zodiac} Quantum Punch village council election "
            "was removed by an administrator."
        )
        send_system_message(conn, cand_pid, "Nomination Removed", body)
    conn.commit()
    return jsonify({"ok": True, "candidate_id": candidate_id, "removed": True})


@app.get("/api/user/private_details")
@admin_required
def api_user_private_details():
    private_id = (request.args.get("private_id") or "").strip()
    if not private_id:
        return jsonify({"error": "private_id is required"}), 400
    conn = get_db()
    user_row = conn.execute(
        "SELECT * FROM users WHERE private_id = ?",
        (private_id,),
    ).fetchone()
    if not user_row:
        return jsonify({"error": "User not found"}), 404
    try:
        age = int(user_row["age"])
    except (TypeError, ValueError):
        age = 0
    life_stage = life_stage_from_age(age)
    birth_vid = str(user_row["birth_location_id"] or "").strip()
    current_vid = str(user_row["current_location_id"] or "").strip()
    birth_hier = current_location_hierarchy(conn, birth_vid) if birth_vid else []
    current_hier = current_location_hierarchy(conn, current_vid) if current_vid else []

    def hierarchy_dict(hier: list[dict[str, str]]) -> dict[str, dict[str, str]]:
        return {
            str(item["scope"]): {
                "id": str(item["id"] or ""),
                "name": str(item["name"] or ""),
            }
            for item in hier
        }

    social_core.ensure_wallet(conn, "user", private_id)
    wallet_balance = social_core.get_wallet_balance(conn, "user", private_id)
    tx_rows = conn.execute(
        """
        SELECT id, amount, reason, created_at
        FROM qoin_transactions
        WHERE user_private_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT 10
        """,
        (private_id,),
    ).fetchall()
    recent_transactions = [
        {
            "id": int(tr["id"]),
            "amount": int(tr["amount"]),
            "reason": str(tr["reason"] or ""),
            "created_at": str(tr["created_at"] or ""),
        }
        for tr in tx_rows
    ]
    account_type = "H_U"
    try:
        account_type = str(user_row["account_type"] or "H_U")
    except (KeyError, IndexError):
        pass
    return jsonify(
        {
            "first_name": str(user_row["first_name"] or ""),
            "last_name": str(user_row["last_name"] or ""),
            "full_name": (
                f'{user_row["first_name"] or ""} {user_row["last_name"] or ""}'.strip()
            ),
            "private_id": private_id,
            "public_id": str(user_row["public_id"] or ""),
            "gender": str(user_row["gender"] or ""),
            "age": age,
            "age_group": str(user_row["age_group"] or life_stage),
            "life_stage": life_stage,
            "sun_sign": str(user_row["sun_sign"] or ""),
            "element": str(user_row["element"] or ""),
            "karma_index": _user_karma_index(user_row),
            "account_type": account_type,
            "is_admin": bool(int(user_row["is_admin"] or 0)),
            "birth_location_label": location_display_label(conn, birth_vid)
            if birth_vid
            else "",
            "current_location_label": location_display_label(conn, current_vid)
            if current_vid
            else "",
            "birth_location_hierarchy": hierarchy_dict(birth_hier),
            "current_location_hierarchy": hierarchy_dict(current_hier),
            "wallet_balance": wallet_balance,
            "recent_transactions": recent_transactions,
        }
    )


def _location_members_for_scope(
    conn: sqlite3.Connection, location_type: str, location_id: str
) -> tuple[str, list[dict[str, Any]]]:
    lt = location_type.strip().lower()
    lid = (location_id or "").strip()
    allowed_admin_scopes = frozenset(
        {"earth", "continent", "country", "zone", "state", "district", "tehsil", "village", "india"}
    )
    if lt not in allowed_admin_scopes:
        raise ValueError("invalid location scope")
    if lt == "india":
        if lid.upper() != "IND":
            raise ValueError("invalid India scope id")
        pred, tup = _indian_users_predicate(conn)
        page_title = "India (national)"
    else:
        tbl = GEO_ROUTE_TABLE.get(lt)
        if not tbl or not _geo_table_exists(conn, tbl):
            raise ValueError("location table missing")
        if conn.execute(f"SELECT 1 FROM {tbl} WHERE id = ?", (lid,)).fetchone() is None:
            raise ValueError("location not found")
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
    return page_title, members


@app.get("/api/admin/location_members")
@admin_required
def api_admin_location_members_json():
    conn = get_db()
    lt = (request.args.get("location_type") or "village").strip().lower()
    lid = (request.args.get("location_id") or "").strip()
    if not lid:
        user_row = g.current_user
        lid = str(user_row["current_location_id"] or "").strip()
        if not lid:
            return jsonify({"error": "No current village for this user"}), 400
        lt = "village"
    try:
        page_title, members = _location_members_for_scope(conn, lt, lid)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg:
            return jsonify({"error": "Location not found"}), 404
        return jsonify({"error": msg}), 400
    return jsonify(
        {
            "location_type": lt,
            "location_id": lid,
            "location_title": page_title,
            "members": members,
        }
    )


@app.post("/api/election/vote")
@login_required
def api_election_vote():
    if not elections_are_enabled():
        return jsonify(
            {
                "error": (
                    "Elections are currently paused. They will resume during the "
                    "Gemini month. Please check back later."
                )
            }
        ), 403
    conn = get_db()
    user = g.current_user
    uid = str(user["private_id"])
    if _account_has_limited_access(user):
        st = _user_account_status(user)
        msg = (
            "Account pending verification. Voting is limited until verified."
            if st == "pending_verification"
            else "Verification failed. Retry your donation to unlock voting."
        )
        return jsonify({"error": msg}), 403
    cycle_row, active = _election_cycle_row_for_today(conn)
    if not cycle_row or not active:
        return jsonify({"error": "No active election cycle"}), 400
    active_sign = str(active[0])
    if not _election_user_can_vote(user, active_sign):
        if not _election_user_location_match(user):
            return jsonify({"error": "Only village residents may vote"}), 403
        try:
            age = int(user["age"])
        except (TypeError, ValueError):
            age = -1
        if age < 13:
            return jsonify({"error": "You must be at least 13 years old to vote"}), 403
        if not _election_user_sun_sign_matches_cycle(user, active_sign):
            return jsonify({"error": "Your sun sign does not match this cycle"}), 403
        return jsonify({"error": "You are not eligible to vote in this cycle"}), 403
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
          AND status = 'approved'
        """,
        (cid, cand_pid),
    ).fetchone()
    if not target:
        return jsonify({"error": "Candidate not found or not approved"}), 404
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
    rewards_activated = donation_core.activate_rewards(
        conn, uid, notify_fn=send_system_message
    )
    conn.commit()
    return jsonify({"ok": True, "rewards_activated": rewards_activated})


@app.get("/api/election/results")
@login_required
def api_election_results():
    if not elections_are_enabled():
        return jsonify({"paused": True, "cycles": []})
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
    if not elections_are_enabled():
        return jsonify(
            {
                "paused": True,
                "king": None,
                "queen": None,
                "nayak": None,
                "nayika": None,
                "members": [],
                "message": (
                    "Elections are currently paused. They will resume during the "
                    "Gemini month. Please check back later."
                ),
            }
        )
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
@_api_handle_errors
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
    ).strip() or str(_row_get(g.current_user, "public_id", "A user") or "A user")
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
    ).strip() or str(_row_get(g.current_user, "public_id", "User") or "User")
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


@app.get("/api/user/education")
@login_required
def api_user_education_get():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    row = conn.execute(
        "SELECT * FROM user_education WHERE user_private_id = ?", (pid,)
    ).fetchone()
    return jsonify({"education": _education_row_to_dict(row)})


@app.get("/api/user/work")
@login_required
def api_user_work_get():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    row = conn.execute(
        "SELECT * FROM user_work WHERE user_private_id = ?", (pid,)
    ).fetchone()
    return jsonify({"work": _work_row_to_dict(row)})


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


@app.get("/api/wallet/balance")
@login_required
def api_wallet_balance():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    qoin_core.ensure_wallet(conn, "user", pid)
    bal = qoin_core.wallet_balance(conn, "user", pid)
    rupees = qoin_core.wallet_rupee_total(conn, "user", pid)
    return jsonify(
        {
            "balance_qoins": bal,
            "karma_points": bal,
            "total_rupees": rupees,
            "coins": _user_wallet_coin_breakdown(conn, pid),
        }
    )


def _user_wallet_coin_breakdown(conn: sqlite3.Connection, pid: str) -> list[dict[str, Any]]:
    coins = qoin_core.wallet_breakdown(conn, "user", pid)
    return [
        {"rupee_value": int(c["denom"]), "count": int(c["count"])}
        for c in coins
    ]


@app.post("/api/karma/donate")
@app.post("/api/qoin/donate")
@login_required
def api_qoin_donate():
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        amount = int(payload.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer (rupees)"}), 400
    if amount < 1 or amount > 500:
        return jsonify({"error": "Donation must be between ₹1 and ₹500"}), 400
    method = str(payload.get("method") or "upi").strip().lower()
    if method not in ("cash", "upi"):
        return jsonify({"error": "method must be cash or upi"}), 400
    agent_id = str(payload.get("agent_id") or "").strip()
    if method == "cash":
        if not agent_id:
            return jsonify({"error": "Agent Account ID is required for cash donations"}), 400
        if not _validate_agent_public_id(conn, agent_id):
            return jsonify(
                {"error": "Account ID must belong to an Agent or Admin account"}
            ), 400
    pid = str(g.current_user["private_id"])
    village_id = str(g.current_user["current_location_id"] or "").strip() or None
    try:
        result = qoin_core.process_donation(
            conn,
            donor_private_id=pid,
            amount_rupees=amount,
            village_id=village_id,
            method=method,
            agent_public_id=agent_id if method == "cash" else None,
        )
        conn.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **result})


@app.get("/api/karma/transactions")
@app.get("/api/qoin/transactions")
@login_required
def api_qoin_transactions():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    try:
        limit = min(int(request.args.get("limit") or 50), 100)
    except (TypeError, ValueError):
        limit = 50
    return jsonify({"transactions": qoin_core.user_transactions(conn, pid, limit=limit)})


@app.get("/api/karma/statements")
@app.get("/api/qoin/statements")
@login_required
def api_qoin_statements_list():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    return jsonify({"statements": qoin_core.list_weekly_statements(conn, pid)})


@app.get("/api/karma/statements/<int:statement_id>")
@app.get("/api/qoin/statements/<int:statement_id>")
@login_required
def api_qoin_statement_detail(statement_id: int):
    conn = get_db()
    pid = str(g.current_user["private_id"])
    stmt = qoin_core.get_weekly_statement(conn, pid, statement_id=statement_id)
    if not stmt:
        return jsonify({"error": "Statement not found"}), 404
    return jsonify(stmt)


@app.get("/api/karma/statements/<int:statement_id>/html")
@app.get("/api/qoin/statements/<int:statement_id>/html")
@login_required
def api_qoin_statement_html(statement_id: int):
    conn = get_db()
    pid = str(g.current_user["private_id"])
    stmt = qoin_core.get_weekly_statement(conn, pid, statement_id=statement_id)
    if not stmt:
        return "Statement not found", 404
    html = qoin_core.statement_html_report(stmt)
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.get("/api/karma/pending")
@app.get("/api/qoin/pending")
@login_required
def api_qoin_pending_summary():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    summary = qoin_core.pending_summary(conn)
    karma = qoin_core.user_pending_karma(conn, pid)
    return jsonify({**summary, "karma_pending": karma})


@app.post("/api/karma/commercial")
@app.post("/api/qoin/commercial")
@login_required
def api_qoin_commercial():
    conn = get_db()
    if not user_in_indian_village(conn, g.current_user):
        return jsonify({"error": "Commerce is available only in Indian villages"}), 403
    payload = request.get_json(silent=True) or {}
    try:
        amount = int(payload.get("amount_rupees") or payload.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "amount_rupees must be an integer"}), 400
    seller = str(payload.get("seller_private_id") or "").strip()
    if amount <= 0 or not seller:
        return jsonify({"error": "seller_private_id and positive amount required"}), 400
    pid = str(g.current_user["private_id"])
    if seller == pid:
        return jsonify({"error": "Cannot trade with yourself"}), 400
    txid = qoin_core.record_commercial_transaction(
        conn,
        buyer_private_id=pid,
        seller_private_id=seller,
        amount_rupees=amount,
        description=str(payload.get("description") or ""),
    )
    conn.commit()
    return jsonify({"ok": True, "transaction_id": txid, "pending": True})


@app.post("/api/karma/record")
@app.post("/api/karma/karma")
@app.post("/api/qoin/karma")
@login_required
def api_qoin_karma_record():
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    action_code = str(payload.get("action_code") or "").strip()
    if not action_code:
        return jsonify({"error": "action_code is required"}), 400
    pid = str(g.current_user["private_id"])
    try:
        result = qoin_core.record_karma_action(
            conn,
            user_private_id=pid,
            action_code=action_code,
            description=str(payload.get("description") or ""),
            verified=bool(payload.get("verified", True)),
        )
        conn.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **result})


@app.get("/api/karma/types")
@app.get("/api/qoin/karma/types")
@login_required
def api_qoin_karma_types():
    conn = get_db()
    return jsonify({"actions": qoin_core.karma_action_types_list(conn)})


def _public_base_url() -> str:
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return config.DEFAULT_PUBLIC_URL


def _razorpay_client():
    try:
        import razorpay
    except ImportError:
        return None
    key_id = getattr(config, "RAZORPAY_KEY_ID", "") or ""
    key_secret = getattr(config, "RAZORPAY_KEY_SECRET", "") or ""
    if not key_id or not key_secret:
        return None
    return razorpay.Client(auth=(key_id, key_secret))


def _create_razorpay_order(amount_rupees: int, *, receipt: str = "") -> dict[str, Any]:
    client = _razorpay_client()
    if client is None:
        raise ValueError("Payment gateway is not configured")
    order_data = {
        "amount": int(amount_rupees) * 100,
        "currency": "INR",
        "payment_capture": 1,
        "receipt": receipt or f"donation-{secrets.token_hex(6)}",
    }
    return client.order.create(data=order_data)


_MERCHANT_UPI_VPA_CACHE: str = ""


def _clean_env_value(value: str) -> str:
    """Strip whitespace and surrounding quotes from env values."""
    v = (value or "").strip()
    while len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
        v = v[1:-1].strip()
    return v


def _mask_secret(value: str, visible: int = 4) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= visible:
        return "*" * len(v)
    return v[:visible] + "…" + f"({len(v)} chars)"


def _parse_upi_vpa_from_uri(upi_uri: str) -> str:
    uri = (upi_uri or "").strip()
    if not uri or "?" not in uri:
        return ""
    query = uri.split("?", 1)[1]
    for part in query.split("&"):
        if part.startswith("pa="):
            return unquote(part[3:]).strip()
    return ""


def _discover_razorpay_upi_vpa(client: Any) -> str:
    """Create a probe QR via Razorpay and read merchant VPA from image_content."""
    try:
        qr = client.qrcode.create(
            {
                "type": "upi_qr",
                "name": "QumanityProbe",
                "usage": "single_use",
                "fixed_amount": True,
                "payment_amount": 100,
                "description": "UPI VPA discovery",
                "close_by": int(time.time()) + 900,
            }
        )
        content = str(qr.get("image_content") or "").strip()
        vpa = _parse_upi_vpa_from_qr_response(qr) or _parse_upi_vpa_from_uri(content)
        if vpa:
            app.logger.info("Discovered merchant UPI VPA from Razorpay: %s", vpa)
        return vpa
    except Exception as exc:
        app.logger.warning("Could not discover UPI VPA from Razorpay: %s", exc)
        return ""


def _resolve_merchant_upi_vpa() -> tuple[str, str]:
    """Return merchant UPI VPA and source label. Always returns a usable VPA."""
    global _MERCHANT_UPI_VPA_CACHE
    for env_name in (
        "DONATION_UPI_VPA",
        "RAZORPAY_UPI_VPA",
        "UPI_VPA",
        "MERCHANT_UPI_VPA",
    ):
        vpa = _clean_env_value(os.environ.get(env_name, ""))
        if vpa and "@" in vpa:
            if vpa.lower() in _PLACEHOLDER_UPI_VPAS:
                app.logger.warning(
                    "%s is a placeholder (%s); trying Razorpay discovery",
                    env_name,
                    vpa,
                )
            elif _validate_upi_vpa(vpa):
                return vpa, env_name
            else:
                app.logger.warning("Invalid %s format: %s", env_name, vpa)

    vpa = _clean_env_value(getattr(config, "DONATION_UPI_VPA", ""))
    if vpa and "@" in vpa and vpa.lower() not in _PLACEHOLDER_UPI_VPAS and _validate_upi_vpa(vpa):
        return vpa, "config_module"

    if _MERCHANT_UPI_VPA_CACHE and "@" in _MERCHANT_UPI_VPA_CACHE:
        return _MERCHANT_UPI_VPA_CACHE, "cache"

    client = _razorpay_client()
    if client is not None:
        discovered = _discover_razorpay_upi_vpa(client)
        if discovered and "@" in discovered:
            _MERCHANT_UPI_VPA_CACHE = discovered
            return discovered, "razorpay_discover"

    fallback = _clean_env_value(getattr(config, "UPI_VPA_FALLBACK", ""))
    if fallback and "@" in fallback and _validate_upi_vpa(fallback):
        app.logger.warning("Using UPI_VPA_FALLBACK: %s", fallback)
        return fallback, "fallback_env"

    app.logger.error(
        "No valid DONATION_UPI_VPA in environment. Set your real Razorpay merchant UPI ID "
        "(Razorpay Dashboard → Settings → UPI)."
    )
    placeholder = "merchant@razorpay"
    return placeholder, "builtin_default"


def _razorpay_upi_uri_for_donation(amount_paise: int, donation_id: int) -> tuple[str, str]:
    """Fetch NPCI-compatible UPI URI from Razorpay (best compatibility with UPI apps)."""
    client = _razorpay_client()
    if client is None:
        return "", ""
    txn_ref = f"QUM{donation_id}"
    try:
        qr = client.qrcode.create(
            {
                "type": "upi_qr",
                "name": "QumanityDonation",
                "usage": "single_use",
                "fixed_amount": True,
                "payment_amount": int(amount_paise),
                "description": f"Donation {txn_ref}",
                "close_by": int(time.time()) + 900,
                "notes": {"donation_id": str(donation_id)},
            }
        )
        content = str(qr.get("image_content") or "").strip()
        qr_id = str(qr.get("id") or "").strip()
        if content.startswith("upi://"):
            return content, qr_id
    except Exception as exc:
        app.logger.warning("Razorpay UPI URI fetch failed: %s", exc)
    return "", ""


def _generate_upi_qr_simple(amount_rupees: float, donation_id: int) -> dict[str, Any]:
    """
    Direct static UPI QR — encodes upi://pay locally for UPI apps.
    """
    vpa, vpa_source = _resolve_merchant_upi_vpa()
    amount_paise = int(round(float(amount_rupees) * 100))
    txn_ref = f"QUM{donation_id}"
    qr_id = ""

    razorpay_uri, razorpay_qr_id = _razorpay_upi_uri_for_donation(amount_paise, donation_id)
    if razorpay_uri:
        upi_uri = razorpay_uri
        qr_id = razorpay_qr_id
        vpa_from_uri = _parse_upi_vpa_from_uri(razorpay_uri)
        if vpa_from_uri and _validate_upi_vpa(vpa_from_uri):
            vpa = vpa_from_uri
        vpa_source = "razorpay_image_content"
    else:
        if not _validate_upi_vpa(vpa):
            raise ValueError(f"Invalid UPI VPA: {vpa!r}")
        upi_uri = _build_upi_pay_uri(
            vpa,
            amount_rupees,
            payee_name="Qumanity",
            transaction_note=f"Donation {txn_ref}",
            transaction_ref=txn_ref,
        )

    app.logger.info(
        "UPI QR donation=%s vpa_source=%s uri=%s",
        donation_id,
        vpa_source,
        upi_uri,
    )
    qr_b64 = _generate_upi_qr_base64(upi_uri)
    return {
        "qr_id": qr_id,
        "qr_image_base64": qr_b64,
        "upi_vpa": vpa,
        "upi_uri": upi_uri,
        "transaction_ref": txn_ref,
        "vpa_source": vpa_source,
        "vpa_valid": _validate_upi_vpa(vpa),
        "amount": amount_rupees,
        "vpa_is_placeholder": vpa.lower() in _PLACEHOLDER_UPI_VPAS,
    }


def _get_donation_upi_vpa(client: Any | None = None) -> str:
    """Resolve merchant UPI VPA from env/config or Razorpay API."""
    global _MERCHANT_UPI_VPA_CACHE

    for env_name in (
        "DONATION_UPI_VPA",
        "RAZORPAY_UPI_VPA",
        "UPI_VPA",
        "MERCHANT_UPI_VPA",
    ):
        vpa = _clean_env_value(os.environ.get(env_name, ""))
        if vpa:
            app.logger.info("Using %s from environment (%d chars)", env_name, len(vpa))
            _MERCHANT_UPI_VPA_CACHE = vpa
            return vpa

    vpa = _clean_env_value(getattr(config, "DONATION_UPI_VPA", ""))
    if vpa:
        _MERCHANT_UPI_VPA_CACHE = vpa
        return vpa

    if _MERCHANT_UPI_VPA_CACHE:
        return _MERCHANT_UPI_VPA_CACHE

    if client is None:
        client = _razorpay_client()
    if client is not None:
        discovered = _discover_razorpay_upi_vpa(client)
        if discovered:
            _MERCHANT_UPI_VPA_CACHE = discovered
            return discovered

    return ""


def _generate_upi_qr_base64(upi_uri: str) -> str:
    """Generate PNG QR as base64; raises with actionable error if libraries missing."""
    qr_b64 = referral_core.generate_qr_base64(upi_uri)
    if qr_b64:
        return qr_b64
    try:
        import base64
        from io import BytesIO

        import qrcode

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(upi_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:
        app.logger.exception("UPI QR image generation failed")
        raise ValueError(
            f"Could not generate QR image: {exc}. "
            "Ensure Pillow is installed (requirements: Pillow, qrcode[pil])."
        ) from exc


def _validate_upi_vpa(vpa: str) -> bool:
    """Validate UPI VPA format (user@psp)."""
    v = (vpa or "").strip()
    if not v or " " in v or "@" not in v:
        return False
    parts = v.split("@")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return False
    return bool(re.match(r"^[A-Za-z0-9._-]+@[A-Za-z0-9][A-Za-z0-9.-]*$", v))


_PLACEHOLDER_UPI_VPAS = frozenset(
    {
        "merchant@razorpay",
        "yourmerchant@razorpay",
        "donation@razorpay",
        "qumanity@razorpay",
    }
)

# Razorpay test VPAs work in Checkout / Payment Links, not PhonePe/GPay static QR scan.
_STATIC_QR_UNRELIABLE_VPAS = frozenset(
    {
        "success@razorpay",
        "failure@razorpay",
    }
)


def _static_qr_scan_warning(vpa: str, vpa_source: str, used_razorpay_uri: bool) -> str | None:
    if used_razorpay_uri:
        return None
    vpa_lower = (vpa or "").strip().lower()
    if vpa_lower in _PLACEHOLDER_UPI_VPAS:
        return (
            "QR uses a placeholder VPA — set DONATION_UPI_VPA to your real merchant UPI ID, "
            "or use Pay with UPI Link instead."
        )
    if vpa_lower in _STATIC_QR_UNRELIABLE_VPAS:
        return (
            "Static QR with success@razorpay often fails in PhonePe / GPay / Paytm. "
            "Use Pay with UPI Link for reliable test payments."
        )
    if vpa_source in ("builtin_default", "fallback_env"):
        return "Use Pay with UPI Link if QR scan fails in your UPI app."
    return None


def _format_upi_amount(amount_rupees: float) -> str:
    """Format amount for UPI deep links (NPCI: rupees as decimal string)."""
    amount = round(float(amount_rupees), 2)
    if abs(amount - int(amount)) < 0.001:
        return str(int(amount))
    return f"{amount:.2f}"


def _build_upi_pay_uri(
    vpa: str,
    amount_rupees: float,
    *,
    payee_name: str = "Qumanity",
    transaction_note: str = "",
    transaction_ref: str = "",
) -> str:
    """
    Build a UPI deep link for PhonePe / GPay / Paytm.

    Critical: keep `@` literal in `pa` — encoding as %40 breaks most UPI apps.
    """
    vpa = (vpa or "").strip().lower()
    if not _validate_upi_vpa(vpa):
        raise ValueError(f"Invalid UPI VPA format: {vpa!r}")

    params: list[str] = [f"pa={vpa}"]

    pn = (payee_name or "").strip()
    if pn:
        params.append(f"pn={quote(pn, safe='')}")

    if amount_rupees > 0:
        params.append(f"am={_format_upi_amount(amount_rupees)}")

    params.append("cu=INR")

    tn = (transaction_note or "").strip()
    if tn:
        tn = tn[:80]
        params.append(f"tn={quote(tn, safe='')}")

    tr = re.sub(r"[^A-Za-z0-9]", "", (transaction_ref or "").strip())[:35]
    if tr:
        params.append(f"tr={tr}")

    return "upi://pay?" + "&".join(params)


def _parse_upi_vpa_from_qr_response(qr: dict[str, Any]) -> str:
    """Extract merchant VPA from Razorpay QR `image_content` UPI URI."""
    content = str(qr.get("image_content") or "").strip()
    if not content or "?" not in content:
        return ""
    query = content.split("?", 1)[1]
    for part in query.split("&"):
        if part.startswith("pa="):
            return unquote(part[3:]).strip()
    return ""


def _create_direct_upi_qr_for_donation(
    order_id: str,
    amount_paise: int,
    donation_id: int,
) -> dict[str, Any]:
    """Backward-compatible wrapper — always uses simple static UPI QR."""
    del order_id  # Razorpay order is optional; QR does not depend on it.
    return _generate_upi_qr_simple(int(amount_paise) / 100.0, donation_id)


def _verify_razorpay_payment(
    payment_id: str, order_id: str, signature: str
) -> None:
    client = _razorpay_client()
    if client is None:
        raise ValueError("Payment gateway is not configured")
    params_dict = {
        "razorpay_payment_id": payment_id,
        "razorpay_order_id": order_id,
        "razorpay_signature": signature,
    }
    client.utility.verify_payment_signature(params_dict)


@app.get("/api/referral/stats")
@login_required
def api_referral_stats():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    stats = referral_core.get_referral_stats(conn, pid)
    base = _public_base_url()
    reg_url = referral_core.build_registration_url(base, stats["referral_code"])
    qr = referral_core.generate_qr_base64(reg_url)
    return jsonify(
        {
            **stats,
            "registration_url": reg_url,
            "qr_code_base64": qr,
        }
    )


@app.post("/api/referral/share")
@login_required
def api_referral_share():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    share_type = str(payload.get("share_type") or "").strip().lower()
    if not share_type:
        return jsonify({"error": "share_type is required"}), 400
    referral_core.log_share(conn, pid, share_type)
    conn.commit()
    return jsonify({"ok": True})


@app.get("/api/referral/leaderboard")
@login_required
def api_referral_leaderboard():
    conn = get_db()
    limit = request.args.get("limit", 10, type=int)
    rows = referral_core.get_leaderboard(conn, limit=limit or 10)
    return jsonify({"leaderboard": rows})


@app.get("/api/referral/generate-qr")
@login_required
def api_referral_generate_qr():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    stats = referral_core.get_referral_stats(conn, pid)
    base = _public_base_url()
    reg_url = referral_core.build_registration_url(base, stats["referral_code"])
    qr = referral_core.generate_qr_base64(reg_url)
    if not qr:
        return jsonify({"error": "QR generation unavailable (install qrcode)"}), 503
    return jsonify({"registration_url": reg_url, "qr_code_base64": qr})


@app.post("/api/referral/karma-share-text")
@login_required
def api_referral_karma_share_text():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    payload = request.get_json(silent=True) or {}
    action_code = str(payload.get("action_code") or "").strip()
    amount = int(payload.get("amount_rupees") or 0)
    stats = referral_core.get_referral_stats(conn, pid)
    text = referral_core.karma_share_text(action_code, amount, stats["referral_code"])
    reg_url = referral_core.build_registration_url(
        _public_base_url(), stats["referral_code"]
    )
    return jsonify({"text": text, "registration_url": reg_url, "referral_code": stats["referral_code"]})


@app.post("/api/referral/validate")
def api_referral_validate():
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    code = str(payload.get("referral_code") or payload.get("code") or "").strip()
    result = referral_core.validate_referral_code(conn, code)
    status = 200 if result.get("valid") else 400
    return jsonify(result), status


@app.post("/api/donation/preview")
def api_donation_preview():
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        amount = int(payload.get("donation_amount") if payload.get("donation_amount") is not None else payload.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400
    if amount < 0 or amount > 200:
        return jsonify({"error": "Donation must be between ₹0 and ₹200"}), 400
    village_id = str(payload.get("village_id") or payload.get("current_location_id") or "").strip()
    country_id = str(payload.get("country_id") or "IND").strip().upper()
    continent_id = str(payload.get("continent_id") or "").strip().upper()
    referrer_private_id = str(payload.get("referrer_private_id") or "").strip()
    if not referrer_private_id:
        ref_code = str(payload.get("referral_code") or "").strip()
        if ref_code:
            referrer_private_id = (
                referral_core.lookup_referrer_by_code(conn, ref_code) or ""
            )
    loc_ctx = donation_location_context(
        conn,
        village_id=village_id,
        country_id=country_id,
        continent_id=continent_id,
    )
    try:
        if not referrer_private_id:
            distribution, meta = donation_core.calculate_no_referral_distribution(
                amount,
                location_context=loc_ctx,
            )
            preview = donation_core.preview_donation(amount, distribution, meta=meta)
        else:
            distribution = donation_core.calculate_donation_distribution(
                amount,
                location_context=loc_ctx,
                referrer_private_id=referrer_private_id,
            )
            preview = donation_core.preview_donation(amount, distribution)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(preview)


@app.post("/api/donation/preview/no-referral")
def api_donation_preview_no_referral():
    """Public JSON preview for registration without referral (no login required)."""
    try:
        payload = request.get_json(silent=True) or {}
        try:
            amount = int(
                payload.get("donation_amount")
                if payload.get("donation_amount") is not None
                else payload.get("amount", 0)
            )
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "amount must be an integer"}), 400
        if amount < 0 or amount > 200:
            return jsonify(
                {"success": False, "error": "Donation must be between ₹0 and ₹200"}
            ), 400

        conn = get_db()
        village_id = str(
            payload.get("village_id") or payload.get("current_location_id") or ""
        ).strip()
        country_id = str(payload.get("country_id") or "IND").strip().upper()
        continent_id = str(payload.get("continent_id") or "").strip().upper()
        loc_ctx = donation_location_context(
            conn,
            village_id=village_id,
            country_id=country_id,
            continent_id=continent_id,
        )
        preview = donation_core.preview_no_referral_donation(
            amount,
            location_context=loc_ctx,
        )

        tier_labels = {
            "earth": "Earth",
            "continent": "Continent",
            "country": "Country",
            "zone": "Zone",
            "state": "State",
            "district": "District",
            "tehsil": "Tehsil",
            "village": "Village",
        }
        location_rows: list[dict[str, Any]] = []
        user_share_rupees = preview.get("user_pending_rupees", 0)
        for item in preview.get("distribution") or []:
            tier = str(item.get("tier") or "")
            if tier == "new_user":
                user_share_rupees = float(item.get("rupee_amount") or user_share_rupees)
                continue
            if tier not in tier_labels:
                continue
            paise = int(item.get("amount_paise") or round(float(item.get("rupee_amount") or 0) * 100))
            location_rows.append(
                {
                    "name": tier_labels[tier],
                    "tier": tier,
                    "amount_rupees": round(paise / 100.0, 2),
                    "amount_paise": paise,
                    "rupee_amount": paise / 100.0,
                }
            )

        per_loc = location_rows[0]["amount_paise"] if location_rows else 0
        response: dict[str, Any] = {
            "success": True,
            "donation_amount": amount,
            "total_paise": int(round(float(preview.get("effective_rupees") or 0) * 100)),
            "total_rupees": preview.get("effective_rupees") or preview.get("total_rupees"),
            "effective_rupees": preview.get("effective_rupees"),
            "location_share_paise": per_loc,
            "location_share_rupees": round(per_loc / 100.0, 2),
            "user_share_paise": int(round(float(user_share_rupees) * 100)),
            "user_share_rupees": round(float(user_share_rupees), 2),
            "user_pending_rupees": user_share_rupees,
            "user_share_after_vote": True,
            "system_generated": bool(preview.get("system_generated")),
            "distribution": location_rows,
            "location_total_rupees": preview.get("location_share_rupees"),
        }
        resp = jsonify(response)
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
        return resp, 200
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("no-referral donation preview failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@app.post("/api/register/no-referral")
def api_register_no_referral():
    """Alias for Indian registration donation when no referral code is used."""
    pending = session.get("pending_registration")
    if not pending:
        return jsonify({"error": "No pending registration. Complete the form first."}), 400
    if pending.get("referred_by_private_id"):
        return jsonify({"error": "This endpoint is for registration without a referral code"}), 400
    return api_register_donate()


@app.post("/api/rewards/activate-after-vote")
@login_required
def api_rewards_activate_after_vote():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    activated = donation_core.activate_user_reward_after_vote(
        conn, pid, notify_fn=send_system_message
    )
    conn.commit()
    return jsonify({"ok": True, "activated": activated})


@app.post("/api/volunteer/apply")
@login_required
def api_volunteer_apply():
    conn = get_db()
    user = g.current_user
    payload = request.get_json(silent=True) or {}
    bank_name = str(payload.get("bank_name") or "").strip()
    account_number = str(payload.get("account_number") or "").strip()
    branch = str(payload.get("branch") or "").strip()
    ifsc_code = str(payload.get("ifsc_code") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    if not all([bank_name, account_number, branch, ifsc_code]):
        return jsonify({"error": "All bank fields are required"}), 400
    if not reason:
        return jsonify({"error": "Please explain why you want to become a volunteer"}), 400
    pid = str(user["private_id"])
    vid = str(user["current_location_id"] or "").strip()
    hier = current_location_hierarchy(conn, vid) if vid else []
    state_name = next((h["name"] for h in hier if h["scope"] == "state"), "")
    try:
        req_id = referral_core.submit_volunteer_application(
            conn,
            applicant_private_id=pid,
            applicant_name=f'{user["first_name"]} {user["last_name"]}'.strip(),
            applicant_village_id=vid,
            applicant_state=str(state_name or ""),
            reason=reason,
            bank_name=bank_name,
            account_number=account_number,
            branch=branch,
            ifsc_code=ifsc_code,
        )
        conn.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "request_id": req_id})


@app.get("/api/volunteer/status")
@login_required
def api_volunteer_status():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    return jsonify(referral_core.get_volunteer_status(conn, pid))


@app.get("/api/volunteer/dashboard")
@login_required
def api_volunteer_dashboard():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    try:
        data = referral_core.get_volunteer_dashboard(conn, pid)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    base = _public_base_url()
    data["registration_url"] = referral_core.build_registration_url(
        base, data.get("volunteer_code") or ""
    )
    return jsonify(data)


@app.get("/api/volunteer/signups")
@login_required
def api_volunteer_signups():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    vol = referral_core.get_volunteer_by_private_id(conn, pid)
    if not vol or str(vol.get("status")) != "active":
        return jsonify({"error": "Active volunteer record not found"}), 404
    signups = referral_core.list_volunteer_signups(conn, pid)
    return jsonify({"signups": signups})


@app.get("/api/upgrade/check-permission")
@login_required
def api_upgrade_check_permission():
    conn = get_db()
    user = g.current_user
    target = str(request.args.get("role") or request.args.get("new_account_type") or "").strip()
    allowed = user_can_upgrade_to(conn, user, target) if target else False
    if is_admin_user(user):
        allowed_roles = sorted(UPGRADE_ACCOUNT_TYPES)
    elif is_council_member(conn, user):
        allowed_roles = sorted(COUNCIL_UPGRADE_TYPES)
    else:
        allowed_roles = []
    return jsonify(
        {
            "allowed": allowed,
            "allowed_roles": allowed_roles,
            "is_admin": is_admin_user(user),
            "is_council_member": is_council_member(conn, user),
        }
    )


@app.post("/api/upgrade/user")
@council_or_admin_required
def api_upgrade_user():
    payload = request.get_json(silent=True) or {}
    lookup = str(payload.get("public_id") or payload.get("private_id") or "").strip()
    new_type = str(payload.get("new_account_type") or payload.get("role") or "").strip()
    if not lookup:
        return jsonify({"error": "public_id or private_id is required"}), 400
    if new_type not in UPGRADE_ACCOUNT_TYPES:
        return jsonify(
            {
                "error": "new_account_type must be one of: "
                + ", ".join(sorted(UPGRADE_ACCOUNT_TYPES))
            }
        ), 400
    conn = get_db()
    upgrader = g.current_user
    if not user_can_upgrade_to(conn, upgrader, new_type):
        return jsonify({"error": f"You cannot upgrade users to {new_type}"}), 403
    row = conn.execute(
        """
        SELECT * FROM users
        WHERE public_id = ? COLLATE NOCASE OR private_id = ? COLLATE NOCASE
        """,
        (lookup, lookup),
    ).fetchone()
    if not row:
        return jsonify({"error": "User not found"}), 404
    at = str(row["account_type"] or "")
    if _is_demo_account_type(at):
        return jsonify({"error": "Demo users cannot be upgraded"}), 400
    if at not in ("H_U",) and at not in UPGRADE_ACCOUNT_TYPES:
        return jsonify({"error": "Only Human User accounts can be upgraded"}), 400
    pid = str(row["private_id"])
    conn.execute(
        "UPDATE users SET account_type = ? WHERE private_id = ?",
        (new_type, pid),
    )
    nm = f'{row["first_name"] or ""} {row["last_name"] or ""}'.strip() or pid
    upgraded_by = "an administrator" if is_admin_user(upgrader) else "a council member"
    send_system_message(
        conn,
        pid,
        "Account upgraded",
        f"Your Qumanity account has been upgraded to {new_type} by {upgraded_by}.",
    )
    conn.commit()
    return jsonify(
        {
            "ok": True,
            "private_id": pid,
            "public_id": str(row["public_id"]),
            "account_type": new_type,
            "full_name": nm,
        }
    )


@app.post("/api/donation/init-bank-qr")
def api_donation_init_bank_qr():
    """Create a pending bank-QR donation when user selects QR payment."""
    pending = session.get("pending_registration")
    if not pending:
        return jsonify(
            {
                "error": "Complete registration or log in first",
                "code": "no_pending_registration",
            }
        ), 401
    payload = request.get_json(silent=True) or {}
    try:
        amount = int(payload.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400
    if amount < 1 or amount > 200:
        return jsonify({"error": "Donation must be between ₹1 and ₹200"}), 400

    conn = get_db()
    session_marker = secrets.token_hex(8)
    donation_id = sita_platform_core.record_donation(
        conn,
        user_private_id=f"{sita_platform_core.PENDING_USER_PREFIX}{session_marker}",
        user_public_id="PENDING",
        amount=amount,
        payment_method="bank_qr",
        status="pending",
        payment_status="pending",
        amount_paise=amount * 100,
    )
    txn_ref = f"QUM{donation_id}"
    conn.execute(
        "UPDATE donations SET transaction_id = ? WHERE id = ?",
        (txn_ref, int(donation_id)),
    )
    session["pending_donation_id"] = int(donation_id)
    session["pending_donation_marker"] = session_marker
    session.pop("bank_qr_payment_confirmed", None)
    session.pop("qr_txn_submitted", None)
    conn.commit()
    return jsonify(
        {
            "ok": True,
            "success": True,
            "donation_id": donation_id,
            "amount": amount,
            "payment_status": "pending",
        }
    )


def _validate_upi_txn_reference(txn_reference: str) -> bool:
    ref = (txn_reference or "").strip()
    if len(ref) < 10 or len(ref) > 30:
        return False
    return bool(re.match(r"^[A-Za-z0-9]+$", ref))


def _donation_session_allowed(row: dict[str, Any] | sqlite3.Row) -> bool:
    donation_id = int(row["id"])
    session_donation_id = session.get("pending_donation_id")
    if session_donation_id is not None and int(session_donation_id) == donation_id:
        return True
    if getattr(g, "current_user", None):
        if str(g.current_user["private_id"]) == str(row["user_private_id"]):
            return True
        if str(row["user_private_id"]).startswith(sita_platform_core.PENDING_USER_PREFIX):
            marker = session.get("pending_donation_marker")
            if marker and str(row["user_private_id"]) == (
                f"{sita_platform_core.PENDING_USER_PREFIX}{marker}"
            ):
                return True
    return False


@app.post("/api/donation/verify-bank-payment")
def api_donation_verify_bank_payment():
    """
    Confirm bank QR payment after user pays via UPI app.
    Auto-verifies for registration (replace with SBI API when available).
    """
    pending = session.get("pending_registration")
    if not pending:
        return jsonify(
            {
                "error": "Complete registration or log in first",
                "code": "no_pending_registration",
            }
        ), 401
    payload = request.get_json(silent=True) or {}
    donation_id = payload.get("donation_id") or session.get("pending_donation_id")
    if not donation_id:
        return jsonify({"success": False, "error": "No payment session. Select QR again."}), 400
    try:
        donation_id_int = int(donation_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Invalid donation_id"}), 400
    try:
        amount = int(
            payload.get("amount")
            if payload.get("amount") is not None
            else payload.get("donation_amount", 0)
        )
    except (TypeError, ValueError):
        amount = 0

    conn = get_db()
    row = sita_platform_core.get_donation(conn, donation_id_int)
    if not row:
        return jsonify({"success": False, "error": "Donation not found"}), 404
    if not _donation_session_allowed(row):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    if amount > 0 and int(row.get("amount") or 0) != amount:
        return jsonify({"success": False, "error": "Amount mismatch"}), 400

    pay_status = sita_platform_core._payment_status_for_row(row)
    if pay_status == "completed":
        session["bank_qr_payment_confirmed"] = True
        session["pending_donation_id"] = donation_id_int
        return jsonify(
            {
                "ok": True,
                "success": True,
                "message": "Payment already verified",
                "donation_id": donation_id_int,
                "payment_status": "completed",
                "verification_method": "already_verified",
            }
        )

    conn.execute(
        """
        UPDATE donations
        SET status = 'confirmed',
            payment_status = 'completed',
            confirmed_at = ?,
            confirmed_by = 'auto_verify'
        WHERE id = ?
        """,
        (sita_platform_core._now(), donation_id_int),
    )
    session["pending_donation_id"] = donation_id_int
    session["bank_qr_payment_confirmed"] = True
    conn.commit()
    return jsonify(
        {
            "ok": True,
            "success": True,
            "message": "Payment verified successfully",
            "donation_id": donation_id_int,
            "payment_status": "completed",
            "verification_method": "auto_verify",
        }
    )


def _notify_admins_pending_qr_verification(
    conn: sqlite3.Connection,
    donation_id: int,
    txn_reference: str,
    amount_rupees: int,
) -> None:
    body = (
        f"A registration donation needs payment verification.\n\n"
        f"Donation ID: {donation_id}\n"
        f"Amount: ₹{amount_rupees}\n"
        f"UPI reference: {txn_reference}\n\n"
        "Verify against your bank statement and confirm in Admin → Donations."
    )
    for row in conn.execute(
        "SELECT private_id FROM users WHERE COALESCE(is_admin, 0) = 1",
    ):
        send_system_message(
            conn,
            str(row["private_id"]),
            "QR donation pending verification",
            body,
        )


@app.post("/api/donation/verify-qr-payment")
def api_donation_verify_qr_payment():
    """Submit UPI transaction reference for admin verification."""
    payload = request.get_json(silent=True) or {}
    donation_id = payload.get("donation_id") or session.get("pending_donation_id")
    txn_reference = str(
        payload.get("txn_reference") or payload.get("txn_ref") or ""
    ).strip()
    if not donation_id:
        return jsonify({"success": False, "error": "donation_id required"}), 400
    if not _validate_upi_txn_reference(txn_reference):
        return jsonify(
            {
                "success": False,
                "error": (
                    "Invalid transaction reference. Enter the 10–30 character "
                    "UPI reference from your payment app."
                ),
            }
        ), 400
    conn = get_db()
    row = sita_platform_core.get_donation(conn, int(donation_id))
    if not row:
        return jsonify({"success": False, "error": "Donation not found"}), 404
    if not _donation_session_allowed(row):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    ok, err_msg = sita_platform_core.submit_bank_qr_txn_reference(
        conn, int(donation_id), txn_reference
    )
    if not ok:
        return jsonify(
            {
                "success": False,
                "error": err_msg or (
                    "Please enter a valid transaction reference number"
                ),
            }
        ), 400
    amount_rupees = sita_platform_core.donation_amount_rupees(row)
    _notify_admins_pending_qr_verification(
        conn, int(donation_id), txn_reference, amount_rupees
    )
    session["qr_txn_submitted"] = True
    session["pending_donation_id"] = int(donation_id)
    conn.commit()
    return jsonify(
        {
            "ok": True,
            "success": True,
            "message": "Transaction reference submitted",
            "donation_id": int(donation_id),
            "payment_status": "pending_verification",
            "account_status": "pending_verification",
        }
    )


@app.post("/api/donation/submit-txn-reference")
def api_donation_submit_txn_reference():
    """Alias for verify-qr-payment with spec-compliant path."""
    return api_donation_verify_qr_payment()


@app.get("/api/donation/check-verification/<int:donation_id>")
def api_donation_check_verification(donation_id: int):
    """Poll whether admin has verified a bank-QR donation."""
    conn = get_db()
    row = sita_platform_core.get_donation(conn, donation_id)
    if not row:
        return jsonify({"error": "Donation not found"}), 404
    if not _donation_session_allowed(row):
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(sita_platform_core.get_verification_check_payload(conn, donation_id))


@app.post("/api/donation/admin-verify/<int:donation_id>")
def api_donation_admin_verify(donation_id: int):
    """Admin API key endpoint to verify a bank-QR donation."""
    admin_key = (request.headers.get("X-Admin-Key") or "").strip()
    expected = getattr(config, "ADMIN_API_KEY", "") or ""
    if not expected or not admin_key or admin_key != expected:
        return jsonify({"error": "Unauthorized"}), 401
    conn = get_db()
    ok = sita_platform_core.confirm_donation(conn, donation_id, "admin_api_key")
    if not ok:
        return jsonify({"error": "Donation not found or already confirmed"}), 404
    row = sita_platform_core.get_donation(conn, donation_id)
    if row:
        pid = str(row.get("user_private_id") or "").strip()
        if pid and not pid.startswith(sita_platform_core.PENDING_USER_PREFIX):
            _notify_user_verification_event(conn, pid, "verified")
    conn.commit()
    return jsonify(
        {
            "ok": True,
            "success": True,
            "message": "Donation verified and account activated",
            "donation_id": donation_id,
            "verified": True,
        }
    )


@app.post("/api/donation/create-order")
def api_donation_create_order():
    pending = session.get("pending_registration")
    if not pending and not getattr(g, "current_user", None):
        return jsonify(
            {
                "error": "Complete registration or log in first",
                "code": "no_pending_registration",
            }
        ), 401
    payload = request.get_json(silent=True) or {}
    try:
        amount = int(payload.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400
    if amount < 1 or amount > 200:
        return jsonify({"error": "Donation must be between ₹1 and ₹200"}), 400

    order_id = ""
    order_currency = "INR"
    try:
        if _razorpay_client() is not None:
            order = _create_razorpay_order(amount)
            order_id = str(order.get("id") or "").strip()
            order_currency = str(order.get("currency") or "INR")
        else:
            app.logger.warning(
                "Razorpay keys not configured; using static UPI QR only"
            )
    except Exception as exc:
        app.logger.warning(
            "Razorpay order create failed; continuing with static UPI QR: %s", exc
        )

    conn = get_db()
    session_marker = secrets.token_hex(8)
    donation_id = sita_platform_core.record_donation(
        conn,
        user_private_id=f"{sita_platform_core.PENDING_USER_PREFIX}{session_marker}",
        user_public_id="PENDING",
        amount=amount,
        payment_method="qr_code",
        status="pending",
        payment_status="pending",
        razorpay_order_id=order_id or None,
        amount_paise=amount * 100,
    )
    try:
        qr_payload = _generate_upi_qr_simple(float(amount), donation_id)
    except Exception as exc:
        conn.rollback()
        app.logger.exception("UPI QR generation failed for donation %s", donation_id)
        return jsonify(
            {
                "error": f"Failed to generate QR: {exc}",
                "code": "qr_exception",
            }
        ), 503
    txn_ref = str(qr_payload.get("transaction_ref") or f"QUM{donation_id}").strip()
    conn.execute(
        "UPDATE donations SET transaction_id = ? WHERE id = ?",
        (txn_ref, int(donation_id)),
    )
    qr_id = str(qr_payload.get("qr_id") or "").strip()
    if qr_id:
        conn.execute(
            "UPDATE donations SET razorpay_qr_id = ? WHERE id = ?",
            (qr_id, int(donation_id)),
        )
    session["pending_donation_id"] = int(donation_id)
    session["pending_donation_marker"] = session_marker
    conn.commit()
    scan_warning = _static_qr_scan_warning(
        str(qr_payload.get("upi_vpa") or ""),
        str(qr_payload.get("vpa_source") or ""),
        str(qr_payload.get("vpa_source") or "") == "razorpay_image_content",
    )
    return jsonify(
        {
            "ok": True,
            "success": True,
            "donation_id": donation_id,
            "order_id": order_id,
            "amount": amount,
            "currency": order_currency,
            "qr_image_base64": qr_payload.get("qr_image_base64"),
            "upi_vpa": qr_payload.get("upi_vpa"),
            "upi_uri": qr_payload.get("upi_uri"),
            "vpa_source": qr_payload.get("vpa_source"),
            "vpa_valid": qr_payload.get("vpa_valid"),
            "vpa_is_placeholder": qr_payload.get("vpa_is_placeholder"),
            "static_qr_warning": scan_warning,
            "qr_uses_razorpay_uri": (
                str(qr_payload.get("vpa_source") or "") == "razorpay_image_content"
            ),
        }
    )


@app.get("/api/decode-qr-uri")
def api_decode_qr_uri():
    """Return the UPI URI that would be encoded in a static donation QR."""
    amount = request.args.get("amount", 1, type=float)
    donation_id = request.args.get("donation_id", 999, type=int)
    vpa, source = _resolve_merchant_upi_vpa()
    txn_ref = f"QUM{donation_id}"
    try:
        upi_uri = _build_upi_pay_uri(
            vpa,
            amount,
            payee_name="Qumanity",
            transaction_note=f"Donation {txn_ref}",
            transaction_ref=txn_ref,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc), "vpa": vpa}), 400
    return jsonify(
        {
            "upi_uri": upi_uri,
            "vpa": vpa,
            "vpa_source": source,
            "contains_encoded_at": "%40" in upi_uri.split("pa=", 1)[-1].split("&", 1)[0],
            "contains_literal_at": "@" in upi_uri,
            "valid_format": upi_uri.startswith("upi://pay?pa="),
            "static_qr_warning": _static_qr_scan_warning(vpa, source, False),
            "suggestion": "Copy upi_uri into a UPI app to test static QR payments.",
        }
    )


@app.get("/api/test-upi-uri")
def api_test_upi_uri():
    """Validate UPI URI format for PhonePe / GPay / Paytm."""
    from urllib.parse import parse_qs, urlparse

    amount = request.args.get("amount", 1, type=float)
    vpa, source = _resolve_merchant_upi_vpa()
    donation_id = 999
    txn_ref = f"QUM{donation_id}"
    try:
        upi_uri = _build_upi_pay_uri(
            vpa,
            amount,
            payee_name="Qumanity",
            transaction_note=f"Donation {txn_ref}",
            transaction_ref=txn_ref,
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc), "vpa": vpa}), 400

    parsed = urlparse(upi_uri)
    query_params = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(parsed.query).items()}
    pa_raw = query_params.get("pa", "")
    pa_encoded_at = "%40" in upi_uri and "@" not in upi_uri.split("pa=", 1)[-1].split("&", 1)[0]

    return jsonify(
        {
            "success": True,
            "upi_uri": upi_uri,
            "vpa": vpa,
            "vpa_source": source,
            "vpa_valid": _validate_upi_vpa(vpa),
            "vpa_is_placeholder": vpa.lower() in _PLACEHOLDER_UPI_VPAS,
            "params": query_params,
            "pa_has_literal_at": "@" in pa_raw,
            "pa_encoded_as_percent40": pa_encoded_at,
            "hint": (
                "If vpa_is_placeholder is true, set DONATION_UPI_VPA to your real "
                "Razorpay merchant VPA from Dashboard → Settings → UPI."
            ),
        }
    )


@app.get("/api/test-qr")
def api_test_qr():
    """Smoke-test UPI QR generation (no session required)."""
    try:
        payload = _generate_upi_qr_simple(1.0, 0)
        b64 = str(payload.get("qr_image_base64") or "")
        return jsonify(
            {
                "success": True,
                "ok": True,
                "upi_vpa": payload.get("upi_vpa"),
                "upi_uri": payload.get("upi_uri"),
                "vpa_source": payload.get("vpa_source"),
                "qr_base64_length": len(b64),
                "qr_base64_preview": (b64[:80] + "…") if len(b64) > 80 else b64,
            }
        )
    except Exception as exc:
        app.logger.exception("api_test_qr failed")
        return jsonify({"success": False, "ok": False, "error": str(exc)}), 500


@app.get("/api/check-env")
def api_check_env():
    """Report payment-related environment variables (values shown for VPA only)."""
    env_names = [
        "DONATION_UPI_VPA",
        "RAZORPAY_UPI_VPA",
        "UPI_VPA",
        "MERCHANT_UPI_VPA",
        "FALLBACK_DONATION_UPI_VPA",
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
    ]
    env_vars: dict[str, Any] = {}
    for key in env_names:
        raw = os.environ.get(key)
        cleaned = _clean_env_value(raw or "")
        if key.endswith("_SECRET") or key == "RAZORPAY_KEY_ID":
            env_vars[key] = {
                "exists": raw is not None,
                "length": len(cleaned),
                "preview": _mask_secret(cleaned, 6),
            }
        else:
            env_vars[key] = {
                "exists": raw is not None,
                "value": cleaned or None,
                "length": len(cleaned),
                "has_at_sign": "@" in cleaned,
            }
    try:
        import qrcode  # noqa: F401

        qrcode_available = True
    except ImportError:
        qrcode_available = False
    vpa, source = _resolve_merchant_upi_vpa()
    return jsonify(
        {
            "environment_variables": env_vars,
            "config_DONATION_UPI_VPA": config.DONATION_UPI_VPA or None,
            "resolved_vpa": vpa,
            "resolved_vpa_source": source,
            "qrcode_available": qrcode_available,
        }
    )


@app.get("/api/diagnose-config")
def api_diagnose_config():
    """Debug payment configuration (masked secrets)."""
    secret = (os.environ.get("DIAGNOSTIC_SECRET") or "").strip()
    if secret:
        provided = (request.headers.get("X-Diagnostic-Secret") or "").strip()
        if not provided or not hmac.compare_digest(provided, secret):
            return jsonify({"error": "Forbidden"}), 403

    env_names = [
        "DONATION_UPI_VPA",
        "RAZORPAY_UPI_VPA",
        "UPI_VPA",
        "MERCHANT_UPI_VPA",
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
        "RAZORPAY_WEBHOOK_SECRET",
    ]
    env_report: dict[str, Any] = {}
    for name in env_names:
        raw = os.environ.get(name)
        cleaned = _clean_env_value(raw or "")
        env_report[name] = {
            "exists": raw is not None,
            "length": len(cleaned),
            "preview": _mask_secret(cleaned, 6),
            "has_at_sign": "@" in cleaned,
        }

    vpa_resolved, vpa_source = _resolve_merchant_upi_vpa()
    qr_ok = False
    qr_error = ""
    if vpa_resolved:
        try:
            test_uri = _build_upi_pay_uri(vpa_resolved, 1.0, transaction_ref="QUMTEST")
            qr_ok = bool(_generate_upi_qr_base64(test_uri))
        except Exception as exc:
            qr_error = str(exc)

    return jsonify(
        {
            "ok": True,
            "config_module": {
                "DONATION_UPI_VPA": _mask_secret(config.DONATION_UPI_VPA, 6),
                "RAZORPAY_KEY_ID": _mask_secret(config.RAZORPAY_KEY_ID, 8),
                "RAZORPAY_KEY_SECRET": "set" if config.RAZORPAY_KEY_SECRET else "missing",
            },
            "environment": env_report,
            "resolved_upi_vpa": _mask_secret(vpa_resolved, 6),
            "resolved_vpa_source": vpa_source,
            "qr_generation_test": qr_ok,
            "qr_generation_error": qr_error,
            "session_pending_registration": bool(session.get("pending_registration")),
            "razorpay_client": _razorpay_client() is not None,
        }
    )


@app.post("/api/donation/verify")
@login_required
def api_donation_verify():
    payload = request.get_json(silent=True) or {}
    payment_id = str(payload.get("razorpay_payment_id") or payload.get("payment_id") or "").strip()
    order_id = str(payload.get("razorpay_order_id") or payload.get("order_id") or "").strip()
    signature = str(payload.get("razorpay_signature") or payload.get("signature") or "").strip()
    try:
        amount = int(payload.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400
    if not all([payment_id, order_id, signature]):
        return jsonify({"error": "payment_id, order_id, and signature are required"}), 400
    try:
        _verify_razorpay_payment(payment_id, order_id, signature)
    except Exception as exc:
        return jsonify({"error": f"Payment verification failed: {exc}"}), 400
    conn = get_db()
    pid = str(g.current_user["private_id"])
    donation_core.record_donation_transaction(
        conn,
        user_private_id=pid,
        amount=amount,
        payment_method=str(payload.get("payment_method") or "card"),
        transaction_id=payment_id,
        status="completed",
    )
    conn.commit()
    return jsonify({"ok": True, "payment_id": payment_id})


@app.post("/api/location/donate")
@login_required
def api_location_donate():
    payload = request.get_json(silent=True) or {}
    scope = str(payload.get("location_scope") or payload.get("scope") or "").strip().lower()
    location_id = str(payload.get("location_id") or "").strip()
    try:
        amount = int(payload.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400
    if amount < 1 or amount > 200:
        return jsonify({"error": "Donation must be between ₹1 and ₹200"}), 400
    if not scope or not location_id:
        return jsonify({"error": "location_scope and location_id are required"}), 400

    payment_id = str(payload.get("razorpay_payment_id") or "").strip()
    order_id = str(payload.get("razorpay_order_id") or "").strip()
    signature = str(payload.get("razorpay_signature") or "").strip()
    method = str(payload.get("payment_method") or "upi").strip().lower()

    conn = get_db()
    user = g.current_user
    pid = str(user["private_id"])
    village_id = str(user["current_location_id"] or "").strip()
    loc_ctx = donation_location_context(
        conn,
        village_id=village_id,
        country_id=str(user["current_country_id"] or "IND"),
        continent_id=str(user["current_continent_id"] or ""),
    )
    if scope in loc_ctx:
        loc_ctx[scope] = location_id
    if scope == "india":
        loc_ctx["country"] = "IND"
    referrer_private_id = str(user["referred_by"] or "").strip()
    ref_code = str(payload.get("referral_code") or "").strip()
    if ref_code and not referrer_private_id:
        referrer_private_id = referral_core.lookup_referrer_by_code(conn, ref_code) or ""
    distribution = donation_core.calculate_donation_distribution(
        amount,
        location_context=loc_ctx,
        referrer_private_id=referrer_private_id,
        new_user_private_id=pid,
    )

    if payment_id and order_id and signature:
        try:
            _verify_razorpay_payment(payment_id, order_id, signature)
        except Exception as exc:
            return jsonify({"error": f"Payment verification failed: {exc}"}), 400
        status = "completed"
    elif method == "cash":
        agent_private_id = str(payload.get("agent_private_id") or "").strip()
        if not agent_private_id or not referral_core.lookup_active_volunteer_by_private_id(
            conn, agent_private_id
        ):
            return jsonify({"error": "Valid volunteer Private ID required for cash"}), 400
        status = "completed"
        payment_id = f"cash-{secrets.token_hex(4)}"
    else:
        return jsonify({"error": "Complete online payment or use cash with volunteer ID"}), 400

    donation_core.record_donation_transaction(
        conn,
        user_private_id=pid,
        amount=amount,
        payment_method=method,
        transaction_id=payment_id,
        status=status,
        distribution=distribution,
        location_scope=scope,
        location_id=location_id,
    )
    for item in distribution:
        donation_core._credit_distribution_item(
            conn, item, ref_suffix=f"loc-{location_id}-{payment_id[:8]}"
        )
    conn.commit()
    return jsonify({"ok": True, "distribution": distribution})


@app.post("/api/employment/apply")
@login_required
def api_employment_apply():
    conn = get_db()
    user = g.current_user
    payload = request.get_json(silent=True) or {}
    bank = str(payload.get("bank_account_details") or "").strip()
    bank_name = str(payload.get("bank_name") or "").strip()
    account_number = str(payload.get("account_number") or "").strip()
    branch = str(payload.get("branch") or "").strip()
    ifsc_code = str(payload.get("ifsc_code") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    availability = str(payload.get("availability") or "").strip()
    pid = str(user["private_id"])
    vid = str(user["current_location_id"] or "").strip()
    hier = current_location_hierarchy(conn, vid) if vid else []
    state_name = next((h["name"] for h in hier if h["scope"] == "state"), "")
    if not reason:
        return jsonify({"error": "Please explain why you want to become a volunteer"}), 400
    if bank_name and account_number:
        try:
            req_id = referral_core.submit_volunteer_application(
                conn,
                applicant_private_id=pid,
                applicant_name=f'{user["first_name"]} {user["last_name"]}'.strip(),
                applicant_village_id=vid,
                applicant_state=str(state_name or ""),
                reason=reason,
                bank_name=bank_name,
                account_number=account_number,
                branch=branch,
                ifsc_code=ifsc_code,
            )
            conn.commit()
            return jsonify({"ok": True, "request_id": req_id})
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
    if not bank:
        return jsonify({"error": "Bank account details are required"}), 400
    try:
        req_id = referral_core.submit_employment_request(
            conn,
            applicant_private_id=pid,
            applicant_name=f'{user["first_name"]} {user["last_name"]}'.strip(),
            applicant_village_id=vid,
            applicant_state=str(state_name or ""),
            reason=reason,
            bank_account_details=bank,
            availability=availability,
        )
        conn.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "request_id": req_id})


@app.get("/api/admin/employment/requests")
@admin_required
def api_admin_employment_requests():
    conn = get_db()
    return jsonify({"requests": referral_core.list_pending_employment_requests(conn)})


@app.post("/api/admin/employment/approve")
@admin_required
def api_admin_employment_approve():
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        req_id = int(payload.get("request_id") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "request_id required"}), 400
    try:
        result = referral_core.approve_employment_request(
            conn,
            req_id,
            approved_by=str(g.current_user["private_id"]),
            notify_fn=send_system_message,
        )
        conn.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, **result})


@app.post("/api/admin/employment/reject")
@admin_required
def api_admin_employment_reject():
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        req_id = int(payload.get("request_id") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "request_id required"}), 400
    note = str(payload.get("review_note") or payload.get("reason") or "").strip()
    try:
        referral_core.reject_employment_request(
            conn,
            req_id,
            reviewed_by=str(g.current_user["private_id"]),
            review_note=note,
            notify_fn=send_system_message,
        )
        conn.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True})


@app.post("/api/rewards/activate")
@login_required
def api_rewards_activate():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    activated = donation_core.activate_rewards(
        conn, pid, notify_fn=send_system_message
    )
    conn.commit()
    return jsonify({"ok": True, "activated": activated})


@app.get("/api/karma/karma/pending")
@app.get("/api/qoin/karma/pending")
@login_required
def api_qoin_karma_pending():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    return jsonify({"items": qoin_core.user_pending_karma(conn, pid)})


@app.post("/api/admin/karma/settlement")
@app.post("/api/admin/qoin/settlement")
@admin_required
def api_admin_qoin_settlement():
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get("force", True))
    result = qoin_scheduler.run_weekly_settlement_if_due(
        conn,
        hierarchy_resolver=_qoin_hierarchy_resolver,
        notify_fn=send_system_message,
        force=force,
    )
    if result is None:
        result = qoin_core.process_weekly_settlement(
            conn,
            triggered_by="admin",
            hierarchy_resolver=_qoin_hierarchy_resolver,
            notify_fn=send_system_message,
        )
        conn.commit()
    return jsonify({"ok": True, "result": result})


@app.get("/api/admin/karma/nested-wallets")
@app.get("/api/admin/qoin/nested-wallets")
@admin_required
def api_admin_nested_wallets():
    conn = get_db()
    circulation = qoin_core.circulation_total(conn)
    wallets = qoin_core.nested_wallets_summary(conn)
    pending = qoin_core.pending_summary(conn)
    return jsonify({"circulation": circulation, "wallets": wallets, "pending": pending})


@app.get("/api/admin/karma/karma-types")
@app.get("/api/admin/qoin/karma-types")
@admin_required
def api_admin_karma_types_list():
    conn = get_db()
    return jsonify({"actions": qoin_core.karma_action_types_list(conn)})


@app.post("/api/admin/karma/karma-types")
@app.post("/api/admin/qoin/karma-types")
@admin_required
def api_admin_karma_types_upsert():
    conn = get_db()
    payload = request.get_json(silent=True) or {}
    code = str(payload.get("action_code") or "").strip()
    label = str(payload.get("label") or "").strip()
    try:
        val = int(payload.get("rupee_value") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "rupee_value must be an integer"}), 400
    if not code or not label or val <= 0:
        return jsonify({"error": "action_code, label, and positive rupee_value required"}), 400
    qoin_core.upsert_karma_action_type(
        conn,
        action_code=code,
        label=label,
        rupee_value=val,
        active=bool(payload.get("active", True)),
    )
    conn.commit()
    return jsonify({"ok": True})


@app.get("/api/village/wallet")
@login_required
def api_village_wallet():
    village_id = (request.args.get("village_id") or "").strip()
    if not village_id:
        return jsonify({"error": "village_id is required"}), 400
    conn = get_db()
    if not village_exists(conn, village_id):
        return jsonify({"error": "Village not found"}), 404
    qoin_core.ensure_wallet(conn, "village", village_id)
    return jsonify(
        {
            "village_id": village_id,
            "balance_qoins": qoin_core.wallet_balance(conn, "village", village_id),
            "total_rupees": qoin_core.wallet_rupee_total(conn, "village", village_id),
        }
    )


@app.get("/api/admin/village_donations")
@admin_required
def api_admin_village_donations():
    village_id = (request.args.get("village_id") or "").strip()
    if not village_id:
        return jsonify({"error": "village_id is required"}), 400
    conn = get_db()
    if not village_exists(conn, village_id):
        return jsonify({"error": "Village not found"}), 404
    return jsonify(qoin_core.village_donation_report(conn, village_id))


@app.get("/api/user/birth_chart")
@login_required
def api_user_birth_chart():
    """Birth chart JSON for the logged-in user (never HTML)."""
    user = g.current_user
    try:
        lat = float(user["birth_latitude"]) if user["birth_latitude"] is not None else None
    except (KeyError, TypeError, ValueError):
        lat = None
    try:
        lon = float(user["birth_longitude"]) if user["birth_longitude"] is not None else None
    except (KeyError, TypeError, ValueError):
        lon = None
    try:
        is_admin = bool(int(user["is_admin"] or 0))
    except (KeyError, TypeError, ValueError):
        is_admin = False
    try:
        payload = birth_chart.compute_birth_chart(
            date_of_birth=str(user["date_of_birth"] or "2000-01-01"),
            birth_time=str(user["birth_time"] or "12:00"),
            sun_sign=str(user["sun_sign"] or ""),
            moon_sign=str(user["moon_sign"] or ""),
            latitude=lat,
            longitude=lon,
            private_id=str(user["private_id"] or ""),
            is_admin=is_admin,
        )
    except Exception as exc:
        app.logger.exception("birth chart endpoint failed")
        if birth_chart._is_admin_reference_user(
            str(user["private_id"] or ""),
            str(user["date_of_birth"] or ""),
            str(user["birth_time"] or ""),
            is_admin=is_admin,
        ):
            payload = birth_chart.admin_reference_chart()
        else:
            payload = birth_chart.compute_birth_chart(
                date_of_birth=str(user["date_of_birth"] or "2000-01-01"),
                birth_time=str(user["birth_time"] or "12:00"),
                sun_sign=str(user["sun_sign"] or ""),
                moon_sign=str(user["moon_sign"] or ""),
                latitude=lat,
                longitude=lon,
                private_id=str(user["private_id"] or ""),
                is_admin=is_admin,
            )
        payload["error"] = "Chart calculation failed"
        payload["details"] = str(exc)
    resp = jsonify(payload)
    resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp


@app.get("/api/admin/users/search")
@council_or_admin_required
def api_admin_users_search():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"users": []})
    conn = get_db()
    like = f"%{q}%"
    cur = conn.execute(
        """
        SELECT private_id, public_id, first_name, last_name, account_type
        FROM users
        WHERE public_id LIKE ? COLLATE NOCASE
           OR private_id LIKE ? COLLATE NOCASE
           OR first_name LIKE ? COLLATE NOCASE
           OR last_name LIKE ? COLLATE NOCASE
           OR (first_name || ' ' || last_name) LIKE ? COLLATE NOCASE
        ORDER BY last_name, first_name
        LIMIT 20
        """,
        (like, like, like, like, like),
    )
    users: list[dict[str, Any]] = []
    for r in cur:
        at = str(r["account_type"] or "")
        if _is_demo_account_type(at):
            continue
        users.append(
            {
                "private_id": str(r["private_id"]),
                "public_id": str(r["public_id"]),
                "full_name": f'{r["first_name"] or ""} {r["last_name"] or ""}'.strip(),
                "account_type": at,
            }
        )
    return jsonify({"users": users})


@app.post("/api/admin/upgrade_user")
@council_or_admin_required
def api_admin_upgrade_user():
    return api_upgrade_user()


@app.get("/api/admin/villages/search")
@admin_required
def api_admin_villages_search():
    q = (request.args.get("q") or "").strip()
    conn = get_db()
    if not q:
        return jsonify({"villages": []})
    like = f"%{q}%"
    cur = conn.execute(
        """
        SELECT id, name FROM village
        WHERE id LIKE ? OR name LIKE ?
        ORDER BY name COLLATE NOCASE
        LIMIT 20
        """,
        (like, like),
    )
    return jsonify(
        {
            "villages": [
                {"id": str(r["id"]), "name": str(r["name"] or r["id"])}
                for r in cur
            ]
        }
    )


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
    """Legacy alias — archived posts for the signed-in author."""
    return api_my_posts_previous()


@app.get("/api/my_posts/previous")
@login_required
def api_my_posts_previous():
    conn = get_db()
    _ = conn
    pid = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT id, content, current_level, status, total_score, created_at,
               level_start_time, level_end_time, archived_at_level, previous_levels
        FROM posts
        WHERE user_private_id = ?
          AND status = 'archived'
          AND current_level = 'private_history'
        ORDER BY datetime(COALESCE(level_end_time, created_at)) DESC, id DESC
        LIMIT 100
        """,
        (pid,),
    )
    posts = []
    for r in cur:
        d = dict(r)
        d["archive_label"] = _archived_level_label(r)
        posts.append(d)
    return jsonify({"posts": posts})


@app.get("/api/my_posts/active")
@login_required
def api_my_posts_active():
    conn = get_db()
    _ = conn
    pid = str(g.current_user["private_id"])
    cur = conn.execute(
        """
        SELECT p.*, u.public_id AS author_public_id, u.first_name AS author_first,
               u.last_name AS author_last, u.age AS author_age,
               u.gender AS author_gender, u.current_location_id AS author_current_location_id,
               v.vote_value AS current_user_vote
        FROM posts p
        JOIN users u ON u.private_id = p.user_private_id
        LEFT JOIN post_votes v
          ON v.post_id = p.id AND v.voter_private_id = ?
        WHERE p.user_private_id = ?
          AND p.status = 'live'
          AND p.current_level = 'personal'
        ORDER BY datetime(p.created_at) DESC, p.id DESC
        LIMIT 80
        """,
        (pid, pid),
    )
    rows = list(cur)
    return jsonify(
        {
            "posts": _filter_board_posts(
                rows, conn, g.current_user, "personal", "live"
            ),
        }
    )


@app.get("/api/collective_board")
@login_required
@_api_handle_errors
def api_collective_board():
    conn = get_db()
    level = (request.args.get("level") or "").strip().lower()
    if not user_can_access_collective_board(conn, g.current_user, level):
        return jsonify({"error": "This collective board level is not available for your account."}), 403
    _safe_escalate_posts(conn)

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
@_api_handle_errors
def api_posts():
    conn = get_db()
    level = (request.args.get("level") or "").strip().lower()
    if not user_can_access_collective_board(conn, g.current_user, level):
        return jsonify({"error": "This collective board level is not available for your account."}), 403
    _safe_escalate_posts(conn)

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
    _ = conn
    scope = (request.args.get("scope") or "active").strip().lower()
    if scope in {"previous", "archived", "history"}:
        return api_my_posts_previous()
    if scope in {"active", "current", "live"}:
        return api_my_posts_active()
    return jsonify({"error": "scope must be active or previous"}), 400


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
                "any_collective_board": level not in {"personal", "personal_history", "private_history"}
                and not level.endswith("_frozen")
                and status == "live",
            },
        }
    )


@app.route("/")
def index():
    conn = get_db()
    total_users_earth = count_registered_users(conn)
    total_users_asia = count_homepage_asia_users(conn)
    total_users_india = count_homepage_india_users(conn)

    # Hero stats: villages with at least one resident + Qoins in circulation.
    try:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT TRIM(current_location_id)) AS c
            FROM users
            WHERE TRIM(COALESCE(current_location_id,'')) != ''
            """
        ).fetchone()
        total_villages = int(row["c"]) if row else 0
    except sqlite3.Error:
        total_villages = 0
    try:
        total_qoins = int(qoin_core.circulation_total(conn).get("total_qoins") or 0)
    except sqlite3.Error:
        total_qoins = 0
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
        total_villages=total_villages,
        total_qoins=total_qoins,
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


@app.route("/settings")
def settings_page():
    """Settings placeholder — mother tongue & notification preferences (coming soon)."""
    return render_template("settings.html")


@app.route("/india-explorer")
@login_required
def india_explorer():
    """Council-only screen: full India geography tree with search + stats links."""
    conn = get_db()
    if not is_council_member(conn, g.current_user):
        flash("India Explorer is available to council members only.", "error")
        return redirect(url_for("dashboard"))
    return render_template("india_explorer.html")


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


def _geo_api_language() -> str:
    """Language for geography dropdown labels (?lang= or session/UI default)."""
    from translations import TRANSLATIONS as _TR

    lang = (request.args.get("lang") or "").strip().lower()
    if lang in _TR:
        return lang
    try:
        conn = get_db()
    except Exception:
        conn = None
    return active_ui_language(conn, None)


def _jsonify_localized_geo(
    conn: sqlite3.Connection,
    rows: list[dict[str, str]],
    location_type: str,
) -> list[dict[str, str]]:
    lang = _geo_api_language()
    return language_core.localize_geo_rows(conn, rows, location_type, lang)


@app.route("/api/states")
def api_states():
    conn = get_db()
    cur = conn.execute("SELECT id, name FROM state ORDER BY name COLLATE NOCASE ASC")
    rows = [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
    return jsonify(_jsonify_localized_geo(conn, rows, "state"))


@app.route("/api/country/<country_id>/languages")
def api_country_languages(country_id: str):
    """Languages available for mother-tongue selection in a country."""
    iso = (country_id or "").strip().upper()
    if not iso:
        return jsonify({"error": "country_id is required"}), 400
    conn = get_db()
    element_core.migrate_element_core_schema(conn)
    return jsonify({"languages": element_core.get_country_languages(conn, iso)})


@app.route("/api/country/<country_id>/states")
def api_country_states(country_id: str):
    """States for a country; ``has_states`` false when none are seeded."""
    iso = (country_id or "").strip().upper()
    if not iso:
        return jsonify({"error": "country_id is required"}), 400
    if iso == "IND":
        return jsonify({"country_id": iso, "has_states": False, "states": []})
    conn = get_db()
    return jsonify(global_core.country_states_payload(conn, iso))


@app.get("/api/location/<path:location_id>/details")
def api_location_details(location_id: str):
    """Human-readable path for a village, global state, or country id."""
    conn = get_db()
    lid = (location_id or "").strip()
    if not lid:
        return jsonify({"error": "Missing location id"}), 400

    if village_exists(conn, lid):
        return jsonify(
            {
                "id": lid,
                "type": "village",
                "full_path": location_display_label(conn, lid),
            }
        )

    state_row = conn.execute(
        """
        SELECT sg.name AS state_name, sg.country_id, c.name AS country_name
          FROM states_global sg
          LEFT JOIN country c ON c.id = sg.country_id
         WHERE sg.state_id = ?
        """,
        (lid,),
    ).fetchone()
    if state_row:
        parts = [str(state_row["state_name"] or "").strip()]
        country_name = str(state_row["country_name"] or state_row["country_id"] or "").strip()
        if country_name:
            parts.append(country_name)
        return jsonify(
            {
                "id": lid,
                "type": "global_state",
                "full_path": ", ".join(p for p in parts if p),
            }
        )

    country_row = conn.execute(
        """
        SELECT c.name AS country_name, co.name AS continent_name
          FROM country c
          LEFT JOIN continent co ON co.id = c.continent_id
         WHERE c.id = ?
        """,
        (lid.strip().upper(),),
    ).fetchone()
    if country_row:
        parts = [
            str(country_row["country_name"] or "").strip(),
            str(country_row["continent_name"] or "").strip(),
        ]
        return jsonify(
            {
                "id": lid.strip().upper(),
                "type": "country",
                "full_path": ", ".join(p for p in parts if p),
            }
        )

    return jsonify({"error": "Location not found"}), 404


@app.route("/api/states/<country_id>")
def api_global_states_for_country(country_id: str):
    """Legacy alias — prefer ``/api/country/<id>/states``."""
    iso = (country_id or "").strip().upper()
    if iso == "IND":
        return jsonify({"has_states": False, "states": [], "message": "Use /api/states for India"})
    conn = get_db()
    payload = global_core.country_states_payload(conn, iso)
    return jsonify(payload)


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
        rows = [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
        return jsonify(_jsonify_localized_geo(conn, rows, "district"))
    base = state_raw_to_district_base(raw_path(state_id))
    rows = fetch_direct_children_geo_path(conn, "district", base)
    return jsonify(_jsonify_localized_geo(conn, rows, "district"))


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
        rows = [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
        return jsonify(_jsonify_localized_geo(conn, rows, "tehsil"))
    rows = fetch_direct_children_geo_path(conn, "tehsil", raw_path(district_id))
    return jsonify(_jsonify_localized_geo(conn, rows, "tehsil"))


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
        rows = [{"id": str(r["id"]), "name": str(r["name"])} for r in cur]
        return jsonify(_jsonify_localized_geo(conn, rows, "village"))
    rows = fetch_direct_children_geo_path(conn, "village", raw_path(tehsil_id))
    return jsonify(_jsonify_localized_geo(conn, rows, "village"))


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
@_api_handle_errors
def api_dashboard_public_stats():
    conn = get_db()
    if not identity_core.user_show_public_account(g.current_user):
        return jsonify({"error": "Public Account is not available for your profile."}), 403
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Public timeline requires an India birth or present location."}), 403
    lid = (request.args.get("location_id") or "").strip()
    if not lid:
        lid = present_village_id(g.current_user)
    if not lid:
        return jsonify({"error": "location_id is required"}), 400
    allowed = user_public_allowed_location_ids_present(conn, g.current_user)
    if lid not in allowed:
        return jsonify({"error": "location_id must be your present-location hierarchy"}), 403
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
            "location_mode": "present",
        }
    )


@app.get("/api/location/member_count")
@app.get("/api/location/stats")
@login_required
@_api_handle_errors
def api_location_member_count():
    """Member count for a village/tehsil/district/etc. (JSON alias for dashboard stats)."""
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
    total = int(bundle["total_users"])
    return jsonify(
        {
            "count": total,
            "total_users": total,
            "location_id": lid,
            "scope": scope,
            "gender_counts": {str(r["label"]): int(r["count"]) for r in bundle["gender"]},
            "element_counts": {str(r["label"]): int(r["count"]) for r in bundle["sun_element"]},
            "life_stage_counts": {str(r["label"]): int(r["count"]) for r in bundle["age_group"]},
            "stats_url": build_geo_public_url(scope, lid),
        }
    )


@app.get("/api/dashboard/geo_feed")
@login_required
def api_dashboard_geo_feed():
    conn = get_db()
    if not identity_core.user_show_public_account(g.current_user):
        return jsonify({"error": "Public Account is not available for your profile."}), 403
    if not user_has_full_dashboard(conn, g.current_user):
        return jsonify({"error": "Public timeline requires an India birth or present location."}), 403
    lid = (request.args.get("location_id") or "").strip()
    if not lid:
        return jsonify({"error": "location_id is required"}), 400
    allowed = user_public_allowed_location_ids_present(conn, g.current_user)
    if lid not in allowed:
        return jsonify({"error": "location_id must be your present-location hierarchy"}), 403
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
    return _api_global_stats_response()


@app.get("/api/global/stats")
@login_required
def api_global_stats():
    """Alias for dashboard global statistics (Earth / Continent / Country / Zone)."""
    return _api_global_stats_response()


def _api_global_stats_response():
    conn = get_db()
    _ = conn
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

    zone_name: str | None = None
    zone_code: str | None = None
    if scope == "zone":
        rp = raw_path(geo_id)
        if "." in rp:
            zone_code = rp.split(".", 1)[1].upper()
        zone_name = INDIA_ZONE_NAMES.get(zone_code or "", zone_code)
        if _geo_table_exists(conn, "zone"):
            meta = _geo_row_optional_meta(conn, "zone", geo_id)
            if meta.get("name"):
                zone_name = str(meta["name"])

    return jsonify(
        {
            "total_users": bundle["total_users"],
            "gender_counts": {str(r["label"]): int(r["count"]) for r in bundle["gender"]},
            "element_counts": {str(r["label"]): int(r["count"]) for r in bundle["sun_element"]},
            "life_stage_counts": {str(r["label"]): int(r["count"]) for r in bundle["age_group"]},
            "stats_url": build_geo_public_url(scope, url_id),
            "scope": scope,
            "zone_name": zone_name,
            "zone_code": zone_code,
        }
    )


@app.get("/api/messages/unread_count")
@login_required
def api_messages_unread_count():
    conn = get_db()
    me = str(g.current_user["private_id"])
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM messages
         WHERE recipient_id = ? COLLATE NOCASE
           AND is_draft = 0
           AND is_deleted_by_recipient = 0
           AND read_at IS NULL
        """,
        (me,),
    ).fetchone()
    return jsonify({"unread_count": int(row["c"]) if row else 0})


@app.get("/api/messages")
@login_required
def api_messages_folder():
    """Unified folder fetch: ``?folder=inbox|sent|drafts``."""
    conn = get_db()
    me = str(g.current_user["private_id"])
    folder = (request.args.get("folder") or "inbox").strip().lower()
    if folder == "sent":
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
    elif folder == "drafts":
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
    else:
        folder = "inbox"
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
    return jsonify(
        {
            "folder": folder,
            "messages": [_message_row_to_dict(r) for r in cur],
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
        """
        SELECT private_id FROM users
         WHERE private_id = ? COLLATE NOCASE
            OR public_id = ? COLLATE NOCASE
        """,
        (recipient_raw, recipient_raw),
    ).fetchone()
    if not row_r:
        return jsonify({"error": "Recipient Private ID or Public ID not found"}), 400
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


@app.route("/api/registration-stats")
def registration_stats():
    conn = get_db()
    return jsonify(registration_stats_bundle(conn))


@app.route("/register", methods=["GET", "POST"])
def register():
    # Registration page is always English — mother tongue is stored for dashboard only.
    session["preferred_language"] = "en"
    g.ui_language = "en"

    conn = get_db()
    global_core.migrate_global_location_schema(conn)
    element_core.migrate_element_core_schema(conn)
    continents_form: list[dict[str, str]] = []
    if _geo_table_exists(conn, "continent"):
        continents_form = [
            {"id": str(r["id"]), "name": str(r["name"])}
            for r in conn.execute(
                "SELECT id, name FROM continent ORDER BY name COLLATE NOCASE"
            )
        ]

    language_choices = language_core.all_language_choices(conn)

    if request.method == "GET":
        ref_prefill = referral_core.normalize_referral_code(
            request.args.get("ref") or ""
        )
        form_prefill = {"referral_code": ref_prefill} if ref_prefill else {}
        ref_locked = bool(request.args.get("ref"))
        ref_referrer_name = ""
        if ref_prefill:
            ref_validation = referral_core.validate_referral_code(conn, ref_prefill)
            if ref_validation.get("valid"):
                ref_referrer_name = str(ref_validation.get("referrer_name") or "")
        return render_template(
            "register.html",
            gender_options=GENDER_OPTIONS,
            continents=continents_form,
            language_choices=language_choices,
            form=form_prefill,
            errors=None,
            field_errors=None,
            new_private_id=None,
            new_public_id=None,
            show_donation_step=False,
            pending_registration=False,
            ref_locked=ref_locked,
            ref_referrer_name=ref_referrer_name,
        )

    form = dict(request.form)
    errors: list[str] = []
    field_errors: dict[str, str] = {}

    def add_error(field: str, message: str) -> None:
        errors.append(message)
        if field not in field_errors:
            field_errors[field] = message

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
    phone_raw = (form.get("phone") or "").strip() or None
    password = form.get("password") or ""
    confirm = form.get("confirm_password") or ""
    mother_tongue_code = (form.get("mother_tongue_code") or "").strip().lower() or None
    mother_tongue_name = None
    if mother_tongue_code and birth_ctry:
        ok_mt, mt_name = element_core.mother_tongue_allowed(conn, birth_ctry, mother_tongue_code)
        if not ok_mt:
            add_error(
                "mother_tongue_code",
                "Invalid mother tongue selection for the selected birth country.",
            )
        else:
            mother_tongue_name = mt_name
            if not mother_tongue_name:
                for ch in language_choices:
                    if ch["code"] == mother_tongue_code:
                        mother_tongue_name = ch["name"]
                        break
    elif mother_tongue_code:
        for ch in language_choices:
            if ch["code"] == mother_tongue_code:
                mother_tongue_name = ch["name"]
                break
        if not mother_tongue_name:
            mother_tongue_code = None

    if email_raw and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_raw):
        add_error("email", "Please enter a valid email address.")

    if phone_raw and len(re.sub(r"\D", "", phone_raw)) < 10:
        add_error("phone", "Please enter a valid phone number (at least 10 digits).")

    if not first_name:
        add_error("first_name", "First name is required.")
    if not last_name:
        add_error("last_name", "Last name is required.")

    if gender not in GENDER_OPTIONS:
        add_error("gender", "Please choose a valid gender option.")

    dob_dt = parse_date_iso(dob_s)
    if not dob_dt:
        add_error("date_of_birth", "Please enter a valid date of birth.")

    if not birth_time:
        add_error("birth_time", "Birth time is required.")
    else:
        m_time = re.match(r"^(\d{2}:\d{2})", birth_time)
        if not m_time:
            add_error("birth_time", "Birth time must be in HH:MM format.")
        else:
            birth_time = m_time.group(1)

    if not birth_cont or not birth_ctry:
        add_error("birth_continent_id", "Birth continent and country are required.")
    elif not _continent_country_valid(conn, birth_cont, birth_ctry):
        add_error("birth_country_id", "Invalid birth continent or country combination.")

    if not curr_cont or not curr_ctry:
        add_error("current_continent_id", "Current continent and country are required.")
    elif not _continent_country_valid(conn, curr_cont, curr_ctry):
        add_error(
            "current_country_id",
            "Invalid current continent or country combination.",
        )

    if birth_ctry == "IND":
        if not birth_loc:
            add_error("birth_village", "For birth in India, select state through village.")
        elif not village_exists(conn, birth_loc):
            add_error("birth_village", "Invalid birth village selection.")
    else:
        birth_loc = None
        birth_global_state = (form.get("birth_global_state_id") or "").strip()
        if global_core.country_has_states(conn, birth_ctry):
            if not birth_global_state:
                add_error(
                    "birth_global_state_id",
                    "Select your birth state or province.",
                )
            elif not conn.execute(
                "SELECT 1 FROM states_global WHERE state_id = ?",
                (birth_global_state,),
            ).fetchone():
                add_error("birth_global_state_id", "Invalid birth state selection.")

    if curr_ctry == "IND":
        if not curr_loc:
            add_error(
                "current_village",
                "For current residence in India, select state through village.",
            )
        elif not village_exists(conn, curr_loc):
            add_error("current_village", "Invalid current village selection.")
    else:
        curr_loc = None
        curr_global_state = (form.get("current_global_state_id") or "").strip()
        if global_core.country_has_states(conn, curr_ctry):
            if not curr_global_state:
                add_error(
                    "current_global_state_id",
                    "Select your current state or province.",
                )
            elif not conn.execute(
                "SELECT 1 FROM states_global WHERE state_id = ?",
                (curr_global_state,),
            ).fetchone():
                add_error("current_global_state_id", "Invalid current state selection.")

    if len(password) < 9:
        add_error("password", "Password must be at least 9 characters.")
    else:
        ok_pw, pw_msg = validate_password_strength(password)
        if not ok_pw:
            add_error("password", pw_msg)
    if password != confirm:
        add_error("confirm_password", "Password and confirmation do not match.")

    referral_code_input = referral_core.normalize_referral_code(
        (form.get("referral_code") or request.args.get("ref") or "").strip()
    )
    referred_by_private_id: str | None = None
    referral_warning: str | None = None
    is_indian = curr_ctry == "IND"
    if referral_code_input:
        referred_by_private_id = referral_core.lookup_referrer_by_code(
            conn, referral_code_input
        )
        if not referred_by_private_id:
            referral_warning = (
                "Invalid referral code. You can still register without it."
            )
            if not is_indian:
                add_error(
                    "referral_code",
                    "Referral code not found or inactive.",
                )

    if dob_dt:
        age = compute_age(dob_dt)
        if age > 130:
            add_error("date_of_birth", "Age out of supported range.")

    if errors or not dob_dt:
        _enrich_register_form_geo(conn, form)
        return render_template(
            "register.html",
            gender_options=GENDER_OPTIONS,
            continents=continents_form,
            language_choices=language_choices,
            form=form,
            errors=errors,
            field_errors=field_errors,
            new_private_id=None,
            new_public_id=None,
            show_donation_step=False,
            pending_registration=False,
        )

    dob_iso = dob_dt.strftime("%Y-%m-%d")
    age = compute_age(dob_dt)
    agroup = age_group_from_age(age)
    sun = sun_sign_for_date(dob_dt)
    moon = moon_sign_simplified(dob_dt)
    elem = element_for_sun(sun)

    legacy_country_text = "India" if curr_ctry == "IND" else "Other"

    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

    pending = {
        "first_name": first_name,
        "last_name": last_name,
        "gender": gender,
        "dob_iso": dob_iso,
        "birth_time": birth_time,
        "age": age,
        "agroup": agroup,
        "sun": sun,
        "moon": moon,
        "elem": elem,
        "birth_loc": birth_loc,
        "curr_loc": curr_loc,
        "birth_global_state_id": (form.get("birth_global_state_id") or "").strip() or None,
        "current_global_state_id": (form.get("current_global_state_id") or "").strip() or None,
        "birth_cont": birth_cont,
        "birth_ctry": birth_ctry,
        "curr_cont": curr_cont,
        "curr_ctry": curr_ctry,
        "legacy_country_text": legacy_country_text,
        "email_raw": email_raw,
        "phone_raw": phone_raw,
        "password_hash": pw_hash,
        "mother_tongue_code": mother_tongue_code,
        "mother_tongue_name": mother_tongue_name,
        "referred_by_private_id": referred_by_private_id,
        "referral_code_input": referral_code_input,
        "referral_warning": referral_warning,
    }

    if is_indian:
        session["pending_registration"] = pending
        session.permanent = True
        if referral_warning:
            flash(referral_warning, "warning")
        _enrich_register_form_geo(conn, form)
        return render_template(
            "register.html",
            gender_options=GENDER_OPTIONS,
            continents=continents_form,
            language_choices=language_choices,
            form=form,
            errors=None,
            field_errors=None,
            new_private_id=None,
            new_public_id=None,
            show_donation_step=True,
            pending_registration=True,
        )

    try:
        private_id, public_id = _finalize_registration(conn, pending)
        if referred_by_private_id:
            loc_ctx = donation_location_context(
                conn,
                village_id=str(curr_loc or birth_loc or ""),
                country_id=curr_ctry,
                continent_id=curr_cont,
            )
            distribution = donation_core.calculate_donation_distribution(
                0,
                location_context=loc_ctx,
                referrer_private_id=referred_by_private_id,
                new_user_private_id=private_id,
            )
            donation_core.store_pending_distribution(
                conn,
                new_user_private_id=private_id,
                referrer_private_id=referred_by_private_id,
                donation_amount=0,
                distribution=distribution,
                payment_method="none",
            )
            conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        errors.append("Could not create account. Try again.")
        _enrich_register_form_geo(conn, form)
        return render_template(
            "register.html",
            gender_options=GENDER_OPTIONS,
            continents=continents_form,
            language_choices=language_choices,
            form=form,
            errors=errors,
            field_errors=field_errors,
            new_private_id=None,
            new_public_id=None,
            show_donation_step=False,
            pending_registration=False,
        )

    session.pop("pending_registration", None)
    # Show the "save your IDs" screen instead of auto-login: the user must
    # confirm they saved their Private ID before proceeding to login.
    return render_template(
        "register.html",
        gender_options=GENDER_OPTIONS,
        continents=continents_form,
        language_choices=language_choices,
        form=form,
        errors=[],
        field_errors={},
        new_private_id=private_id,
        new_public_id=public_id,
        show_donation_step=False,
        pending_registration=False,
    )


def generate_9_digit_private_id(conn: sqlite3.Connection) -> str:
    """Generate a unique human Private ID: HU- + 9 digits."""
    for _ in range(100_000):
        digits = str(secrets.randbelow(900_000_000) + 100_000_000)
        candidate = f"{HUMAN_PRIVATE_ID_PREFIX}{digits}"
        row = conn.execute(
            "SELECT 1 FROM users WHERE private_id = ? COLLATE NOCASE",
            (candidate,),
        ).fetchone()
        if not row:
            return candidate
    raise RuntimeError("Could not allocate a unique HU- private ID")


def format_human_private_id(digits: str) -> str:
    """Normalize 9-digit numeric string to HU- prefixed Private ID."""
    d = str(digits or "").strip()
    if d.upper().startswith(HUMAN_PRIVATE_ID_PREFIX):
        return f"{HUMAN_PRIVATE_ID_PREFIX}{d[3:]}"
    return f"{HUMAN_PRIVATE_ID_PREFIX}{d}"


def generate_unique_private_id(conn: sqlite3.Connection) -> str:
    """Alias for generate_9_digit_private_id."""
    return generate_9_digit_private_id(conn)


def _user_account_status(user: dict[str, Any] | sqlite3.Row) -> str:
    return str(_row_get(user, "account_status", "active") or "active").strip().lower()


def _account_has_limited_access(user: dict[str, Any] | sqlite3.Row) -> bool:
    return _user_account_status(user) in (
        "pending_verification",
        "verification_failed",
    )


def _account_features_for_status(status: str) -> dict[str, bool]:
    limited = status in ("pending_verification", "verification_failed")
    return {
        "view_profile": True,
        "view_donations": True,
        "submit_vote": not limited,
        "withdraw_funds": not limited,
    }


def _dashboard_banner_for_status(
    status: str,
    *,
    txn_reference: str = "",
    failure_reason: str = "",
) -> str:
    if status == "pending_verification":
        return "Account pending verification. Some features limited."
    if status == "verification_failed":
        return "Verification failed. Please retry payment."
    return ""


def _send_account_notification(
    email: str | None,
    phone: str | None,
    notification_type: str,
    *,
    reason: str = "",
) -> None:
    """Send SMS and email for registration / verification lifecycle events."""
    templates = {
        "registration_pending": {
            "sms": (
                "Your Qumanity account is created. Verification pending. "
                "Thank you for your donation."
            ),
            "email_subject": "Welcome to Qumanity — verification pending",
            "email_body": (
                "Welcome to Qumanity! Your account is pending admin verification. "
                "You can log in with your Private ID while we confirm your donation."
            ),
        },
        "verified": {
            "sms": (
                "Your Qumanity account is verified and activated! "
                "Welcome to the community."
            ),
            "email_subject": "Account Activated!",
            "email_body": (
                "Account Activated! Your Qumanity membership is now permanent."
            ),
        },
        "failed": {
            "sms": (
                "Your donation verification failed. Please visit Qumanity to retry."
            ),
            "email_subject": "Verification Failed",
            "email_body": (
                "Verification Failed. Please retry your donation."
                + (f"\n\nReason: {reason}" if reason else "")
            ),
        },
    }
    tpl = templates.get(notification_type)
    if not tpl:
        return
    if phone:
        identity_core.send_sms_notification(phone, tpl["sms"])
    if email:
        identity_core.send_email_notification(
            email,
            tpl["email_subject"],
            tpl["email_body"],
        )


def _notify_user_verification_event(
    conn: sqlite3.Connection,
    user_private_id: str,
    event: str,
    *,
    reason: str = "",
) -> None:
    row = conn.execute(
        "SELECT id, email, phone FROM users WHERE private_id = ?",
        (str(user_private_id).strip(),),
    ).fetchone()
    if not row:
        return
    _send_account_notification(
        str(row["email"] or "") or None,
        str(row["phone"] or "") or None,
        event,
        reason=reason,
    )
    sita_platform_core._record_notification(
        conn,
        user_private_id,
        "both",
        event,
        reason or event,
    )


def _finalize_registration(
    conn: sqlite3.Connection,
    pending: dict[str, Any],
    *,
    account_status: str = "active",
    temp_access: bool = False,
) -> tuple[str, str]:
    """Create user account and wallet. Returns (private, public)."""
    birth_path = identity_core.location_path_for_id(
        pending.get("birth_loc"),
        country_id=pending.get("birth_ctry"),
    )
    present_path = identity_core.location_path_for_id(
        pending.get("curr_loc"),
        country_id=pending.get("curr_ctry"),
    )
    _structured_private_id, public_id = identity_core.generate_unique_ids(
        conn,
        pending["first_name"],
        pending["last_name"],
        pending["gender"],
        pending["agroup"],
        pending["sun"],
        birth_path,
        present_path,
    )
    # Login identity is a unique 9-digit number; the structured format is kept
    # only for the public (account) ID.
    private_id = generate_9_digit_private_id(conn)
    status_norm = (account_status or "active").strip().lower()
    if status_norm not in ("active", "pending_verification", "verification_failed", "suspended"):
        status_norm = "active"
    conn.execute(
        """
        INSERT INTO users (
            private_id, public_id, first_name, last_name, gender,
            date_of_birth, birth_time, age, age_group,
            sun_sign, moon_sign, element,
            birth_location_id, current_location_id,
            birth_continent_id, birth_country_id,
            current_continent_id, current_country_id,
            birth_global_state_id, current_global_state_id,
            country, email, phone, password_hash,
            mother_tongue_code, mother_tongue_name,
            account_type, is_active, account_status, temp_access
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'H_U', 1, ?, ?)
        """,
        (
            private_id,
            public_id,
            pending["first_name"],
            pending["last_name"],
            pending["gender"],
            pending["dob_iso"],
            pending["birth_time"],
            pending["age"],
            pending["agroup"],
            pending["sun"],
            pending["moon"],
            pending["elem"],
            pending.get("birth_loc"),
            pending.get("curr_loc"),
            pending.get("birth_cont"),
            pending.get("birth_ctry"),
            pending.get("curr_cont"),
            pending.get("curr_ctry"),
            pending.get("birth_global_state_id"),
            pending.get("current_global_state_id"),
            pending.get("legacy_country_text"),
            pending.get("email_raw"),
            pending.get("phone_raw"),
            pending["password_hash"],
            pending.get("mother_tongue_code"),
            pending.get("mother_tongue_name"),
            status_norm,
            1 if temp_access or status_norm == "pending_verification" else 0,
        ),
    )
    identity_core.register_user_accounts(
        conn,
        user_private_id=private_id,
        public_id=public_id,
        birth_location_id=pending.get("birth_loc"),
        present_location_id=pending.get("curr_loc"),
        birth_path=birth_path,
        present_path=present_path,
    )
    qoin_core.ensure_wallet(conn, "user", private_id)
    referral_code = referral_core.generate_referral_code(conn)
    conn.execute(
        "UPDATE users SET referral_code = ? WHERE private_id = ?",
        (referral_code, private_id),
    )
    referred_by = pending.get("referred_by_private_id")
    if referred_by and referred_by != private_id:
        referral_core.create_pending_referral(conn, str(referred_by), private_id)
    conn.execute(
        """
        UPDATE users SET current_age_category = ? WHERE private_id = ?
        """,
        (pending["agroup"], private_id),
    )
    try:
        planetary_core.save_user_birth_planets(
            conn,
            private_id,
            date_of_birth=str(pending["dob_iso"]),
            birth_time=str(pending.get("birth_time") or "12:00"),
        )
    except Exception:
        app.logger.exception("birth planet calculation failed for %s", private_id)
    conn.commit()
    if status_norm == "pending_verification":
        _send_account_notification(
            pending.get("email_raw"),
            pending.get("phone_raw"),
            "registration_pending",
        )
        id_msg = (
            f"Welcome to Qumanity, {pending['first_name']}!\n\n"
            f"Private ID (9-digit login): {private_id}\n"
            f"Public ID (Account ID): {public_id}\n\n"
            "Your account is pending admin verification. "
            "Save your Private ID — you need it to log in."
        )
        if pending.get("email_raw"):
            identity_core.send_email_notification(
                pending.get("email_raw"),
                "Your Qumanity IDs — verification pending",
                id_msg,
            )
    else:
        identity_core.notify_user_ids(
            email=pending.get("email_raw"),
            phone=pending.get("phone_raw"),
            private_id=private_id,
            public_id=public_id,
            first_name=pending["first_name"],
        )
    return private_id, public_id


def _finalize_registration_with_donation(
    conn: sqlite3.Connection,
    pending: dict[str, Any],
    donation_rupees: int,
    *,
    method: str = "upi",
    agent_private_id: str | None = None,
) -> tuple[str, str]:
    """Create account and store pending 10-tier distribution (credited after first vote)."""
    referrer_private_id = str(pending.get("referred_by_private_id") or "").strip()
    pending_verify = (
        method == "qr"
        and int(donation_rupees) > 0
        and session.get("qr_txn_submitted")
    )
    account_status = "pending_verification" if pending_verify else "active"
    private_id, public_id = _finalize_registration(
        conn,
        pending,
        account_status=account_status,
        temp_access=pending_verify,
    )
    village_id = str(pending.get("curr_loc") or pending.get("birth_loc") or "").strip()
    loc_ctx = donation_location_context(
        conn,
        village_id=village_id,
        country_id=str(pending.get("curr_ctry") or "IND"),
        continent_id=str(pending.get("curr_cont") or ""),
    )
    referral_code_input = str(pending.get("referral_code_input") or "").strip()
    if not referrer_private_id:
        donation_core.process_no_referral_registration(
            conn,
            user_private_id=private_id,
            donation_amount_rupees=int(donation_rupees),
            location_context=loc_ctx,
            payment_method=method,
            referral_code=referral_code_input,
        )
    else:
        distribution = donation_core.calculate_donation_distribution(
            int(donation_rupees),
            location_context=loc_ctx,
            referrer_private_id=referrer_private_id,
            new_user_private_id=private_id,
        )
        donation_core.store_pending_distribution(
            conn,
            new_user_private_id=private_id,
            referrer_private_id=referrer_private_id,
            donation_amount=int(donation_rupees),
            distribution=distribution,
            payment_method=method,
            agent_private_id=agent_private_id,
        )
    if referrer_private_id:
        vol = referral_core.lookup_active_volunteer_by_private_id(
            conn, referrer_private_id
        )
        if vol:
            distribution = donation_core.calculate_donation_distribution(
                int(donation_rupees),
                location_context=loc_ctx,
                referrer_private_id=referrer_private_id,
                new_user_private_id=private_id,
            )
            ref_earn = sum(
                int(i.get("rupee_amount") or 0)
                for i in distribution
                if str(i.get("tier")) == "referrer"
            )
            referral_core.record_volunteer_signup(
                conn,
                volunteer_private_id=referrer_private_id,
                earnings_rupees=ref_earn,
            )
    if method == "cash" and agent_private_id and donation_rupees > 0:
        agent_row = conn.execute(
            "SELECT public_id FROM users WHERE private_id = ?",
            (agent_private_id,),
        ).fetchone()
        if agent_row:
            qoin_core.record_cash_donation(
                conn,
                donor_private_id=private_id,
                agent_public_id=str(agent_row["public_id"]),
                amount_rupees=int(donation_rupees),
            )
    if donation_rupees > 0:
        pending_donation_id = session.get("pending_donation_id")
        if pending_donation_id:
            sita_platform_core.link_donation_to_user(
                conn,
                int(pending_donation_id),
                private_id,
                public_id,
            )
        else:
            pay_method = "qr_code" if method == "qr" else "cash"
            donation_status = "pending" if pay_method == "qr_code" else "confirmed"
            sita_platform_core.record_donation(
                conn,
                user_private_id=private_id,
                user_public_id=public_id,
                amount=int(donation_rupees),
                payment_method=pay_method,
                referral_id=agent_private_id or referrer_private_id or None,
                status=donation_status,
            )
    session.pop("pending_donation_id", None)
    session.pop("pending_donation_marker", None)
    conn.commit()
    return private_id, public_id


@app.route("/donation-required")
def donation_required():
    return redirect(url_for("register_donation"))


@app.route("/register/donation", methods=["GET"])
def register_donation():
    pending = session.get("pending_registration")
    if not pending:
        flash("Complete the registration form first.", "error")
        return redirect(url_for("register"))
    return render_template(
        "register_donation.html",
        donation_amounts=[1, 2, 5, 10, 20, 50, 100, 200, 500],
        pending_name=pending.get("first_name", ""),
    )


@app.get("/api/user/dashboard-status")
@login_required
def api_user_dashboard_status():
    """Account verification status and feature flags for dashboard UI."""
    conn = get_db()
    user = g.current_user
    status = _user_account_status(user)
    txn_reference = ""
    failure_reason = str(_row_get(user, "verification_failed_reason", "") or "").strip()
    if status in ("pending_verification", "verification_failed"):
        row = conn.execute(
            """
            SELECT upi_txn_reference, verification_status
            FROM donations
            WHERE user_private_id = ?
            ORDER BY datetime(created_at) DESC
            LIMIT 1
            """,
            (str(user["private_id"]),),
        ).fetchone()
        if row:
            txn_reference = str(row["upi_txn_reference"] or "").strip()
    return jsonify(
        {
            "account_status": status,
            "banner": _dashboard_banner_for_status(
                status,
                txn_reference=txn_reference,
                failure_reason=failure_reason,
            ),
            "can_access": True,
            "txn_reference": txn_reference,
            "failure_reason": failure_reason,
            "features": _account_features_for_status(status),
        }
    )


@app.post("/api/donation/retry")
@login_required
def api_donation_retry():
    """Start a new QR donation flow after verification failure."""
    user = g.current_user
    if _user_account_status(user) != "verification_failed":
        return jsonify({"error": "Retry is only available after verification failure"}), 400
    payload = request.get_json(silent=True) or {}
    try:
        amount = int(payload.get("amount", 50))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400
    if amount < 1 or amount > 200:
        return jsonify({"error": "Donation must be between ₹1 and ₹200"}), 400
    conn = get_db()
    pid = str(user["private_id"])
    pub = str(user["public_id"])
    donation_id = sita_platform_core.record_donation(
        conn,
        user_private_id=pid,
        user_public_id=pub,
        amount=amount,
        payment_method="bank_qr",
        status="pending",
        payment_status="pending",
        amount_paise=amount * 100,
    )
    txn_ref = f"QUM{donation_id}"
    conn.execute(
        "UPDATE donations SET transaction_id = ? WHERE id = ?",
        (txn_ref, int(donation_id)),
    )
    conn.execute(
        """
        UPDATE users
        SET account_status = 'pending_verification',
            temp_access = 1,
            verification_failed_reason = NULL
        WHERE private_id = ?
        """,
        (pid,),
    )
    conn.commit()
    qr_image = url_for("static", filename="images/SitaFoundation Donate.jpg")
    return jsonify(
        {
            "success": True,
            "donation_id": donation_id,
            "amount": amount,
            "qr_image": qr_image,
            "bank_details": {
                "bank": getattr(config, "DONATION_BANK", "State Bank of India"),
                "upi": getattr(config, "DONATION_UPI_DISPLAY", "41711366837@sbi"),
                "account": getattr(config, "DONATION_BANK_ACCOUNT", "41711366837"),
                "ifsc": getattr(config, "DONATION_IFSC", "SBIN0011551"),
                "organisation": getattr(config, "DONATION_BANK_NAME", "SITA Foundation"),
            },
        }
    )


@app.post("/api/register/donate")
def api_register_donate():
    pending = session.get("pending_registration")
    if not pending:
        return jsonify({"error": "No pending registration. Complete the form first."}), 400
    payload = request.get_json(silent=True) or {}
    try:
        amount = int(payload.get("amount") if payload.get("amount") is not None else payload.get("donation_amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400
    if amount < 0 or amount > 200:
        return jsonify({"error": "Donation must be between ₹0 and ₹200"}), 400
    method = str(payload.get("method") or payload.get("payment_method") or "qr").strip().lower()
    allowed_methods = ("qr", "cash")
    if method not in allowed_methods:
        return jsonify({"error": "method must be one of: " + ", ".join(allowed_methods)}), 400
    agent_private_id = str(
        payload.get("agent_private_id") or payload.get("agent_id") or ""
    ).strip()
    referral_code = str(payload.get("referral_code") or "").strip()
    conn = get_db()
    if method == "cash":
        if referral_code:
            ref_result = referral_core.validate_referral_code(conn, referral_code)
            if not ref_result.get("valid"):
                return jsonify({"error": ref_result.get("error") or "Invalid Referral ID"}), 400
            agent_private_id = str(ref_result.get("referrer_private_id") or "")
        elif agent_private_id:
            if not referral_core.lookup_active_volunteer_by_private_id(conn, agent_private_id):
                return jsonify({"error": "Private ID must belong to an active volunteer"}), 400
        else:
            return jsonify({"error": "Referral ID is required for cash payments"}), 400
    elif method == "qr" and amount > 0:
        pending_donation_id = session.get("pending_donation_id")
        if not pending_donation_id:
            return jsonify(
                {"error": "Submit your UPI transaction reference after paying."}
            ), 400
        if not session.get("qr_txn_submitted"):
            return jsonify(
                {
                    "error": (
                        "Enter your UPI transaction reference after paying "
                        "before submitting registration."
                    ),
                }
            ), 400
        donation_row = sita_platform_core.get_donation(conn, int(pending_donation_id))
        if not donation_row:
            return jsonify({"error": "Payment record not found."}), 400
        pay_status = sita_platform_core._payment_status_for_row(donation_row)
        if pay_status not in ("pending_verification", "completed"):
            return jsonify(
                {
                    "error": "Payment reference not accepted. Check your transaction ID.",
                    "payment_status": pay_status,
                }
            ), 400
    pending_verify = (
        method == "qr"
        and amount > 0
        and session.get("qr_txn_submitted")
    )
    try:
        private_id, public_id = _finalize_registration_with_donation(
            conn,
            pending,
            amount,
            method=method,
            agent_private_id=agent_private_id if method == "cash" else None,
        )
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"error": "Could not create account. Try again."}), 400
    except ValueError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    session.pop("pending_registration", None)
    session.pop("pending_donation_id", None)
    session.pop("pending_donation_marker", None)
    session.pop("bank_qr_payment_confirmed", None)
    session.pop("qr_txn_submitted", None)
    account_status = "pending_verification" if pending_verify else "active"
    message = (
        "Account created! Your donation is pending admin verification. "
        "You can log in with limited access until verified."
        if pending_verify
        else (
            "Account created! Your rewards will be credited after your first "
            "village election vote."
        )
    )
    return jsonify(
        {
            "ok": True,
            "private_id": private_id,
            "public_id": public_id,
            "account_status": account_status,
            "message": message,
            "redirect": url_for("login"),
        }
    )


@app.route("/sita-foundation")
def sita_foundation_page():
    return render_template("sita_foundation.html")


@app.post("/webhook/donation")
def donation_webhook():
    """Razorpay webhook — confirms donations when payment.captured fires."""
    payload_bytes = request.get_data()
    webhook_signature = (request.headers.get("X-Razorpay-Signature") or "").strip()
    secret = getattr(config, "RAZORPAY_WEBHOOK_SECRET", "") or ""
    if secret:
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not webhook_signature or not hmac.compare_digest(
            expected_signature, webhook_signature
        ):
            return jsonify({"error": "Invalid signature"}), 401
    try:
        data = json.loads(payload_bytes.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON"}), 400
    event = str(data.get("event") or "").strip()
    conn = get_db()
    handled = sita_platform_core.process_razorpay_webhook(conn, event, data)
    conn.commit()
    if event in (
        "payment.captured",
        "payment.failed",
        "payment.authorized",
        "qr_code.credited",
    ) and not handled:
        app.logger.warning("Webhook: no matching pending donation for event %s", event)
    return jsonify({"status": "success"}), 200


@app.get("/api/registration/status/<int:donation_id>")
def api_registration_status(donation_id: int):
    """Alias for registration payment polling (same as donation status)."""
    return api_donation_status(donation_id)


@app.get("/api/donation/status/<int:donation_id>")
def api_donation_status(donation_id: int):
    """Poll donation status during registration (session-bound) or for logged-in owner."""
    conn = get_db()
    row = sita_platform_core.get_donation(conn, donation_id)
    if not row:
        return jsonify({"error": "Not found"}), 404
    allowed = False
    if session.get("pending_donation_id") == donation_id:
        allowed = True
    elif getattr(g, "current_user", None):
        if str(g.current_user["private_id"]) == str(row["user_private_id"]):
            allowed = True
        elif str(row["user_private_id"]).startswith(sita_platform_core.PENDING_USER_PREFIX):
            marker = session.get("pending_donation_marker")
            if marker and str(row["user_private_id"]) == (
                f"{sita_platform_core.PENDING_USER_PREFIX}{marker}"
            ):
                allowed = True
    if not allowed:
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(sita_platform_core.get_donation_status_payload(conn, donation_id))


@app.post("/api/donation/verify-registration")
def api_donation_verify_registration():
    """Verify Razorpay payment client-side and confirm pending registration donation."""
    if not session.get("pending_registration"):
        return jsonify({"error": "No pending registration"}), 400
    data = request.get_json(silent=True) or {}
    donation_id = session.get("pending_donation_id") or data.get("donation_id")
    payment_id = str(data.get("razorpay_payment_id") or data.get("payment_id") or "").strip()
    order_id = str(data.get("razorpay_order_id") or data.get("order_id") or "").strip()
    signature = str(data.get("razorpay_signature") or data.get("signature") or "").strip()
    if not donation_id:
        return jsonify({"error": "donation_id required"}), 400
    if not all([payment_id, order_id, signature]):
        return jsonify({"error": "payment_id, order_id, and signature are required"}), 400
    try:
        _verify_razorpay_payment(payment_id, order_id, signature)
    except Exception as exc:
        return jsonify({"error": f"Payment verification failed: {exc}"}), 400
    conn = get_db()
    ok = sita_platform_core.confirm_donation_from_razorpay(
        conn,
        int(donation_id),
        razorpay_payment_id=payment_id,
        razorpay_order_id=order_id,
        confirmed_by="razorpay_client",
    )
    if not ok:
        return jsonify({"error": "Donation not found"}), 404
    conn.commit()
    return jsonify(
        {
            "ok": True,
            **sita_platform_core.get_donation_status_payload(conn, int(donation_id)),
        }
    )


@app.post("/api/donation/record")
@login_required
def api_donation_record():
    data = request.get_json(silent=True) or {}
    user_row = g.current_user
    try:
        amount = int(data.get("amount") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400
    if amount < 0 or amount > 200:
        return jsonify({"error": "amount must be between 0 and 200"}), 400
    method = str(data.get("payment_method") or data.get("method") or "qr_code").strip().lower()
    if method == "qr":
        method = "qr_code"
    referral_id = str(data.get("referral_id") or data.get("referral_code") or "").strip() or None
    status = "pending" if method == "qr_code" and amount > 0 else "confirmed"
    conn = get_db()
    donation_id = sita_platform_core.record_donation(
        conn,
        user_private_id=str(user_row["private_id"]),
        user_public_id=str(user_row["public_id"]),
        amount=amount,
        payment_method=method,
        referral_id=referral_id,
        status=status if amount > 0 else "confirmed",
    )
    conn.commit()
    return jsonify({"ok": True, "donation_id": donation_id, "status": status})


@app.get("/api/donation/history")
@login_required
def api_donation_history():
    conn = get_db()
    payload = sita_platform_core.user_donation_history(conn, str(g.current_user["private_id"]))
    return jsonify(payload)


@app.get("/api/donation/admin/list")
@login_required
def api_donation_admin_list():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    return jsonify(sita_platform_core.admin_donation_list(conn))


@app.route("/admin/panel")
@login_required
def admin_panel():
    """Standalone admin tools page (moved from private account dashboard)."""
    conn = get_db()
    user_row = g.current_user
    is_council = is_council_member(conn, user_row)
    is_mentor = deceased_core.is_mentor_user(conn, user_row)
    is_admin = is_admin_user(user_row)
    if not (is_admin or is_council or is_mentor):
        flash("Admin access required.", "error")
        return redirect(url_for("dashboard"))

    preferred_lang = active_ui_language(conn, user_row)
    current_hierarchy, default_vid = public_hierarchy_for_user(
        conn, user_row, language_code=preferred_lang
    )
    geo_displays = user_dashboard_geo_displays(conn, user_row)
    show_upgrade_panel = is_admin or is_council

    dash_client_config: dict[str, Any] = {
        "userHierarchy": [dict(item) for item in current_hierarchy],
        "defaultVillageId": default_vid or "",
        "quantumPunchVillageId": election_scheduler.TARGET_VILLAGE_ID,
        "isAdmin": is_admin,
        "isCouncilMember": is_council,
        "showUpgradePanel": show_upgrade_panel,
        "canUpgradeRoles": sorted(UPGRADE_ACCOUNT_TYPES)
        if is_admin
        else sorted(COUNCIL_UPGRADE_TYPES)
        if is_council
        else [],
        "userPrivateId": str(user_row["private_id"] or ""),
        "preferredLanguage": preferred_lang,
        "uiStrings": get_dashboard_ui_strings(preferred_lang),
        "electionsEnabled": elections_are_enabled(),
    }

    return render_template(
        "admin_panel.html",
        user=user_row,
        dash_client_config=dash_client_config,
        quantum_punch_village_id=election_scheduler.TARGET_VILLAGE_ID,
        show_upgrade_panel=show_upgrade_panel,
        is_mentor=is_mentor,
        is_admin=is_admin,
    )


def _redirect_admin_panel_section(section_id: str):
    """Redirect friendly /admin/* URLs to admin panel anchor sections."""
    return redirect(url_for("admin_panel") + f"#{section_id}")


@app.route("/admin/upgrade-users")
@admin_page_required
def admin_upgrade_users():
    return _redirect_admin_panel_section("qb-admin-upgrade-users")


@app.route("/admin/mark-deceased")
@admin_page_required
def admin_mark_deceased():
    return _redirect_admin_panel_section("qb-mentor-mark-deceased")


@app.route("/admin/varna-system")
@admin_page_required
def admin_varna_system():
    return _redirect_admin_panel_section("qb-admin-varna-section")


@app.route("/admin/family-removal")
@admin_page_required
def admin_family_removal():
    return _redirect_admin_panel_section("qb-private-admin-tools")


@app.route("/admin/volunteer-applications")
@admin_page_required
def admin_volunteer_applications():
    return _redirect_admin_panel_section("qb-admin-employment-requests")


@app.route("/admin/karma-economy")
@admin_page_required
def admin_karma_economy():
    return _redirect_admin_panel_section("qb-admin-karma-economy")


@app.route("/admin/donation-reports")
@admin_page_required
def admin_donation_reports():
    return _redirect_admin_panel_section("qb-admin-donation-reports")


@app.route("/admin/donation-management")
@admin_page_required
def admin_donation_management():
    return _redirect_admin_panel_section("qb-admin-donation-mgmt")


@app.route("/admin/edit-requests")
@admin_page_required
def admin_edit_requests():
    return _redirect_admin_panel_section("qb-admin-edit-requests")


@app.route("/admin/manage-elections")
@admin_page_required
def admin_manage_elections():
    return _redirect_admin_panel_section("qb-private-manage-elections")


@app.route("/admin/verifications")
@admin_page_required
def admin_verifications_page():
    """Standalone admin page for pending QR donation verifications."""
    conn = get_db()
    data = sita_platform_core.admin_donation_list(conn)
    pending_donations: list[dict[str, Any]] = []
    for d in data.get("donations") or []:
        pay_st = str(d.get("payment_status") or "").lower()
        st = str(d.get("status") or "")
        if st == "pending" or pay_st in ("pending", "pending_verification"):
            pending_donations.append(
                {
                    "id": d["id"],
                    "user_name": d.get("user_name") or "Pending registration",
                    "email": d.get("email") or "",
                    "phone": d.get("phone") or "",
                    "txn_reference": d.get("upi_txn_reference") or "",
                    "amount": d.get("amount_rupees") or d.get("amount"),
                    "created_at": d.get("created_at") or "",
                }
            )
    return render_template(
        "admin/verifications.html",
        pending_count=data.get("pending_count", 0),
        verified_count=data.get("confirmed_count", 0),
        failed_count=data.get("failed_count", 0),
        pending_donations=pending_donations,
    )


@app.get("/api/donation/admin/export")
@login_required
def api_donation_admin_export():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    csv_data = sita_platform_core.donations_csv(conn)
    return (
        csv_data,
        200,
        {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": "attachment; filename=donations.csv",
        },
    )


@app.post("/api/donation/confirm")
@login_required
def api_donation_confirm():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    data = request.get_json(silent=True) or {}
    donation_id = data.get("donation_id") or data.get("id")
    try:
        donation_id_int = int(donation_id)
    except (TypeError, ValueError):
        return jsonify({"error": "donation_id required"}), 400
    conn = get_db()
    ok = sita_platform_core.confirm_donation(
        conn, donation_id_int, str(g.current_user["private_id"])
    )
    if not ok:
        return jsonify({"error": "Donation not found or already confirmed"}), 404
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/donation/reject")
@login_required
def api_donation_reject():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    data = request.get_json(silent=True) or {}
    donation_id = data.get("donation_id") or data.get("id")
    reason = str(data.get("reason") or data.get("admin_notes") or "").strip()
    try:
        donation_id_int = int(donation_id)
    except (TypeError, ValueError):
        return jsonify({"error": "donation_id required"}), 400
    conn = get_db()
    ok = sita_platform_core.reject_donation(
        conn,
        donation_id_int,
        str(g.current_user["private_id"]),
        reason,
    )
    if not ok:
        return jsonify({"error": "Donation not found"}), 404
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/edit/request")
@login_required
def api_edit_request():
    data = request.get_json(silent=True) or {}
    field_name = str(data.get("field_name") or "").strip()
    new_value = str(data.get("new_value") or "").strip()
    reason = str(data.get("reason") or "").strip()
    conn = get_db()
    try:
        req_id = sita_platform_core.submit_edit_request(
            conn,
            str(g.current_user["private_id"]),
            field_name,
            new_value,
            reason,
        )
        conn.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "request_id": req_id})


@app.get("/api/edit/admin/list")
@login_required
def api_edit_admin_list():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    return jsonify({"requests": sita_platform_core.admin_edit_request_list(conn)})


@app.post("/api/edit/admin/approve")
@login_required
def api_edit_admin_approve():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    data = request.get_json(silent=True) or {}
    request_id = data.get("request_id") or data.get("id")
    try:
        request_id_int = int(request_id)
    except (TypeError, ValueError):
        return jsonify({"error": "request_id required"}), 400
    conn = get_db()
    ok = sita_platform_core.approve_edit_request(
        conn,
        request_id_int,
        str(g.current_user["private_id"]),
        notify_fn=send_system_message,
        age_from_dob_fn=compute_age,
    )
    if not ok:
        return jsonify({"error": "Request not found or not pending"}), 404
    conn.commit()
    return jsonify({"ok": True})


@app.post("/api/edit/admin/reject")
@login_required
def api_edit_admin_reject():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    data = request.get_json(silent=True) or {}
    request_id = data.get("request_id") or data.get("id")
    reason = str(data.get("reason") or data.get("admin_notes") or "").strip()
    try:
        request_id_int = int(request_id)
    except (TypeError, ValueError):
        return jsonify({"error": "request_id required"}), 400
    conn = get_db()
    ok = sita_platform_core.reject_edit_request(
        conn,
        request_id_int,
        str(g.current_user["private_id"]),
        reason,
        notify_fn=send_system_message,
    )
    if not ok:
        return jsonify({"error": "Request not found or not pending"}), 404
    conn.commit()
    return jsonify({"ok": True})


@app.get("/api/admin/donations")
@login_required
def api_admin_donations_alias():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    return jsonify(sita_platform_core.admin_donation_list(conn))


@app.post("/api/admin/donation/confirm/<int:donation_id>")
@login_required
def api_admin_donation_confirm_alias(donation_id: int):
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    row = sita_platform_core.get_donation(conn, donation_id)
    ok = sita_platform_core.confirm_donation(
        conn, donation_id, str(g.current_user["private_id"])
    )
    if not ok:
        return jsonify({"error": "Donation not found or already confirmed"}), 404
    if row:
        pid = str(row.get("user_private_id") or "").strip()
        if pid and not pid.startswith(sita_platform_core.PENDING_USER_PREFIX):
            _notify_user_verification_event(conn, pid, "verified")
    conn.commit()
    return jsonify({"success": True, "message": "Donation verified and account activated"})


@app.post("/api/admin/donation/verify/<int:donation_id>")
def api_admin_donation_verify_alias(donation_id: int):
    """Verify donation via admin session or X-Admin-Key header."""
    admin_key = (request.headers.get("X-Admin-Key") or "").strip()
    expected = getattr(config, "ADMIN_API_KEY", "") or ""
    if admin_key and expected and admin_key == expected:
        conn = get_db()
        row = sita_platform_core.get_donation(conn, donation_id)
        ok = sita_platform_core.confirm_donation(conn, donation_id, "admin_api_key")
        if not ok:
            return jsonify({"error": "Donation not found or already confirmed"}), 404
        if row:
            pid = str(row.get("user_private_id") or "").strip()
            if pid and not pid.startswith(sita_platform_core.PENDING_USER_PREFIX):
                _notify_user_verification_event(conn, pid, "verified")
        conn.commit()
        return jsonify(
            {"success": True, "message": "Donation verified and account activated"}
        )
    if not getattr(g, "current_user", None) or not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    return api_admin_donation_confirm_alias(donation_id)


@app.post("/api/admin/donation/reject/<int:donation_id>")
@login_required
def api_admin_donation_reject_alias(donation_id: int):
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason") or "").strip()
    conn = get_db()
    row = sita_platform_core.get_donation(conn, donation_id)
    ok = sita_platform_core.reject_donation(
        conn, donation_id, str(g.current_user["private_id"]), reason
    )
    if not ok:
        return jsonify({"error": "Donation not found"}), 404
    if row:
        pid = str(row.get("user_private_id") or "").strip()
        if pid and not pid.startswith(sita_platform_core.PENDING_USER_PREFIX):
            _notify_user_verification_event(conn, pid, "failed", reason=reason)
    conn.commit()
    return jsonify({"success": True, "message": "Donation rejected and user notified"})


@app.get("/api/admin/donation/export")
@login_required
def api_admin_donation_export_alias():
    if not is_admin_user(g.current_user):
        return jsonify({"error": "Admin only"}), 403
    conn = get_db()
    csv_data = sita_platform_core.donations_csv(conn)
    return (
        csv_data,
        200,
        {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": "attachment; filename=donations.csv",
        },
    )


RECOVERY_VERIFY_FAIL_MSG = (
    "Could not verify your identity. Please contact village council for assistance."
)
RECOVERY_SESSION_TTL_SEC = 600


def _recovery_users_by_identity(
    conn: sqlite3.Connection,
    first_name: str,
    last_name: str,
    date_of_birth: str,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, private_id, public_id, first_name, last_name, gender,
               birth_location_id, email, phone
          FROM users
         WHERE LOWER(TRIM(first_name)) = LOWER(TRIM(?))
           AND LOWER(TRIM(last_name)) = LOWER(TRIM(?))
           AND date_of_birth = ?
         ORDER BY id ASC
        """,
        (first_name, last_name, date_of_birth),
    ).fetchall()


def _recovery_resolve_user(
    conn: sqlite3.Connection,
    *,
    first_name: str,
    last_name: str,
    date_of_birth: str,
    user_id: int | None,
    user_private_id: str | None,
) -> sqlite3.Row | None:
    if user_private_id:
        row = conn.execute(
            "SELECT * FROM users WHERE private_id = ? LIMIT 1", (user_private_id,)
        ).fetchone()
        if not row:
            return None
        if (
            str(row["date_of_birth"] or "") != date_of_birth
            or str(row["first_name"] or "").strip().lower()
            != first_name.strip().lower()
            or str(row["last_name"] or "").strip().lower() != last_name.strip().lower()
        ):
            return None
        return row

    rows = _recovery_users_by_identity(conn, first_name, last_name, date_of_birth)
    if not rows:
        return None
    if user_id is not None:
        for row in rows:
            if int(row["id"]) == int(user_id):
                return conn.execute(
                    "SELECT * FROM users WHERE id = ? LIMIT 1", (int(user_id),)
                ).fetchone()
        return None
    if len(rows) == 1:
        return conn.execute(
            "SELECT * FROM users WHERE id = ? LIMIT 1", (int(rows[0]["id"]),)
        ).fetchone()
    return None


def _recovery_birth_location_matches(user_row: sqlite3.Row, birth_location_id: str) -> bool:
    stored = str(user_row["birth_location_id"] or "").strip()
    selected = str(birth_location_id or "").strip()
    if not stored or not selected:
        return False
    return stored == selected


@app.route("/recovery", methods=["GET"])
def recovery_page():
    return render_template("recovery.html")


@app.post("/api/recovery/search")
def api_recovery_search():
    payload = request.get_json(silent=True) or {}
    first_name = (payload.get("first_name") or "").strip()
    last_name = (payload.get("last_name") or "").strip()
    dob = str(payload.get("date_of_birth") or "").strip()
    if not first_name or not last_name or not dob:
        return jsonify({"error": "First name, last name, and date of birth are required."}), 400
    if not parse_date_iso(dob):
        return jsonify({"error": "Please enter a valid date of birth."}), 400

    conn = get_db()
    rows = _recovery_users_by_identity(conn, first_name, last_name, dob)
    if not rows:
        return jsonify({"error": RECOVERY_VERIFY_FAIL_MSG}), 404

    candidates = [
        {
            "user_id": int(r["id"]),
            "first_name": str(r["first_name"]),
            "last_name": str(r["last_name"]),
            "gender": str(r["gender"] or ""),
        }
        for r in rows
    ]
    session["recovery_search"] = {
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": dob,
        "candidate_ids": [int(r["id"]) for r in rows],
        "searched_at": time.time(),
    }
    return jsonify(
        {
            "ok": True,
            "multiple": len(candidates) > 1,
            "count": len(candidates),
            "candidates": candidates,
        }
    )


@app.post("/api/recovery/verify")
def api_recovery_verify():
    payload = request.get_json(silent=True) or {}
    purpose = str(payload.get("purpose") or "").strip()
    if purpose not in ("recovery_id", "reset_password"):
        return jsonify({"error": "Invalid purpose"}), 400

    first_name = (payload.get("first_name") or "").strip()
    last_name = (payload.get("last_name") or "").strip()
    dob = str(payload.get("date_of_birth") or "").strip()
    birth_location_id = str(payload.get("birth_location_id") or "").strip()
    user_private_id = (payload.get("user_private_id") or "").strip() or None
    user_id_raw = payload.get("user_id")
    user_id: int | None
    try:
        user_id = int(user_id_raw) if user_id_raw is not None and str(user_id_raw).strip() else None
    except (TypeError, ValueError):
        user_id = None

    if not first_name or not last_name or not dob or not birth_location_id:
        return jsonify({"error": "Full name, date of birth, and birth location are required."}), 400
    if not parse_date_iso(dob):
        return jsonify({"error": "Please enter a valid date of birth."}), 400

    search_ctx = session.get("recovery_search") or {}
    if search_ctx:
        if time.time() - float(search_ctx.get("searched_at") or 0) > RECOVERY_SESSION_TTL_SEC:
            session.pop("recovery_search", None)
            return jsonify({"error": "Recovery session expired. Start again."}), 403
        if (
            search_ctx.get("first_name", "").strip().lower() != first_name.lower()
            or search_ctx.get("last_name", "").strip().lower() != last_name.lower()
            or str(search_ctx.get("date_of_birth") or "") != dob
        ):
            return jsonify({"error": RECOVERY_VERIFY_FAIL_MSG}), 403
        allowed_ids = {int(x) for x in (search_ctx.get("candidate_ids") or [])}
        if user_id is not None and user_id not in allowed_ids:
            return jsonify({"error": RECOVERY_VERIFY_FAIL_MSG}), 403
        if user_id is None and len(allowed_ids) > 1:
            return jsonify({"error": "Multiple accounts match. Select your account first."}), 400

    conn = get_db()
    if not village_exists(conn, birth_location_id):
        return jsonify({"error": RECOVERY_VERIFY_FAIL_MSG}), 403

    user = _recovery_resolve_user(
        conn,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=dob,
        user_id=user_id,
        user_private_id=user_private_id,
    )
    if not user or not _recovery_birth_location_matches(user, birth_location_id):
        return jsonify({"error": RECOVERY_VERIFY_FAIL_MSG}), 403

    private_id = str(user["private_id"])
    public_id = str(user["public_id"])

    if purpose == "recovery_id":
        identity_core.notify_user_ids(
            email=str(user["email"] or "") or None,
            phone=str(user["phone"] or "") or None,
            private_id=private_id,
            public_id=public_id,
            first_name=str(user["first_name"]),
        )
        session.pop("recovery_search", None)
        return jsonify(
            {
                "ok": True,
                "private_id": private_id,
                "public_id": public_id,
                "notified": bool(user["email"] or user["phone"]),
                "message": "Your Private ID is shown below."
                + (
                    " A courtesy copy was also sent to your registered email/phone."
                    if user["email"] or user["phone"]
                    else ""
                ),
            }
        )

    reset_token = secrets.token_urlsafe(32)
    session["recovery_reset_password"] = {
        "token": reset_token,
        "user_id": int(user["id"]),
        "user_private_id": private_id,
        "verified_at": time.time(),
    }
    session.pop("recovery_search", None)
    return jsonify(
        {
            "ok": True,
            "verified": True,
            "user_private_id": private_id,
            "reset_token": reset_token,
        }
    )


@app.post("/api/recovery/reset-password")
def api_recovery_reset_password():
    payload = request.get_json(silent=True) or {}
    user_private_id = str(payload.get("user_private_id") or "").strip()
    new_password = str(payload.get("new_password") or payload.get("password") or "")
    confirm = str(payload.get("confirm_password") or "")
    reset_token = str(payload.get("reset_token") or "").strip()

    rec = session.get("recovery_reset_password")
    if not rec:
        return jsonify({"error": "Complete birth location verification first."}), 403
    if time.time() - float(rec.get("verified_at") or 0) > RECOVERY_SESSION_TTL_SEC:
        session.pop("recovery_reset_password", None)
        return jsonify({"error": "Recovery session expired. Start again."}), 403
    if reset_token and rec.get("token") != reset_token:
        return jsonify({"error": RECOVERY_VERIFY_FAIL_MSG}), 403
    if user_private_id and rec.get("user_private_id") != user_private_id:
        return jsonify({"error": RECOVERY_VERIFY_FAIL_MSG}), 403

    if len(new_password) < 9:
        return jsonify({"error": "Password must be at least 9 characters."}), 400
    ok_pw, pw_msg = validate_password_strength(new_password)
    if not ok_pw:
        return jsonify({"error": pw_msg}), 400
    if new_password != confirm:
        return jsonify({"error": "Passwords do not match."}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT private_id, public_id FROM users WHERE id = ? LIMIT 1",
        (int(rec["user_id"]),),
    ).fetchone()
    if not user:
        session.pop("recovery_reset_password", None)
        return jsonify({"error": RECOVERY_VERIFY_FAIL_MSG}), 403

    pw_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode(
        "ascii"
    )
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (pw_hash, int(rec["user_id"])),
    )
    conn.commit()
    session.pop("recovery_reset_password", None)
    return jsonify(
        {
            "ok": True,
            "private_id": str(user["private_id"]),
            "public_id": str(user["public_id"]),
            "message": "Please save these IDs in a safe place.",
        }
    )


@app.get("/api/user/account-ids")
@login_required
def api_user_account_ids():
    conn = get_db()
    pid = str(g.current_user["private_id"])
    accounts = identity_core.list_user_accounts(conn, pid)
    return jsonify(
        {
            "accounts": accounts,
            "primary_public_id": str(g.current_user["public_id"]),
        }
    )


@app.post("/api/user/location-mode")
@login_required
def api_user_location_mode():
    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode") or "").strip().lower()
    if mode not in ("birth", "present"):
        return jsonify({"error": "mode must be birth or present"}), 400
    if not identity_core.can_toggle_location(g.current_user):
        return jsonify({"error": "Location toggle not available for your profile"}), 403
    session["location_mode"] = mode
    conn = get_db()
    hier, vid = dashboard_hierarchy_for_user(conn, g.current_user)
    return jsonify(
        {
            "ok": True,
            "location_mode": mode,
            "default_village_id": vid,
            "hierarchy": hier,
        }
    )


def _canonical_private_id_for_login(raw: str) -> str | None:
    """Normalize login input to HU- + 9 digits. Rejects email and invalid IDs."""
    s = (raw or "").strip()
    if not s or "@" in s:
        return None
    if s.upper().startswith(HUMAN_PRIVATE_ID_PREFIX):
        digits = re.sub(r"\D", "", s[len(HUMAN_PRIVATE_ID_PREFIX):])
    else:
        digits = re.sub(r"\D", "", s)
    if not PRIVATE_ID_LOGIN_RE.match(digits):
        return None
    return format_human_private_id(digits)


def _private_id_login_candidates(raw: str) -> list[str]:
    """Build Private ID lookup candidates (HU- prefixed, bare digits, legacy admin)."""
    import admin_login_repair

    s = (raw or "").strip()
    digits = re.sub(r"\D", "", s.upper().startswith(HUMAN_PRIVATE_ID_PREFIX) and s[len(HUMAN_PRIVATE_ID_PREFIX):] or s)
    canonical = _canonical_private_id_for_login(raw)
    if not canonical and PRIVATE_ID_LOGIN_RE.match(digits):
        canonical = format_human_private_id(digits)
    if not canonical:
        return []

    candidates: list[str] = [
        canonical,
        canonical[len(HUMAN_PRIVATE_ID_PREFIX):],
    ]
    if canonical.upper() == ADMIN_PRIVATE_ID.upper():
        candidates.append(LEGACY_ADMIN_PRIVATE_ID)
    if digits == ADMIN_PRIVATE_ID[len(HUMAN_PRIVATE_ID_PREFIX):]:
        candidates.extend([ADMIN_PRIVATE_ID, LEGACY_ADMIN_PRIVATE_ID])
    backup_digits = admin_login_repair.BACKUP_PRIVATE_ID[len(HUMAN_PRIVATE_ID_PREFIX):]
    if digits == backup_digits:
        candidates.extend(
            [admin_login_repair.BACKUP_PRIVATE_ID, backup_digits]
        )
    # Preserve order, drop duplicates (case-insensitive).
    seen: set[str] = set()
    unique: list[str] = []
    for cand in candidates:
        key = cand.upper()
        if key not in seen:
            seen.add(key)
            unique.append(cand)
    return unique


def _private_id_digits_from_form() -> str:
    """Collect 9-digit Private ID from OTP boxes or hidden field."""
    digits = ""
    for i in range(1, 10):
        digits += (request.form.get(f"otp_{i}") or "").strip()
    if not digits:
        digits = (request.form.get("private_id") or "").strip()
    return re.sub(r"\D", "", digits)


def _lookup_user_by_private_id(
    conn: sqlite3.Connection,
    private_id: str,
) -> sqlite3.Row | None:
    """Find user by private_id (trimmed, case-insensitive, exact fallback)."""
    pid = str(private_id or "").strip()
    if not pid:
        return None
    row = conn.execute(
        """
        SELECT id, password_hash, private_id, first_name, last_name, account_type, is_admin
        FROM users WHERE TRIM(private_id) = ? COLLATE NOCASE
        """,
        (pid,),
    ).fetchone()
    if row:
        return row
    row = conn.execute(
        """
        SELECT id, password_hash, private_id, first_name, last_name, account_type, is_admin
        FROM users WHERE TRIM(private_id) = ?
        """,
        (pid,),
    ).fetchone()
    if row:
        return row
    return conn.execute(
        """
        SELECT id, password_hash, private_id, first_name, last_name, account_type, is_admin
        FROM users WHERE private_id = ? COLLATE NOCASE
        """,
        (pid,),
    ).fetchone()


def _authenticate_user_login(
    conn: sqlite3.Connection,
    login_input: str,
    password: str,
) -> sqlite3.Row | None:
    """Verify password for a Private ID (HU- + 9 digits only)."""
    login_input = (login_input or "").strip()
    password = password or ""
    if not login_input or not password:
        return None

    candidates = _private_id_login_candidates(login_input)
    row: sqlite3.Row | None = None
    tried: list[str] = []
    for cand in candidates:
        tried.append(cand)
        row = _lookup_user_by_private_id(conn, cand)
        if row:
            break

    if not row:
        app.logger.warning(
            "Login lookup failed for digits=%s candidates=%s",
            re.sub(r"\D", "", login_input),
            tried,
        )
        return None

    stored = row["password_hash"]
    if not stored:
        app.logger.warning(
            "Login failed: empty password_hash for private_id=%s",
            row["private_id"],
        )
        return None
    stored_b = stored.encode("utf-8") if isinstance(stored, str) else stored
    try:
        ok = bcrypt.checkpw(password.encode("utf-8"), stored_b)
    except (ValueError, TypeError) as exc:
        app.logger.warning(
            "Login bcrypt error for private_id=%s: %s",
            row["private_id"],
            exc,
        )
        return None
    if not ok:
        app.logger.warning(
            "Login password mismatch for private_id=%s",
            row["private_id"],
        )
        return None
    return row


def _user_pk_for_login_row(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
) -> int | None:
    """Resolve session user_pk; repair legacy rows where users.id is NULL."""
    try:
        pk = row["id"]
        if pk is not None:
            return int(pk)
    except (KeyError, TypeError, ValueError):
        pass

    import admin_login_repair

    admin_login_repair.repair_null_user_ids(conn)
    refreshed = _lookup_user_by_private_id(conn, str(row["private_id"]))
    if refreshed:
        try:
            pk = refreshed["id"]
            if pk is not None:
                return int(pk)
        except (KeyError, TypeError, ValueError):
            pass

    fb = conn.execute(
        "SELECT rowid FROM users WHERE private_id = ? COLLATE NOCASE",
        (str(row["private_id"]),),
    ).fetchone()
    if not fb:
        return None
    rid = int(fb[0])
    conn.execute(
        """
        UPDATE users SET id = ?
        WHERE private_id = ? COLLATE NOCASE AND id IS NULL
        """,
        (rid, str(row["private_id"])),
    )
    conn.commit()
    return rid


def _normalize_login_private_id(raw: str) -> str | None:
    """Legacy helper — first candidate for a Private ID login string."""
    candidates = _private_id_login_candidates(raw)
    return candidates[0] if candidates else None


@app.route("/login", methods=["GET", "POST"])
def login():
    conn = get_db()

    if request.method == "GET":
        if session.get("user_pk"):
            session.clear()
        return render_template("login.html", error=None)

    try:
        password = (request.form.get("password") or "").strip()
        raw_pid = _private_id_digits_from_form()

        app.logger.info("Login attempt digits=%s len=%d", raw_pid, len(raw_pid))

        if not raw_pid:
            return render_template(
                "login.html",
                error="Please enter your Private ID.",
            )

        if not password:
            return render_template(
                "login.html",
                error="Please enter your password.",
            )

        if len(raw_pid) != 9:
            app.logger.warning("Login rejected: expected 9 digits, got %d", len(raw_pid))
            return render_template(
                "login.html",
                error="Please enter exactly 9 digits for your Private ID.",
            )

        if not _canonical_private_id_for_login(raw_pid):
            return render_template(
                "login.html",
                error="Private ID must contain only digits.",
            )

        row = _authenticate_user_login(conn, raw_pid, password)
        if not row:
            app.logger.warning(
                "Login failed for digits=%s — running admin self-heal and retry",
                raw_pid,
            )
            import admin_login_repair

            heal = admin_login_repair.ensure_admin_healthy(conn, force=True)
            app.logger.info("Login retry heal result: %s", heal.get("actions"))
            row = _authenticate_user_login(conn, raw_pid, password)
        if not row:
            app.logger.warning("Login failed for digits=%s", raw_pid)
            return render_template(
                "login.html",
                error="Invalid Private ID or Password.",
            )

        user_pk = _user_pk_for_login_row(conn, row)
        if not user_pk:
            app.logger.error(
                "Login auth ok but user_pk missing for private_id=%s",
                row["private_id"],
            )
            return render_template(
                "login.html",
                error="Invalid Private ID or Password.",
            )

        session.clear()
        session["user_pk"] = user_pk
        full_user = load_user(conn, user_pk)
        _session_sync_admin_flag(full_user)
        app.logger.info("Login successful private_id=%s", row["private_id"])
        dest = request.args.get("next") or ""
        if dest.startswith("/") and full_user:
            return redirect(dest)
        return redirect(url_for("dashboard"))
    except Exception as exc:
        app.logger.exception("Login error: %s", exc)
        return render_template(
            "login.html",
            error="Login error. Please try again.",
        )


@app.post("/api/login")
def api_login():
    """JSON login — Private ID (HU- + 9 digits) and password only."""
    data = request.get_json(silent=True) or {}
    raw_pid = re.sub(r"\D", "", str(data.get("private_id") or "").strip())
    password = str(data.get("password") or "")
    conn = get_db()

    if len(raw_pid) != 9 or not _canonical_private_id_for_login(raw_pid):
        return jsonify({"error": "Enter a valid 9-digit Private ID"}), 400

    row = _authenticate_user_login(conn, raw_pid, password)
    if not row:
        import admin_login_repair

        admin_login_repair.ensure_admin_healthy(conn, force=True)
        row = _authenticate_user_login(conn, raw_pid, password)
    if not row:
        return jsonify({"error": "Invalid login or password"}), 401

    user_pk = _user_pk_for_login_row(conn, row)
    if not user_pk:
        return jsonify({"error": "Invalid login or password"}), 401

    session.clear()
    session["user_pk"] = user_pk
    full_user = load_user(conn, user_pk)
    _session_sync_admin_flag(full_user)
    return jsonify(
        {
            "success": True,
            "ok": True,
            "message": "Login successful",
            "redirect": url_for("dashboard"),
            "private_id": str(row["private_id"]),
            "user_name": f'{row["first_name"]} {row["last_name"]}',
            "account_type": str(row["account_type"] or "H_U"),
        }
    )


@app.get("/logout")
@app.post("/logout")
def logout():
    """Clear session immediately without running schema bootstrap."""
    session.clear()
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    user_row = g.current_user

    display_name = f'{user_row["first_name"]} {user_row["last_name"]}'
    preferred_lang = active_ui_language(conn, user_row)
    current_hierarchy, default_vid = public_hierarchy_for_user(
        conn, user_row, language_code=preferred_lang
    )
    language_choices = language_core.all_language_choices(conn)
    loc_mode = "present"
    can_toggle_loc = identity_core.can_toggle_location(user_row)
    user_situation = identity_core.user_situation_type(user_row)
    show_public_account = identity_core.user_show_public_account(user_row)
    if user_situation == "C":
        post_form_location_id = (
            global_core.user_global_state_id(user_row)
            or str(user_row["current_country_id"] or "").strip()
        )
    else:
        post_form_location_id = default_vid or ""

    birth_vid = user_row["birth_location_id"]
    cloc = present_village_id(user_row) or effective_dashboard_village_id(conn, user_row)
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

    user_village_stats_url = "#"
    if default_vid:
        user_village_stats_url = build_geo_public_url("village", str(default_vid).strip())

    user_life_stage = life_stage_from_age(int(user_row["age"]))

    active_zodiac = _election_active_zodiac_sign()
    election_nomination_eligible = _election_user_can_nominate(user_row, active_zodiac)
    election_vote_eligible = _election_user_can_vote(user_row, active_zodiac)

    geo_displays = user_dashboard_geo_displays(conn, user_row)
    geo_displays["user_current_location_id_display"] = cloc or geo_displays.get(
        "user_current_location_id_display"
    )
    referral_stats = referral_core.get_referral_stats(conn, pid)
    public_base = _public_base_url()
    referral_reg_url = referral_core.build_registration_url(
        public_base, referral_stats["referral_code"]
    )
    referral_qr = referral_core.generate_qr_base64(referral_reg_url)
    referral_leaderboard = referral_core.get_leaderboard(conn, limit=10)
    volunteer_status = referral_core.get_volunteer_status(conn, pid)
    is_council = is_council_member(conn, user_row)
    is_mentor = deceased_core.is_mentor_user(conn, user_row)
    show_upgrade_panel = is_admin_user(user_row) or is_council
    varna_core.migrate_varna_schema(conn)
    varna_profile = varna_core.profile_for_user(conn, pid)
    conn.commit()

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
        "isCouncilMember": is_council,
        "showUpgradePanel": show_upgrade_panel,
        "canUpgradeRoles": sorted(UPGRADE_ACCOUNT_TYPES)
        if is_admin_user(user_row)
        else sorted(COUNCIL_UPGRADE_TYPES)
        if is_council
        else [],
        "volunteerStatus": volunteer_status,
        "razorpayKeyId": getattr(config, "RAZORPAY_KEY_ID", ""),
        "userPrivateId": str(user_row["private_id"] or ""),
        "electionNominationEligible": election_nomination_eligible,
        "electionVoteEligible": election_vote_eligible,
        "userDisplayName": display_name,
        "userPublicId": str(user_row["public_id"] or ""),
        "accountStatus": _user_account_status(user_row),
        "userZoneId": geo_displays.get("user_zone_id") or "",
        "userZoneName": geo_displays.get("user_zone_name") or "",
        "userZoneCode": geo_displays.get("user_zone_code") or "",
        "commerceEnabled": user_in_indian_village(conn, user_row),
        "electionsEnabled": elections_are_enabled(),
        "locationMode": loc_mode,
        "canToggleLocation": can_toggle_loc,
        "publicTimelinePresentOnly": True,
        "userSituationType": user_situation,
        "isGlobalUser": global_core.is_global_only_user(user_row),
        "globalStateId": global_core.user_global_state_id(user_row) or "",
        "postFormLocationId": post_form_location_id or "",
        "birthLocationId": str(birth_vid or ""),
        "presentLocationId": str(user_row["current_location_id"] or ""),
        "preferredLanguage": preferred_lang,
        "uiStrings": get_dashboard_ui_strings(preferred_lang),
        "referralCode": referral_stats["referral_code"],
        "referralCount": referral_stats["referral_count"],
        "referralEarnings": referral_stats["referral_earnings"],
        "referralRegistrationUrl": referral_reg_url,
        "referralQrBase64": referral_qr,
        "referralLeaderboard": referral_leaderboard,
        "publicBaseUrl": public_base,
    }

    return render_template(
        "dashboard.html",
        user=user_row,
        election_nomination_eligible=election_nomination_eligible,
        election_vote_eligible=election_vote_eligible,
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
        account_badges=_user_account_badges(user_row),
        show_dashboard_post_form=bool(post_form_location_id),
        post_form_location_id=post_form_location_id,
        dash_client_config=dash_client_config,
        quantum_punch_village_id=election_scheduler.TARGET_VILLAGE_ID,
        location_mode=loc_mode,
        can_toggle_location=can_toggle_loc,
        user_situation_type=user_situation,
        show_public_account=show_public_account,
        preferred_language=preferred_lang,
        language_choices=language_choices,
        referral_stats=referral_stats,
        referral_registration_url=referral_reg_url,
        referral_qr_base64=referral_qr,
        referral_leaderboard=referral_leaderboard,
        volunteer_status=volunteer_status,
        is_council_member=is_council,
        is_mentor=is_mentor,
        show_upgrade_panel=show_upgrade_panel,
        varna_profile=varna_profile,
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
    try:
        page_title, members = _location_members_for_scope(conn, lt, lid)
    except ValueError:
        abort(404)
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
    """Legacy route — all users now use the main dashboard."""
    return redirect(url_for("dashboard"))


@app.route("/calendar")
@login_required
def calendar_page():
    user_row = g.current_user
    display_name = f'{user_row["first_name"]} {user_row["last_name"]}'
    return render_template(
        "calendar.html",
        user=user_row,
        display_name=display_name,
    )


@app.route("/api/calendar/solar-months")
@login_required
def api_calendar_solar_months():
    months = zodiac_calendar.get_solar_months_2026()
    return jsonify(
        {
            "vikram_samvat": zodiac_calendar.VIKRAM_SAMVAT_2026,
            "months": months,
            "element_colours": zodiac_calendar.ELEMENT_COLOUR,
        }
    )


@app.route("/api/calendar/events")
@login_required
def api_calendar_events():
    conn = get_db()
    year = request.args.get("year", type=int, default=2026)
    month = (request.args.get("month") or "").strip()
    solar = (request.args.get("solar") or "").strip()

    if solar:
        bounds = zodiac_calendar._solar_month_bounds(solar)
        if not bounds:
            return jsonify({"error": f"Unknown solar month: {solar}"}), 400
        start, end = bounds
        payload = zodiac_calendar.events_for_solar_month(conn, start, end)
        return jsonify(
            {
                "year": year,
                "month": month or solar,
                "solar_month": solar,
                "start_date": start,
                "end_date": end,
                **payload,
            }
        )

    if not month:
        return jsonify({"error": "month or solar query parameter required"}), 400

    festivals = zodiac_calendar.get_festivals_for_month(conn, year, month)
    lunar = zodiac_calendar.get_lunar_events_for_month(conn, year, month)
    return jsonify(
        {
            "year": year,
            "month": month,
            "festivals": festivals,
            "lunar_events": lunar,
        }
    )


@app.route("/api/calendar/user-birthdays")
@login_required
def api_calendar_user_birthdays():
    user_row = g.current_user
    try:
        is_admin = int(user_row["is_admin"] or 0)
    except (KeyError, TypeError, ValueError):
        is_admin = 0
    if is_admin:
        return jsonify({"birthday": None, "note": "Admin birthdays are hidden."})
    birthday = zodiac_calendar.get_user_birthday_payload(user_row)
    return jsonify({"birthday": birthday})


def _user_village_id_row(user_row: sqlite3.Row) -> str:
    return str(user_row["current_location_id"] or "").strip()


def _is_village_council_member(
    conn: sqlite3.Connection, private_id: str, village_id: str
) -> bool:
    admin_row = conn.execute(
        "SELECT is_admin FROM users WHERE private_id = ? COLLATE NOCASE",
        (private_id,),
    ).fetchone()
    if admin_row and int(admin_row["is_admin"] or 0):
        return True
    row = conn.execute(
        """
        SELECT 1 FROM village_council
        WHERE TRIM(village_id) = TRIM(?)
          AND (male_head_private_id = ? OR female_head_private_id = ?)
        """,
        (village_id, private_id, private_id),
    ).fetchone()
    return row is not None


def _approved_business_for_user(
    conn: sqlite3.Connection, private_id: str
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM businesses
        WHERE owner_private_id = ? AND status = 'approved'
        ORDER BY id DESC LIMIT 1
        """,
        (private_id,),
    ).fetchone()


import village_platform as _village_platform

_village_platform.register(
    app,
    deps={
        "login_required": login_required,
        "get_db": get_db,
        "user_in_indian_village": user_in_indian_village,
        "user_village_id": _user_village_id_row,
        "is_council_member": _is_village_council_member,
        "approved_business_for_user": _approved_business_for_user,
        "location_display_label": location_display_label,
        "send_system_message": send_system_message,
        "ensure_economic_account": identity_core.get_or_create_economic_account,
    },
)

from varna_routes import register_varna_routes

register_varna_routes(app, get_db, login_required, admin_required)

from space_routes import register_space_routes

register_space_routes(app, get_db, login_required, is_admin_user_fn=is_admin_user)

from qsi_routes import register_qsi_routes

register_qsi_routes(
    app,
    get_db,
    login_required,
    admin_required,
    admin_page_required,
    is_admin_user,
)

_geography_seeded = False
_geography_seed_lock = threading.Lock()


def _seed_geography_background() -> None:
    """Run geography seeding once in background after startup."""
    global _geography_seeded
    with _geography_seed_lock:
        if _geography_seeded:
            return
    time.sleep(5)
    try:
        subprocess.run(
            [sys.executable, str(BASE_DIR / "add_global_geography.py")],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(BASE_DIR),
        )
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "fix_geography.py")],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(BASE_DIR),
        )
        if result.returncode == 0:
            logger.info("Geography seeded successfully in background")
            _geography_seeded = True
        else:
            logger.warning(
                "Geography seeding warning: %s",
                (result.stderr or result.stdout or "").strip() or result.returncode,
            )
    except subprocess.TimeoutExpired:
        logger.warning("Geography seeding timed out")
    except Exception as exc:
        logger.warning("Geography seeding error: %s", exc)


def _start_geography_background() -> None:
    thread = threading.Thread(target=_seed_geography_background, daemon=True)
    thread.start()


with app.app_context():
    _start_geography_background()


_migrate_startup_lock = threading.Lock()
_migrate_startup_done = False


def _load_migrate_admin_module():
    """Load scripts/migrate_admin_fix.py without requiring scripts package."""
    import importlib.util

    script_path = BASE_DIR / "scripts" / "migrate_admin_fix.py"
    if not script_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("migrate_admin_fix", script_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _migration_html_response(status: dict[str, Any]) -> str:
    ok = bool(status.get("ok"))
    title = "Migration complete" if ok else "Migration failed"
    alert_class = "qb-alert-success" if ok else "qb-alert-error"
    already = status.get("already_configured")
    body = status.get("message") or title
    if already:
        body = "Admin is already configured with the correct credentials."
    hu = status.get("hu_prefix_updated", 0)
    return f"""
    <div class="container py-4">
      <div class="qb-panel p-4">
        <h1 class="h4 mb-3">{title}</h1>
        <div class="qb-alert {alert_class} mb-3">{body}</div>
        <p><strong>Admin Private ID:</strong> <code>{status.get("admin_private_id", ADMIN_PRIVATE_ID)}</code></p>
        <p><strong>Admin Public ID:</strong> <code>{status.get("admin_public_id", "ADMIN-PUBLIC")}</code></p>
        <p><strong>Email:</strong> <code>{status.get("admin_email", "")}</code></p>
        <p><strong>Phone:</strong> <code>{status.get("admin_phone", "")}</code></p>
        <p><strong>Password:</strong> <code>{status.get("admin_password", "P@y#umans123")}</code></p>
        <p class="small text-muted">HU- prefix updates: {hu}</p>
        <a href="{url_for('login')}" class="qb-btn qb-btn-primary">Login</a>
        <a href="{url_for('dashboard')}" class="qb-btn qb-btn-neutral ms-2">Dashboard</a>
      </div>
    </div>
    """


def _run_startup_admin_migration() -> None:
    """Run admin migration once after the app module has fully loaded."""
    global _migrate_startup_done, _migration_startup_status
    with _migrate_startup_lock:
        if _migrate_startup_done:
            return
        _migrate_startup_done = True

    _migration_startup_status["running"] = True
    app.logger.info("=" * 50)
    app.logger.info("Starting auto-migration check…")
    app.logger.info("=" * 50)

    try:
        mod = _load_migrate_admin_module()
        if mod is None:
            msg = "migrate_admin_fix.py not found — skipping startup migration"
            app.logger.warning(msg)
            _migration_startup_status.update(
                {"ok": False, "message": msg, "running": False}
            )
            return

        with app.app_context():
            import admin_login_repair

            conn = get_db()
            heal = admin_login_repair.ensure_admin_healthy(conn, force=True)
            result = {
                "ok": heal.get("ok"),
                "login_verified": heal.get("login_verified"),
                "message": (
                    "Admin self-heal complete"
                    if heal.get("ok")
                    else str(heal.get("error") or "Admin heal failed")
                ),
                "actions": heal.get("actions"),
            }
            admin_exists = bool(heal.get("login_simulated"))
            _migration_startup_status.update(
                {
                    "ok": bool(result.get("ok")),
                    "admin_exists": admin_exists,
                    "already_configured": bool(heal.get("ok")),
                    "message": str(result.get("message") or ""),
                    "hu_prefix_updated": 0,
                    "admin_private_id": ADMIN_PRIVATE_ID,
                    "running": False,
                    "self_heal_actions": heal.get("actions"),
                }
            )
            if result.get("ok"):
                app.logger.info(
                    "Auto-migration complete: %s actions=%s",
                    result.get("message"),
                    heal.get("actions"),
                )
            else:
                app.logger.warning(
                    "Auto-migration failed: %s", result.get("message")
                )
    except Exception as exc:
        app.logger.exception("Auto-migration error: %s", exc)
        _migration_startup_status.update(
            {
                "ok": False,
                "message": str(exc),
                "running": False,
            }
        )
    finally:
        _migration_startup_status["running"] = False
        app.logger.info("=" * 50)


def _start_admin_migration_background() -> None:
    thread = threading.Thread(
        target=_run_startup_admin_migration,
        name="qumanity-admin-migration",
        daemon=True,
    )
    thread.start()


@app.route("/migrate-admin")
def migrate_admin_page():
    """Public one-click admin migration (no API key). Visit once after deploy."""
    mod = _load_migrate_admin_module()
    if mod is None:
        return (
            "<h1>Migration script missing</h1><p>scripts/migrate_admin_fix.py not found.</p>",
            500,
        )
    try:
        status = mod.run_migration_with_status(reset_password=True, force=True)
    except Exception as exc:
        app.logger.exception("migrate-admin failed")
        return f"<h1>Migration failed</h1><pre>{exc}</pre>", 500
    return _migration_html_response(status), (200 if status.get("ok") else 500)


@app.get("/api/migrate-admin")
def api_migrate_admin_json():
    """JSON variant of /migrate-admin for the admin UI button."""
    mod = _load_migrate_admin_module()
    if mod is None:
        return jsonify({"ok": False, "error": "Migration script not found"}), 500
    try:
        status = mod.run_migration_with_status(reset_password=True, force=True)
    except Exception as exc:
        app.logger.exception("migrate-admin api failed")
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify(status), (200 if status.get("ok") else 500)


@app.route("/setup")
def setup_database():
    """Temporary route to seed database — remove after first use."""
    result: dict[str, Any] = {"steps": []}

    def _count_table(table: str) -> int:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0

    try:
        result["steps"].append("Running init_db.py...")
        r1 = subprocess.run(
            [sys.executable, str(BASE_DIR / "init_db.py")],
            timeout=30,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
        )
        result["steps"].append(f"init_db: {r1.returncode}")

        result["steps"].append("Running add_global_geography.py...")
        r2 = subprocess.run(
            [sys.executable, str(BASE_DIR / "add_global_geography.py")],
            timeout=60,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
        )
        result["steps"].append(f"global geography: {r2.returncode}")

        result["steps"].append("Running fix_geography.py (Indian states/villages)...")
        r3 = subprocess.run(
            [sys.executable, str(BASE_DIR / "fix_geography.py")],
            timeout=600,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
        )
        result["steps"].append(f"india geography: {r3.returncode}")
        if r3.returncode != 0:
            result["steps"].append(
                (r3.stderr or r3.stdout or "fix_geography failed").strip()[:500]
            )

        conn = sqlite3.connect(str(DB_PATH), timeout=15)
        continent_count = _count_table("continent")
        country_count = _count_table("country")
        state_count = _count_table("state")
        district_count = _count_table("district")
        tehsil_count = _count_table("tehsil")
        village_count = _count_table("village")
        conn.close()

        result["continent_count"] = continent_count
        result["country_count"] = country_count
        result["state_count"] = state_count
        result["district_count"] = district_count
        result["tehsil_count"] = tehsil_count
        result["village_count"] = village_count
        result["status"] = (
            "success"
            if state_count > 0 and village_count > 0
            else "partial"
        )

        return f"""
        <h1>Database Setup Complete</h1>
        <ul>
            <li>Continents: {continent_count}</li>
            <li>Countries: {country_count}</li>
            <li>States: {state_count}</li>
            <li>Districts: {district_count}</li>
            <li>Tehsils: {tehsil_count}</li>
            <li>Villages: {village_count}</li>
            <li>Status: {result['status']}</li>
        </ul>
        <p><a href="/register">Go to Registration Page</a></p>
        """

    except Exception as exc:
        return f"<h1>Error</h1><pre>{str(exc)}</pre>"


@app.post("/api/admin/bootstrap")
def api_admin_bootstrap():
    """
    Create or reset an admin account (Railway / production bootstrap).

    Secured with ``X-Admin-Key`` or ``X-Master-Key`` matching ``ADMIN_API_KEY``.
    """
    admin_key = (
        (request.headers.get("X-Admin-Key") or "").strip()
        or (request.headers.get("X-Master-Key") or "").strip()
    )
    expected = getattr(config, "ADMIN_API_KEY", "") or ""
    if not expected or not admin_key or admin_key != expected:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    conn = get_db()
    try:
        result = admin_bootstrap.create_admin_user(
            conn,
            email=str(payload.get("email") or "admin@qumanity.com"),
            phone=str(payload.get("phone") or "9999999999"),
            first_name=str(payload.get("first_name") or payload.get("name") or "Admin"),
            last_name=str(payload.get("last_name") or "User"),
            password=str(payload.get("password") or admin_bootstrap.DEFAULT_PASSWORD),
            private_id=str(payload.get("private_id") or admin_bootstrap.DEFAULT_PRIVATE_ID),
            public_id=str(payload.get("public_id") or admin_bootstrap.DEFAULT_PUBLIC_ID)
            if payload.get("public_id")
            else None,
            reset_password=bool(payload.get("reset_password", True)),
        )
    except Exception as exc:
        conn.rollback()
        app.logger.exception("admin bootstrap failed")
        return jsonify({"error": str(exc)}), 500

    return jsonify({"success": True, **result})


@app.post("/api/setup/migrate-admin")
def api_setup_migrate_admin():
    """
    Run admin conversion + HU- prefix migration (Railway-friendly).

    Secured with ``X-Admin-Key`` or ``X-Master-Key`` matching ``ADMIN_API_KEY``.
  Use when Railway shell cannot find scripts or railway CLI is unavailable:

      curl -X POST https://YOUR-APP/api/setup/migrate-admin \\
        -H "X-Admin-Key: YOUR_ADMIN_API_KEY"
    """
    admin_key = (
        (request.headers.get("X-Admin-Key") or "").strip()
        or (request.headers.get("X-Master-Key") or "").strip()
    )
    expected = getattr(config, "ADMIN_API_KEY", "") or ""
    if not expected or not admin_key or admin_key != expected:
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    reset_password = bool(payload.get("reset_password", True))

    try:
        import importlib.util

        script_path = BASE_DIR / "scripts" / "migrate_admin_fix.py"
        if not script_path.is_file():
            return jsonify({"error": f"Migration script not found at {script_path}"}), 500
        spec = importlib.util.spec_from_file_location("migrate_admin_fix", script_path)
        if spec is None or spec.loader is None:
            return jsonify({"error": "Could not load migration script"}), 500
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        ok = mod.run_migration(reset_password=reset_password)
    except Exception as exc:
        app.logger.exception("migrate-admin failed")
        return jsonify({"error": str(exc)}), 500

    if not ok:
        return jsonify({"error": "Migration failed — check server logs"}), 500

    return jsonify(
        {
            "success": True,
            "message": "Admin migration complete",
            "admin_private_id": ADMIN_PRIVATE_ID,
            "admin_public_id": ADMIN_PUBLIC_ID,
            "admin_email": "sekyorintantra@gmail.com",
            "admin_phone": "8287696616",
        }
    )


def _cli_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@click.command("create-admin")
@click.option("--email", default="admin@qumanity.com", help="Admin email (optional metadata)")
@click.option("--phone", default="9999999999", help="Admin phone (optional metadata)")
@click.option("--first-name", default="Admin")
@click.option("--last-name", default="User")
@click.option("--password", default=admin_bootstrap.DEFAULT_PASSWORD)
@click.option("--private-id", default=admin_bootstrap.DEFAULT_PRIVATE_ID)
@click.option("--no-reset-password", is_flag=True, help="Keep existing password if admin exists")
def create_admin_cli(
    email: str,
    phone: str,
    first_name: str,
    last_name: str,
    password: str,
    private_id: str,
    no_reset_password: bool,
) -> None:
    """Create or update an admin user in the local/Railway SQLite database."""
    conn = _cli_db_connection()
    try:
        result = admin_bootstrap.create_admin_user(
            conn,
            email=email,
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            password=password,
            private_id=private_id,
            reset_password=not no_reset_password,
        )
    except Exception as exc:
        conn.close()
        raise click.ClickException(str(exc)) from exc
    conn.close()

    click.echo(f"Admin {result['action']} successfully.")
    click.echo(f"  Private ID: {result['private_id']}  (use this to log in)")
    click.echo(f"  Public ID:  {result['public_id']}")
    if result.get("email"):
        click.echo(f"  Email:      {result['email']}")
    if result.get("phone"):
        click.echo(f"  Phone:      {result['phone']}")
    if result.get("password"):
        click.echo(f"  Password:   {result['password']}")
    click.echo(f"  Login:      {result['login_url']}")
    click.echo(f"  Admin UI:   {result['admin_verifications_url']}")


@click.command("reset-admin")
def reset_admin_cli() -> None:
    """Delete all admins and create HU-014918240 / P@y#umans123."""
    import subprocess

    script = BASE_DIR / "scripts" / "reset_admin.py"
    result = subprocess.run([sys.executable, str(script)], cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise click.ClickException("reset_admin.py failed")


@click.command("fix-admin-login")
def fix_admin_login_cli() -> None:
    """Diagnose and repair admin login (HU-014918240 / P@y#umans123)."""
    import subprocess

    script = BASE_DIR / "scripts" / "fix_admin_login.py"
    result = subprocess.run([sys.executable, str(script)], cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise click.ClickException("fix_admin_login.py failed")


@click.command("migrate-user-ids")
@click.option("--db", default=None, help="Database path (default: DATABASE_PATH)")
@click.argument("action", type=click.Choice(["convert-admin", "add-hu-prefix", "all"]))
@click.option("--from", "source_id", default="306931970", help="Source Private ID for convert-admin/all")
def migrate_user_ids_cli(action: str, db: str | None, source_id: str) -> None:
    """Migrate Private IDs: convert-admin, add-hu-prefix, or all."""
    import subprocess

    script = BASE_DIR / "scripts" / "migrate_user_ids.py"
    cmd = [sys.executable, str(script), action]
    if action in ("convert-admin", "all"):
        cmd.extend(["--from", source_id])
    if db:
        cmd.extend(["--db", db])
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    if result.returncode != 0:
        raise click.ClickException("migrate_user_ids.py failed")


app.cli.add_command(create_admin_cli)
app.cli.add_command(reset_admin_cli)
app.cli.add_command(fix_admin_login_cli)
app.cli.add_command(migrate_user_ids_cli)


# Defer migration until the app module is fully loaded (avoids import deadlock on Railway).
with app.app_context():
    _start_admin_migration_background()


if __name__ == "__main__":
    port = int(os.environ.get("FLASK_RUN_PORT", os.environ.get("PORT", 5001)))
    app.run(debug=True, host="0.0.0.0", port=port)
