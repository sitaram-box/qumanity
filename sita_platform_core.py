"""SITA Foundation donations tracking and profile edit requests."""

from __future__ import annotations

import csv
import io
import sqlite3
from datetime import date, datetime, timezone
from typing import Any, Callable

NotifyFn = Callable[[sqlite3.Connection, str, str, str], None]

EDITABLE_FIELDS: dict[str, str] = {
    "name": "Name",
    "date_of_birth": "Date of Birth",
    "birth_time": "Birth Time",
    "birth_location": "Birth Location",
    "current_location": "Current Location",
    "phone": "Phone",
    "email": "Email",
}

FIELD_COLUMN_MAP: dict[str, str] = {
    "name": "first_name",  # special: splits into first/last
    "date_of_birth": "date_of_birth",
    "birth_time": "birth_time",
    "birth_location": "birth_location_id",
    "current_location": "current_location_id",
    "phone": "phone",
    "email": "email",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def migrate_sita_platform_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_private_id TEXT NOT NULL,
            user_public_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            payment_method TEXT,
            referral_id TEXT,
            status TEXT DEFAULT 'pending',
            transaction_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TIMESTAMP,
            confirmed_by TEXT,
            admin_notes TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_donations_user
        ON donations(user_private_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_donations_status
        ON donations(status)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS edit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_private_id TEXT NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT NOT NULL,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            reviewed_by TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_edit_requests_user
        ON edit_requests(user_private_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_edit_requests_status
        ON edit_requests(status)
        """
    )
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(donations)")}
    if "admin_notes" not in cols:
        try:
            conn.execute("ALTER TABLE donations ADD COLUMN admin_notes TEXT")
        except sqlite3.OperationalError:
            pass


def mask_private_id(private_id: str) -> str:
    s = str(private_id or "").strip()
    if len(s) <= 3:
        return "***"
    return f"***{s[-3:]}"


def record_donation(
    conn: sqlite3.Connection,
    *,
    user_private_id: str,
    user_public_id: str,
    amount: int,
    payment_method: str,
    referral_id: str | None = None,
    status: str = "pending",
    transaction_id: str | None = None,
) -> int:
    migrate_sita_platform_schema(conn)
    method = (payment_method or "").strip().lower()
    if method == "qr":
        method = "qr_code"
    cur = conn.execute(
        """
        INSERT INTO donations (
            user_private_id, user_public_id, amount, payment_method,
            referral_id, status, transaction_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(user_private_id).strip(),
            str(user_public_id).strip(),
            int(amount),
            method or None,
            (referral_id or "").strip() or None,
            (status or "pending").strip().lower(),
            (transaction_id or "").strip() or None,
            _now(),
        ),
    )
    return int(cur.lastrowid or 0)


def user_donation_history(conn: sqlite3.Connection, user_private_id: str) -> dict[str, Any]:
    migrate_sita_platform_schema(conn)
    pid = str(user_private_id).strip()
    rows = conn.execute(
        """
        SELECT id, amount, payment_method, referral_id, status,
               transaction_id, created_at, confirmed_at
        FROM donations
        WHERE user_private_id = ?
        ORDER BY datetime(created_at) DESC
        """,
        (pid,),
    ).fetchall()
    total = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS s
        FROM donations
        WHERE user_private_id = ? AND status = 'confirmed'
        """,
        (pid,),
    ).fetchone()
    return {
        "donations": [dict(r) for r in rows],
        "total_confirmed": int(total["s"] or 0) if total else 0,
    }


def admin_donation_list(conn: sqlite3.Connection) -> dict[str, Any]:
    migrate_sita_platform_schema(conn)
    rows = conn.execute(
        """
        SELECT d.id, d.user_private_id, d.user_public_id, d.amount,
               d.payment_method, d.referral_id, d.status, d.transaction_id,
               d.created_at, d.confirmed_at, d.confirmed_by, d.admin_notes,
               u.first_name, u.last_name
        FROM donations d
        LEFT JOIN users u ON u.private_id = d.user_private_id
        ORDER BY datetime(d.created_at) DESC
        LIMIT 500
        """
    ).fetchall()
    total = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS s
        FROM donations WHERE status = 'confirmed'
        """
    ).fetchone()
    return {
        "donations": [dict(r) for r in rows],
        "total_confirmed": int(total["s"] or 0) if total else 0,
    }


def confirm_donation(
    conn: sqlite3.Connection,
    donation_id: int,
    admin_private_id: str,
) -> bool:
    migrate_sita_platform_schema(conn)
    row = conn.execute(
        "SELECT id, status FROM donations WHERE id = ?",
        (int(donation_id),),
    ).fetchone()
    if not row or str(row["status"]) == "confirmed":
        return False
    conn.execute(
        """
        UPDATE donations
        SET status = 'confirmed', confirmed_at = ?, confirmed_by = ?
        WHERE id = ?
        """,
        (_now(), str(admin_private_id).strip(), int(donation_id)),
    )
    return True


def reject_donation(
    conn: sqlite3.Connection,
    donation_id: int,
    admin_private_id: str,
    reason: str,
) -> bool:
    migrate_sita_platform_schema(conn)
    row = conn.execute("SELECT id FROM donations WHERE id = ?", (int(donation_id),)).fetchone()
    if not row:
        return False
    conn.execute(
        """
        UPDATE donations
        SET status = 'failed', confirmed_at = ?, confirmed_by = ?, admin_notes = ?
        WHERE id = ?
        """,
        (_now(), str(admin_private_id).strip(), (reason or "").strip(), int(donation_id)),
    )
    return True


def donations_csv(conn: sqlite3.Connection) -> str:
    data = admin_donation_list(conn)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "user_name",
            "user_public_id",
            "amount",
            "payment_method",
            "referral_id",
            "status",
            "created_at",
            "confirmed_at",
        ]
    )
    for d in data["donations"]:
        name = f"{d.get('first_name') or ''} {d.get('last_name') or ''}".strip()
        writer.writerow(
            [
                d.get("id"),
                name,
                d.get("user_public_id"),
                d.get("amount"),
                d.get("payment_method"),
                d.get("referral_id"),
                d.get("status"),
                d.get("created_at"),
                d.get("confirmed_at"),
            ]
        )
    return buf.getvalue()


