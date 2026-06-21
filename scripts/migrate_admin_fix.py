#!/usr/bin/env python3
"""
Standalone admin + HU- prefix migration for Railway (no railway CLI required).

Run from project root inside Railway shell / console:

  cd /app && python scripts/migrate_admin_fix.py

One-liner (paste entire line in Railway console):

  cd /app && python scripts/migrate_admin_fix.py

Or if only python -c works:

  python -c "import runpy; runpy.run_path('scripts/migrate_admin_fix.py')"

After migration, login at /login with:
  Private ID: HU-014918240
  Password:   P@y#umans123
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import bcrypt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ADMIN_PRIVATE_ID = "HU-014918240"
ADMIN_PUBLIC_ID = "ADMIN-PUBLIC"
ADMIN_EMAIL = "sekyorintantra@gmail.com"
ADMIN_PHONE = "8287696616"
ADMIN_PASSWORD = "P@y#umans123"
LEGACY_ADMIN_PRIVATE_ID = "H_U_ADMIN"
SOURCE_PRIVATE_IDS = ("306931970", "HU-306931970", LEGACY_ADMIN_PRIVATE_ID)
ADMIN_SKIP_PREFIXES = ("HU-", "AN-", "NB-", "H_U_")


def resolve_db_path() -> Path:
    """Find indiaq.db on Railway volume, DATABASE_PATH, or local project."""
    from db_path import resolve_database_path

    candidates: list[Path] = [
        resolve_database_path(ROOT),
        ROOT / "indiaq.db",
        Path("/app/indiaq.db"),
        Path("/data/indiaq.db"),
    ]
    explicit = (os.environ.get("DATABASE_PATH") or "").strip()
    if explicit:
        candidates.insert(0, Path(explicit))
    volume = (os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
    if volume:
        candidates.insert(0, Path(volume) / "indiaq.db")

    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Database not found. Tried: " + ", ".join(str(p) for p in candidates)
    )


def _password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _find_source_user(conn: sqlite3.Connection) -> sqlite3.Row | None:
    for pid in SOURCE_PRIVATE_IDS:
        row = conn.execute(
            "SELECT * FROM users WHERE private_id = ? COLLATE NOCASE",
            (pid,),
        ).fetchone()
        if row:
            return row
    return None


def _remove_user(conn: sqlite3.Connection, private_id: str) -> None:
    pid = str(private_id).strip()
    try:
        conn.execute(
            "DELETE FROM wallets WHERE owner_type = 'user' AND owner_id = ?",
            (pid,),
        )
    except sqlite3.OperationalError:
        pass
    conn.execute("DELETE FROM users WHERE private_id = ? COLLATE NOCASE", (pid,))


def _ensure_schema(conn: sqlite3.Connection) -> None:
    try:
        from app import migrate_users_app_extensions

        migrate_users_app_extensions(conn)
    except Exception as exc:
        print(f"  Warning: schema migration skipped ({exc})")
    try:
        import qoin_core

        qoin_core.migrate_qoin_economy_tables(conn)
    except Exception as exc:
        print(f"  Warning: qoin schema skipped ({exc})")


def _migrate_legacy_admin_id(conn: sqlite3.Connection) -> None:
    """Rename H_U_ADMIN to HU-014918240 when the legacy row still exists."""
    import identity_core

    legacy = conn.execute(
        "SELECT id FROM users WHERE private_id = ? COLLATE NOCASE",
        (LEGACY_ADMIN_PRIVATE_ID,),
    ).fetchone()
    if not legacy:
        return

    target = conn.execute(
        "SELECT id FROM users WHERE private_id = ? COLLATE NOCASE",
        (ADMIN_PRIVATE_ID,),
    ).fetchone()
    if target and int(target["id"]) != int(legacy["id"]):
        print(f" Removing duplicate admin row at {ADMIN_PRIVATE_ID}…")
        _remove_user(conn, ADMIN_PRIVATE_ID)

    legacy = conn.execute(
        "SELECT id FROM users WHERE private_id = ? COLLATE NOCASE",
        (LEGACY_ADMIN_PRIVATE_ID,),
    ).fetchone()
    if not legacy:
        return

    identity_core.reassign_user_private_id(
        conn,
        LEGACY_ADMIN_PRIVATE_ID,
        ADMIN_PRIVATE_ID,
        new_public_id=ADMIN_PUBLIC_ID,
    )
    print(f" Migrated {LEGACY_ADMIN_PRIVATE_ID} → {ADMIN_PRIVATE_ID}")


def convert_to_admin(
    conn: sqlite3.Connection,
    *,
    reset_password: bool = True,
) -> None:
    import identity_core

    from app import format_human_private_id

    _migrate_legacy_admin_id(conn)

    source = _find_source_user(conn)
    pw_hash = _password_hash(ADMIN_PASSWORD) if reset_password else None

    if source:
        old_pid = str(source["private_id"])
        name = f"{source['first_name']} {source['last_name']}".strip()
        print(f" Found user: {name}")
        print(f"   Private ID: {old_pid}")
        print(f"   Public ID:  {source['public_id']}")

        if old_pid.upper() == ADMIN_PRIVATE_ID:
            print(f" User is already {ADMIN_PRIVATE_ID} — updating contact details.")
        else:
            existing_admin = conn.execute(
                "SELECT id FROM users WHERE private_id = ? COLLATE NOCASE",
                (ADMIN_PRIVATE_ID,),
            ).fetchone()
            if existing_admin and int(existing_admin["id"]) != int(source["id"]):
                print(f" Removing old bootstrap admin row at {ADMIN_PRIVATE_ID}…")
                _remove_user(conn, ADMIN_PRIVATE_ID)

            identity_core.reassign_user_private_id(
                conn,
                old_pid,
                ADMIN_PRIVATE_ID,
                new_public_id=ADMIN_PUBLIC_ID,
            )
            print(f" Converted {old_pid} → {ADMIN_PRIVATE_ID}")
    else:
        print(f" Source user not found — configuring {ADMIN_PRIVATE_ID} directly.")
        existing = conn.execute(
            "SELECT id FROM users WHERE private_id = ? COLLATE NOCASE",
            (ADMIN_PRIVATE_ID,),
        ).fetchone()
        if not existing:
            try:
                from admin_bootstrap import create_admin_user

                create_admin_user(
                    conn,
                    email=ADMIN_EMAIL,
                    phone=ADMIN_PHONE,
                    first_name="Admin",
                    last_name="User",
                    password=ADMIN_PASSWORD,
                    private_id=ADMIN_PRIVATE_ID,
                    public_id=ADMIN_PUBLIC_ID,
                    reset_password=True,
                )
                print(" Created admin via admin_bootstrap.")
                return
            except Exception as exc:
                print(f"  admin_bootstrap failed ({exc}), using minimal INSERT…")
                if not pw_hash:
                    pw_hash = _password_hash(ADMIN_PASSWORD)
                conn.execute(
                    """
                    INSERT INTO users (
                        private_id, public_id, first_name, last_name, gender,
                        password_hash, email, phone, account_type,
                        is_admin, is_active, account_status, country
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'H_U', 1, 1, 'active', 'India')
                    """,
                    (
                        ADMIN_PRIVATE_ID,
                        ADMIN_PUBLIC_ID,
                        "Admin",
                        "User",
                        "Male",
                        pw_hash,
                        ADMIN_EMAIL,
                        ADMIN_PHONE,
                    ),
                )

    updates = [
        ("email", ADMIN_EMAIL),
        ("phone", ADMIN_PHONE),
        ("is_admin", 1),
        ("is_active", 1),
        ("account_status", "active"),
        ("temp_access", 0),
        ("public_id", ADMIN_PUBLIC_ID),
        ("verification_failed_reason", None),
    ]
    if reset_password and pw_hash:
        updates.append(("password_hash", pw_hash))

    set_clause = ", ".join(f"{col} = ?" for col, _ in updates)
    conn.execute(
        f"UPDATE users SET {set_clause} WHERE private_id = ? COLLATE NOCASE",
        [val for _, val in updates] + [ADMIN_PRIVATE_ID],
    )

    try:
        import qoin_core

        qoin_core.ensure_wallet(conn, "user", ADMIN_PRIVATE_ID)
    except Exception:
        pass


def add_hu_prefix(conn: sqlite3.Connection) -> int:
    import identity_core

    from app import format_human_private_id

    rows = conn.execute(
        """
        SELECT id, private_id FROM users
        WHERE COALESCE(is_admin, 0) = 0
        ORDER BY id
        """
    ).fetchall()
    updated = 0
    for row in rows:
        pid = str(row["private_id"] or "").strip()
        if not pid:
            continue
        upper = pid.upper()
        if upper == ADMIN_PRIVATE_ID or upper.startswith(ADMIN_SKIP_PREFIXES):
            continue
        if not re.fullmatch(r"\d{9}", pid):
            continue
        new_pid = format_human_private_id(pid)
        conflict = conn.execute(
            "SELECT 1 FROM users WHERE private_id = ? COLLATE NOCASE AND id != ?",
            (new_pid, int(row["id"])),
        ).fetchone()
        if conflict:
            print(f"  Skip {pid}: {new_pid} already exists")
            continue
        identity_core.reassign_user_private_id(conn, pid, new_pid)
        updated += 1
        print(f"   {pid} → {new_pid}")
    return updated


def admin_needs_setup(conn: sqlite3.Connection) -> bool:
    """True when admin account is missing or not configured with target credentials."""
    admin = conn.execute(
        """
        SELECT id, email, phone, is_admin FROM users
        WHERE private_id = ? COLLATE NOCASE
        """,
        (ADMIN_PRIVATE_ID,),
    ).fetchone()
    if not admin or not int(admin["is_admin"] or 0):
        return True
    if str(admin["email"] or "").strip().lower() != ADMIN_EMAIL.lower():
        return True
    if str(admin["phone"] or "").strip() != ADMIN_PHONE:
        return True
    if _find_source_user(conn):
        return True
    legacy = conn.execute(
        "SELECT 1 FROM users WHERE private_id = ? COLLATE NOCASE",
        (LEGACY_ADMIN_PRIVATE_ID,),
    ).fetchone()
    if legacy:
        return True
    row = conn.execute(
        """
        SELECT 1 FROM users
        WHERE COALESCE(is_admin, 0) = 0
          AND private_id GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
        LIMIT 1
        """
    ).fetchone()
    if row:
        return True
    return False


def run_migration(*, reset_password: bool = True) -> bool:
    result = run_migration_with_status(reset_password=reset_password)
    return bool(result.get("ok"))


def run_migration_with_status(
    *,
    reset_password: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Run migration and return a status dict for HTTP responses."""
    out: dict[str, Any] = {
        "ok": False,
        "already_configured": False,
        "hu_prefix_updated": 0,
        "admin_private_id": ADMIN_PRIVATE_ID,
        "admin_public_id": ADMIN_PUBLIC_ID,
        "admin_email": ADMIN_EMAIL,
        "admin_phone": ADMIN_PHONE,
        "admin_password": ADMIN_PASSWORD if reset_password else None,
        "message": "",
    }
    print("Starting Qumanity admin migration…")
    try:
        db_path = resolve_db_path()
    except FileNotFoundError as exc:
        out["message"] = str(exc)
        print(f"ERROR: {exc}")
        return out

    print(f"Using database: {db_path}")
    conn = _connect(db_path)
    try:
        if not force and not admin_needs_setup(conn):
            out["ok"] = True
            out["already_configured"] = True
            out["message"] = "Admin already configured."
            print(" Admin already configured — skipping migration.")
            return out

        _ensure_schema(conn)
        convert_to_admin(conn, reset_password=reset_password)
        count = add_hu_prefix(conn)
        conn.commit()
        out["ok"] = True
        out["hu_prefix_updated"] = count
        out["message"] = "Migration complete."
    except Exception as exc:
        conn.rollback()
        out["message"] = str(exc)
        print(f"ERROR: Migration failed: {exc}")
        import traceback

        traceback.print_exc()
        return out
    finally:
        conn.close()

    print()
    print("Migration complete!")
    print(f"  Updated {out['hu_prefix_updated']} user(s) with HU- prefix")
    print(f"  Admin Private ID: {ADMIN_PRIVATE_ID}")
    print(f"  Admin Public ID:  {ADMIN_PUBLIC_ID}")
    print(f"  Admin Email:      {ADMIN_EMAIL}")
    print(f"  Admin Phone:      {ADMIN_PHONE}")
    print(f"  Admin Password:   {ADMIN_PASSWORD}")
    print("  Login at: /login")
    return out


if __name__ == "__main__":
    no_reset = "--keep-password" in sys.argv
    ok = run_migration(reset_password=not no_reset)
    sys.exit(0 if ok else 1)
