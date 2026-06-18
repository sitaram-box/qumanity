"""
Admin login repair — shared by app routes, CLI, and scripts/fix_admin_login.py.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from typing import Any

import bcrypt

ROOT = Path(__file__).resolve().parent
ADMIN_PRIVATE_ID = "HU-014918240"
ADMIN_PUBLIC_ID = "ADMIN-PUBLIC"
ADMIN_EMAIL = "sekyorintantra@gmail.com"
ADMIN_PHONE = "8287696616"
ADMIN_PASSWORD = "P@y#umans123"
LEGACY_ADMIN_PRIVATE_ID = "H_U_ADMIN"


def _load_migrate_module() -> Any | None:
    script_path = ROOT / "scripts" / "migrate_admin_fix.py"
    if not script_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("migrate_admin_fix", script_path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec.loader.exec_module(mod)
    return mod


def diagnose_admin(conn: sqlite3.Connection) -> dict[str, Any]:
    admins = conn.execute(
        """
        SELECT id, private_id, public_id, email, phone, is_admin, account_status,
               password_hash IS NOT NULL AS has_password
        FROM users
        WHERE COALESCE(is_admin, 0) = 1
        ORDER BY id
        """
    ).fetchall()
    target = conn.execute(
        """
        SELECT id, private_id, email, is_admin, account_status, password_hash
        FROM users WHERE private_id = ? COLLATE NOCASE
        """,
        (ADMIN_PRIVATE_ID,),
    ).fetchone()
    legacy = conn.execute(
        "SELECT id, private_id FROM users WHERE private_id = ? COLLATE NOCASE",
        (LEGACY_ADMIN_PRIVATE_ID,),
    ).fetchone()
    return {
        "admins": [dict(r) for r in admins],
        "target": dict(target) if target else None,
        "legacy": dict(legacy) if legacy else None,
    }


def verify_admin_password(conn: sqlite3.Connection, password: str = ADMIN_PASSWORD) -> bool:
    row = conn.execute(
        "SELECT password_hash FROM users WHERE private_id = ? COLLATE NOCASE",
        (ADMIN_PRIVATE_ID,),
    ).fetchone()
    if not row or not row["password_hash"]:
        return False
    stored = row["password_hash"]
    stored_b = stored.encode("utf-8") if isinstance(stored, str) else stored
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_b)
    except (ValueError, TypeError):
        return False


def run_repair(*, reset_password: bool = True, force: bool = True) -> dict[str, Any]:
    """Run forced admin migration and verify password."""
    out: dict[str, Any] = {
        "ok": False,
        "message": "",
        "admin_private_id": ADMIN_PRIVATE_ID,
        "admin_public_id": ADMIN_PUBLIC_ID,
        "admin_email": ADMIN_EMAIL,
        "admin_phone": ADMIN_PHONE,
        "admin_password": ADMIN_PASSWORD if reset_password else None,
        "login_digits": ADMIN_PRIVATE_ID[len("HU-"):],
        "login_verified": False,
    }
    mod = _load_migrate_module()
    if mod is None:
        out["message"] = "migrate_admin_fix.py not found"
        return out

    try:
        result = mod.run_migration_with_status(reset_password=reset_password, force=force)
        out.update(result)
        out["login_digits"] = ADMIN_PRIVATE_ID[len("HU-"):]

        from db_path import resolve_database_path

        db_path = resolve_database_path(ROOT)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            out["login_verified"] = verify_admin_password(conn)
            out["diagnosis"] = diagnose_admin(conn)
        finally:
            conn.close()

        if out.get("ok") and out["login_verified"]:
            out["message"] = "Admin login repaired and verified."
        elif out.get("ok"):
            out["message"] = "Migration ran but login verification failed."
            out["ok"] = False
    except Exception as exc:
        out["message"] = str(exc)
        out["ok"] = False

    return out


def format_repair_log(status: dict[str, Any]) -> str:
    lines = [
        "=" * 50,
        "Admin login repair",
        "=" * 50,
        f"ok: {status.get('ok')}",
        f"message: {status.get('message')}",
        f"admin_private_id: {status.get('admin_private_id')}",
        f"login_digits: {status.get('login_digits')}",
        f"password: {ADMIN_PASSWORD}",
        f"login_verified: {status.get('login_verified')}",
        "=" * 50,
    ]
    return "\n".join(lines)
