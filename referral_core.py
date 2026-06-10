"""Referral codes, share logging, and first-karma reward logic for Qumanity."""

from __future__ import annotations

import base64
import json
import random
import re
import sqlite3
import string
from io import BytesIO
from typing import Any, Callable

import qoin_core

REFERRAL_CODE_PREFIX = "QUM-"
ADMIN_CODE_PREFIX = "ADM-"
VOLUNTEER_CODE_PREFIX = "VOL-"
AGENT_CODE_PREFIX = "AGT-"  # legacy alias → VOL-
REFERRAL_CODE_BODY_LEN = 6
REFERRAL_REWARD_RUPEES = 5
REFERRAL_MILESTONE_BONUS_RUPEES = 25
REFERRAL_MILESTONE_EVERY = 5

NotifyFn = Callable[[sqlite3.Connection, str, str, str], None]

KARMA_SHARE_TEMPLATES: dict[str, str] = {
    "plant_tree": (
        "I just earned {amount} Qoins by planting a tree with Qumanity! "
        "Join me and help make India green again. Use my code: {code}"
    ),
    "teach_hour": (
        "I just earned {amount} Qoins by teaching 1 hour with Qumanity! "
        "Knowledge is power. Join me: {code}"
    ),
    "help_elder": (
        "I just earned {amount} Qoins by helping an elder with Qumanity! "
        "Respect our elders. Join me: {code}"
    ),
}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _now() -> str:
    return qoin_core._now()


def _migrate_referral_agents_to_volunteers(conn: sqlite3.Connection) -> None:
    """Copy legacy referral_agents rows into volunteers (AGT- → VOL- codes)."""
    er_cols = _table_columns(conn, "employment_requests")
    for col_name, decl in [
        ("bank_name", "TEXT"),
        ("account_number", "TEXT"),
        ("branch", "TEXT"),
        ("ifsc_code", "TEXT"),
    ]:
        if col_name not in er_cols:
            try:
                conn.execute(
                    f"ALTER TABLE employment_requests ADD COLUMN {col_name} {decl}"
                )
            except sqlite3.OperationalError:
                pass

    try:
        existing = int(
            conn.execute("SELECT COUNT(*) FROM volunteers").fetchone()[0]
        )
    except sqlite3.OperationalError:
        return
    if existing > 0:
        return
    try:
        agents = conn.execute("SELECT * FROM referral_agents").fetchall()
    except sqlite3.OperationalError:
        return
    for ag in agents:
        code = str(ag["agent_code"] or "")
        if code.startswith(AGENT_CODE_PREFIX):
            code = VOLUNTEER_CODE_PREFIX + code[len(AGENT_CODE_PREFIX):]
        conn.execute(
            """
            INSERT OR IGNORE INTO volunteers (
                volunteer_private_id, volunteer_name, volunteer_code,
                bank_account_details, availability, status,
                approved_by, approved_at,
                total_volunteer_signups, total_volunteer_earnings, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ag["agent_private_id"]),
                str(ag["agent_name"]),
                code,
                str(ag["bank_account_details"] or ""),
                str(ag["availability"] or ""),
                str(ag["status"] or "pending"),
                ag["approved_by"],
                ag["approved_at"],
                int(ag["total_referrals"] or 0),
                int(ag["total_earnings"] or 0),
                ag["created_at"],
            ),
        )
        if str(ag["status"]) == "active":
            conn.execute(
                "UPDATE users SET referral_code = ? WHERE private_id = ?",
                (code, str(ag["agent_private_id"])),
            )


def migrate_referral_schema(conn: sqlite3.Connection) -> None:
    """Add referral columns, tables, and backfill codes for existing users."""
    cols = _table_columns(conn, "users")
    additions: list[tuple[str, str]] = [
        ("referral_code", "TEXT"),
        ("referred_by", "TEXT"),
        ("referral_count", "INTEGER NOT NULL DEFAULT 0"),
        ("referral_earnings", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col_name, decl in additions:
        if col_name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {decl}")
        except sqlite3.OperationalError:
            pass

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code
        ON users(referral_code)
        WHERE referral_code IS NOT NULL AND referral_code != ''
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_private_id TEXT NOT NULL,
            referred_private_id TEXT NOT NULL,
            referred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'pending',
            reward_amount INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (referrer_private_id) REFERENCES users(private_id),
            FOREIGN KEY (referred_private_id) REFERENCES users(private_id)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_referrals_referrer
        ON referrals(referrer_private_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_referrals_referred
        ON referrals(referred_private_id)
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS share_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_private_id TEXT NOT NULL,
            share_type TEXT NOT NULL,
            shared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS referral_agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_private_id TEXT NOT NULL UNIQUE,
            agent_name TEXT NOT NULL,
            agent_code TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'pending',
            approved_by TEXT,
            approved_at TIMESTAMP,
            bank_account_details TEXT,
            availability TEXT,
            total_referrals INTEGER NOT NULL DEFAULT 0,
            total_earnings INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_private_id) REFERENCES users(private_id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS volunteers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            volunteer_private_id TEXT NOT NULL UNIQUE,
            volunteer_name TEXT NOT NULL,
            volunteer_code TEXT NOT NULL UNIQUE,
            bank_name TEXT,
            account_number TEXT,
            branch TEXT,
            ifsc_code TEXT,
            bank_account_details TEXT,
            availability TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            approved_by TEXT,
            approved_at TIMESTAMP,
            total_volunteer_signups INTEGER NOT NULL DEFAULT 0,
            total_volunteer_earnings INTEGER NOT NULL DEFAULT 0,
            weekly_signups TEXT,
            monthly_signups TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (volunteer_private_id) REFERENCES users(private_id)
        )
        """
    )
    _migrate_referral_agents_to_volunteers(conn)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applicant_private_id TEXT NOT NULL,
            applicant_name TEXT NOT NULL,
            applicant_village_id TEXT NOT NULL,
            applicant_state TEXT NOT NULL,
            reason TEXT,
            bank_account_details TEXT,
            availability TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            reviewed_by TEXT,
            review_note TEXT,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    rows = conn.execute(
        """
        SELECT private_id FROM users
        WHERE referral_code IS NULL OR TRIM(referral_code) = ''
        """
    ).fetchall()
    for row in rows:
        pid = str(row["private_id"])
        code = generate_referral_code(conn)
        conn.execute(
            "UPDATE users SET referral_code = ? WHERE private_id = ?",
            (code, pid),
        )