def submit_edit_request(
    conn: sqlite3.Connection,
    user_private_id: str,
    field_name: str,
    new_value: str,
    reason: str,
) -> int:
    migrate_sita_platform_schema(conn)
    field = str(field_name or "").strip().lower().replace(" ", "_")
    if field not in EDITABLE_FIELDS:
        raise ValueError("Invalid field")
    new_val = str(new_value or "").strip()
    if not new_val:
        raise ValueError("New value is required")
    old_val = _current_field_value(conn, user_private_id, field)
    cur = conn.execute(
        """
        INSERT INTO edit_requests (
            user_private_id, field_name, old_value, new_value, reason,
            status, created_at
        ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            str(user_private_id).strip(),
            field,
            old_val,
            new_val,
            (reason or "").strip(),
            _now(),
        ),
    )
    return int(cur.lastrowid or 0)


def _current_field_value(
    conn: sqlite3.Connection, user_private_id: str, field_name: str
) -> str | None:
    row = conn.execute(
        "SELECT * FROM users WHERE private_id = ?",
        (str(user_private_id).strip(),),
    ).fetchone()
    if not row:
        return None
    if field_name == "name":
        return f"{row['first_name']} {row['last_name']}".strip()
    col = FIELD_COLUMN_MAP.get(field_name)
    if not col:
        return None
    try:
        return str(row[col] or "") if row[col] is not None else ""
    except (KeyError, IndexError):
        return None


def admin_edit_request_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    migrate_sita_platform_schema(conn)
    rows = conn.execute(
        """
        SELECT er.id, er.user_private_id, er.field_name, er.old_value,
               er.new_value, er.reason, er.status, er.admin_notes,
               er.created_at, er.reviewed_at, er.reviewed_by,
               u.first_name, u.last_name, u.public_id
        FROM edit_requests er
        LEFT JOIN users u ON u.private_id = er.user_private_id
        WHERE er.status = 'pending'
        ORDER BY datetime(er.created_at) ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def approve_edit_request(
    conn: sqlite3.Connection,
    request_id: int,
    admin_private_id: str,
    notify_fn: NotifyFn | None = None,
    *,
    age_from_dob_fn: Callable[[date], int] | None = None,
) -> bool:
    migrate_sita_platform_schema(conn)
    req = conn.execute(
        "SELECT * FROM edit_requests WHERE id = ? AND status = 'pending'",
        (int(request_id),),
    ).fetchone()
    if not req:
        return False
    pid = str(req["user_private_id"])
    field = str(req["field_name"])
    new_val = str(req["new_value"])
    _apply_field_update(conn, pid, field, new_val, age_from_dob_fn=age_from_dob_fn)
    conn.execute(
        """
        UPDATE edit_requests
        SET status = 'approved', reviewed_at = ?, reviewed_by = ?
        WHERE id = ?
        """,
        (_now(), str(admin_private_id).strip(), int(request_id)),
    )
    if notify_fn:
        label = EDITABLE_FIELDS.get(field, field)
        notify_fn(
            conn,
            pid,
            "Profile edit approved",
            f"Your request to change {label} was approved.",
        )
    return True


def reject_edit_request(
    conn: sqlite3.Connection,
    request_id: int,
    admin_private_id: str,
    reason: str,
    notify_fn: NotifyFn | None = None,
) -> bool:
    migrate_sita_platform_schema(conn)
    req = conn.execute(
        "SELECT * FROM edit_requests WHERE id = ? AND status = 'pending'",
        (int(request_id),),
    ).fetchone()
    if not req:
        return False
    pid = str(req["user_private_id"])
    field = str(req["field_name"])
    conn.execute(
        """
        UPDATE edit_requests
        SET status = 'rejected', reviewed_at = ?, reviewed_by = ?, admin_notes = ?
        WHERE id = ?
        """,
        (_now(), str(admin_private_id).strip(), (reason or "").strip(), int(request_id)),
    )
    if notify_fn:
        label = EDITABLE_FIELDS.get(field, field)
        body = f"Your request to change {label} was rejected."
        if reason:
            body += f" Reason: {reason}"
        notify_fn(conn, pid, "Profile edit rejected", body)
    return True


def _apply_field_update(
    conn: sqlite3.Connection,
    user_private_id: str,
    field_name: str,
    new_value: str,
    *,
    age_from_dob_fn: Callable[[date], int] | None = None,
) -> None:
    if field_name == "name":
        parts = new_value.strip().split(None, 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
        conn.execute(
            "UPDATE users SET first_name = ?, last_name = ? WHERE private_id = ?",
            (first, last, user_private_id),
        )
        return
    col = FIELD_COLUMN_MAP.get(field_name)
    if not col:
        raise ValueError("Unsupported field")
    conn.execute(
        f"UPDATE users SET {col} = ? WHERE private_id = ?",
        (new_value.strip(), user_private_id),
    )
    if field_name == "date_of_birth" and age_from_dob_fn:
        try:
            dob = date.fromisoformat(new_value.strip())
            age = age_from_dob_fn(dob)
            conn.execute(
                "UPDATE users SET age = ? WHERE private_id = ?",
                (int(age), user_private_id),
            )
        except ValueError:
            pass
