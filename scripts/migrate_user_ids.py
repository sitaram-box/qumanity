#!/usr/bin/env python3
"""
Migrate Qumanity user Private IDs to HU- prefix and convert a user to admin.

Usage (local or Railway):
  python scripts/migrate_user_ids.py convert-admin --from 306931970
  python scripts/migrate_user_ids.py add-hu-prefix
  python scripts/migrate_user_ids.py all --from 306931970
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import identity_core
import qoin_core

from app import (
    ADMIN_PRIVATE_ID,
    ADMIN_PUBLIC_ID,
    format_human_private_id,
    migrate_users_app_extensions,
)

DB_PATH = os.environ.get("DATABASE_PATH", str(ROOT / "indiaq.db"))
ADMIN_SKIP_PREFIXES = ("HU-", "AN-", "NB-", "H_U_")


def _connect(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.is_file():
        print(f"Database not found: {path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _find_user_by_private_id(conn: sqlite3.Connection, private_id: str) -> sqlite3.Row | None:
    pid = str(private_id or "").strip()
    candidates = [pid]
    if pid.isdigit() and len(pid) == 9:
        candidates.append(format_human_private_id(pid))
    if pid.upper().startswith("HU-") and len(pid) > 3:
        candidates.append(pid[3:])
    for cand in candidates:
        row = conn.execute(
            "SELECT * FROM users WHERE private_id = ? COLLATE NOCASE",
            (cand,),
        ).fetchone()
        if row:
            return row
    return None


def _remove_user_by_private_id(conn: sqlite3.Connection, private_id: str) -> None:
    pid = str(private_id).strip()
    try:
        conn.execute(
            "DELETE FROM wallets WHERE owner_type = 'user' AND owner_id = ?",
            (pid,),
        )
    except sqlite3.OperationalError:
        pass
    conn.execute("DELETE FROM users WHERE private_id = ? COLLATE NOCASE", (pid,))


def convert_user_to_admin(
    conn: sqlite3.Connection,
    source_private_id: str,
) -> None:
    """Promote user to admin with H_U_ADMIN / ADMIN-PUBLIC IDs."""
    source = _find_user_by_private_id(conn, source_private_id)
    if not source:
        print(f"User not found for Private ID: {source_private_id}", file=sys.stderr)
        sys.exit(1)

    old_pid = str(source["private_id"])
    old_pub = str(source["public_id"] or "")
    name = f"{source['first_name']} {source['last_name']}".strip()

    print(f"Found user: {name}")
    print(f"  Current Private ID: {old_pid}")
    print(f"  Current Public ID:  {old_pub}")

    if old_pid.upper() == ADMIN_PRIVATE_ID:
        conn.execute(
            """
            UPDATE users
            SET public_id = ?, is_admin = 1, is_active = 1,
                account_status = 'active', temp_access = 0
            WHERE private_id = ?
            """,
            (ADMIN_PUBLIC_ID, ADMIN_PRIVATE_ID),
        )
        conn.commit()
        print("User is already H_U_ADMIN — admin flags refreshed.")
        return

    existing_admin = conn.execute(
        "SELECT id, private_id FROM users WHERE private_id = ? COLLATE NOCASE",
        (ADMIN_PRIVATE_ID,),
    ).fetchone()
    if existing_admin and int(existing_admin["id"]) != int(source["id"]):
        print(f"Removing existing bootstrap admin ({ADMIN_PRIVATE_ID})…")
        _remove_user_by_private_id(conn, ADMIN_PRIVATE_ID)

    identity_core.reassign_user_private_id(
        conn,
        old_pid,
        ADMIN_PRIVATE_ID,
        new_public_id=ADMIN_PUBLIC_ID,
    )
    conn.execute(
        """
        UPDATE users
        SET is_admin = 1,
            is_active = 1,
            account_status = 'active',
            temp_access = 0,
            verification_failed_reason = NULL,
            public_id = ?
        WHERE private_id = ?
        """,
        (ADMIN_PUBLIC_ID, ADMIN_PRIVATE_ID),
    )
    qoin_core.ensure_wallet(conn, "user", ADMIN_PRIVATE_ID)
    conn.commit()

    print("User converted to admin!")
    print(f"  Private ID: {ADMIN_PRIVATE_ID}")
    print(f"  Public ID:  {ADMIN_PUBLIC_ID}")
    print("  Password: unchanged (use your existing password)")


def add_hu_prefix_to_users(conn: sqlite3.Connection) -> int:
    """Add HU- prefix to legacy numeric Private IDs."""
    rows = conn.execute(
        """
        SELECT id, private_id FROM users
        WHERE COALESCE(is_admin, 0) = 0
        ORDER BY id
        """
    ).fetchall()
    updated = 0
    for row in rows:
        pid = str(row["private_id"] or "").strip()
        if not pid:
            continue
        upper = pid.upper()
        if upper == ADMIN_PRIVATE_ID or upper.startswith(ADMIN_SKIP_PREFIXES):
            continue
        if not re.fullmatch(r"\d{9}", pid):
            continue
        new_pid = format_human_private_id(pid)
        conflict = conn.execute(
            "SELECT 1 FROM users WHERE private_id = ? COLLATE NOCASE AND id != ?",
            (new_pid, int(row["id"])),
        ).fetchone()
        if conflict:
            print(f"  Skip {pid}: {new_pid} already taken", file=sys.stderr)
            continue
        identity_core.reassign_user_private_id(conn, pid, new_pid)
        updated += 1
        print(f"  {pid} → {new_pid}")
    conn.commit()
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Qumanity user Private IDs")
    parser.add_argument("--db", default=DB_PATH, help="Path to SQLite database")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("convert-admin", help="Convert a user to H_U_ADMIN")
    p_admin.add_argument(
        "--from",
        dest="source_id",
        default="306931970",
        help="Source Private ID (numeric or HU- prefixed)",
    )

    sub.add_parser("add-hu-prefix", help="Add HU- prefix to all legacy numeric IDs")

    p_all = sub.add_parser("all", help="Convert admin then add HU- prefix to others")
    p_all.add_argument("--from", dest="source_id", default="306931970")

    args = parser.parse_args()
    conn = _connect(args.db)
    migrate_users_app_extensions(conn)
    qoin_core.migrate_qoin_economy_tables(conn)

    if args.command == "convert-admin":
        convert_user_to_admin(conn, args.source_id)
    elif args.command == "add-hu-prefix":
        count = add_hu_prefix_to_users(conn)
        print(f"\nUpdated {count} user(s) with HU- prefix.")
    elif args.command == "all":
        convert_user_to_admin(conn, args.source_id)
        count = add_hu_prefix_to_users(conn)
        print(f"\nUpdated {count} other user(s) with HU- prefix.")


if __name__ == "__main__":
    main()
