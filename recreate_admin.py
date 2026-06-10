#!/usr/bin/env python3
"""
Recreate the default admin account (H_U_ADMIN) in indiaq.db.

Run from the project root:
  python3 recreate_admin.py

Safe to run when other users already exist — only removes/replaces H_U_ADMIN.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import bcrypt
import qoin_core

from app import (
    compute_age,
    element_for_sun,
    life_stage_from_age,
    migrate_users_app_extensions,
    moon_sign_simplified,
    sun_sign_for_date,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "indiaq.db"

ADMIN_PRIVATE_ID = "H_U_ADMIN"
ADMIN_PUBLIC_ID = "ADMIN-PUBLIC"
ADMIN_PASSWORD = "Admin123"
VILLAGE_ID = "0.राम|IND/CS/DL.5.4.1E"
ADMIN_DOB = date(1990, 7, 30)
ADMIN_BIRTH_TIME = "07:05"


def recreate_admin(conn: sqlite3.Connection) -> None:
    migrate_users_app_extensions(conn)
    qoin_core.migrate_qoin_economy_tables(conn)

    existing = conn.execute(
        "SELECT id FROM users WHERE private_id = ? COLLATE NOCASE",
        (ADMIN_PRIVATE_ID,),
    ).fetchone()
    if existing:
        conn.execute(
            "DELETE FROM wallets WHERE owner_type = 'user' AND owner_id = ?",
            (ADMIN_PRIVATE_ID,),
        )
        conn.execute(
            "DELETE FROM users WHERE private_id = ? COLLATE NOCASE",
            (ADMIN_PRIVATE_ID,),
        )
        print(f"Removed existing admin account ({ADMIN_PRIVATE_ID}).")

    age = compute_age(ADMIN_DOB)
    age_group = life_stage_from_age(age)
    sun_sign = sun_sign_for_date(ADMIN_DOB)
    moon_sign = moon_sign_simplified(ADMIN_DOB)
    element = element_for_sun(sun_sign)
    password_hash = bcrypt.hashpw(
        ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()
    ).decode("ascii")

    conn.execute(
        """
        INSERT INTO users (
            private_id, public_id, first_name, last_name, gender,
            date_of_birth, birth_time, age, age_group,
            sun_sign, moon_sign, element,
            birth_location_id, current_location_id,
            birth_continent_id, birth_country_id,
            current_continent_id, current_country_id,
            country, email, password_hash,
            account_type, mentor_level, manager_level, leader_level, agent_level,
            is_admin, is_active
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            ADMIN_PRIVATE_ID,
            ADMIN_PUBLIC_ID,
            "Rohit",
            "Mudgal",
            "Male",
            ADMIN_DOB.isoformat(),
            ADMIN_BIRTH_TIME,
            age,
            age_group,
            sun_sign,
            moon_sign,
            element,
            VILLAGE_ID,
            VILLAGE_ID,
            "AS",
            "IND",
            "AS",
            "IND",
            "India",
            None,
            password_hash,
            "H_U",
            1,
            0,
            1,
            0,
            1,
            1,
        ),
    )

    qoin_core.ensure_wallet(conn, "user", ADMIN_PRIVATE_ID)
    conn.execute(
        """
        UPDATE wallets
        SET balance = 0, qoins_encrypted = ?
        WHERE owner_type = ? AND owner_id = ?
        """,
        (qoin_core.encrypt_json([]), "user", ADMIN_PRIVATE_ID),
    )


def main() -> None:
    if not DB_PATH.is_file():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        recreate_admin(conn)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"Failed to recreate admin: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    print()
    print("Admin account recreated successfully.")
    print(f"  Database: {DB_PATH}")
    print(f"  Private ID: {ADMIN_PRIVATE_ID}")
    print(f"  Public ID:  {ADMIN_PUBLIC_ID}")
    print(f"  Password:   {ADMIN_PASSWORD}")
    print(f"  Name:       Rohit Mudgal")
    print(f"  Location:   {VILLAGE_ID}")
    print()
    print("You can now log in at /login with the credentials above.")


if __name__ == "__main__":
    main()
