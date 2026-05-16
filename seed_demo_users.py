#!/usr/bin/env python3
"""
One-off seed: default admin (H_U_ADMIN) + 100 demo users in a fixed village.

Run from project root (after migrations):
  python3 seed_demo_users.py

Requires: bcrypt, village ``0.राम|IND/CS/DL.5.4.1E`` present in ``indiaq.db``.
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
    sun_sign_for_date,
    village_exists,
)

VILLAGE_ID = "0.राम|IND/CS/DL.5.4.1E"
VILLAGE_SHORT = raw_path(VILLAGE_ID).replace("/", "_").replace(".", "_")
TODAY = date(2026, 5, 12)

MALE_FIRST = (
    "Arjun",
    "Vikram",
    "Rohan",
    "Karan",
    "Dev",
    "Aryan",
    "Rahul",
    "Siddharth",
    "Aditya",
    "Manish",
    "Nikhil",
    "Pranav",
    "Suresh",
    "Rajesh",
    "Amit",
    "Vivek",
    "Gaurav",
    "Harsh",
    "Yash",
    "Kunal",
    "Ankit",
    "Deepak",
    "Ravi",
    "Sanjay",
    "Pankaj",
    "Ashok",
    "Mukesh",
    "Vinod",
    "Sunil",
    "Naveen",
    "Harish",
    "Jitendra",
    "Lokesh",
    "Mahesh",
    "Dinesh",
    "Girish",
    "Ramesh",
    "Sachin",
    "Varun",
    "Tarun",
)

FEMALE_FIRST = (
    "Priya",
    "Ananya",
    "Kavya",
    "Meera",
    "Sneha",
    "Divya",
    "Isha",
    "Neha",
    "Pooja",
    "Riya",
    "Shreya",
    "Tanvi",
    "Aditi",
    "Swati",
    "Anjali",
    "Kiran",
    "Lata",
    "Manju",
    "Nisha",
    "Radha",
    "Sunita",
    "Uma",
    "Vidya",
    "Asha",
    "Geeta",
    "Hema",
    "Jyoti",
    "Kavita",
    "Lakshmi",
    "Maya",
    "Naina",
    "Pallavi",
    "Ritu",
    "Sarita",
    "Tara",
    "Urvashi",
    "Vandana",
    "Yamini",
    "Zara",
    "Bhavna",
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
    "Chopra",
    "Desai",
    "Kulkarni",
    "Pillai",
    "Rao",
    "Mehta",
    "Shah",
    "Tiwari",
    "Mishra",
    "Pandey",
    "Yadav",
    "Jain",
    "Saxena",
    "Bhatt",
    "Dutta",
)


def random_dob_in_age_range(age_min: int, age_max: int) -> date:
    """Random DOB such that ``compute_age(dob, TODAY)`` lies in ``[age_min, age_max]``."""
    for _ in range(800):
        a = random.randint(age_min, age_max)
        y = TODAY.year - a
        m = random.randint(1, 12)
        d = random.randint(1, 28)
        try:
            dob = date(y, m, d)
        except ValueError:
            continue
        ag = compute_age(dob, TODAY)
        if age_min <= ag <= age_max:
            return dob
    return TODAY - timedelta(days=365 * age_min + 60)


def build_demo_slots() -> list[tuple[str, str, str, int, int, str]]:
    """
    (gender, age_code, life_stage_label, age_min, age_max)
    Male / Female counts per spec for village cohort.
    """
    slots: list[tuple[str, str, str, int, int, str]] = []
    # Balak D_U_B: 2 M, 3 F, ages 0–24
    slots += [("Male", "D_U_B", "Balak", 0, 24)] * 2
    slots += [("Female", "D_U_B", "Balak", 0, 24)] * 3
    # Yuvak D_U_Y: 35 M, 25 F, 25–49
    slots += [("Male", "D_U_Y", "Yuvak", 25, 49)] * 35
    slots += [("Female", "D_U_Y", "Yuvak", 25, 49)] * 25
    # Vridh D_U_V: 12 M, 13 F, 50–75
    slots += [("Male", "D_U_V", "Vridh", 50, 75)] * 12
    slots += [("Female", "D_U_V", "Vridh", 50, 75)] * 13
    # Sanyas D_U_S: 5 M, 5 F, 76–100
    slots += [("Male", "D_U_S", "Sanyas", 76, 100)] * 5
    slots += [("Female", "D_U_S", "Sanyas", 76, 100)] * 5
    random.shuffle(slots)
    return slots


def insert_user(
    conn: sqlite3.Connection,
    *,
    private_id: str,
    public_id: str,
    first_name: str,
    last_name: str,
    gender: str,
    dob: date,
    birth_time: str,
    life_stage: str,
    account_type: str,
    password_plain: str,
    is_admin: int,
) -> None:
    dob_iso = dob.strftime("%Y-%m-%d")
    age = compute_age(dob, TODAY)
    sun = sun_sign_for_date(dob)
    moon = moon_sign_simplified(dob)
    elem = element_for_sun(sun)
    pw = bcrypt.hashpw(password_plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
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
            birth_time,
            age,
            life_stage,
            sun,
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
            account_type,
            0,
            0,
            0,
            0,
            is_admin,
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
                f"ERROR: Village {VILLAGE_ID!r} does not exist in the database "
                "(check ``village.id`` in indiaq.db). Seeding aborted.",
                file=sys.stderr,
            )
            sys.exit(1)

        cur = conn.execute(
            "SELECT COUNT(*) FROM users WHERE private_id LIKE ?",
            (f"D_U_%_{VILLAGE_SHORT}_%",),
        )
        existing_demo = int(cur.fetchone()[0])
        if existing_demo >= 100:
            print(
                f"Found {existing_demo} demo users already (pattern D_U_%_{VILLAGE_SHORT}_%). "
                "Skip seeding demo users."
            )
        else:
            slots = build_demo_slots()
            birth_time = "10:30"
            for i, (gender, age_code, life_stage, amin, amax) in enumerate(slots, start=1):
                seq = f"{i:04d}"
                private_id = f"{age_code}_{VILLAGE_SHORT}_{seq}"
                public_id = f"D-PUB-{seq}"
                first = random.choice(MALE_FIRST if gender == "Male" else FEMALE_FIRST)
                last = random.choice(LAST_NAMES)
                dob = random_dob_in_age_range(amin, amax)
                insert_user(
                    conn,
                    private_id=private_id,
                    public_id=public_id,
                    first_name=first,
                    last_name=last,
                    gender=gender,
                    dob=dob,
                    birth_time=birth_time,
                    life_stage=life_stage,
                    account_type=age_code,
                    password_plain="Demo@123",
                    is_admin=0,
                )
            conn.commit()
            print(f"Inserted {len(slots)} demo users in {VILLAGE_ID!r}.")

        row_ad = conn.execute(
            "SELECT 1 FROM users WHERE private_id = ? COLLATE NOCASE",
            ("H_U_ADMIN",),
        ).fetchone()
        if row_ad:
            print("Admin user H_U_ADMIN already exists; skipped.")
        else:
            admin_dob = date(1988, 6, 15)
            insert_user(
                conn,
                private_id="H_U_ADMIN",
                public_id="ADMIN-PUBLIC",
                first_name="Rohit",
                last_name="Mudgal",
                gender="Male",
                dob=admin_dob,
                birth_time="09:00",
                life_stage="Yuvak",
                account_type="H_U",
                password_plain="Admin@123",
                is_admin=1,
            )
            conn.commit()
            print("Inserted admin user H_U_ADMIN (public_id ADMIN-PUBLIC).")

        total = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        demo_n = int(
            conn.execute(
                "SELECT COUNT(*) FROM users WHERE private_id LIKE ?",
                (f"D_U_%_{VILLAGE_SHORT}_%",),
            ).fetchone()[0]
        )
        print("\n--- Summary ---")
        print(f"Total users in database: {total}")
        print(f"Demo users (pattern D_U_*_{VILLAGE_SHORT}_*): {demo_n}")
        print("Demo login password (all demo users): Demo@123")
        print("Admin login: H_U_ADMIN / Admin@123")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
