#!/usr/bin/env python3
"""Initialise / migrate core SQLite tables inside indiaq.db (geography stays untouched).

Configure:
  DB_PATH — default ``BASE_DIR / "indiaq.db"`` (same folder as this repo / Flask app).

Run:
  python3 init_db.py            # idempotent: create missing tables, add missing columns
  python3 init_db.py --reset    # DESTRUCTIVE: drop core app tables then recreate (data loss)

Calendar tables (calendar_solar, calendar_lunar): run ``python3 init_calendar_2026.py`` separately.

This script mirrors the migrations run by Flask on each request (``app._before_request``),
plus wallet column extensions and the admin profile data patch. It never deletes rows
unless you pass ``--reset``.
"""

from __future__ import annotations

import argparse
import sqlite3
from typing import Callable

import election_scheduler
import identity_core
import language_core
import leadership_core
import qoin_core
import donation_core
import referral_core
import scheduler  # noqa: F401 — weekly settlement + monthly varna recalc
import varna_core
import element_core
import global_core
import planetary_core
import zodiac_calendar
from app import (
    BASE_DIR,
    DB_PATH,
    FAMILY_RELATIONSHIPS_SQL,
    POST_TABLE_SQL,
    USER_TABLE_SQL,
    ensure_users_country_column,
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
    migrate_user_education_work_v2,
    migrate_user_family_setup_table,
    migrate_users_app_extensions,
)
from social_core import ensure_posts_escalation_columns, ensure_wallet_and_vote_tables
from blockchain_core import migrate_blockchain_schema


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def ensure_wallet_schema(conn: sqlite3.Connection) -> None:
    """Add optional wallet columns used by newer Qoin code paths."""
    if not _table_exists(conn, "wallets"):
        return
    cols = _table_columns(conn, "wallets")
    additions: list[tuple[str, str]] = [
        ("qoins_encrypted", "TEXT"),
        ("balance_qoins", "TEXT"),
    ]
    for col_name, decl in additions:
        if col_name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE wallets ADD COLUMN {col_name} {decl}")
            print(f"  wallets: added column {col_name}")
        except sqlite3.OperationalError as exc:
            print(f"  wallets: skip column {col_name} ({exc})")


def apply_migrations(conn: sqlite3.Connection, *, verbose: bool = True) -> None:
    """
    Idempotent schema bootstrap — same order as ``app._before_request`` migrations,
    plus admin profile patch and extra wallet columns.
    """
    steps: list[tuple[str, Callable[[sqlite3.Connection], None]]] = [
        ("users / posts base tables", lambda c: c.executescript(USER_TABLE_SQL + POST_TABLE_SQL)),
        ("users.country column", ensure_users_country_column),
        ("users app extensions", migrate_users_app_extensions),
        ("messages", migrate_messages_table),
        ("connection_requests", migrate_connection_requests_table),
        ("connection_requests.accepted_at", migrate_connection_requests_accepted_at),
        ("connection_requests.family_member_type", migrate_connection_requests_family_member_type),
        ("connection_requests.request_member_profile", migrate_connection_requests_request_member_profile),
        ("family_profile / family_members", migrate_family_tables),
        ("family_relationships", migrate_family_relationships_table),
        ("family_relationships indexes", lambda c: c.executescript(FAMILY_RELATIONSHIPS_SQL)),
        ("family_removal_requests", migrate_family_removal_requests_table),
        ("link_requests", migrate_link_requests_table),
        ("user_family_setup", migrate_user_family_setup_table),
        ("user_education / user_work", migrate_user_education_work_v2),
        ("connection_requests.request_member_life_stage", migrate_connection_requests_life_stage),
        ("election tables", election_scheduler.migrate_election_tables),
        ("leadership_council", leadership_core.migrate_leadership_council),
        ("leadership_council mentor seed", leadership_core.seed_mentor_slots),
        ("state_languages / location_translations", language_core.migrate_and_seed),
        ("pilot state language translations", language_core.seed_pilot_location_translations),
        ("wallets / post_votes / qoin_transactions", ensure_wallet_and_vote_tables),
        ("qoin_transactions extensions", qoin_core.migrate_qoin_transactions),
        ("cash_donations", qoin_core.migrate_cash_donations),
        ("qoin economy tables", qoin_core.migrate_qoin_economy_tables),
        ("calendar event tables", zodiac_calendar.migrate_calendar_event_tables),
        ("posts escalation columns", ensure_posts_escalation_columns),
        # current_level supports Indian (personal→village→…→earth) and global
        # (personal→country→continent→earth) tracks; see social_core.post_level_order
        ("posts soft-delete columns", migrate_posts_deletion_columns),
        ("wallets extra columns", ensure_wallet_schema),
        ("village platform tables", lambda c: __import__("village_platform").migrate_village_platform_tables(c)),
        ("identity / user_accounts / otp", identity_core.migrate_identity_tables),
        ("referral schema", referral_core.migrate_referral_schema),
        ("donation distribution schema", donation_core.migrate_donation_schema),
        ("varna / category schema", varna_core.migrate_varna_schema),
        ("space / planetary schema", planetary_core.migrate_space_schema),
        ("global location schema", global_core.migrate_global_location_schema),
        ("zodiac planets / country languages", element_core.migrate_element_core_schema),
        ("admin profile patch (H_U_ADMIN)", migrate_admin_user_profile),
        ("blockchain schema", migrate_blockchain_schema),
    ]

    for label, fn in steps:
        if verbose:
            print(f"Migrating: {label}…")
        fn(conn)

    conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "DESTRUCTIVE: drop core app tables (users, posts, wallets, messages, …) "
            "before applying migrations. All data in those tables is lost."
        ),
    )
    args = parser.parse_args()

    if not DB_PATH.parent.is_dir():
        raise SystemExit(f"Project folder missing: {DB_PATH.parent}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if args.reset:
            print("WARNING: --reset will DELETE data in core app tables.")
            for table in (
                "post_votes",
                "qoin_transactions",
                "wallets",
                "connection_requests",
                "family_removal_requests",
                "family_relationships",
                "family_members",
                "family_profile",
                "link_requests",
                "user_family_setup",
                "user_education",
                "user_work",
                "messages",
                "posts",
                "users",
            ):
                conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.commit()
            print("Dropped core app tables listed above.")

        apply_migrations(conn)

        print(f"\nMigrations complete: {DB_PATH.resolve()}")
        print("No data was deleted (unless you used --reset).")
        print("Optional: python3 init_calendar_2026.py")
        print("Optional: python3 scripts/seed_global_locations.py")
        print("Optional: python3 scripts/add_all_country_states.py")
        print("Verify schema: python3 check_db.py")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
