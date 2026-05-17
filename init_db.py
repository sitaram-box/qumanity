#!/usr/bin/env python3
"""Initialise core SQLite tables inside indiaq.db (geography stays untouched).

Configure:
  DB_PATH — default ``BASE_DIR / "indiaq.db"`` (same folder as this repo / Flask app).

Run:
  python3 init_db.py            # ensures tables / indexes exist
  python3 init_db.py --reset    # DROP listed tables + recreate

Calendar tables (calendar_solar, calendar_lunar): run ``python3 init_calendar_2026.py`` separately.

Tables applied by this script (in order):
  1. ``users`` — from ``app.USER_TABLE_SQL``
  2. ``posts`` — migrated in-place if an old table exists, then ``app.POST_TABLE_SQL`` (indexes)
     including soft-delete columns (``deleted_at``, ``deleted_by``, ``delete_reason``).
  3. ``post_votes`` — one row per voter per post (vote_value: +1, 0, -1)
  4. ``wallets`` — ``owner_type`` ``'user'`` | ``'location'``, ``owner_id`` text key
  5. ``qoin_transactions`` — audit log for user Qoin credits
  6. ``messages`` — private account messaging (via ``app.migrate_messages_table``);
     also carries admin-deletion notices authored by the SYSTEM sender.
  7. User extension columns (``account_type``, ``is_admin``, … via ``app.migrate_users_app_extensions``)
  8. ``connection_requests`` — family / social request workflow (+ ``accepted_at`` column)
  9. ``family_profile`` / ``family_members`` — family activation form + close-family rows
     (includes ``is_placeholder`` slots and ``source = 'self'`` for the account holder)
 10. ``family_relationships`` — graph edges as ``source_id`` / ``target_id`` / ``relation_type``
 11. ``family_removal_requests`` — admin-approval queue for family removals
     requested more than 2 days after the member was added
 12. ``link_requests``, ``user_family_setup`` (``answers_json`` stores initial family questionnaire,
     including sibling name lists), ``user_education``, ``user_work`` —
     via ``app.migrate_*`` helpers
 13. Quantum Punch elections — ``election_cycles``, ``election_candidates``,
     ``election_votes``, ``village_council`` (``election_scheduler.migrate_election_tables``)

``users`` must include ``age``, ``age_group``, and ``sun_sign`` (core ``USER_TABLE_SQL``) for
election nomination (Yuvak + matching sign) and voting (age 13+ + matching sign + village).

``election_candidates.status`` is ``pending`` | ``approved`` | ``rejected`` (plus optional
``rejection_reason``, ``reviewed_at`` via ``election_scheduler.migrate_election_tables``).

Admin profile (``H_U_ADMIN``): ``migrate_admin_user_profile`` sets DOB 1990-07-30, birth time
07:05, computed age/age_group, sun sign Leo, element Fire (idempotent; other users unchanged).

``users.is_active`` — existing rows set active on migration; new Human Users activate after
registration donation (``/register/donation``). ``qoin_core.migrate_qoin_transactions`` extends
``qoin_transactions`` with recipient_type, rupee_value, etc.
"""

from __future__ import annotations

import argparse
import sqlite3

import election_scheduler
import qoin_core
from app import (
    BASE_DIR,
    FAMILY_RELATIONSHIPS_SQL,
    POST_TABLE_SQL,
    USER_TABLE_SQL,
    migrate_admin_user_profile,
    migrate_connection_requests_life_stage,
    migrate_connection_requests_table,
    migrate_connection_requests_accepted_at,
    migrate_connection_requests_family_member_type,
    migrate_connection_requests_request_member_profile,
    migrate_family_tables,
    migrate_family_relationships_table,
    migrate_family_removal_requests_table,
    migrate_link_requests_table,
    migrate_messages_table,
    migrate_posts_deletion_columns,
    migrate_user_education_table,
    migrate_user_family_setup_table,
    migrate_user_work_table,
    migrate_users_app_extensions,
)
from social_core import ensure_posts_escalation_columns, ensure_wallet_and_vote_tables

DB_PATH = BASE_DIR / "indiaq.db"

# --- Same DDL as ``social_core.WALLET_DDL`` (kept here for documentation / init). ---
SOCIAL_VOTES_WALLETS_QOIN_SQL = """
CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0,
    UNIQUE(owner_type, owner_id)
);
CREATE INDEX IF NOT EXISTS idx_wallets_owner ON wallets(owner_type, owner_id);

CREATE TABLE IF NOT EXISTS qoin_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_qoin_user ON qoin_transactions(user_private_id);

CREATE TABLE IF NOT EXISTS post_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    voter_private_id TEXT NOT NULL,
    vote_value INTEGER NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, voter_private_id)
);
CREATE INDEX IF NOT EXISTS idx_post_votes_post ON post_votes(post_id);
"""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _posts_column_names(conn: sqlite3.Connection) -> set[str]:
    if not _table_exists(conn, "posts"):
        return set()
    return {str(r[1]) for r in conn.execute("PRAGMA table_info(posts)")}


