"""
Admin login repair — shared by app routes, CLI, and scripts/fix_admin_login.py.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import time
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

# Backup admin — 9-digit HU- ID (login OTP: 999000001)
BACKUP_PRIVATE_ID = "HU-999000001"
BACKUP_PUBLIC_ID = "BACKUP-PUBLIC"
BACKUP_EMAIL = "backup@qumanity.com"
BACKUP_PHONE = "9999999999"
BACKUP_PASSWORD = "AdminBackup@2024"

# Throttle lightweight self-heal (seconds between full checks).
_ADMIN_HEAL_INTERVAL_SEC = 60.0
_last_admin_heal_monotonic: float = 0.0


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


def repair_null_user_ids(conn: sqlite3.Connection) -> int:
    """Assign SQLite rowid to users.id where missing (legacy schemas without AUTOINCREMENT)."""
    null_count = conn.execute(
        "SELECT COUNT(*) FROM users WHERE id IS NULL"
    ).fetchone()[0]
    if null_count:
        conn.execute("UPDATE users SET id = rowid WHERE id IS NULL")
        conn.commit()
    return int(null_count or 0)


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


def simulate_admin_login(conn: sqlite3.Connection) -> bool:
    """Exercise the same lookup + password path as the web login form."""
    try:
        from app import _authenticate_user_login, _user_pk_for_login_row

        row = _authenticate_user_login(conn, ADMIN_PRIVATE_ID[len("HU-"):], ADMIN_PASSWORD)
        if not row:
            return False
        pk = _user_pk_for_login_row(conn, row)
        return pk is not None and pk > 0
    except Exception:
        return False


def _repair_primary_admin(conn: sqlite3.Connection) -> None:
    """Create or update primary admin without deleting other users."""
    import admin_bootstrap

    admin_bootstrap.create_admin_user(
        conn,
        email=ADMIN_EMAIL,
        phone=ADMIN_PHONE,
        first_name="Admin",
        last_name="User",
        password=ADMIN_PASSWORD,
        private_id=ADMIN_PRIVATE_ID,
        public_id=ADMIN_PUBLIC_ID,
        reset_password=True,
        migrate=False,
    )
    repair_null_user_ids(conn)
    conn.execute(
        """
        UPDATE users SET is_admin = 1, is_active = 1, account_status = 'active',
               temp_access = 0
        WHERE private_id = ? COLLATE NOCASE
        """,
        (ADMIN_PRIVATE_ID,),
    )
    conn.commit()


def ensure_backup_admin(conn: sqlite3.Connection) -> bool:
    """Ensure backup admin exists with known credentials."""
    import admin_bootstrap

    row = conn.execute(
        "SELECT id FROM users WHERE private_id = ? COLLATE NOCASE",
        (BACKUP_PRIVATE_ID,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE users SET is_admin = 1, is_active = 1, account_status = 'active',
                   temp_access = 0, password_hash = ?
            WHERE private_id = ? COLLATE NOCASE AND password_hash IS NULL
            """,
            (admin_bootstrap._password_hash(BACKUP_PASSWORD), BACKUP_PRIVATE_ID),
        )
        conn.commit()
        return False

    admin_bootstrap.create_admin_user(
        conn,
        email=BACKUP_EMAIL,
        phone=BACKUP_PHONE,
        first_name="Backup",
        last_name="Admin",
        password=BACKUP_PASSWORD,
        private_id=BACKUP_PRIVATE_ID,
        public_id=BACKUP_PUBLIC_ID,
        reset_password=True,
        migrate=False,
    )
    repair_null_user_ids(conn)
    conn.execute(
        """
        UPDATE users SET is_admin = 1, is_active = 1, account_status = 'active'
        WHERE private_id = ? COLLATE NOCASE
        """,
        (BACKUP_PRIVATE_ID,),
    )
    conn.commit()
    return True