def normalize_referral_code(raw: str | None) -> str:
    code = (raw or "").strip().upper()
    if not code:
        return ""
    for prefix in (ADMIN_CODE_PREFIX, VOLUNTEER_CODE_PREFIX, AGENT_CODE_PREFIX, REFERRAL_CODE_PREFIX):
        if code.startswith(prefix):
            if code.startswith(AGENT_CODE_PREFIX):
                return VOLUNTEER_CODE_PREFIX + code[len(AGENT_CODE_PREFIX):]
            return code
    if re.fullmatch(r"[A-Z0-9]{6}", code):
        return REFERRAL_CODE_PREFIX + code
    return code


def _generate_unique_code(conn: sqlite3.Connection, prefix: str) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(200):
        body = "".join(random.choice(alphabet) for _ in range(REFERRAL_CODE_BODY_LEN))
        code = f"{prefix}{body}"
        if conn.execute(
            "SELECT 1 FROM users WHERE referral_code = ?", (code,)
        ).fetchone():
            continue
        if conn.execute(
            "SELECT 1 FROM volunteers WHERE volunteer_code = ?", (code,)
        ).fetchone():
            continue
        if conn.execute(
            "SELECT 1 FROM referral_agents WHERE agent_code = ?", (code,)
        ).fetchone():
            continue
        return code
    raise RuntimeError(f"Unable to allocate unique code for prefix {prefix}")


def generate_referral_code(conn: sqlite3.Connection) -> str:
    """Return a unique QUM-XXXXXX code for general user sharing."""
    return _generate_unique_code(conn, REFERRAL_CODE_PREFIX)


def generate_admin_code(conn: sqlite3.Connection) -> str:
    return _generate_unique_code(conn, ADMIN_CODE_PREFIX)


