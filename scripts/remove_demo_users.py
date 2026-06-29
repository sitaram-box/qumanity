#!/usr/bin/env python3
"""Remove all demo users (is_demo=1) while preserving admin accounts."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo_user_core import count_demo_users, delete_all_demo_users, migrate_demo_schema

DEFAULT_DB = ROOT / "indiaq.db"


def verify(conn: sqlite3.Connection) -> None:
    demo_left = conn.execute(
        "SELECT COUNT(*) FROM users WHERE is_demo = 1 AND COALESCE(is_admin, 0) = 0"
    ).fetchone()[0]
    admins = conn.execute(
        "SELECT COUNT(*) FROM users WHERE COALESCE(is_admin, 0) = 1"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"Demo users remaining: {demo_left}")
    print(f"Admin users: {admins}")
    print(f"Total users: {total}")
    if admins:
        rows = conn.execute(
            "SELECT private_id, first_name, last_name FROM users "
            "WHERE COALESCE(is_admin, 0) = 1 ORDER BY private_id"
        ).fetchall()
        for row in rows:
            pid = row["private_id"] if hasattr(row, "keys") else row[0]
            name = (
                f"{row['first_name']} {row['last_name']}"
                if hasattr(row, "keys")
                else f"{row[1]} {row[2]}"
            )
            print(f"  Admin preserved: {pid} — {name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove all demo users from Qumanity (preserves admin accounts)"
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to indiaq.db")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only print counts; do not delete",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        migrate_demo_schema(conn)
        demo_count = count_demo_users(conn)

        if args.verify_only:
            print(f"Demo users to remove: {demo_count}")
            verify(conn)
            return

        if demo_count == 0:
            print("No demo users found.")
            verify(conn)
            return

        print(f"Found {demo_count:,} demo users (is_demo=1, not admin).")
        print("Admin accounts (is_admin=1) will be preserved.")
        print("All posts, votes, elections, wallets, and related data will be removed.")

        if not args.yes:
            confirm = input("Delete all demo users? Type 'yes' to confirm: ")
            if confirm.strip().lower() != "yes":
                print("Aborted.")
                return

        result = delete_all_demo_users(conn)
        deleted = int(result.get("deleted", 0))
        rows_deleted = result.get("rows_deleted") or {}

        print(f"Removed {deleted:,} demo users.")
        if rows_deleted:
            print("Associated rows removed:")
            for key, n in sorted(rows_deleted.items()):
                if n:
                    print(f"  {key}: {n:,}")

        print("\nVerification:")
        verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