def ensure_admin_healthy(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Self-heal primary + backup admin accounts (throttled unless ``force``).

    Repairs NULL user ids, resets corrupt password hashes, and recreates
    missing admins using the full app schema (not raw SQL).
    """
    global _last_admin_heal_monotonic

    now = time.monotonic()
    if not force and (now - _last_admin_heal_monotonic) < _ADMIN_HEAL_INTERVAL_SEC:
        return {"skipped": True, "ok": True, "throttled": True}

    _last_admin_heal_monotonic = now
    actions: list[str] = []

    try:
        null_fixed = repair_null_user_ids(conn)
        if null_fixed:
            actions.append(f"repaired_null_ids:{null_fixed}")

        healthy = verify_admin_password(conn) and simulate_admin_login(conn)
        if not healthy:
            _repair_primary_admin(conn)
            actions.append("repaired_primary_admin")
            healthy = verify_admin_password(conn) and simulate_admin_login(conn)

        return {
            "skipped": False,
            "ok": healthy,
            "login_verified": verify_admin_password(conn),
            "login_simulated": simulate_admin_login(conn),
            "actions": actions,
        }
    except Exception as exc:
        return {
            "skipped": False,
            "ok": False,
            "error": str(exc),
            "actions": actions,
        }


def test_admin_login_status(conn: sqlite3.Connection) -> dict[str, Any]:
    """Public diagnostic payload for /test-admin-login."""
    diag = diagnose_admin(conn)
    target = diag.get("target")
    null_ids = conn.execute(
        "SELECT COUNT(*) FROM users WHERE id IS NULL"
    ).fetchone()[0]
    pwd_ok = verify_admin_password(conn)
    sim_ok = simulate_admin_login(conn)
    backup = conn.execute(
        """
        SELECT id, private_id, email FROM users
        WHERE private_id = ? COLLATE NOCASE
        """,
        (BACKUP_PRIVATE_ID,),
    ).fetchone()
    return {
        "exists": target is not None,
        "user_id": target.get("id") if target else None,
        "private_id": ADMIN_PRIVATE_ID,
        "login_digits": ADMIN_PRIVATE_ID[len("HU-"):],
        "password_valid": pwd_ok,
        "login_simulated": sim_ok,
        "users_with_null_id": int(null_ids or 0),
        "message": (
            "Login will work"
            if pwd_ok and sim_ok
            else "Admin needs repair — auto-heal will run"
        ),
        "backup_admin": dict(backup) if backup else None,
        "backup_login_digits": BACKUP_PRIVATE_ID[len("HU-"):],
        "all_admins": diag.get("admins"),
    }


def _connect_db(*, for_reset: bool = False) -> tuple[sqlite3.Connection, Path]:
    from db_path import resolve_database_path

    db_path = resolve_database_path(ROOT)
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    if for_reset:
        conn.execute("PRAGMA foreign_keys = OFF")
    else:
        conn.execute("PRAGMA foreign_keys = ON")
    return conn, db_path


def _remove_user_hard(conn: sqlite3.Connection, private_id: str) -> bool:
    """Remove a user row, wallets, and private_id FK references."""
    import identity_core

    pid = str(private_id or "").strip()
    if not pid:
        return False
    row = conn.execute(
        "SELECT id FROM users WHERE private_id = ? COLLATE NOCASE",
        (pid,),
    ).fetchone()
    if not row:
        return False

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for table, column in identity_core._private_id_fk_updates():
            try:
                conn.execute(
                    f"DELETE FROM [{table}] WHERE [{column}] = ?",
                    (pid,),
                )
            except sqlite3.OperationalError:
                pass

        for table in ("family_profile", "user_education", "user_work", "user_family_setup"):
            try:
                conn.execute(
                    f"DELETE FROM [{table}] WHERE user_private_id = ?",
                    (pid,),
                )
            except sqlite3.OperationalError:
                pass

        for table in ("registration_donations", "user_accounts"):
            try:
                conn.execute(
                    f"DELETE FROM [{table}] WHERE user_private_id = ?",
                    (pid,),
                )
            except sqlite3.OperationalError:
                pass

        try:
            conn.execute(
                "DELETE FROM wallets WHERE owner_type = 'user' AND owner_id = ?",
                (pid,),
            )
        except sqlite3.OperationalError:
            pass

        user_id = row["id"]
        if user_id is not None:
            conn.execute("DELETE FROM users WHERE id = ?", (int(user_id),))
        else:
            conn.execute(
                "DELETE FROM users WHERE private_id = ? COLLATE NOCASE",
                (pid,),
            )
    finally:
        if conn.execute("PRAGMA foreign_keys").fetchone()[0]:
            conn.execute("PRAGMA foreign_keys = ON")
    return True


def _ensure_schema(conn: sqlite3.Connection) -> None:
    from app import migrate_users_app_extensions

    migrate_users_app_extensions(conn)
    import qoin_core

    qoin_core.migrate_qoin_economy_tables(conn)
    repair_null_user_ids(conn)


def run_reset() -> dict[str, Any]:
    """
    Delete every admin account and create a fresh HU-014918240 admin.
    """
    out: dict[str, Any] = {
        "ok": False,
        "message": "",
        "deleted_admins": [],
        "admin_private_id": ADMIN_PRIVATE_ID,
        "admin_public_id": ADMIN_PUBLIC_ID,
        "admin_email": ADMIN_EMAIL,
        "admin_phone": ADMIN_PHONE,
        "admin_password": ADMIN_PASSWORD,
        "login_digits": ADMIN_PRIVATE_ID[len("HU-"):],
        "login_verified": False,
    }
    log_lines: list[str] = []

    try:
        conn, db_path = _connect_db(for_reset=True)
        log_lines.append(f"Database: {db_path}")
        _ensure_schema(conn)

        admins = conn.execute(
            """
            SELECT id, private_id, email FROM users
            WHERE COALESCE(is_admin, 0) = 1
            ORDER BY id
            """
        ).fetchall()
        log_lines.append(f"Found {len(admins)} admin account(s)")
        for row in admins:
            log_lines.append(
                f"  id={row['id']} private_id={row['private_id']} email={row['email']}"
            )

        targets_to_remove: list[str] = []
        for row in admins:
            targets_to_remove.append(str(row["private_id"]))
        for pid in (ADMIN_PRIVATE_ID, LEGACY_ADMIN_PRIVATE_ID):
            if pid not in targets_to_remove:
                dup = conn.execute(
                    "SELECT 1 FROM users WHERE private_id = ? COLLATE NOCASE",
                    (pid,),
                ).fetchone()
                if dup:
                    targets_to_remove.append(pid)

        deleted: list[str] = []
        for pid in targets_to_remove:
            if _remove_user_hard(conn, pid):
                deleted.append(pid)
                log_lines.append(f"Deleted: {pid}")
        out["deleted_admins"] = deleted
        conn.commit()

        import admin_bootstrap

        log_lines.append(f"Creating fresh admin at fixed ID {ADMIN_PRIVATE_ID}…")
        result = admin_bootstrap.create_admin_user(
            conn,
            email=ADMIN_EMAIL,
            phone=ADMIN_PHONE,
            first_name="Admin",
            last_name="User",
            password=ADMIN_PASSWORD,
            private_id=ADMIN_PRIVATE_ID,
            public_id=ADMIN_PUBLIC_ID,
            reset_password=True,
            migrate=False,
        )
        created_pid = str(result.get("private_id") or "").strip()
        log_lines.append(f"Admin {result.get('action')}: {created_pid}")
        if created_pid.upper() != ADMIN_PRIVATE_ID.upper():
            out["message"] = (
                f"Admin created with wrong ID {created_pid}; expected {ADMIN_PRIVATE_ID}"
            )
            out["log"] = "\n".join(log_lines)
            conn.close()
            return out

        repaired_ids = repair_null_user_ids(conn)
        if repaired_ids:
            log_lines.append(f"Repaired {repaired_ids} user row(s) with NULL id")

        out["login_verified"] = verify_admin_password(conn)
        out["login_simulated"] = simulate_admin_login(conn)
        out["diagnosis"] = diagnose_admin(conn)
        out["log"] = "\n".join(log_lines)

        if out["login_verified"] and out.get("login_simulated") and out["diagnosis"].get("target"):
            out["ok"] = True
            out["message"] = "Admin reset complete and login verified."
        elif out["login_verified"]:
            out["message"] = "Admin reset done; password OK but login simulation failed."
        else:
            out["message"] = "Admin reset finished but login verification failed."
        conn.close()
    except Exception as exc:
        out["message"] = str(exc)
        out["log"] = "\n".join(log_lines) + f"\nERROR: {exc}"
        out["ok"] = False

    return out


def format_reset_log(status: dict[str, Any]) -> str:
    lines = [
        "=" * 50,
        "Admin reset",
        "=" * 50,
    ]
    if status.get("log"):
        lines.append(str(status["log"]))
    lines.extend(
        [
            f"deleted: {status.get('deleted_admins')}",
            f"ok: {status.get('ok')}",
            f"message: {status.get('message')}",
            f"admin_private_id: {status.get('admin_private_id')}",
            f"login_digits: {status.get('login_digits')}",
            f"password: {ADMIN_PASSWORD}",
            f"login_verified: {status.get('login_verified')}",
            f"login_simulated: {status.get('login_simulated')}",
            "=" * 50,
        ]
    )
    return "\n".join(lines)


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
            out["login_simulated"] = simulate_admin_login(conn)
            out["diagnosis"] = diagnose_admin(conn)
        finally:
            conn.close()

        if out.get("ok") and out["login_verified"] and out.get("login_simulated"):
            out["message"] = "Admin login repaired and verified."
        elif out.get("ok") and out["login_verified"]:
            out["message"] = "Password OK but login simulation failed (check users.id)."
            out["ok"] = False
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
        f"login_simulated: {status.get('login_simulated')}",
        "=" * 50,
    ]
    return "\n".join(lines)
