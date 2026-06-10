#!/usr/bin/env python3
"""Delete listed demo user accounts (preserves H_U_ADMIN)."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

DB_PATH = os.environ.get("DATABASE_PATH", "indiaq.db")
ADMIN_PRIVATE_ID = "H_U_ADMIN"

DEMO_USERS = [
    "I4U9-DU-F-Y-ZL-HKG",
    "RR8-DU-GM-AB-WS-CAN",
    "T24-DU-GF-AY-AA-SS.TS.2.E.2",
    "MRXU-PM-GM-AV-FA-NS.HR.11.3.A9",
    "NV41-DU-GM-AY-FS-CS.JK.1.5.33",
    "DMG3-DU-GM-AB-FA-ES.JH.11.D.F",
    "380373241",
    "NKEC-DU-GF-AB-WC-CS.JK.B.3.11",
]

# (table, column) pairs — best-effort; missing tables/columns are skipped.
USER_REF_DELETES: tuple[tuple[str, str], ...] = (
    ("connection_requests", "from_user_private_id"),
    ("connection_requests", "to_user_private_id"),
    ("messages", "sender_id"),
    ("messages", "recipient_id"),
    ("post_votes", "voter_private_id"),
    ("posts", "user_private_id"),
    ("family_members", "user_private_id"),
    ("family_members", "member_private_id"),
    ("family_profile", "user_private_id"),
    ("election_votes", "voter_private_id"),
    ("election_candidates", "candidate_private_id"),
    ("qoin_transactions", "user_private_id"),
    ("user_accounts", "user_private_id"),
    ("pending_referrals", "referrer_private_id"),
    ("pending_referrals", "referred_private_id"),
    ("user_education", "user_private_id"),
    ("user_work", "user_private_id"),
    ("user_family_setup", "user_private_id"),
    ("user_birth_planets", "user_private_id"),
    ("link_requests", "from_user_private_id"),
    ("link_requests", "to_user_private_id"),
    ("category_history", "user_private_id"),
    ("varna_appeals", "user_private_id"),
    ("akashic_records", "user_private_id"),
)


def _safe_delete(conn: sqlite3.Connection, table: str, column: str, pid: str) -> int:
    try:
        cur = conn.execute(
            f"DELETE FROM {table} WHERE {column} = ?",
            (pid,),
        )
        return cur.rowcount
    except sqlite3.OperationalError:
        return 0


def _delete_family_relationships(conn: sqlite3.Connection, pid: str) -> int:
    try:
        cur = conn.execute(
            """
            DELETE FROM family_relationships
             WHERE source_id IN (SELECT id FROM family_members WHERE user_private_id = ?)
                OR target_id IN (SELECT id FROM family_members WHERE user_private_id = ?)
            """,
            (pid, pid),
        )
        return cur.rowcount
    except sqlite3.OperationalError:
        return 0


def delete_demo_users(db_path: str = DB_PATH) -> None:
    path = Path(db_path)
    if not path.is_file():
        print(f"Database not found: {path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    print("Deleting demo users…")

    for pid in DEMO_USERS:
        if pid.upper() == ADMIN_PRIVATE_ID:
            print(f"  Skipping admin id: {pid}")
            continue
        print(f"  {pid}")
        _delete_family_relationships(conn, pid)
        for table, column in USER_REF_DELETES:
            n = _safe_delete(conn, table, column, pid)
            if n:
                print(f"    - {table}.{column}: {n}")
        try:
            n = conn.execute(
                "DELETE FROM wallets WHERE owner_type = 'user' AND owner_id = ?",
                (pid,),
            ).rowcount
            if n:
                print(f"    - wallets: {n}")
        except sqlite3.OperationalError:
            pass
        n = _safe_delete(conn, "users", "private_id", pid)
        if n:
            print(f"    - users: {n}")

    conn.commit()
    rows = conn.execute(
        "SELECT private_id, first_name, last_name, account_type, is_admin FROM users ORDER BY private_id"
    ).fetchall()
    conn.close()

    print("\nRemaining users:")
    for row in rows:
        admin_flag = " [admin]" if row["is_admin"] else ""
        print(
            f"  {row['private_id']} — {row['first_name']} {row['last_name']} "
            f"({row['account_type']}){admin_flag}"
        )


if __name__ == "__main__":
    delete_demo_users(sys.argv[1] if len(sys.argv) > 1 else DB_PATH)