def generate_volunteer_code(conn: sqlite3.Connection) -> str:
    return _generate_unique_code(conn, VOLUNTEER_CODE_PREFIX)


def generate_agent_code(conn: sqlite3.Connection) -> str:
    """Legacy alias."""
    return generate_volunteer_code(conn)


def ensure_user_referral_code(conn: sqlite3.Connection, private_id: str) -> str:
    row = conn.execute(
        "SELECT referral_code FROM users WHERE private_id = ?",
        (private_id,),
    ).fetchone()
    if row and row["referral_code"]:
        return str(row["referral_code"])
    code = generate_referral_code(conn)
    conn.execute(
        "UPDATE users SET referral_code = ? WHERE private_id = ?",
        (code, private_id),
    )
    return code


def lookup_referrer_by_code(conn: sqlite3.Connection, code: str) -> str | None:
    result = validate_referral_code(conn, code)
    return result.get("referrer_private_id") if result.get("valid") else None


def validate_referral_code(conn: sqlite3.Connection, code: str) -> dict[str, Any]:
    """Validate ADM-, VOL- (or legacy AGT-), or QUM- referral codes."""
    migrate_referral_schema(conn)
    normalized = normalize_referral_code(code)
    if not normalized:
        return {"valid": False, "error": "Referral code is required"}

    if normalized.startswith(VOLUNTEER_CODE_PREFIX) or normalized.startswith(
        AGENT_CODE_PREFIX
    ):
        lookup_code = normalized
        if lookup_code.startswith(AGENT_CODE_PREFIX):
            lookup_code = VOLUNTEER_CODE_PREFIX + lookup_code[len(AGENT_CODE_PREFIX):]
        row = conn.execute(
            """
            SELECT volunteer_private_id, volunteer_name, volunteer_code, status
            FROM volunteers WHERE volunteer_code = ?
            """,
            (lookup_code,),
        ).fetchone()
        if not row:
            legacy = conn.execute(
                """
                SELECT agent_private_id, agent_name, agent_code, status
                FROM referral_agents WHERE agent_code = ?
                """,
                (normalized,),
            ).fetchone()
            if legacy and str(legacy["status"]) == "active":
                return {
                    "valid": True,
                    "code_type": "volunteer",
                    "referrer_private_id": str(legacy["agent_private_id"]),
                    "referrer_name": str(legacy["agent_name"]),
                    "referral_code": lookup_code,
                }
        if not row or str(row["status"]) != "active":
            return {
                "valid": False,
                "error": "Volunteer referral code not found or inactive",
            }
        return {
            "valid": True,
            "code_type": "volunteer",
            "referrer_private_id": str(row["volunteer_private_id"]),
            "referrer_name": str(row["volunteer_name"]),
            "referral_code": str(row["volunteer_code"]),
        }

    row = conn.execute(
        """
        SELECT private_id, first_name, last_name, referral_code, is_active
        FROM users WHERE referral_code = ?
        """,
        (normalized,),
    ).fetchone()
    if not row or not int(row["is_active"] or 0):
        return {"valid": False, "error": "Referral code not found"}

    code_type = "admin" if normalized.startswith(ADMIN_CODE_PREFIX) else "user"
    name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
    return {
        "valid": True,
        "code_type": code_type,
        "referrer_private_id": str(row["private_id"]),
        "referrer_name": name,
        "referral_code": normalized,
    }


def lookup_active_volunteer_by_private_id(
    conn: sqlite3.Connection, private_id: str
) -> dict[str, Any] | None:
    migrate_referral_schema(conn)
    row = conn.execute(
        """
        SELECT volunteer_private_id, volunteer_name, volunteer_code, status
        FROM volunteers
        WHERE volunteer_private_id = ? AND status = 'active'
        """,
        (str(private_id),),
    ).fetchone()
    if row:
        return {
            "volunteer_private_id": str(row["volunteer_private_id"]),
            "volunteer_name": str(row["volunteer_name"]),
            "volunteer_code": str(row["volunteer_code"]),
        }
    legacy = conn.execute(
        """
        SELECT agent_private_id, agent_name, agent_code, status
        FROM referral_agents
        WHERE agent_private_id = ? AND status = 'active'
        """,
        (str(private_id),),
    ).fetchone()
    if not legacy:
        return None
    code = str(legacy["agent_code"])
    if code.startswith(AGENT_CODE_PREFIX):
        code = VOLUNTEER_CODE_PREFIX + code[len(AGENT_CODE_PREFIX):]
    return {
        "volunteer_private_id": str(legacy["agent_private_id"]),
        "volunteer_name": str(legacy["agent_name"]),
        "volunteer_code": code,
    }


