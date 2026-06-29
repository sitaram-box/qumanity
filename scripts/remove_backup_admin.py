#!/usr/bin/env python3
"""Remove Backup Admin account (HU-999000001 / BACKUP-PUBLIC) from the database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import admin_login_repair
from db_path import resolve_database_path

BACKUP_PRIVATE_ID = admin_login_repair.BACKUP_PRIVATE_ID
BACKUP_PUBLIC_ID = admin_login_repair.BACKUP_PUBLIC_ID


def remove_backup_admin(conn: sqlite3.Connection) -> dict[str, int | bool]:
    existing = conn.execute(
        """
        SELECT private_id, public_id, first_name, last_name
        FROM users
        WHERE private_id = ? COLLATE NOCASE OR public_id = ? COLLATE NOCASE
        """,
        (BACKUP_PRIVATE_ID, BACKUP_PUBLIC_ID),
    ).fetchall()

    removed_private = admin_login_repair._remove_user_hard(conn, BACKUP_PRIVATE_ID)
    conn.commit()

    remaining = conn.execute(
        """
        SELECT private_id, public_id FROM users
        WHERE private_id = ? COLLATE NOCASE OR public_id = ? COLLATE NOCASE
        """,
        (BACKUP_PRIVATE_ID, BACKUP_PUBLIC_ID),
    ).fetchall()

    return {
        "found_before": len(existing),
        "removed_private": removed_private,
        "remaining": len(remaining),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove Backup Admin from Qumanity (HU-999000001 / BACKUP-PUBLIC)"
    )
    parser.add_argument(
        "--db",
        default=str(resolve_database_path(ROOT)),
        help="Path to SQLite database",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        before = conn.execute(
            """
            SELECT private_id, public_id FROM users
            WHERE private_id = ? COLLATE NOCASE OR public_id = ? COLLATE NOCASE
            """,
            (BACKUP_PRIVATE_ID, BACKUP_PUBLIC_ID),
        ).fetchall()

        if not before:
            print("⚠️ Backup Admin not found or already removed")
            print("✅ Confirmed: Backup Admin is gone")
            return

        if not args.yes:
            print("Backup Admin account(s) to remove:")
            for row in before:
                print(f"  {row['private_id']} / {row['public_id']}")
            confirm = input("Delete Backup Admin? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Cancelled.")
                return

        result = remove_backup_admin(conn)
        if result["removed_private"] or result["found_before"]:
            print(
                f"✅ Backup Admin removed successfully! "
                f"(found {result['found_before']} row(s) before delete)"
            )
        else:
            print("⚠️ Backup Admin not found or already removed")

        if result["remaining"]:
            print(f"⚠️ Still found: {result['remaining']} row(s)")
        else:
            print("✅ Confirmed: Backup Admin is gone")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
