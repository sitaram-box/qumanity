"""SITA Foundation donations tracking, Razorpay webhooks, and profile edit requests."""

from __future__ import annotations

import csv
import io
import json
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
    "name": "first_name",
    "date_of_birth": "date_of_birth",
    "birth_time": "birth_time",
    "birth_location": "birth_location_id",
    "current_location": "current_location_id",
    "phone": "phone",
    "email": "email",
}

PENDING_USER_PREFIX = "PENDING:"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _donation_columns(conn: sqlite3.Connection) -> set[str]:
    return {str(r[1]) for r in conn.execute("PRAGMA table_info(donations)")}


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
    additions: list[tuple[str, str]] = [
        ("admin_notes", "TEXT"),
        ("amount_paise", "INTEGER"),
        ("razorpay_payment_id", "TEXT"),
        ("razorpay_order_id", "TEXT"),
        ("razorpay_qr_id", "TEXT"),
        ("payment_status", "TEXT DEFAULT 'pending'"),
        ("webhook_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("webhook_payload", "TEXT"),
    ]
    cols = _donation_columns(conn)
    for col_name, decl in additions:
        if col_name not in cols:
            try:
                conn.execute(f"ALTER TABLE donations ADD COLUMN {col_name} {decl}")
            except sqlite3.OperationalError:
                pass
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_donations_razorpay_payment
        ON donations(razorpay_payment_id)
        WHERE razorpay_payment_id IS NOT NULL AND razorpay_payment_id != ''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_donations_razorpay_order
        ON donations(razorpay_order_id)
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


def mask_private_id(private_id: str) -> str:
    s = str(private_id or "").strip()
    if len(s) <= 3:
        return "***"
    return f"***{s[-3:]}"


def _payment_status_for_row(row: dict[str, Any] | sqlite3.Row) -> str:
    explicit = str(row.get("payment_status") or "").strip().lower()
    if explicit:
        return explicit
    status = str(row.get("status") or "pending").strip().lower()
    if status == "confirmed":
        return "completed"
    if status in ("failed", "authorized", "pending"):
        return status
    return "pending"


def donation_amount_rupees(row: dict[str, Any] | sqlite3.Row) -> int:
    try:
        paise = row["amount_paise"]
    except (KeyError, IndexError, TypeError):
        paise = None
    if paise is not None and int(paise or 0) > 0:
        return int(int(paise) / 100)
    return int(row["amount"] or 0)


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
    razorpay_order_id: str | None = None,
    razorpay_payment_id: str | None = None,
    razorpay_qr_id: str | None = None,
    amount_paise: int | None = None,
    payment_status: str | None = None,
) -> int:
    migrate_sita_platform_schema(conn)
    method = (payment_method or "").strip().lower()
    if method == "qr":
        method = "qr_code"
    rupees = int(amount)
    paise = int(amount_paise if amount_paise is not None else rupees * 100)
    status_norm = (status or "pending").strip().lower()
    pay_status = (payment_status or "").strip().lower()
    if not pay_status:
        pay_status = (
            "completed"
            if status_norm == "confirmed"
            else ("failed" if status_norm == "failed" else "pending")
        )
    cur = conn.execute(
        """
        INSERT INTO donations (
            user_private_id, user_public_id, amount, amount_paise, payment_method,
            referral_id, status, payment_status, transaction_id, razorpay_order_id,
            razorpay_payment_id, razorpay_qr_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(user_private_id).strip(),
            str(user_public_id).strip(),
            rupees,
            paise,
            method or None,
            (referral_id or "").strip() or None,
            status_norm,
            pay_status,
            (transaction_id or "").strip() or None,
            (razorpay_order_id or "").strip() or None,
            (razorpay_payment_id or "").strip() or None,
            (razorpay_qr_id or "").strip() or None,
            _now(),
        ),
    )
    return int(cur.lastrowid or 0)


def get_donation(conn: sqlite3.Connection, donation_id: int) -> dict[str, Any] | None:
    migrate_sita_platform_schema(conn)
    row = conn.execute(
        "SELECT * FROM donations WHERE id = ?",
        (int(donation_id),),
    ).fetchone()
    return dict(row) if row else None


def get_donation_status_payload(conn: sqlite3.Connection, donation_id: int) -> dict[str, Any]:
    row = get_donation(conn, donation_id)
    if not row:
        return {}
    status = str(row.get("status") or "pending")
    payment_status = _payment_status_for_row(row)
    webhook_verified = row.get("webhook_verified")
    confirmed = payment_status == "completed" or status == "confirmed"
    return {
        "id": row["id"],
        "status": status,
        "payment_status": payment_status,
        "paymentStatus": payment_status,
        "paid": confirmed,
        "can_submit": confirmed,
        "webhook_verified": bool(int(webhook_verified or 0)),
        "amount_rupees": donation_amount_rupees(row),
        "razorpay_order_id": row.get("razorpay_order_id"),
        "razorpay_payment_id": row.get("razorpay_payment_id"),
    }


def _find_donation_for_razorpay(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    payment_id: str,
) -> sqlite3.Row | None:
    if order_id:
        row = conn.execute(
            "SELECT * FROM donations WHERE razorpay_order_id = ?",
            (order_id,),
        ).fetchone()
        if row:
            return row
    if payment_id:
        return conn.execute(
            "SELECT * FROM donations WHERE razorpay_payment_id = ?",
            (payment_id,),
        ).fetchone()
    return None


def _find_donation_for_qr_id(conn: sqlite3.Connection, qr_id: str) -> sqlite3.Row | None:
    qr_id = (qr_id or "").strip()
    if not qr_id:
        return None
    return conn.execute(
        "SELECT * FROM donations WHERE razorpay_qr_id = ?",
        (qr_id,),
    ).fetchone()


def confirm_donation_from_razorpay(
    conn: sqlite3.Connection,
    donation_id: int,
    *,
    razorpay_payment_id: str,
    razorpay_order_id: str | None = None,
    amount_paise: int | None = None,
    confirmed_by: str = "razorpay_client",
) -> bool:
    migrate_sita_platform_schema(conn)
    row = conn.execute("SELECT id FROM donations WHERE id = ?", (int(donation_id),)).fetchone()
    if not row:
        return False
    conn.execute(
        """
        UPDATE donations
        SET status = 'confirmed',
            payment_status = 'completed',
            webhook_verified = 1,
            confirmed_at = ?,
            confirmed_by = ?,
            razorpay_payment_id = ?,
            razorpay_order_id = COALESCE(razorpay_order_id, ?),
            amount_paise = CASE WHEN ? IS NOT NULL AND ? > 0 THEN ? ELSE amount_paise END
        WHERE id = ?
        """,
        (
            _now(),
            confirmed_by,
            razorpay_payment_id,
            (razorpay_order_id or "").strip() or None,
            amount_paise,
            amount_paise or 0,
            amount_paise or 0,
            int(donation_id),
        ),
    )
    return True


def link_donation_to_user(
    conn: sqlite3.Connection,
    donation_id: int,
    user_private_id: str,
    user_public_id: str,
) -> None:
    migrate_sita_platform_schema(conn)
    conn.execute(
        """
        UPDATE donations
        SET user_private_id = ?, user_public_id = ?
        WHERE id = ?
        """,
        (
            str(user_private_id).strip(),
            str(user_public_id).strip(),
            int(donation_id),
        ),
    )


def process_razorpay_webhook(
    conn: sqlite3.Connection,
    event: str,
    payload: dict[str, Any],
) -> bool:
    """Apply Razorpay webhook event to donations table."""
    migrate_sita_platform_schema(conn)
    payload_json = json.dumps(payload)
    if event == "payment.authorized":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = str(payment.get("id") or "").strip()
        order_id = str(payment.get("order_id") or "").strip()
        if not payment_id and not order_id:
            return False
        row = _find_donation_for_razorpay(conn, order_id=order_id, payment_id=payment_id)
        if row is None:
            return False
        conn.execute(
            """
            UPDATE donations
            SET status = 'authorized',
                payment_status = 'authorized',
                razorpay_payment_id = COALESCE(razorpay_payment_id, ?),
                razorpay_order_id = COALESCE(razorpay_order_id, ?),
                webhook_payload = ?
            WHERE id = ? AND status IN ('pending', 'authorized')
            """,
            (
                payment_id or None,
                order_id or None,
                payload_json,
                int(row["id"]),
            ),
        )
        return True
    if event == "payment.captured":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = str(payment.get("id") or "").strip()
        order_id = str(payment.get("order_id") or "").strip()
        amount_paise = int(payment.get("amount") or 0)
        if not payment_id:
            return False
        row = _find_donation_for_razorpay(conn, order_id=order_id, payment_id=payment_id)
        if row is None:
            return False
        conn.execute(
            """
            UPDATE donations
            SET status = 'confirmed',
                payment_status = 'completed',
                webhook_verified = 1,
                confirmed_at = ?,
                confirmed_by = 'razorpay_webhook',
                razorpay_payment_id = ?,
                razorpay_order_id = COALESCE(razorpay_order_id, ?),
                amount_paise = CASE WHEN ? > 0 THEN ? ELSE amount_paise END,
                webhook_payload = ?
            WHERE id = ?
            """,
            (
                _now(),
                payment_id,
                order_id or None,
                amount_paise,
                amount_paise,
                payload_json,
                int(row["id"]),
            ),
        )
        return True
    if event == "payment.failed":
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        payment_id = str(payment.get("id") or "").strip()
        order_id = str(payment.get("order_id") or "").strip()
        if order_id:
            conn.execute(
                """
                UPDATE donations
                SET status = 'failed',
                    payment_status = 'failed',
                    webhook_payload = ?
                WHERE razorpay_order_id = ? AND status IN ('pending', 'authorized')
                """,
                (payload_json, order_id),
            )
            return True
        if payment_id:
            conn.execute(
                """
                UPDATE donations
                SET status = 'failed',
                    payment_status = 'failed',
                    webhook_payload = ?
                WHERE razorpay_payment_id = ? AND status IN ('pending', 'authorized')
                """,
                (payload_json, payment_id),
            )
            return True
    if event == "qr_code.credited":
        qr_entity = payload.get("payload", {}).get("qr_code", {}).get("entity", {})
        payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
        qr_id = str(qr_entity.get("id") or "").strip()
        payment_id = str(payment.get("id") or "").strip()
        order_id = str(payment.get("order_id") or "").strip()
        amount_paise = int(payment.get("amount") or 0)
        row = _find_donation_for_razorpay(conn, order_id=order_id, payment_id=payment_id)
        if row is None and qr_id:
            row = _find_donation_for_qr_id(conn, qr_id)
        if row is None:
            return False
        conn.execute(
            """
            UPDATE donations
            SET status = 'confirmed',
                payment_status = 'completed',
                webhook_verified = 1,
                confirmed_at = ?,
                confirmed_by = 'razorpay_webhook_qr',
                razorpay_payment_id = COALESCE(?, razorpay_payment_id),
                razorpay_order_id = COALESCE(razorpay_order_id, ?),
                razorpay_qr_id = COALESCE(razorpay_qr_id, ?),
                amount_paise = CASE WHEN ? > 0 THEN ? ELSE amount_paise END,
                webhook_payload = ?
            WHERE id = ?
            """,
            (
                _now(),
                payment_id or None,
                order_id or None,
                qr_id or None,
                amount_paise,
                amount_paise,
                payload_json,
                int(row["id"]),
            ),
        )
        return True
    return False


def user_donation_history(conn: sqlite3.Connection, user_private_id: str) -> dict[str, Any]:
    migrate_sita_platform_schema(conn)
    pid = str(user_private_id).strip()
    rows = conn.execute(
        """
        SELECT id, amount, amount_paise, payment_method, referral_id, status,
               transaction_id, razorpay_payment_id, webhook_verified,
               created_at, confirmed_at
        FROM donations
        WHERE user_private_id = ?
        ORDER BY datetime(created_at) DESC
        """,
        (pid,),
    ).fetchall()
    donations = []
    total_confirmed = 0
    for r in rows:
        d = dict(r)
        d["amount_rupees"] = donation_amount_rupees(r)
        donations.append(d)
        if str(d.get("status") or "") == "confirmed":
            total_confirmed += int(d["amount_rupees"])
    return {"donations": donations, "total_confirmed": total_confirmed}


def admin_donation_list(conn: sqlite3.Connection) -> dict[str, Any]:
    migrate_sita_platform_schema(conn)
    rows = conn.execute(
        """
        SELECT d.id, d.user_private_id, d.user_public_id, d.amount, d.amount_paise,
               d.payment_method, d.referral_id, d.status, d.transaction_id,
               d.razorpay_payment_id, d.razorpay_order_id, d.webhook_verified,
               d.created_at, d.confirmed_at, d.confirmed_by, d.admin_notes,
               u.first_name, u.last_name
        FROM donations d
        LEFT JOIN users u ON u.private_id = d.user_private_id
        ORDER BY datetime(d.created_at) DESC
        LIMIT 500
        """
    ).fetchall()
    donations: list[dict[str, Any]] = []
    pending_count = 0
    confirmed_count = 0
    failed_count = 0
    total_confirmed = 0
    for r in rows:
        d = dict(r)
        d["amount_rupees"] = donation_amount_rupees(r)
        d["user_name"] = f"{d.get('first_name') or ''} {d.get('last_name') or ''}".strip()
        if d.get("user_name") == "" and str(d.get("user_private_id") or "").startswith(
            PENDING_USER_PREFIX
        ):
            d["user_name"] = "Pending registration"
        donations.append(d)
        st = str(d.get("status") or "")
        if st == "pending":
            pending_count += 1
        elif st == "confirmed":
            confirmed_count += 1
            total_confirmed += int(d["amount_rupees"])
        elif st == "failed":
            failed_count += 1
    return {
        "donations": donations,
        "total_donations": len(donations),
        "total_amount": total_confirmed,
        "total_confirmed": total_confirmed,
        "pending_count": pending_count,
        "confirmed_count": confirmed_count,
        "failed_count": failed_count,
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
            "amount_rupees",
            "payment_method",
            "referral_id",
            "status",
            "webhook_verified",
            "razorpay_payment_id",
            "created_at",
            "confirmed_at",
        ]
    )
    for d in data["donations"]:
        writer.writerow(
            [
                d.get("id"),
                d.get("user_name"),
                d.get("user_public_id"),
                d.get("amount_rupees"),
                d.get("payment_method"),
                d.get("referral_id"),
                d.get("status"),
                d.get("webhook_verified"),
                d.get("razorpay_payment_id"),
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