def lookup_active_agent_by_private_id(
    conn: sqlite3.Connection, private_id: str
) -> dict[str, Any] | None:
    """Legacy alias — returns volunteer record with agent_* keys."""
    vol = lookup_active_volunteer_by_private_id(conn, private_id)
    if not vol:
        return None
    return {
        "agent_private_id": vol["volunteer_private_id"],
        "agent_name": vol["volunteer_name"],
        "agent_code": vol["volunteer_code"],
    }


def submit_employment_request(
    conn: sqlite3.Connection,
    *,
    applicant_private_id: str,
    applicant_name: str,
    applicant_village_id: str,
    applicant_state: str,
    reason: str,
    bank_account_details: str = "",
    bank_name: str = "",
    account_number: str = "",
    branch: str = "",
    ifsc_code: str = "",
    availability: str = "",
) -> int:
    migrate_referral_schema(conn)
    existing = conn.execute(
        """
        SELECT id FROM employment_requests
        WHERE applicant_private_id = ? AND status = 'pending'
        """,
        (applicant_private_id,),
    ).fetchone()
    if existing:
        raise ValueError("You already have a pending volunteer application")
    bank_summary = bank_account_details.strip()
    if not bank_summary and bank_name:
        bank_summary = (
            f"Bank: {bank_name.strip()}; A/C: {account_number.strip()}; "
            f"Branch: {branch.strip()}; IFSC: {ifsc_code.strip()}"
        )
    if not bank_summary:
        raise ValueError("Bank details are required")
    conn.execute(
        """
        INSERT INTO employment_requests (
            applicant_private_id, applicant_name, applicant_village_id,
            applicant_state, reason, bank_account_details, availability,
            bank_name, account_number, branch, ifsc_code
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            applicant_private_id,
            applicant_name,
            applicant_village_id,
            applicant_state,
            reason.strip(),
            bank_summary,
            availability.strip(),
            bank_name.strip(),
            account_number.strip(),
            branch.strip(),
            ifsc_code.strip(),
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def submit_volunteer_application(
    conn: sqlite3.Connection,
    *,
    applicant_private_id: str,
    applicant_name: str,
    applicant_village_id: str,
    applicant_state: str,
    reason: str,
    bank_name: str,
    account_number: str,
    branch: str,
    ifsc_code: str,
) -> int:
    """Submit volunteer application with structured bank fields."""
    return submit_employment_request(
        conn,
        applicant_private_id=applicant_private_id,
        applicant_name=applicant_name,
        applicant_village_id=applicant_village_id,
        applicant_state=applicant_state,
        reason=reason,
        bank_name=bank_name,
        account_number=account_number,
        branch=branch,
        ifsc_code=ifsc_code,
    )


def approve_employment_request(
    conn: sqlite3.Connection,
    request_id: int,
    *,
    approved_by: str,
    notify_fn: NotifyFn | None = None,
) -> dict[str, Any]:
    migrate_referral_schema(conn)
    req = conn.execute(
        "SELECT * FROM employment_requests WHERE id = ? AND status = 'pending'",
        (int(request_id),),
    ).fetchone()
    if not req:
        raise ValueError("Employment request not found or already reviewed")
    pid = str(req["applicant_private_id"])
    volunteer_code = generate_volunteer_code(conn)
    volunteer_name = str(req["applicant_name"])
    conn.execute(
        """
        INSERT INTO volunteers (
            volunteer_private_id, volunteer_name, volunteer_code, status,
            approved_by, approved_at, bank_name, account_number, branch,
            ifsc_code, bank_account_details, availability
        ) VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pid,
            volunteer_name,
            volunteer_code,
            approved_by,
            _now(),
            str(req["bank_name"] or ""),
            str(req["account_number"] or ""),
            str(req["branch"] or ""),
            str(req["ifsc_code"] or ""),
            str(req["bank_account_details"] or ""),
            str(req["availability"] or ""),
        ),
    )
    conn.execute(
        """
        UPDATE employment_requests
        SET status = 'approved', reviewed_by = ?, reviewed_at = ?
        WHERE id = ?
        """,
        (approved_by, _now(), int(request_id)),
    )
    conn.execute(
        "UPDATE users SET referral_code = ?, account_type = 'Volunteer' WHERE private_id = ?",
        (volunteer_code, pid),
    )
    if notify_fn:
        notify_fn(
            conn,
            pid,
            "Volunteer application approved",
            f"Your volunteer application was approved. Your volunteer code is {volunteer_code}.",
        )
    return {
        "volunteer_code": volunteer_code,
        "volunteer_private_id": pid,
        "agent_code": volunteer_code,
        "agent_private_id": pid,
    }