def migrate_posts_schema(conn: sqlite3.Connection) -> None:
    """
    Upgrade an existing ``posts`` table (e.g. old rows with only location_id)
    without dropping data. Must run *before* ``POST_TABLE_SQL`` so CREATE INDEX
    on ``current_level`` does not fail.

    Column set matches ``app.POST_TABLE_SQL`` / social escalation model.
    """
    if not _table_exists(conn, "posts"):
        return

    cols = _posts_column_names(conn)
    # (column_name, SQLite ALTER fragment). Use DEFAULT so existing rows get values.
    additions: list[tuple[str, str]] = [
        ("location_id", "TEXT"),
        ("current_level", "TEXT NOT NULL DEFAULT 'personal'"),
        ("level_start_time", "TIMESTAMP"),
        ("status", "TEXT NOT NULL DEFAULT 'live'"),
        ("total_score", "INTEGER NOT NULL DEFAULT 0"),
        ("previous_levels", "TEXT DEFAULT ''"),
        ("origin_village_id", "TEXT"),
        ("origin_tehsil_id", "TEXT"),
        ("origin_district_id", "TEXT"),
        ("origin_state_id", "TEXT"),
        ("origin_country_id", "TEXT"),
        ("origin_continent_id", "TEXT"),
        ("freeze_level", "TEXT"),
        ("qoins_settled", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col_name, decl in additions:
        if col_name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col_name} {decl}")
            print(f"  posts: added column {col_name}")
        except sqlite3.OperationalError as exc:
            print(f"  posts: skip column {col_name} ({exc})")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_posts_current_level ON posts(current_level);
        CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
        CREATE INDEX IF NOT EXISTS idx_posts_location_id ON posts(location_id);
        CREATE INDEX IF NOT EXISTS idx_posts_level_start_time ON posts(level_start_time);
        CREATE INDEX IF NOT EXISTS idx_posts_level_status ON posts(current_level, status);
        CREATE INDEX IF NOT EXISTS idx_posts_freeze_level ON posts(freeze_level);
        """
    )
    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop messages, users, posts, wallets, post_votes, qoin_transactions before applying schema.",
    )
    args = parser.parse_args()

    if not DB_PATH.parent.is_dir():
        raise SystemExit(f"Project folder missing: {DB_PATH.parent}")

    conn = sqlite3.connect(DB_PATH)
    try:
        if args.reset:
            conn.execute("DROP TABLE IF EXISTS post_votes")
            conn.execute("DROP TABLE IF EXISTS qoin_transactions")
            conn.execute("DROP TABLE IF EXISTS wallets")
            conn.execute("DROP TABLE IF EXISTS connection_requests")
            conn.execute("DROP TABLE IF EXISTS messages")
            conn.execute("DROP TABLE IF EXISTS posts")
            conn.execute("DROP TABLE IF EXISTS users")
            print(
                "Dropped messages, users, posts, wallets, post_votes, qoin_transactions."
            )

        conn.executescript(USER_TABLE_SQL)

        print("Migrating users extensions / messages…")
        migrate_users_app_extensions(conn)
        migrate_messages_table(conn)
        migrate_connection_requests_table(conn)
        migrate_connection_requests_accepted_at(conn)
        migrate_connection_requests_family_member_type(conn)
        migrate_connection_requests_request_member_profile(conn)
        migrate_family_tables(conn)
        migrate_family_relationships_table(conn)
        conn.executescript(FAMILY_RELATIONSHIPS_SQL)
        migrate_family_removal_requests_table(conn)
        migrate_link_requests_table(conn)
        migrate_user_family_setup_table(conn)
        migrate_user_education_table(conn)
        migrate_user_work_table(conn)
        migrate_connection_requests_life_stage(conn)

        print("Migrating posts schema (if needed)…")
        migrate_posts_schema(conn)

        conn.executescript(POST_TABLE_SQL)
        conn.executescript(SOCIAL_VOTES_WALLETS_QOIN_SQL)
        conn.commit()

        ensure_wallet_and_vote_tables(conn)
        ensure_posts_escalation_columns(conn)
        migrate_posts_deletion_columns(conn)
        election_scheduler.migrate_election_tables(conn)
        migrate_admin_user_profile(conn)
        qoin_core.migrate_qoin_transactions(conn)
        conn.commit()
        print(f"Core tables ready in {DB_PATH.resolve()}")
        print("Admin profile migration applied (H_U_ADMIN DOB / Leo / Fire).")
        print("Optional: python3 init_calendar_2026.py")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
