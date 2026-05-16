#!/usr/bin/env python3
"""
Insert 1000 synthetic users into indiaq.db for chart demos.

From the quantum_box directory:
  python3 seed_users.py

All seeded rows share password: SeedDemo#2626 (bcrypt hashed per row salts).
Uses the same derived-field logic as app registration.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import bcrypt

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import (  # noqa: E402
    DB_PATH,
    allocate_private_id,
    allocate_public_id,
    age_group_from_age,
    compute_age,
    element_for_sun,
    ensure_users_table,
    moon_sign_simplified,
    sun_sign_for_date,
)

FIRST_NAMES = [
    "Aditya",
    "Priya",
    "Rohan",
    "Ananya",
    "Vikram",
    "Deepa",
    "Sneha",
    "Arjun",
    "Meera",
    "Karthik",
    "Neha",
    "Riya",
    "Manish",
    "Pooja",
    "Isha",
    "Dev",
    "Sarah",
    "James",
    "Alex",
    "Jordan",
    "Aria",
]

LAST_NAMES = [
    "Kapoor",
    "Sharma",
    "Singh",
    "Reddy",
    "Gupta",
    "Verma",
    "Mehta",
    "Mishra",
    "Pillai",
    "Roy",
    "Patel",
    "Naidu",
    "Khan",
    "Das",
]

GENDERS = (
    "Male",
    "Female",
    "Male born female",
    "Female born male",
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed dummy users")
    p.add_argument(
        "-n",
        "--count",
        type=int,
        default=1000,
        help="Number of users (default 1000)",
    )
    return p.parse_args()


def random_date_between(rng: random.Random, start: date, end: date) -> date:
    span = (end - start).days
    return start + timedelta(days=rng.randint(0, span))


def random_birth_time(rng: random.Random) -> str:
    return f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"


def random_village_id(conn: sqlite3.Connection, rng: random.Random) -> str:
    row = conn.execute("SELECT id FROM village ORDER BY RANDOM() LIMIT 1").fetchone()
    if not row:
        sys.exit("No villages in indiaq.db — cannot seed.")
    return str(row["id"])


def main() -> None:
    args = parse_args()
    if args.count < 1:
        print("count must be >= 1")
        sys.exit(1)

    if not DB_PATH.is_file():
        print(f"Database not found: {DB_PATH.resolve()}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_users_table(conn)

    rng = random.Random()
    password_hash = bcrypt.hashpw(b"SeedDemo#2626", bcrypt.gensalt(rounds=10)).decode(
        "ascii"
    )

    dob_start = date(1950, 1, 1)
    dob_end = date(2010, 12, 31)

    insert_sql = """
        INSERT INTO users (
            private_id,
            public_id,
            first_name,
            last_name,
            gender,
            date_of_birth,
            birth_time,
            age,
            age_group,
            sun_sign,
            moon_sign,
            element,
            birth_location_id,
            current_location_id,
            birth_continent_id,
            birth_country_id,
            current_continent_id,
            current_country_id,
            email,
            password_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    for _ in range(args.count):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        gender = rng.choice(GENDERS)
        dob = random_date_between(rng, dob_start, dob_end)
        dob_s = dob.strftime("%Y-%m-%d")
        btime = random_birth_time(rng)
        birth_village = random_village_id(conn, rng)
        current_village = random_village_id(conn, rng)
        age = compute_age(dob)
        agroup = age_group_from_age(age)
        sun = sun_sign_for_date(dob)
        moon = moon_sign_simplified(dob)
        elem = element_for_sun(sun)
        private_id = allocate_private_id(conn, first, dob_s, btime, birth_village)
        public_id = allocate_public_id(conn)
        email = f"{public_id.lower().replace('-', '')}@seed.example.invalid"

        conn.execute(
            insert_sql,
            (
                private_id,
                public_id,
                first,
                last,
                gender,
                dob_s,
                btime,
                age,
                agroup,
                sun,
                moon,
                elem,
                birth_village,
                current_village,
                "AS",
                "IND",
                "AS",
                "IND",
                email,
                password_hash,
            ),
        )

    conn.commit()
    conn.close()

    print(f"Inserted {args.count} users into {DB_PATH.resolve()}")
    print("Password for every seeded account: SeedDemo#2626")
    print("Log in with any row's private_id value (shown in DB or registration flow).")


if __name__ == "__main__":
    main()