def reject_employment_request(
    conn: sqlite3.Connection,
    request_id: int,
    *,
    reviewed_by: str,
    review_note: str = "",
    notify_fn: NotifyFn | None = None,
) -> None:
    migrate_referral_schema(conn)
    req = conn.execute(
        "SELECT * FROM employment_requests WHERE id = ? AND status = 'pending'",
        (int(request_id),),
    ).fetchone()
    if not req:
        raise ValueError("Employment request not found or already reviewed")
    conn.execute(
        """
        UPDATE employment_requests
        SET status = 'rejected', reviewed_by = ?, review_note = ?, reviewed_at = ?
        WHERE id = ?
        """,
        (reviewed_by, review_note.strip(), _now(), int(request_id)),
    )
    if notify_fn:
        notify_fn(
            conn,
            str(req["applicant_private_id"]),
            "Volunteer application rejected",
            review_note.strip() or "Your volunteer application was not approved at this time.",
        )


def list_pending_employment_requests(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    migrate_referral_schema(conn)
    rows = conn.execute(
        """
        SELECT * FROM employment_requests
        WHERE status = 'pending'
        ORDER BY datetime(created_at) ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def create_pending_referral(
    conn: sqlite3.Connection,
    referrer_private_id: str,
    referred_private_id: str,
) -> None:
    if referrer_private_id == referred_private_id:
        return
    existing = conn.execute(
        """
        SELECT id FROM referrals
        WHERE referred_private_id = ?
        """,
        (referred_private_id,),
    ).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO referrals (
            referrer_private_id, referred_private_id, status, reward_amount
        ) VALUES (?, ?, 'pending', 0)
        """,
        (referrer_private_id, referred_private_id),
    )
    conn.execute(
        "UPDATE users SET referred_by = ? WHERE private_id = ?",
        (referrer_private_id, referred_private_id),
    )


def build_registration_url(base_url: str, referral_code: str) -> str:
    base = (base_url or "").rstrip("/")
    code = normalize_referral_code(referral_code)
    return f"{base}/register?ref={code}"


def generate_qr_base64(registration_url: str) -> str | None:
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(registration_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("ascii")


def log_share(conn: sqlite3.Connection, user_private_id: str, share_type: str) -> None:
    st = (share_type or "").strip().lower()
    if not st:
        return
    conn.execute(
        """
        INSERT INTO share_logs (user_private_id, share_type, shared_at)
        VALUES (?, ?, ?)
        """,
        (user_private_id, st, _now()),
    )


def get_referral_stats(conn: sqlite3.Connection, private_id: str) -> dict[str, Any]:
    migrate_referral_schema(conn)
    code = ensure_user_referral_code(conn, private_id)
    row = conn.execute(
        """
        SELECT referral_count, referral_earnings, referred_by
        FROM users WHERE private_id = ?
        """,
        (private_id,),
    ).fetchone()
    referral_count = int(row["referral_count"] or 0) if row else 0
    referral_earnings = int(row["referral_earnings"] or 0) if row else 0
    completed = conn.execute(
        """
        SELECT COUNT(*) AS c FROM referrals
        WHERE referrer_private_id = ? AND status IN ('completed', 'rewarded')
        """,
        (private_id,),
    ).fetchone()
    total_completed = int(completed["c"] or 0) if completed else referral_count
    return {
        "referral_code": code,
        "referral_count": max(referral_count, total_completed),
        "referral_earnings": referral_earnings,
        "referred_by": str(row["referred_by"] or "") if row else "",
    }


def get_leaderboard(conn: sqlite3.Connection, *, limit: int = 10) -> list[dict[str, Any]]:
    migrate_referral_schema(conn)
    rows = conn.execute(
        """
        SELECT u.first_name, u.last_name, u.public_id,
               u.referral_count, u.referral_earnings
        FROM users u
        WHERE u.referral_count > 0
        ORDER BY u.referral_count DESC, u.referral_earnings DESC
        LIMIT ?
        """,
        (max(1, min(limit, 50)),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for i, r in enumerate(rows, start=1):
        name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or str(r["public_id"])
        out.append(
            {
                "rank": i,
                "name": name,
                "public_id": str(r["public_id"] or ""),
                "referral_count": int(r["referral_count"] or 0),
                "referral_earnings": int(r["referral_earnings"] or 0),
            }
        )
    return out


def karma_share_text(
    action_code: str,
    amount_rupees: int,
    referral_code: str,
) -> str:
    code = normalize_referral_code(referral_code)
    template = KARMA_SHARE_TEMPLATES.get(
        action_code,
        (
            "I just earned {amount} Qoins with Qumanity! "
            "Join India's quantum governance revolution. Use my code: {code}"
        ),
    )
    return template.format(amount=int(amount_rupees), code=code)


def _send_notification(
    conn: sqlite3.Connection,
    recipient_private_id: str,
    subject: str,
    body: str,
    notify_fn: NotifyFn | None,
) -> None:
    if notify_fn:
        notify_fn(conn, recipient_private_id, subject, body)
        return
    try:
        from app import send_system_message

        send_system_message(conn, recipient_private_id, subject, body)
    except Exception:
        pass


def _credit_referral_reward(
    conn: sqlite3.Connection,
    private_id: str,
    rupees: int,
    ref_label: str,
) -> None:
    denoms = qoin_core.min_qoins_for_amount(int(rupees))
    qoin_core.credit_wallet_denoms(
        conn,
        "user",
        private_id,
        denoms,
        transaction_ref=ref_label,
        amount_rupees=int(rupees),
    )


def _verified_karma_count(conn: sqlite3.Connection, private_id: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM karma_transactions
        WHERE user_private_id = ? AND verified = 1
        """,
        (private_id,),
    ).fetchone()
    return int(row["c"] or 0) if row else 0


def process_referral_on_karma(
    conn: sqlite3.Connection,
    *,
    user_private_id: str,
    action_code: str = "",
    amount_rupees: int = 0,
    notify_fn: NotifyFn | None = None,
) -> dict[str, Any] | None:
    """
    On a user's first verified karma action, reward referrer and referred user.
    Returns summary dict when rewards are issued, else None.
    """
    migrate_referral_schema(conn)
    pid = str(user_private_id)
    if conn.execute(
        "SELECT 1 FROM donation_distributions WHERE new_user_private_id = ?",
        (pid,),
    ).fetchone():
        return None
    if _verified_karma_count(conn, pid) != 1:
        return None

    user = conn.execute(
        "SELECT referred_by FROM users WHERE private_id = ?",
        (pid,),
    ).fetchone()
    if not user or not user["referred_by"]:
        return None

    referrer_pid = str(user["referred_by"])
    referral = conn.execute(
        """
        SELECT id, referrer_private_id, status FROM referrals
        WHERE referred_private_id = ? AND status = 'pending'
        ORDER BY id ASC LIMIT 1
        """,
        (pid,),
    ).fetchone()
    if not referral:
        return None

    reward = REFERRAL_REWARD_RUPEES
    _credit_referral_reward(
        conn,
        referrer_pid,
        reward,
        f"referral-reward-{referral['id']}-referrer",
    )
    _credit_referral_reward(
        conn,
        pid,
        reward,
        f"referral-reward-{referral['id']}-referred",
    )

    conn.execute(
        """
        UPDATE referrals
        SET status = 'rewarded', reward_amount = ?
        WHERE id = ?
        """,
        (reward, int(referral["id"])),
    )
    conn.execute(
        """
        UPDATE users
        SET referral_count = COALESCE(referral_count, 0) + 1,
            referral_earnings = COALESCE(referral_earnings, 0) + ?
        WHERE private_id = ?
        """,
        (reward, referrer_pid),
    )

    milestone_bonus = 0
    ref_row = conn.execute(
        "SELECT referral_count FROM users WHERE private_id = ?",
        (referrer_pid,),
    ).fetchone()
    ref_count = int(ref_row["referral_count"] or 0) if ref_row else 0
    if ref_count > 0 and ref_count % REFERRAL_MILESTONE_EVERY == 0:
        milestone_bonus = REFERRAL_MILESTONE_BONUS_RUPEES
        _credit_referral_reward(
            conn,
            referrer_pid,
            milestone_bonus,
            f"referral-milestone-{ref_count}-{referrer_pid}",
        )
        conn.execute(
            """
            UPDATE users
            SET referral_earnings = COALESCE(referral_earnings, 0) + ?
            WHERE private_id = ?
            """,
            (milestone_bonus, referrer_pid),
        )

    _send_notification(
        conn,
        referrer_pid,
        "Referral reward — Qoins credited",
        (
            f"Your friend completed their first karma action ({action_code or 'karma'}). "
            f"You earned ₹{reward} in Qoins!"
            + (
                f" Milestone bonus: ₹{milestone_bonus} for {ref_count} referrals!"
                if milestone_bonus
                else ""
            )
        ),
        notify_fn,
    )
    _send_notification(
        conn,
        pid,
        "Welcome bonus — Qoins credited",
        (
            f"Congratulations on your first karma action! "
            f"You earned a ₹{reward} welcome bonus in Qoins."
        ),
        notify_fn,
    )

    return {
        "referral_id": int(referral["id"]),
        "referrer_reward": reward,
        "referred_reward": reward,
        "milestone_bonus": milestone_bonus,
    }


def get_volunteer_by_private_id(
    conn: sqlite3.Connection, private_id: str
) -> dict[str, Any] | None:
    migrate_referral_schema(conn)
    row = conn.execute(
        "SELECT * FROM volunteers WHERE volunteer_private_id = ?",
        (str(private_id),),
    ).fetchone()
    return dict(row) if row else None


def get_volunteer_status(conn: sqlite3.Connection, private_id: str) -> dict[str, Any]:
    migrate_referral_schema(conn)
    vol = get_volunteer_by_private_id(conn, private_id)
    if vol:
        return {
            "status": str(vol.get("status") or "pending"),
            "volunteer_code": str(vol.get("volunteer_code") or ""),
            "is_active": str(vol.get("status")) == "active",
        }
    pending = conn.execute(
        """
        SELECT id FROM employment_requests
        WHERE applicant_private_id = ? AND status = 'pending'
        ORDER BY id DESC LIMIT 1
        """,
        (str(private_id),),
    ).fetchone()
    if pending:
        return {"status": "pending", "volunteer_code": "", "is_active": False}
    return {"status": "none", "volunteer_code": "", "is_active": False}


def record_volunteer_signup(
    conn: sqlite3.Connection,
    *,
    volunteer_private_id: str,
    earnings_rupees: int = 0,
) -> None:
    migrate_referral_schema(conn)
    conn.execute(
        """
        UPDATE volunteers
        SET total_volunteer_signups = COALESCE(total_volunteer_signups, 0) + 1,
            total_volunteer_earnings = COALESCE(total_volunteer_earnings, 0) + ?
        WHERE volunteer_private_id = ? AND status = 'active'
        """,
        (int(earnings_rupees), str(volunteer_private_id)),
    )


def _volunteer_signups_since(
    conn: sqlite3.Connection, volunteer_private_id: str, days: int
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM users
        WHERE referred_by = ?
          AND datetime(created_at) >= datetime('now', ?)
        """,
        (str(volunteer_private_id), f"-{int(days)} days"),
    ).fetchone()
    return int(row["c"] or 0) if row else 0


def _volunteer_referrer_earnings_since(
    conn: sqlite3.Connection, volunteer_private_id: str, days: int | None
) -> int:
    if days is None:
        rows = conn.execute(
            """
            SELECT distribution_json FROM donation_distributions
            WHERE referrer_private_id = ?
            """,
            (str(volunteer_private_id),),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT distribution_json FROM donation_distributions
            WHERE referrer_private_id = ?
              AND datetime(created_at) >= datetime('now', ?)
            """,
            (str(volunteer_private_id), f"-{int(days)} days"),
        ).fetchall()
    total = 0
    for r in rows:
        try:
            dist = json.loads(str(r["distribution_json"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            continue
        for item in dist:
            if str(item.get("tier")) == "referrer":
                total += int(item.get("rupee_amount") or 0)
    return total


def get_volunteer_dashboard(
    conn: sqlite3.Connection, private_id: str
) -> dict[str, Any]:
    migrate_referral_schema(conn)
    vol = get_volunteer_by_private_id(conn, private_id)
    if not vol or str(vol.get("status")) != "active":
        raise ValueError("Active volunteer record not found")
    pid = str(private_id)
    code = str(vol.get("volunteer_code") or "")
    total_signups = int(vol.get("total_volunteer_signups") or 0)
    total_earnings = int(vol.get("total_volunteer_earnings") or 0)
    if total_earnings == 0:
        total_earnings = _volunteer_referrer_earnings_since(conn, pid, None)

    return {
        "volunteer_code": code,
        "performance": {
            "week": {
                "signups": _volunteer_signups_since(conn, pid, 7),
                "qoins": _volunteer_referrer_earnings_since(conn, pid, 7),
            },
            "month": {
                "signups": _volunteer_signups_since(conn, pid, 30),
                "qoins": _volunteer_referrer_earnings_since(conn, pid, 30),
            },
            "year": {
                "signups": _volunteer_signups_since(conn, pid, 365),
                "qoins": _volunteer_referrer_earnings_since(conn, pid, 365),
            },
            "total": {"signups": total_signups, "qoins": total_earnings},
        },
    }


def list_volunteer_signups(
    conn: sqlite3.Connection,
    private_id: str,
    *,
    months: int = 12,
    limit: int = 100,
) -> list[dict[str, Any]]:
    migrate_referral_schema(conn)
    rows = conn.execute(
        """
        SELECT u.first_name, u.last_name, u.public_id, u.is_active,
               u.created_at, u.private_id
        FROM users u
        WHERE u.referred_by = ?
          AND datetime(u.created_at) >= datetime('now', ?)
        ORDER BY datetime(u.created_at) DESC
        LIMIT ?
        """,
        (str(private_id), f"-{int(months) * 30} days", max(1, min(limit, 500))),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip() or str(
            r["public_id"]
        )
        dd = conn.execute(
            """
            SELECT donation_amount, distribution_json, activated
            FROM donation_distributions
            WHERE new_user_private_id = ?
            """,
            (str(r["private_id"]),),
        ).fetchone()
        earnings = 0
        status = "Active" if int(r["is_active"] or 0) else "Inactive"
        if dd:
            try:
                dist = json.loads(str(dd["distribution_json"] or "[]"))
                for item in dist:
                    if str(item.get("tier")) == "referrer":
                        earnings = int(item.get("rupee_amount") or 0)
                        break
            except (json.JSONDecodeError, TypeError):
                pass
            if not int(dd["activated"] or 0):
                status = "Pending"
        out.append(
            {
                "user_name": name,
                "signup_date": str(r["created_at"] or "")[:10],
                "status": status,
                "qoins_earned": earnings,
            }
        )
    return out
