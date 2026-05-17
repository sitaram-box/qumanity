#!/usr/bin/env python3
"""
One-off seed: 15 Taurus Yuvak demo users in Rohini Sector-24 for election testing.

Run from project root (after migrations):
  python3 seed_taurus_users.py

All users: village ``0.राम|IND/CS/DL.5.4.1E``, sun_sign Taurus, age_group Yuvak,
account_type D_U_Y, password Demo123 (bcrypt).
"""

from __future__ import annotations

import random
import sqlite3
import sys
from datetime import date, timedelta

import bcrypt

from app import (
    DB_PATH,
    compute_age,
    element_for_sun,
    migrate_messages_table,
    migrate_users_app_extensions,
    moon_sign_simplified,
    raw_path,
    village_exists,
)

VILLAGE_ID = "0.राम|IND/CS/DL.5.4.1E"
VILLAGE_SHORT = raw_path(VILLAGE_ID).replace("/", "_").replace(".", "_")
SEED_PREFIX = "D_U_Y_TAURUS"
SUN_SIGN = "Taurus"
TODAY = date.today()
PASSWORD_PLAIN = "Demo123"
TARGET_COUNT = 15
GENDER_SLOTS: list[str] = ["Female"] * 7 + ["Male"] * 8

MALE_FIRST = (
    "Arjun",
    "Vikram",
    "Rohan",
    "Karan",
    "Dev",
    "Aryan",
    "Rahul",
    "Siddharth",
)

FEMALE_FIRST = (
    "Priya",
    "Ananya",
    "Kavya",
    "Meera",
    "Sneha",
    "Divya",
    "Isha",
)

LAST_NAMES = (
    "Sharma",
    "Verma",
    "Patel",
    "Singh",
    "Kumar",
    "Reddy",
    "Iyer",
    "Menon",
    "Nair",
    "Joshi",
    "Kapoor",
    "Malhotra",
    "Bansal",
    "Gupta",
    "Agarwal",
)


def random_dob_yuvak() -> date:
    """Random DOB with age 25–49 on ``TODAY``."""
    for _ in range(800):
        age = random.randint(25, 49)
        y = TODAY.year - age
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        try:
            dob = date(y, m, d)
        except ValueError:
            continue
        if 25 <= compute_age(dob, TODAY) <= 49:
            return dob
    return TODAY - timedelta(days=365 * 30)


def random_karma_levels() -> tuple[int, int, int, int]:
    return (
        random.randint(0, 5),
        random.randint(0, 5),
        random.randint(0, 5),
        random.randint(0, 5),
    )


def insert_taurus_user(
    conn: sqlite3.Connection,
    *,
    private_id: str,
    public_id: str,
    first_name: str,
    last_name: str,
    gender: str,
    dob: date,
) -> None:
    dob_iso = dob.strftime("%Y-%m-%d")
    age = compute_age(dob, TODAY)
    moon = moon_sign_simplified(dob)
    elem = element_for_sun(SUN_SIGN)
    mentor, manager, leader, agent = random_karma_levels()
    pw = bcrypt.hashpw(PASSWORD_PLAIN.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
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
            is_admin
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            private_id,
            public_id,
            first_name,
            last_name,
            gender,
            dob_iso,
            "10:30",
            age,
            "Yuvak",
            SUN_SIGN,
            moon,
            elem,
            VILLAGE_ID,
            VILLAGE_ID,
            "AS",
            "IND",
            "AS",
            "IND",
            "India",
            None,
            pw,
            "D_U_Y",
            mentor,
            manager,
            leader,
            agent,
            0,
        ),
    )


def main() -> None:
    if not DB_PATH.is_file():
        print(f"Database not found: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        migrate_users_app_extensions(conn)
        migrate_messages_table(conn)

        if not village_exists(conn, VILLAGE_ID):
            print(
                f"ERROR: Village {VILLAGE_ID!r} does not exist in the database. Seeding aborted.",
                file=sys.stderr,
            )
            sys.exit(1)

        existing = int(
            conn.execute(
                "SELECT COUNT(*) FROM users WHERE private_id LIKE ?",
                (f"{SEED_PREFIX}_%",),
            ).fetchone()[0]
        )
        if existing >= TARGET_COUNT:
            print(
                f"Found {existing} Taurus Yuvak demo users (pattern {SEED_PREFIX}_%). "
                "Skip seeding."
            )
            return

        random.shuffle(GENDER_SLOTS)
        inserted = 0
        for i, gender in enumerate(GENDER_SLOTS, start=1):
            seq = f"{i:04d}"
            private_id = f"{SEED_PREFIX}_{seq}"
            public_id = f"TAU-PUB-{seq}"
            first = random.choice(MALE_FIRST if gender == "Male" else FEMALE_FIRST)
            last = random.choice(LAST_NAMES)
            insert_taurus_user(
                conn,
                private_id=private_id,
                public_id=public_id,
                first_name=first,
                last_name=last,
                gender=gender,
                dob=random_dob_yuvak(),
            )
            inserted += 1

        conn.commit()
        print(f"Inserted {inserted} Taurus Yuvak demo users in {VILLAGE_ID!r}.")
        print("\n--- Summary ---")
        print(f"Private ID pattern: {SEED_PREFIX}_0001 … {SEED_PREFIX}_{TARGET_COUNT:04d}")
        print(f"Public ID pattern: TAU-PUB-0001 … TAU-PUB-{TARGET_COUNT:04d}")
        print(f"Gender: 7 Female, 8 Male")
        print(f"Password (all): {PASSWORD_PLAIN}")
        print("Eligible to nominate (during nomination weeks) and vote (age 13+ rules satisfied).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
