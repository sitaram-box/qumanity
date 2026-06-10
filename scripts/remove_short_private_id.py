#!/usr/bin/env python3
"""Remove short_private_id (and short_id_generated_at) from the users table."""

from __future__ import annotations

import os
import sqlite3
import sys

DB_PATH = os.environ.get("DATABASE_PATH", "indiaq.db")
DROP_COLUMNS = frozenset({"short_private_id", "short_id_generated_at"})


def migrate(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cur.fetchall()]

    if "short_private_id" not in columns:
        print("short_private_id column not found — nothing to do")
        conn.close()
        return

    keep = [c for c in columns if c not in DROP_COLUMNS]
    if not keep:
        raise RuntimeError("No columns left on users after dropping short_private_id")

    col_sql = ", ".join(keep)
    print("Removing short_private_id column…")
    cur.execute("DROP INDEX IF EXISTS idx_users_short_private_id")
    cur.execute(f"CREATE TABLE users_new AS SELECT {col_sql} FROM users")
    cur.execute("DROP TABLE users")
    cur.execute("ALTER TABLE users_new RENAME TO users")
    conn.commit()
    conn.close()
    print("short_private_id column removed")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    migrate(path)
