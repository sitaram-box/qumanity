"""
Create or update Qumanity admin accounts (local, Railway, or any SQLite deployment).

Login uses Private ID + password — not email.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

import bcrypt
import qoin_core

DEFAULT_PRIVATE_ID = "H_U_ADMIN"
DEFAULT_PUBLIC_ID = "ADMIN-PUBLIC"
DEFAULT_PASSWORD = "Admin123"
DEFAULT_VILLAGE_ID = "0.राम|IND/CS/DL.5.4.1E"
DEFAULT_DOB = date(1990, 7, 30)
DEFAULT_BIRTH_TIME = "07:05"


def _password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def create_admin_user(
    conn: sqlite3.Connection,
    *,
    email: str | None = None,
    phone: str | None = None,
    first_name: str = "Admin",
    last_name: str = "User",
    password: str = DEFAULT_PASSWORD,
    private_id: str | None = None,
    public_id: str | None = None,
    reset_password: bool = True,
    migrate: bool = True,
) -> dict[str, Any]:
    """
    Create or upgrade an admin user. Returns credentials dict for operators.

    ``migrate`` runs app schema migrations when True (requires app helpers).
    """
    if migrate:
        from app import migrate_users_app_extensions

        migrate_users_app_extensions(conn)
    qoin_core.migrate_qoin_economy_tables(conn)

    from app import (
        compute_age,
        element_for_sun,
        generate_9_digit_private_id,
        life_stage_from_age,
        moon_sign_simplified,
        sun_sign_for_date,
    )
    import identity_core

    pid = (private_id or DEFAULT_PRIVATE_ID).strip()
    pub = (public_id or DEFAULT_PUBLIC_ID).strip()
    if pid != DEFAULT_PRIVATE_ID and (len(pid) != 9 or not pid.isdigit()):
        pid = generate_9_digit_private_id(conn)

    age = compute_age(DEFAULT_DOB)
    age_group = life_stage_from_age(age)
    sun_sign = sun_sign_for_date(DEFAULT_DOB)
    moon_sign = moon_sign_simplified(DEFAULT_DOB)
    element = element_for_sun(sun_sign)
    pw_hash = _password_hash(password) if reset_password else None

    birth_path = identity_core.location_path_for_id(DEFAULT_VILLAGE_ID, country_id="IND")
    present_path = birth_path

    row = conn.execute(
        "SELECT id, password_hash FROM users WHERE private_id = ? COLLATE NOCASE",
        (pid,),
    ).fetchone()

    if row:
        updates: list[tuple[str, Any]] = [
            ("is_admin", 1),
            ("is_active", 1),
            ("account_status", "active"),
            ("temp_access", 0),
            ("account_type", "H_U"),
            ("mentor_level", 1),
            ("leader_level", 1),
            ("first_name", first_name),
            ("last_name", last_name),
            ("date_of_birth", DEFAULT_DOB.isoformat()),
            ("birth_time", DEFAULT_BIRTH_TIME),
            ("age", age),
            ("age_group", age_group),
            ("sun_sign", sun_sign),
            ("moon_sign", moon_sign),
            ("element", element),
        ]
        if email:
            updates.append(("email", email.strip()))
        if phone:
            updates.append(("phone", phone.strip()))
        if reset_password and pw_hash:
            updates.append(("password_hash", pw_hash))
        set_clause = ", ".join(f"{col} = ?" for col, _ in updates)
        conn.execute(
            f"UPDATE users SET {set_clause} WHERE private_id = ? COLLATE NOCASE",
            [val for _, val in updates] + [pid],
        )
        action = "updated"
    else:
        _structured_private_id, generated_public = identity_core.generate_unique_ids(
            conn,
            first_name,
            last_name,
            "Male",
            age_group,
            sun_sign,
            birth_path,
            present_path,
        )
        if pub == DEFAULT_PUBLIC_ID:
            pub = generated_public
        conn.execute(
            """
            INSERT INTO users (
                private_id, public_id, first_name, last_name, gender,
                date_of_birth, birth_time, age, age_group,
                sun_sign, moon_sign, element,
                birth_location_id, current_location_id,
                birth_continent_id, birth_country_id,
                current_continent_id, current_country_id,
                country, email, phone, password_hash,
                account_type, mentor_level, manager_level, leader_level, agent_level,
                is_admin, is_active, account_status, temp_access
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pid,
                pub,
                first_name,
                last_name,
                "Male",
                DEFAULT_DOB.isoformat(),
                DEFAULT_BIRTH_TIME,
                age,
                age_group,
                sun_sign,
                moon_sign,
                element,
                DEFAULT_VILLAGE_ID,
                DEFAULT_VILLAGE_ID,
                "AS",
                "IND",
                "AS",
                "IND",
                "India",
                (email or "").strip() or None,
                (phone or "").strip() or None,
                pw_hash or _password_hash(password),
                "H_U",
                1,
                0,
                1,
                0,
                1,
                1,
                "active",
                0,
            ),
        )
        identity_core.register_user_accounts(
            conn,
            user_private_id=pid,
            public_id=pub,
            birth_location_id=DEFAULT_VILLAGE_ID,
            present_location_id=DEFAULT_VILLAGE_ID,
            birth_path=birth_path,
            present_path=present_path,
        )
        action = "created"

    qoin_core.ensure_wallet(conn, "user", pid)
    conn.commit()

    return {
        "action": action,
        "private_id": pid,
        "public_id": pub,
        "email": (email or "").strip() or None,
        "phone": (phone or "").strip() or None,
        "password": password if reset_password else None,
        "login_url": "/login",
        "admin_verifications_url": "/admin/verifications",
    }
