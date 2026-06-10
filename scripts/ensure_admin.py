#!/usr/bin/env python3
"""Ensure H_U_ADMIN exists with password Admin123 (create or update)."""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

import bcrypt

DB_PATH = os.environ.get("DATABASE_PATH", "indiaq.db")
ADMIN_PRIVATE_ID = "H_U_ADMIN"
ADMIN_PUBLIC_ID = "ADMIN-PUBLIC"
ADMIN_PASSWORD = "Admin123"
VILLAGE_ID = "0.राम|IND/CS/DL.5.4.1E"
ADMIN_DOB = date(1990, 7, 30)
ADMIN_BIRTH_TIME = "07:05"


def _password_hash() -> str:
    return bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def ensure_admin(db_path: str = DB_PATH, *, reset_password: bool = True) -> None:
    path = Path(db_path)
    if not path.is_file():
        print(f"Database not found: {path}", file=sys.stderr)
        sys.exit(1)

    # Import app helpers after DB path is validated.
    sys.path.insert(0, str(path.parent.resolve()))
    from app import (
        compute_age,
        element_for_sun,
        life_stage_from_age,
        migrate_users_app_extensions,
        moon_sign_simplified,
        sun_sign_for_date,
    )

    import qoin_core

    conn = sqlite3.connect(path)
    migrate_users_app_extensions(conn)
    qoin_core.migrate_qoin_economy_tables(conn)

    age = compute_age(ADMIN_DOB)
    age_group = life_stage_from_age(age)
    sun_sign = sun_sign_for_date(ADMIN_DOB)
    moon_sign = moon_sign_simplified(ADMIN_DOB)
    element = element_for_sun(sun_sign)
    pw_hash = _password_hash() if reset_password else None

    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE private_id = ? COLLATE NOCASE",
        (ADMIN_PRIVATE_ID,),
    ).fetchone()

    if row:
        updates = [
            ("is_admin", 1),
            ("is_active", 1),
            ("account_type", "H_U"),
            ("mentor_level", 1),
            ("leader_level", 1),
            ("date_of_birth", ADMIN_DOB.isoformat()),
            ("birth_time", ADMIN_BIRTH_TIME),
            ("age", age),
            ("age_group", age_group),
            ("sun_sign", sun_sign),
            ("moon_sign", moon_sign),
            ("element", element),
        ]
        if reset_password and pw_hash:
            updates.append(("password_hash", pw_hash))
        set_clause = ", ".join(f"{col} = ?" for col, _ in updates)
        conn.execute(
            f"UPDATE users SET {set_clause} WHERE private_id = ? COLLATE NOCASE",
            [val for _, val in updates] + [ADMIN_PRIVATE_ID],
        )
        print(f"Updated existing admin ({ADMIN_PRIVATE_ID}).")
    else:
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
                pw_hash or _password_hash(),
                "H_U",
                1,
                0,
                1,
                0,
                1,
                1,
            ),
        )
        print(f"Created admin account ({ADMIN_PRIVATE_ID}).")

    qoin_core.ensure_wallet(conn, "user", ADMIN_PRIVATE_ID)
    conn.commit()
    conn.close()

    print()
    print("Admin ready:")
    print(f"  Private ID: {ADMIN_PRIVATE_ID}")
    print(f"  Public ID:  {ADMIN_PUBLIC_ID}")
    print(f"  Password:   {ADMIN_PASSWORD}")
    print("  Log in at /login")


if __name__ == "__main__":
    reset = "--no-reset-password" not in sys.argv
    db = DB_PATH
    for arg in sys.argv[1:]:
        if arg.startswith("-"):
            continue
        db = arg
        break
    ensure_admin(db, reset_password=reset)
