#!/usr/bin/env python3
"""Ensure default admin exists (H_U_ADMIN / Admin123). Works on Railway via DATABASE_PATH."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import admin_bootstrap

DB_PATH = os.environ.get("DATABASE_PATH", "indiaq.db")


def ensure_admin(db_path: str = DB_PATH, *, reset_password: bool = True) -> None:
    path = Path(db_path)
    if not path.is_file():
        print(f"Database not found: {path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        result = admin_bootstrap.create_admin_user(
            conn,
            email="admin@qumanity.com",
            phone="9999999999",
            first_name="Admin",
            last_name="User",
            password=admin_bootstrap.DEFAULT_PASSWORD,
            private_id=admin_bootstrap.DEFAULT_PRIVATE_ID,
            reset_password=reset_password,
        )
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    print(f"Admin {result['action']}.")
    print(f"  Private ID: {result['private_id']}")
    print(f"  Public ID:  {result['public_id']}")
    print(f"  Password:   {result['password']}")
    print("  Log in at /login with Private ID (not email).")


if __name__ == "__main__":
    reset = "--no-reset-password" not in sys.argv
    db = DB_PATH
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            continue
        db = arg
        break
    ensure_admin(db, reset_password=reset)
