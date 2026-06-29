"""User ID formation, multi-account IDs, OTP recovery, and notifications."""

from __future__ import annotations

import logging
import random
import re
import secrets
import sqlite3
import string
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

PATH_PREFIX = "0.राम|"

IDENTITY_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS user_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    account_id TEXT UNIQUE NOT NULL,
    location_path TEXT NOT NULL,
    location_id TEXT,
    location_type TEXT NOT NULL,
    is_primary INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_user_accounts_private ON user_accounts(user_private_id);
CREATE INDEX IF NOT EXISTS idx_user_accounts_location ON user_accounts(location_path);

CREATE TABLE IF NOT EXISTS otp_verification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    phone TEXT,
    otp_code TEXT NOT NULL,
    purpose TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    used INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_verification(email);
CREATE INDEX IF NOT EXISTS idx_otp_phone ON otp_verification(phone);
"""

AGE_GROUP_CODES = {
    "Balak": "B",
    "Yuvak": "Y",
    "Vridh": "V",
    "Sanyas": "S",
}

SUN_SIGN_LETTER = {
    "Aries": "A",
    "Taurus": "T",
    "Gemini": "G",
    "Cancer": "C",
    "Leo": "L",
    "Virgo": "V",
    "Libra": "B",
    "Scorpio": "S",
    "Sagittarius": "G",
    "Capricorn": "C",
    "Aquarius": "A",
    "Pisces": "P",
}

# Element first letter + Sun sign first letter (e.g. Fire + Leo → FL).
ZODIAC_ELEMENT_SIGN_CODES = {
    "Aries": "FA",
    "Taurus": "ET",
    "Gemini": "AG",
    "Cancer": "WC",
    "Leo": "FL",
    "Virgo": "EV",
    "Libra": "AL",
    "Scorpio": "WS",
    "Sagittarius": "FS",
    "Capricorn": "EC",
    "Aquarius": "AA",
    "Pisces": "WP",
}


def migrate_identity_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(IDENTITY_TABLES_SQL)
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(users)")}
    for col, decl in (
        ("phone", "TEXT"),
        ("current_age_category", "TEXT"),
    ):
        if col not in cols:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError:
                pass
    conn.commit()
    drop_short_private_id_column(conn)


def drop_short_private_id_column(conn: sqlite3.Connection) -> None:
    """Remove deprecated short_private_id column from users if present."""
    cols = [str(r[1]) for r in conn.execute("PRAGMA table_info(users)")]
    if "short_private_id" not in cols:
        return
    drop_cols = {"short_private_id", "short_id_generated_at"}
    keep = [c for c in cols if c not in drop_cols]
    if not keep:
        return
    col_sql = ", ".join(keep)
    try:
        conn.execute("DROP INDEX IF EXISTS idx_users_short_private_id")
    except sqlite3.OperationalError:
        pass
    conn.execute(f"CREATE TABLE users_new AS SELECT {col_sql} FROM users")
    conn.execute("DROP TABLE users")
    conn.execute("ALTER TABLE users_new RENAME TO users")
    conn.commit()


def replace_age_segment_in_id(full_id: str, new_age_group: str) -> str:
    """Replace the ``A{B|Y|V|S}`` age segment in a private/public/account id."""
    fid = (full_id or "").strip()
    if not fid:
        return fid
    parts = fid.split("-")
    if len(parts) < 4:
        return fid
    new_seg = f"A{_age_group_code(new_age_group)}"
    if parts[3] == new_seg:
        return fid
    parts[3] = new_seg
    return "-".join(parts)


def _private_id_fk_updates() -> tuple[tuple[str, str], ...]:
    return (
        ("posts", "user_private_id"),
        ("messages", "from_user_private_id"),
        ("messages", "to_user_private_id"),
        ("connection_requests", "from_user_private_id"),
        ("connection_requests", "to_user_private_id"),
        ("family_members", "user_private_id"),
        ("family_members", "member_private_id"),
        ("family_relationships", "user_private_id"),
        ("family_relationships", "related_private_id"),
        ("link_requests", "from_user_private_id"),
        ("link_requests", "to_user_private_id"),
        ("user_education", "user_private_id"),
        ("user_work", "user_private_id"),
        ("user_family_setup", "user_private_id"),
        ("qoin_transactions", "user_private_id"),
        ("user_birth_planets", "user_private_id"),
        ("user_accounts", "user_private_id"),
        ("category_history", "user_private_id"),
        ("varna_appeals", "user_private_id"),
        ("leadership_council", "current_holder_private_id"),
        ("leadership_council", "appointed_by_private_id"),
        ("election_candidates", "candidate_private_id"),
        ("election_votes", "voter_private_id"),
        ("pending_referrals", "referrer_private_id"),
        ("pending_referrals", "referred_private_id"),
        ("deceased_users", "original_private_id"),
        ("deceased_users", "wallet_transferred_to"),
        ("akashic_records", "user_private_id"),
        ("donations", "user_private_id"),
        ("registration_donations", "user_private_id"),
        ("registration_donations", "volunteer_private_id"),
        ("donation_distributions", "new_user_private_id"),
        ("donation_distributions", "referrer_private_id"),
        ("donation_distributions", "agent_private_id"),
        ("donation_transactions", "user_private_id"),
        ("referrals", "referrer_private_id"),
        ("referrals", "referred_private_id"),
        ("volunteers", "volunteer_private_id"),
        ("share_logs", "user_private_id"),
        ("edit_requests", "user_private_id"),
        ("family_removal_requests", "user_private_id"),
    )


def reassign_user_private_id(
    conn: sqlite3.Connection,
    old_private_id: str,
    new_private_id: str,
    *,
    new_public_id: str | None = None,
) -> None:
    """Move all FK references from ``old_private_id`` to ``new_private_id``."""
    old_pid = str(old_private_id or "").strip()
    new_pid = str(new_private_id or "").strip()
    if not old_pid or not new_pid or old_pid == new_pid:
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for table, column in _private_id_fk_updates():
            try:
                conn.execute(
                    f"UPDATE [{table}] SET [{column}] = ? WHERE [{column}] = ?",
                    (new_pid, old_pid),
                )
            except sqlite3.OperationalError:
                pass

        for table in ("family_profile", "user_education", "user_work", "user_family_setup"):
            try:
                conn.execute(
                    f"UPDATE [{table}] SET user_private_id = ? WHERE user_private_id = ?",
                    (new_pid, old_pid),
                )
            except sqlite3.OperationalError:
                pass

        try:
            conn.execute(
                """
                UPDATE wallets SET owner_id = ?
                WHERE owner_type = 'user' AND owner_id = ?
                """,
                (new_pid, old_pid),
            )
        except sqlite3.OperationalError:
            pass

        if new_public_id:
            try:
                conn.execute(
                    "UPDATE donations SET user_public_id = ? WHERE user_private_id = ?",
                    (str(new_public_id).strip(), new_pid),
                )
            except sqlite3.OperationalError:
                pass

        cols = {
            str(r[1])
            for r in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "referred_by_private_id" in cols:
            try:
                conn.execute(
                    "UPDATE users SET referred_by_private_id = ? WHERE referred_by_private_id = ?",
                    (new_pid, old_pid),
                )
            except sqlite3.OperationalError:
                pass

        conn.execute(
            """
            UPDATE users
            SET private_id = ?, public_id = COALESCE(?, public_id)
            WHERE private_id = ? COLLATE NOCASE
            """,
            (new_pid, new_public_id, old_pid),
        )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def cascade_private_id_change(
    conn: sqlite3.Connection,
    old_private_id: str,
    new_private_id: str,
    new_public_id: str,
    new_age_group: str,
) -> None:
    """Update FK references and economic account ids after age-category ID change."""
    old_pid = str(old_private_id).strip()
    new_pid = str(new_private_id).strip()
    if not old_pid or old_pid == new_pid:
        return
    for table, column in _private_id_fk_updates():
        try:
            conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE {column} = ?",
                (new_pid, old_pid),
            )
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute(
            """
            UPDATE wallets SET owner_id = ?
            WHERE owner_type = 'user' AND owner_id = ?
            """,
            (new_pid, old_pid),
        )
    except sqlite3.OperationalError:
        pass
    account_rows = conn.execute(
        "SELECT id, account_id FROM user_accounts WHERE user_private_id = ?",
        (old_pid,),
    ).fetchall()
    for acc in account_rows:
        new_aid = replace_age_segment_in_id(str(acc["account_id"]), new_age_group)
        conn.execute(
            """
            UPDATE user_accounts SET account_id = ?, user_private_id = ?
            WHERE id = ?
            """,
            (new_aid, new_pid, int(acc["id"])),
        )


def _age_group_from_id_segment(private_id: str) -> str:
    parts = (private_id or "").split("-")
    if len(parts) < 4:
        return "Yuvak"
    seg = parts[3]
    if len(seg) >= 2 and seg[0] == "A":
        code = seg[1]
        rev = {v: k for k, v in AGE_GROUP_CODES.items()}
        return rev.get(code, "Yuvak")
    return "Yuvak"


def update_user_age_category(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
    *,
    new_age_group: str,
    new_age: int,
    notify_fn: Any | None = None,
) -> bool:
    """Update age group and regenerate private/public IDs when category changes."""
    old_pid = str(user_row["private_id"])
    old_group = str(user_row["age_group"] or "").strip()
    if old_group == new_age_group:
        conn.execute(
            "UPDATE users SET age = ?, current_age_category = ? WHERE private_id = ?",
            (new_age, new_age_group, old_pid),
        )
        return False
    new_private_id = replace_age_segment_in_id(old_pid, new_age_group)
    new_public_id = replace_age_segment_in_id(str(user_row["public_id"]), new_age_group)
    cascade_private_id_change(
        conn, old_pid, new_private_id, new_public_id, new_age_group
    )
    conn.execute(
        """
        UPDATE users
        SET private_id = ?, public_id = ?, age = ?, age_group = ?, current_age_category = ?
        WHERE private_id = ?
        """,
        (new_private_id, new_public_id, new_age, new_age_group, new_age_group, old_pid),
    )
    if notify_fn:
        try:
            notify_fn(
                conn,
                new_private_id,
                "system",
                f"Your age category is now {new_age_group}. Your Private ID and Account ID were updated.",
            )
        except Exception:
            logger.exception("age category notification failed")
    return True


def run_daily_age_category_updates(
    conn: sqlite3.Connection,
    *,
    life_stage_from_age_fn: Any,
    compute_age_fn: Any,
    notify_fn: Any | None = None,
) -> dict[str, int]:
    """Recompute age categories for all users with date of birth."""
    from datetime import date as date_cls

    today = date_cls.today()
    updated = 0
    scanned = 0
    rows = conn.execute(
        """
        SELECT * FROM users
        WHERE date_of_birth IS NOT NULL AND TRIM(date_of_birth) != ''
          AND COALESCE(is_deceased, 0) = 0
        """
    ).fetchall()
    for user in rows:
        scanned += 1
        try:
            dob = date_cls.fromisoformat(str(user["date_of_birth"])[:10])
        except ValueError:
            continue
        age = int(compute_age_fn(dob, today))
        new_group = str(life_stage_from_age_fn(age))
        if update_user_age_category(
            conn,
            user,
            new_age_group=new_group,
            new_age=age,
            notify_fn=notify_fn,
        ):
            updated += 1
    return {"scanned": scanned, "updated": updated}


def raw_path(full_id: str) -> str:
    fid = (full_id or "").strip()
    if fid.startswith(PATH_PREFIX):
        return fid[len(PATH_PREFIX) :]
    return fid


def _gender_code(gender: str | None) -> str:
    g = (gender or "").strip()
    if g in ("Male", "Male born female"):
        return "M"
    if g in ("Female", "Female born male"):
        return "F"
    return "O"


def _age_group_code(age_group: str | None) -> str:
    ag = (age_group or "").strip()
    if ag in AGE_GROUP_CODES:
        return AGE_GROUP_CODES[ag]
    if ag == "Balak":
        return "B"
    return "Y"


def _zodiac_code(sun_sign: str | None) -> str:
    sign = (sun_sign or "").strip()
    if sign in ZODIAC_ELEMENT_SIGN_CODES:
        return ZODIAC_ELEMENT_SIGN_CODES[sign]
    letter = SUN_SIGN_LETTER.get(sign)
    if letter:
        return f"Z{letter}"
    letters = "".join(c for c in sign if c.isalpha())
    letter = (letters[:1].upper() or "X")
    return f"Z{letter}"


def location_path_for_id(
    location_id: str | None,
    *,
    country_id: str | None = None,
) -> str:
    """Convert stored location id to dot path (e.g. CS.DL.5.4.1E)."""
    loc = (location_id or "").strip()
    if not loc:
        return (country_id or "GLOBAL").upper()
    rp = raw_path(loc)
    tail = rp
    if "IND/" in rp:
        tail = rp.split("IND/", 1)[1]
    elif "IND." in rp:
        tail = rp.split("IND.", 1)[1]
    if "/" in tail:
        zone, rest = tail.split("/", 1)
        return f"{zone}.{rest}"
    return tail.replace("/", ".")


def _random_prefix(length: int | None = None) -> str:
    n = length or random.randint(3, 4)
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def _id_core(
    prefix: str,
    first_name: str,
    last_name: str,
    gender: str,
    age_group: str,
    sun_sign: str,
) -> str:
    f1 = (first_name.strip()[:1].upper() or "X")
    l1 = (last_name.strip()[:1].upper() or "X")
    return (
        f"{prefix}-{f1}{l1}-G{_gender_code(gender)}-"
        f"A{_age_group_code(age_group)}-{_zodiac_code(sun_sign)}"
    )


def _id_exists(conn: sqlite3.Connection, candidate: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM users WHERE private_id = ? OR public_id = ? COLLATE NOCASE",
        (candidate, candidate),
    ).fetchone()
    if row:
        return True
    row = conn.execute(
        "SELECT 1 FROM user_accounts WHERE account_id = ? COLLATE NOCASE",
        (candidate,),
    ).fetchone()
    return row is not None


def extract_id_core(private_id: str) -> str | None:
    """Return shared core (prefix through zodiac) from a private id."""
    parts = (private_id or "").strip().split("-")
    if len(parts) < 6:
        return None
    return "-".join(parts[:5])


def generate_unique_ids(
    conn: sqlite3.Connection,
    first_name: str,
    last_name: str,
    gender: str,
    age_group: str,
    sun_sign: str,
    birth_location_path: str,
    present_location_path: str,
    *,
    element: str | None = None,
    fixed_prefix: str | None = None,
) -> tuple[str, str]:
    """Return (private_id, public_id) with collision-safe random prefix.

    Format: ``PREFIX-XY-GM-AY-FL-LOCATION`` where gender is ``G{M|F|O}``,
    age is ``A{B|Y|V|S}``, and zodiac is element+sign (e.g. ``FL`` for Fire/Leo).
    ``element`` is accepted for API compatibility; zodiac codes derive from ``sun_sign``.
    """
    _ = element
    for _ in range(50_000):
        prefix = fixed_prefix or _random_prefix()
        core = _id_core(prefix, first_name, last_name, gender, age_group, sun_sign)
        private_id = f"{core}-{birth_location_path}"
        public_id = f"{core}-{present_location_path}"
        if not _id_exists(conn, private_id) and not _id_exists(conn, public_id):
            return private_id, public_id
        fixed_prefix = None
    raise RuntimeError("Could not allocate unique user IDs")


def generate_economic_account_id(
    conn: sqlite3.Connection,
    user_private_id: str,
    first_name: str,
    last_name: str,
    gender: str,
    age_group: str,
    sun_sign: str,
    location_path: str,
) -> str:
    core = extract_id_core(user_private_id)
    if not core:
        core = _id_core(_random_prefix(), first_name, last_name, gender, age_group, sun_sign)
    for _ in range(50_000):
        account_id = f"{core}-{location_path}"
        if not _id_exists(conn, account_id):
            return account_id
        core = _id_core(_random_prefix(), first_name, last_name, gender, age_group, sun_sign)
    raise RuntimeError("Could not allocate economic account ID")


def user_birth_in_india(user_row: sqlite3.Row) -> bool:
    bc = ""
    if "birth_country_id" in user_row.keys() and user_row["birth_country_id"]:
        bc = str(user_row["birth_country_id"]).strip().upper()
    if bc == "IND":
        return True
    bl = str(user_row["birth_location_id"] or "").strip()
    return bool(bl and ("IND/" in bl or "IND." in bl))


def user_present_in_india(user_row: sqlite3.Row) -> bool:
    cc = ""
    if "current_country_id" in user_row.keys() and user_row["current_country_id"]:
        cc = str(user_row["current_country_id"]).strip().upper()
    if cc == "IND":
        return True
    cl = str(user_row["current_location_id"] or "").strip()
    return bool(cl and ("IND/" in cl or "IND." in cl))


def user_situation_type(user_row: sqlite3.Row) -> str:
    b = user_birth_in_india(user_row)
    p = user_present_in_india(user_row)
    if b and not p:
        return "A"
    if not b and p:
        return "B"
    if not b and not p:
        return "C"
    return "D"


def user_show_public_account(user_row: sqlite3.Row) -> bool:
    """All users including global-only (Type C) may use Public Account."""
    return True


def user_show_zone_tab(user_row: sqlite3.Row) -> bool:
    """Zone tab only for users born and living in India (Type D)."""
    return user_birth_in_india(user_row) and user_present_in_india(user_row)


def default_location_mode(user_row: sqlite3.Row) -> str:
    if user_present_in_india(user_row):
        return "present"
    if user_birth_in_india(user_row):
        return "birth"
    return "present"


def can_toggle_location(user_row: sqlite3.Row) -> bool:
    return user_situation_type(user_row) in ("A", "B", "D")


def active_location_id(user_row: sqlite3.Row, mode: str) -> str | None:
    mode = (mode or "present").strip().lower()
    birth = str(user_row["birth_location_id"] or "").strip() or None
    present = str(user_row["current_location_id"] or "").strip() or None
    if mode == "birth":
        return birth or present
    return present or birth


def register_user_accounts(
    conn: sqlite3.Connection,
    *,
    user_private_id: str,
    public_id: str,
    birth_location_id: str | None,
    present_location_id: str | None,
    birth_path: str,
    present_path: str,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if present_location_id:
        conn.execute(
            """
            INSERT INTO user_accounts (
                user_private_id, account_id, location_path, location_id,
                location_type, is_primary, last_used_at
            ) VALUES (?, ?, ?, ?, 'present', 1, ?)
            """,
            (user_private_id, public_id, present_path, present_location_id, now),
        )
    if birth_location_id and birth_location_id != present_location_id:
        birth_account_id = public_id.rsplit("-", 1)[0] + f"-{birth_path}"
        if not _id_exists(conn, birth_account_id):
            conn.execute(
                """
                INSERT INTO user_accounts (
                    user_private_id, account_id, location_path, location_id,
                    location_type, is_primary, last_used_at
                ) VALUES (?, ?, ?, ?, 'birth', 0, ?)
                """,
                (
                    user_private_id,
                    birth_account_id,
                    birth_path,
                    birth_location_id,
                    now,
                ),
            )


def list_user_accounts(
    conn: sqlite3.Connection, user_private_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT account_id, location_path, location_id, location_type,
               is_primary, created_at, last_used_at
        FROM user_accounts
        WHERE user_private_id = ?
        ORDER BY is_primary DESC, datetime(last_used_at) DESC, id ASC
        """,
        (user_private_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_or_create_economic_account(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
    activity_location_id: str,
) -> str:
    """Return account_id for economic activity at activity_location_id."""
    pid = str(user_row["private_id"])
    path = location_path_for_id(activity_location_id)
    existing = conn.execute(
        """
        SELECT account_id FROM user_accounts
        WHERE user_private_id = ? AND location_path = ?
        LIMIT 1
        """,
        (pid, path),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE user_accounts SET last_used_at = CURRENT_TIMESTAMP
            WHERE user_private_id = ? AND account_id = ?
            """,
            (pid, str(existing["account_id"])),
        )
        return str(existing["account_id"])
    account_id = generate_economic_account_id(
        conn,
        pid,
        str(user_row["first_name"]),
        str(user_row["last_name"]),
        str(user_row["gender"]),
        str(user_row["age_group"]),
        str(user_row["sun_sign"]),
        path,
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO user_accounts (
            user_private_id, account_id, location_path, location_id,
            location_type, is_primary, last_used_at
        ) VALUES (?, ?, ?, ?, 'economic', 0, ?)
        """,
        (pid, account_id, path, activity_location_id, now),
    )
    return account_id


def send_email_notification(
    to_email: str,
    subject: str,
    body: str,
    *,
    reply_to: str | None = None,
) -> bool:
    """Send email via SMTP when configured; otherwise log to console."""
    import smtplib
    from email.message import EmailMessage

    import config

    to_email = (to_email or "").strip()
    if not to_email:
        return False

    if not (config.MAIL_SERVER or "").strip():
        logger.info("[EMAIL -> %s] %s\n%s", to_email, subject, body)
        print(f"[EMAIL -> {to_email}] {subject}\n{body}")
        return True

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = (config.MAIL_DEFAULT_SENDER or config.MAIL_USERNAME or "").strip()
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to.strip()
    msg.set_content(body)

    try:
        with smtplib.SMTP(config.MAIL_SERVER, config.MAIL_PORT, timeout=30) as smtp:
            if config.MAIL_USE_TLS:
                smtp.starttls()
            if config.MAIL_USERNAME:
                smtp.login(config.MAIL_USERNAME, config.MAIL_PASSWORD)
            smtp.send_message(msg)
        logger.info("Email sent to %s: %s", to_email, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        raise


def send_sms_notification(phone: str, message: str) -> None:
    logger.info("[SMS -> %s] %s", phone, message)
    print(f"[SMS -> {phone}] {message}")


def notify_user_ids(
    *,
    email: str | None,
    phone: str | None,
    private_id: str,
    public_id: str,
    first_name: str,
) -> None:
    msg = (
        f"Welcome to Qumanity, {first_name}!\n\n"
        f"Private ID (9-digit login): {private_id}\n"
        f"Public ID (Account ID): {public_id}\n\n"
        "Save your Private ID — you need it to log in."
    )
    if email:
            send_email_notification(email, "Your Qumanity IDs", msg)
    if phone:
        send_sms_notification(phone, msg)


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", (phone or "").strip())


def create_otp(
    conn: sqlite3.Connection,
    *,
    email: str | None,
    phone: str | None,
    purpose: str,
) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn.execute(
        """
        INSERT INTO otp_verification (email, phone, otp_code, purpose, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            (email or "").strip().lower() or None,
            _normalize_phone(phone or "") or None,
            code,
            purpose,
            expires,
        ),
    )
    conn.commit()
    if email:
        send_email_notification(
            email.strip(),
            "Qumanity verification code",
            f"Your OTP is {code}. It expires in 10 minutes.",
        )
    if phone:
        send_sms_notification(phone, f"Qumanity OTP: {code} (expires in 10 min)")
    return code


def verify_otp(
    conn: sqlite3.Connection,
    *,
    email: str | None,
    phone: str | None,
    otp_code: str,
    purpose: str,
) -> bool:
    email_n = (email or "").strip().lower() or None
    phone_n = _normalize_phone(phone or "") or None
    row = conn.execute(
        """
        SELECT id FROM otp_verification
        WHERE purpose = ? AND otp_code = ? AND used = 0
          AND datetime(expires_at) > datetime('now')
          AND (
            (? IS NOT NULL AND LOWER(email) = ?)
            OR (? IS NOT NULL AND phone = ?)
          )
        ORDER BY id DESC LIMIT 1
        """,
        (purpose, otp_code.strip(), email_n, email_n, phone_n, phone_n),
    ).fetchone()
    if not row:
        return False
    conn.execute(
        "UPDATE otp_verification SET used = 1 WHERE id = ?",
        (int(row["id"]),),
    )
    conn.commit()
    return True


def mask_private_id(private_id: str) -> str:
    pid = (private_id or "").strip()
    if len(pid) <= 8:
        return pid[:2] + "***"
    return pid[:4] + "***" + pid[-4:]


def validate_cash_recipient_public_id(
    conn: sqlite3.Connection, public_id: str
) -> bool:
    """Cash donations may be collected by an Agent or Admin account."""
    pid = (public_id or "").strip()
    if not pid:
        return False
    row = conn.execute(
        """
        SELECT account_type, is_admin FROM users
        WHERE public_id = ? COLLATE NOCASE
        """,
        (pid,),
    ).fetchone()
    if not row:
        return False
    acct = str(row["account_type"] or "").strip()
    if acct == "Agent" or int(row["is_admin"] or 0) == 1:
        return True
    if acct.upper().startswith("ADMIN") or "ADMIN" in acct.upper():
        return True
    return False
