#!/usr/bin/env python3
"""
Rebuild `users` in indiaq.db to add global location columns and allow NULL
Indian village IDs when birth/current country is not India.

Also backfills existing rows with birth/current continent AS, country IND.

Run once from project root:
    python3 add_global_location_columns.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "indiaq.db"

USERS_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    private_id TEXT UNIQUE NOT NULL,
    public_id TEXT UNIQUE NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    gender TEXT NOT NULL CHECK(
        gender IN ('Male', 'Female', 'Male born female', 'Female born male')
    ),
    date_of_birth TEXT NOT NULL,
    birth_time TEXT NOT NULL,
    age INTEGER NOT NULL,
    age_group TEXT NOT NULL,
    sun_sign TEXT NOT NULL,
    moon_sign TEXT NOT NULL,
    element TEXT NOT NULL,
    birth_location_id TEXT,
    current_location_id TEXT,
    birth_continent_id TEXT,
    birth_country_id TEXT,
    current_continent_id TEXT,
    current_country_id TEXT,
    country TEXT NOT NULL DEFAULT 'India',
    email TEXT,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_users_current_loc ON users(current_location_id);
CREATE INDEX IF NOT EXISTS idx_users_birth_loc ON users(birth_location_id);
CREATE INDEX IF NOT EXISTS idx_users_private_id ON users(private_id);
CREATE INDEX IF NOT EXISTS idx_users_public_id ON users(public_id);
CREATE INDEX IF NOT EXISTS idx_users_sun_sign ON users(sun_sign);
CREATE INDEX IF NOT EXISTS idx_users_element ON users(element);
CREATE INDEX IF NOT EXISTS idx_users_gender ON users(gender);
CREATE INDEX IF NOT EXISTS idx_users_age_group ON users(age_group);
CREATE INDEX IF NOT EXISTS idx_users_current_country ON users(current_country_id);
CREATE INDEX IF NOT EXISTS idx_users_current_continent ON users(current_continent_id);
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def _needs_migration(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA table_info(users)").fetchall()
    cols = {str(r[1]): r for r in rows}
    if "birth_continent_id" not in cols:
        return True
    bl = cols.get("birth_location_id")
    if bl is not None and int(bl[3]) == 1:
        return True
    return False


def main() -> int:
    if not DB_PATH.is_file():
        log(f"ERROR: {DB_PATH} not found")
        return 1

    conn = sqlite3.connect(DB_PATH)
    try:
        if not _needs_migration(conn):
            log("users table already has global location columns and nullable village IDs — nothing to do.")
            return 0

        log("Migrating users table (rebuild for nullable location IDs + new columns) …")
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ALTER TABLE users RENAME TO users_legacy")

        conn.executescript(USERS_CREATE_SQL.strip())
        conn.executescript(INDEX_SQL.strip())

        conn.execute(
            """
            INSERT INTO users (
                id, private_id, public_id, first_name, last_name, gender,
                date_of_birth, birth_time, age, age_group, sun_sign, moon_sign, element,
                birth_location_id, current_location_id,
                birth_continent_id, birth_country_id, current_continent_id, current_country_id,
                country, email, password_hash, created_at
            )
            SELECT
                id, private_id, public_id, first_name, last_name, gender,
                date_of_birth, birth_time, age, age_group, sun_sign, moon_sign, element,
                birth_location_id, current_location_id,
                'AS', 'IND', 'AS', 'IND',
                country, email, password_hash, created_at
            FROM users_legacy
            """
        )
        conn.execute("DROP TABLE users_legacy")
        conn.commit()
        log("Migration complete.")
    except Exception as exc:
        conn.rollback()
        log(f"ERROR: {exc}")
        return 1
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
