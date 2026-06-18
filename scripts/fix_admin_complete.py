#!/usr/bin/env python3
"""
Complete admin diagnostic and fix script.

Lists users, runs self-heal (primary + backup admin), optional full reset,
and verifies the web login path.

  python scripts/fix_admin_complete.py
  python scripts/fix_admin_complete.py --reset
  railway run python scripts/fix_admin_complete.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import admin_login_repair


def list_all_users(conn) -> None:
    print("\n📋 All users in database:")
    rows = conn.execute(
        """
        SELECT id, private_id, email, phone, is_admin, account_status,
               password_hash IS NOT NULL AS has_password
        FROM users
        ORDER BY COALESCE(id, rowid)
        """
    ).fetchall()
    if not rows:
        print("   (no users)")
        return
    for row in rows:
        role = "ADMIN" if int(row["is_admin"] or 0) else "user"
        id_disp = row["id"] if row["id"] is not None else "NULL"
        print(
            f"   ID: {id_disp}, Private: {row['private_id']}, "
            f"Email: {row['email']}, Role: {role}, "
            f"status: {row['account_status']}, pwd: {bool(row['has_password'])}"
        )


def diagnose_and_fix(*, full_reset: bool = False) -> bool:
    try:
        conn, db_path = admin_login_repair._connect_db()
    except FileNotFoundError as exc:
        print(f"❌ Database not found: {exc}")
        return False

    print(f"📁 Using database: {db_path}")

    admin_login_repair._ensure_schema(conn)
    list_all_users(conn)

    null_before = conn.execute(
        "SELECT COUNT(*) FROM users WHERE id IS NULL"
    ).fetchone()[0]
    if null_before:
        print(f"\n⚠️  {null_before} user(s) with NULL id — repairing…")

    print("\n🔄 Running admin self-heal (primary + backup)…")
    heal = admin_login_repair.ensure_admin_healthy(conn, force=True)
    print(f"   actions: {heal.get('actions')}")
    print(f"   login_verified: {heal.get('login_verified')}")
    print(f"   login_simulated: {heal.get('login_simulated')}")

    status: dict = {}
    if full_reset:
        print("\n🔄 Full admin reset requested…")
        conn.close()
        status = admin_login_repair.run_reset()
        if status.get("log"):
            print(status["log"])
    else:
        conn.close()

    login_verified = bool(
        heal.get("login_verified") or status.get("login_verified")
    )
    login_simulated = bool(
        heal.get("login_simulated") or status.get("login_simulated")
    )

    print("\n" + "=" * 50)
    if login_verified and login_simulated:
        print("✅ Admin login FIXED!")
    elif login_verified:
        print("⚠️  Password OK but login simulation failed — check users.id")
    else:
        print("❌ Admin login STILL FAILING!")
    print(f"   Primary Private ID: {admin_login_repair.ADMIN_PRIVATE_ID}")
    print(f"   Primary login OTP: {admin_login_repair.ADMIN_PRIVATE_ID[len('HU-'):]}")
    print(f"   Primary password: {admin_login_repair.ADMIN_PASSWORD}")
    print(f"   Backup Private ID: {admin_login_repair.BACKUP_PRIVATE_ID}")
    print(f"   Backup login OTP: {admin_login_repair.BACKUP_PRIVATE_ID[len('HU-'):]}")
    print(f"   Backup password: {admin_login_repair.BACKUP_PASSWORD}")
    print(f"   login_verified: {login_verified}")
    print(f"   login_simulated: {login_simulated}")
    if status.get("deleted_admins"):
        print(f"   deleted_admins: {status.get('deleted_admins')}")
    print("=" * 50)

    return login_verified and login_simulated


def main() -> int:
    parser = argparse.ArgumentParser(description="Admin diagnostic and fix")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="After self-heal, delete all admins and recreate primary admin",
    )
    args = parser.parse_args()
    success = diagnose_and_fix(full_reset=args.reset)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
