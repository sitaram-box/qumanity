#!/usr/bin/env python3
"""
Complete the migration for remaining / failed tables.

Use after migrate_to_postgres.py if wallet_paise_ledger or other tables failed.

Run: python3 complete_migration.py
"""

from __future__ import annotations

import sqlite3
import sys

from dotenv import load_dotenv

load_dotenv()

from migrate_to_postgres import (  # noqa: E402
    CRM_DDL,
    SQLITE_PATH,
    create_performance_indexes,
    migrate_table,
    pg_connect,
    sqlite_table_names,
    table_row_count,
)

# Tables commonly missed or failed on first pass.
REMAINING_TABLES = [
    "wallet_paise_ledger",
    "volunteers",
    "referral_agents",
    "posts",
    "post_votes",
    "messages",
    "election_candidates",
    "election_votes",
    "family_members",
    "family_relationships",
    "weekly_statements",
    "registration_donations",
    "donation_distributions",
    "donation_transactions",
    "karma_action_types",
    "karma_transactions",
    "leadership_council",
    "location_translations",
    "state_languages",
    "settlement_runs",
    "cash_donations",
    "wallet_transactions",
    "user_accounts",
    "referrals",
    "share_logs",
    "employment_requests",
]

SUMMARY_TABLES = [
    "users",
    "wallets",
    "wallet_paise_ledger",
    "pending_transactions",
    "tickets",
    "vendors",
    "orders",
    "ratings",
    "volunteers",
]


def main() -> int:
    print("=" * 60)
    print("Completing Qumanity PostgreSQL Migration")
    print("=" * 60)

    if not SQLITE_PATH.is_file():
        print(f"ERROR: SQLite not found at {SQLITE_PATH}")
        return 1

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    pg_conn, _ = pg_connect()
    pg_cur = pg_conn.cursor()

    print("\nEnsuring CRM tables exist…")
    pg_cur.execute(CRM_DDL)
    pg_conn.commit()

    sqlite_tables = set(sqlite_table_names(sqlite_cur))
    todo = [t for t in REMAINING_TABLES if t in sqlite_tables]
    extra = sorted(sqlite_tables - set(REMAINING_TABLES) - set(SUMMARY_TABLES))
    for t in extra:
        if t not in todo:
            todo.append(t)

    print(f"\nProcessing {len(todo)} table(s)…")
    for table in todo:
        print(f"\n→ {table}")
        force = table == "wallet_paise_ledger"
        migrate_table(sqlite_cur, pg_cur, pg_conn, table, force_recreate=force)

    create_performance_indexes(pg_cur, pg_conn)

    sqlite_conn.close()
    pg_cur.close()
    pg_conn.close()

    print("\n" + "=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
    print("\nFinal counts:")

    pg_conn, _ = pg_connect()
    pg_cur = pg_conn.cursor()
    for table in SUMMARY_TABLES:
        count = table_row_count(pg_cur, table)
        if count is None:
            print(f"  {table}: table not found")
        else:
            print(f"  {table}: {count} rows")
    pg_cur.close()
    pg_conn.close()

    print("\nNext: python3 verify_integration.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
