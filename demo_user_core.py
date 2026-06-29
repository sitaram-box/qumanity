#!/usr/bin/env python3
"""Demo user generation — Yuvak villagers with zodiac distribution."""

from __future__ import annotations

import hashlib
import logging
import random
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterator

import bcrypt

logger = logging.getLogger("qumanity.demo_users")

PATH_PREFIX = "0.राम|"
DEMO_PASSWORD_PLAIN = "DemoPass9!"
ACCOUNT_TYPE = "H_U"
ZODIAC_SIGNS: tuple[str, ...] = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)
ELEMENT_BY_SIGN: dict[str, str] = {
    "Aries": "Fire",
    "Leo": "Fire",
    "Sagittarius": "Fire",
    "Taurus": "Earth",
    "Virgo": "Earth",
    "Capricorn": "Earth",
    "Gemini": "Air",
    "Libra": "Air",
    "Aquarius": "Air",
    "Cancer": "Water",
    "Scorpio": "Water",
    "Pisces": "Water",
}

# Approximate tropical sign windows (month, start_day, end_month, end_day)
_SIGN_WINDOWS: list[tuple[str, int, int, int, int]] = [
    ("Capricorn", 12, 22, 1, 19),
    ("Aquarius", 1, 20, 2, 18),
    ("Pisces", 2, 19, 3, 20),
    ("Aries", 3, 21, 4, 19),
    ("Taurus", 4, 20, 5, 20),
    ("Gemini", 5, 21, 6, 20),
    ("Cancer", 6, 21, 7, 22),
    ("Leo", 7, 23, 8, 22),
    ("Virgo", 8, 23, 9, 22),
    ("Libra", 9, 23, 10, 22),
    ("Scorpio", 10, 23, 11, 21),
    ("Sagittarius", 11, 22, 12, 21),
]

STATE_NAME_POOLS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "DL": (("Arjun", "Rahul", "Vikram", "Karan", "Dev"), ("Priya", "Ananya", "Kavya", "Meera", "Sneha")),
    "HR": (("Rajesh", "Suresh", "Amit", "Rohit", "Manoj"), ("Sunita", "Pooja", "Neha", "Ritu", "Anjali")),
    "UP": (("Ramesh", "Surendra", "Vijay", "Ashok", "Dinesh"), ("Sita", "Gita", "Radha", "Lata", "Usha")),
    "MH": (("Sanjay", "Prakash", "Nitin", "Ganesh", "Ravi"), ("Sneha", "Swati", "Pallavi", "Aditi", "Shruti")),
    "TN": (("Murugan", "Karthik", "Arun", "Selvam", "Prabhu"), ("Lakshmi", "Meenakshi", "Kavitha", "Divya", "Priya")),
    "KA": (("Raghav", "Shankar", "Venkat", "Harish", "Naveen"), ("Shweta", "Anitha", "Deepa", "Lakshmi", "Suma")),
    "WB": (("Amit", "Subhash", "Pradeep", "Anil", "Bikash"), ("Maya", "Rina", "Soma", "Tanvi", "Priyanka")),
    "RJ": (("Mahesh", "Lalit", "Hemant", "Sunil", "Raj"), ("Kiran", "Geeta", "Manju", "Rekha", "Poonam")),
    "GJ": (("Jayesh", "Harsh", "Nilesh", "Parth", "Dhruv"), ("Nisha", "Heena", "Jyoti", "Bhavna", "Komal")),
    "PB": (("Harpreet", "Gurpreet", "Manpreet", "Rahul", "Aman"), ("Simran", "Navneet", "Priyanka", "Kiran", "Neetu")),
}

DEFAULT_MALE = ("Arjun", "Vikram", "Rohan", "Karan", "Rahul", "Amit", "Sanjay", "Rajesh")
DEFAULT_FEMALE = ("Priya", "Ananya", "Kavya", "Meera", "Sneha", "Pooja", "Neha", "Divya")
DEFAULT_LAST = (
    "Sharma", "Verma", "Patel", "Singh", "Kumar", "Reddy", "Iyer", "Gupta", "Joshi", "Kapoor",
)

DEMO_LOG_DDL = """
CREATE TABLE IF NOT EXISTS demo_automation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def log_demo_action(conn: sqlite3.Connection, action: str, details: str = "") -> None:
    conn.execute(
        "INSERT INTO demo_automation_log (action, details) VALUES (?, ?)",
        (action, details[:4000]),
    )


def migrate_demo_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DEMO_LOG_DDL)
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(users)")}
    for col, decl in (
        ("is_demo", "INTEGER NOT NULL DEFAULT 0"),
        ("demo_village_id", "TEXT"),
        ("karma_points", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if col in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def raw_path(full_id: str) -> str:
    fid = (full_id or "").strip()
    if fid.startswith(PATH_PREFIX):
        return fid[len(PATH_PREFIX):]
    return fid


def state_code_from_village(village_id: str) -> str:
    raw = raw_path(village_id)
    parts = raw.split("/")
    if len(parts) >= 3:
        return parts[2].split(".")[0].upper()
    return "DL"


def compute_age(dob: date, today: date | None = None) -> int:
    today = today or date.today()
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return max(0, years)


def moon_sign_simplified(d: date) -> str:
    doy = int(d.strftime("%j"))
    return ZODIAC_SIGNS[(doy - 1) % 12]


def _dob_in_sign_window(sign: str, y: int) -> date | None:
    for s, sm, sd, em, ed in _SIGN_WINDOWS:
        if s != sign:
            continue
        if sm <= em:
            try:
                return date(y, sm, min(sd, 28))
            except ValueError:
                return date(y, sm, 15)
        try:
            return date(y, sm, min(sd, 28))
        except ValueError:
            return date(y, 12, 15)
    return None


def random_dob_for_sign(sign: str, today: date | None = None) -> date:
    """DOB yielding Yuvak (25–49) and the requested sun sign."""
    today = today or date.today()
    for _ in range(2000):
        age = random.randint(25, 49)
        year = today.year - age
        dob = _dob_in_sign_window(sign, year)
        if not dob:
            continue
        if compute_age(dob, today) < 25 or compute_age(dob, today) > 49:
            continue
        return dob
    return today - timedelta(days=365 * 30)


def _demo_private_id(village_key: int, seq: int) -> str:
    n = (village_key * 10000 + seq) % 900_000_000 + 100_000_000
    return f"HU-{n:09d}"


def _password_hash() -> str:
    return bcrypt.hashpw(DEMO_PASSWORD_PLAIN.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _random_created_at() -> str:
    days_back = random.randint(1, 730)
    dt = datetime.now(timezone.utc) - timedelta(days=days_back)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _karma_levels_from_points(points: int) -> tuple[int, int, int, int]:
    mentor = min(5, points // 100)
    remainder = points - mentor * 100
    manager = min(5, remainder // 50)
    remainder -= manager * 50
    leader = min(5, remainder // 25)
    remainder -= leader * 25
    agent = min(5, remainder // 10)
    return mentor, manager, leader, agent


DELHI_VILLAGE_PATH_PREFIX = "IND/CS/DL."
DELHI_STATE_NAMES = frozenset({"delhi", "delhi state"})


def resolve_state_village_prefix(
    conn: sqlite3.Connection, state_name: str | None, state_id: str | None
) -> str | None:
    """Return village id LIKE prefix (with PATH_PREFIX) for a state filter."""
    if state_id:
        sid = state_id.strip()
    elif state_name:
        row = conn.execute(
            "SELECT id FROM state WHERE name = ? COLLATE NOCASE LIMIT 1",
            (state_name.strip(),),
        ).fetchone()
        if not row:
            return None
        sid = str(row["id"] if hasattr(row, "keys") else row[0])
    else:
        return None
    raw = raw_path(sid)
    # State ids: IND/CS.DL → villages: IND/CS/DL.
    if "/" in raw and "." in raw.split("/", 1)[1]:
        head, tail = raw.split("/", 1)
        zone, st = tail.split(".", 1)
        village_raw_prefix = f"{head}/{zone}/{st}."
    elif raw.upper().startswith("IND/CS/DL") or raw.upper().endswith("DL"):
        village_raw_prefix = DELHI_VILLAGE_PATH_PREFIX
    else:
        village_raw_prefix = raw + "."
    return PATH_PREFIX + village_raw_prefix


def iter_village_ids(
    conn: sqlite3.Connection,
    *,
    max_villages: int | None = None,
    village_id: str | None = None,
    state_name: str | None = None,
    state_id: str | None = None,
) -> Iterator[tuple[int, str]]:
    if village_id:
        row = conn.execute(
            "SELECT id FROM village WHERE id = ?", (village_id.strip(),)
        ).fetchone()
        if row:
            vid = row["id"] if hasattr(row, "keys") else row[0]
            yield 0, str(vid)
        return

    prefix: str | None = None
    if state_name or state_id:
        prefix = resolve_state_village_prefix(conn, state_name, state_id)
        if not prefix:
            return

    limit_sql = f" LIMIT {int(max_villages)}" if max_villages else ""
    if prefix:
        cur = conn.execute(
            f"SELECT id FROM village WHERE id LIKE ? ORDER BY id{limit_sql}",
            (prefix + "%",),
        )
    else:
        cur = conn.execute(f"SELECT id FROM village ORDER BY id{limit_sql}")
    for idx, row in enumerate(cur):
        vid = row["id"] if hasattr(row, "keys") else row[0]
        yield idx, str(vid)


def count_villages_in_state(
    conn: sqlite3.Connection, state_name: str = "Delhi"
) -> int:
    prefix = resolve_state_village_prefix(conn, state_name, None)
    if not prefix:
        return 0
    row = conn.execute(
        "SELECT COUNT(*) FROM village WHERE id LIKE ?", (prefix + "%",)
    ).fetchone()
    return int(row[0] or 0)


def count_villages(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM village").fetchone()[0])


def demo_users_in_village(conn: sqlite3.Connection, village_id: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM users WHERE is_demo = 1 AND demo_village_id = ?",
        (village_id,),
    ).fetchone()
    return int(row["n"] or 0)


def generate_village_demo_users(
    conn: sqlite3.Connection,
    village_id: str,
    village_key: int,
    *,
    users_per_village: int = 1000,
    skip_if_exists: bool = True,
    activity_fraction: float = 0.15,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, int]:
    """Create demo users for one village with even zodiac / gender split."""
    migrate_demo_schema(conn)
    if skip_if_exists and demo_users_in_village(conn, village_id) >= users_per_village:
        return {"skipped": 1, "inserted": 0}

    state_code = state_code_from_village(village_id)
    male_names, female_names = STATE_NAME_POOLS.get(state_code, (DEFAULT_MALE, DEFAULT_FEMALE))
    loc_path = raw_path(village_id)
    today = date.today()
    pw = _password_hash()
    per_sign = users_per_village // 12
    remainder = users_per_village - per_sign * 12
    inserted = 0
    seq = 0

    for sign_idx, sign in enumerate(ZODIAC_SIGNS):
        count = per_sign + (1 if sign_idx < remainder else 0)
        males = count // 2
        females = count - males
        genders: list[str] = ["Male"] * males + ["Female"] * females
        random.shuffle(genders)
        element = ELEMENT_BY_SIGN[sign]

        for gender in genders:
            seq += 1
            private_id = _demo_private_id(village_key, seq)
            exists = conn.execute(
                "SELECT 1 FROM users WHERE private_id = ?", (private_id,)
            ).fetchone()
            if exists:
                continue
            first = random.choice(male_names if gender == "Male" else female_names)
            last = random.choice(DEFAULT_LAST)
            dob = random_dob_for_sign(sign, today)
            age = compute_age(dob, today)
            karma_pts = random.randint(0, 500)
            m, mg, l, a = _karma_levels_from_points(karma_pts)
            public_id = f"DEMO-{sign[:3].upper()}-{gender[0]}-{village_key:05d}-{seq:04d}-{loc_path[-12:]}"

            conn.execute(
                """
                INSERT INTO users (
                    private_id, public_id, first_name, last_name, gender,
                    date_of_birth, birth_time, age, age_group,
                    sun_sign, moon_sign, element,
                    birth_location_id, current_location_id,
                    birth_continent_id, birth_country_id,
                    current_continent_id, current_country_id,
                    country, email, password_hash, created_at,
                    account_type, mentor_level, manager_level, leader_level, agent_level,
                    is_admin, is_active, is_demo, demo_village_id, karma_points
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    private_id,
                    public_id,
                    first,
                    last,
                    gender,
                    dob.isoformat(),
                    "10:30",
                    age,
                    "Yuvak",
                    sign,
                    moon_sign_simplified(dob),
                    element,
                    village_id,
                    village_id,
                    "AS",
                    "IND",
                    "AS",
                    "IND",
                    "India",
                    None,
                    pw,
                    _random_created_at(),
                    ACCOUNT_TYPE,
                    m,
                    mg,
                    l,
                    a,
                    0,
                    1,
                    1,
                    village_id,
                    karma_pts,
                ),
            )
            inserted += 1

    if inserted and activity_fraction > 0:
        add_demo_activities(conn, village_id, fraction=activity_fraction)

    log_demo_action(
        conn,
        "generate_village_users",
        f"village={village_id} inserted={inserted}",
    )
    conn.commit()
    if progress_cb:
        progress_cb(f"Village {village_id}: {inserted} users")
    return {"inserted": inserted, "skipped": 0}


def add_demo_activities(
    conn: sqlite3.Connection,
    village_id: str,
    fraction: float = 0.15,
) -> dict[str, int]:
    """Posts, votes, and wallet credits for a fraction of demo users."""
    import qoin_core
    import social_core

    qoin_core.migrate_qoin_economy_tables(conn)
    social_core.ensure_wallet_and_vote_tables(conn)

    users = conn.execute(
        """
        SELECT private_id FROM users
        WHERE is_demo = 1 AND demo_village_id = ?
        ORDER BY private_id
        """,
        (village_id,),
    ).fetchall()
    if not users:
        return {"posts": 0, "votes": 0, "wallets": 0}

    sample_n = max(1, int(len(users) * fraction))
    sample = random.sample(users, min(sample_n, len(users)))
    posts = 0
    votes = 0
    wallets = 0
    post_ids: list[int] = []

    for row in sample[:max(1, sample_n // 3)]:
        pid = str(row["private_id"])
        cur = conn.execute(
            """
            INSERT INTO posts (
                user_private_id, location_id, content, current_level, status, total_score,
                origin_village_id
            ) VALUES (?, ?, ?, 'village', 'live', 0, ?)
            """,
            (
                pid,
                village_id,
                f"Demo post from {pid} — community update for our village.",
                village_id,
            ),
        )
        post_ids.append(int(cur.lastrowid))
        posts += 1

    voters = sample[sample_n // 3: sample_n // 3 + sample_n // 3]
    for row in voters:
        if not post_ids:
            break
        pid = str(row["private_id"])
        post_id = random.choice(post_ids)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO post_votes (post_id, voter_private_id, vote_value)
                VALUES (?, ?, ?)
                """,
                (post_id, pid, random.choice([-1, 1])),
            )
            votes += 1
        except sqlite3.OperationalError:
            pass

    for row in sample[2 * sample_n // 3:]:
        pid = str(row["private_id"])
        qoin_core.ensure_wallet(conn, "user", pid)
        amount = random.randint(0, 1000)
        if amount > 0:
            denoms = qoin_core.min_qoins_for_amount(amount)
            qoin_core.credit_wallet_denoms(
                conn,
                "user",
                pid,
                denoms,
                transaction_ref="demo_seed",
                amount_rupees=amount,
            )
            wallets += 1

    conn.commit()
    return {"posts": posts, "votes": votes, "wallets": wallets}


def generate_demo_users_batch(
    conn: sqlite3.Connection,
    *,
    users_per_village: int = 1000,
    max_villages: int | None = 5,
    village_id: str | None = None,
    state_name: str | None = None,
    state_id: str | None = None,
    activity_fraction: float = 0.15,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    migrate_demo_schema(conn)
    totals = {"villages": 0, "inserted": 0, "skipped_villages": 0}
    for village_key, vid in iter_village_ids(
        conn,
        max_villages=max_villages,
        village_id=village_id,
        state_name=state_name,
        state_id=state_id,
    ):
        totals["villages"] += 1
        result = generate_village_demo_users(
            conn,
            vid,
            village_key,
            users_per_village=users_per_village,
            activity_fraction=activity_fraction,
            progress_cb=progress_cb,
        )
        totals["inserted"] += int(result.get("inserted", 0))
        if result.get("skipped"):
            totals["skipped_villages"] += 1
    log_demo_action(conn, "generate_batch", str(totals))
    conn.commit()
    return totals


# Users flagged is_demo=1, excluding admins (HU-014918240 and any is_admin=1).
_DEMO_USER_WHERE = "is_demo = 1 AND COALESCE(is_admin, 0) = 0"
_DEMO_PID_SUB = f"SELECT private_id FROM users WHERE {_DEMO_USER_WHERE}"
_DEMO_ID_SUB = f"SELECT id FROM users WHERE {_DEMO_USER_WHERE}"

# (table, column) — batch delete via demo private_id subquery.
_DEMO_USER_REF_DELETES: tuple[tuple[str, str], ...] = (
    ("connection_requests", "from_user_private_id"),
    ("connection_requests", "to_user_private_id"),
    ("messages", "sender_id"),
    ("messages", "recipient_id"),
    ("post_votes", "voter_private_id"),
    ("posts", "user_private_id"),
    ("family_members", "user_private_id"),
    ("family_members", "member_private_id"),
    ("family_profile", "user_private_id"),
    ("family_removal_requests", "user_private_id"),
    ("election_votes", "voter_private_id"),
    ("election_votes", "candidate_private_id"),
    ("election_candidates", "candidate_private_id"),
    ("pending_transactions", "from_user_id"),
    ("pending_transactions", "to_user_id"),
    ("karma_transactions", "user_private_id"),
    ("qoin_transactions", "user_private_id"),
    ("qoin_transactions", "recipient_id"),
    ("donations", "user_private_id"),
    ("donation_transactions", "user_private_id"),
    ("cash_donations", "donor_private_id"),
    ("registration_donations", "user_private_id"),
    ("registration_donations", "volunteer_private_id"),
    ("user_accounts", "user_private_id"),
    ("pending_referrals", "referrer_private_id"),
    ("pending_referrals", "referred_private_id"),
    ("referrals", "referrer_private_id"),
    ("referrals", "referred_private_id"),
    ("user_education", "user_private_id"),
    ("user_work", "user_private_id"),
    ("user_family_setup", "user_private_id"),
    ("user_birth_planets", "user_private_id"),
    ("link_requests", "from_user_private_id"),
    ("link_requests", "to_user_private_id"),
    ("category_history", "user_private_id"),
    ("category_appeals", "user_private_id"),
    ("varna_raw_scores", "user_private_id"),
    ("akashic_records", "user_private_id"),
    ("edit_requests", "user_private_id"),
    ("karma_claims", "user_private_id"),
    ("share_logs", "user_private_id"),
    ("weekly_statements", "user_private_id"),
    ("job_seeker_profiles", "user_private_id"),
    ("job_applications", "applicant_private_id"),
    ("employment_requests", "applicant_private_id"),
    ("employment_contracts", "employer_private_id"),
    ("employment_contracts", "employee_private_id"),
    ("employment_ratings", "rater_private_id"),
    ("employment_ratings", "ratee_private_id"),
    ("delivery_agents", "user_private_id"),
    ("volunteers", "volunteer_private_id"),
    ("referral_agents", "agent_private_id"),
    ("donation_distributions", "new_user_private_id"),
    ("donation_distributions", "referrer_private_id"),
    ("donation_distributions", "agent_private_id"),
    ("marketplace_cart", "user_private_id"),
    ("marketplace_listings", "seller_private_id"),
    ("marketplace_orders", "buyer_private_id"),
    ("marketplace_orders", "seller_private_id"),
    ("marketplace_orders", "delivery_agent_private_id"),
    ("marketplace_reviews", "reviewer_private_id"),
    ("job_postings", "employer_private_id"),
    ("businesses", "owner_private_id"),
    ("deceased_users", "original_private_id"),
)


def _safe_delete_demo_refs(
    conn: sqlite3.Connection, table: str, column: str
) -> int:
    try:
        cur = conn.execute(
            f"DELETE FROM {table} WHERE {column} IN ({_DEMO_PID_SUB})"
        )
        return int(cur.rowcount or 0)
    except sqlite3.OperationalError:
        return 0


def _safe_execute(conn: sqlite3.Connection, sql: str) -> int:
    try:
        cur = conn.execute(sql)
        return int(cur.rowcount or 0)
    except sqlite3.OperationalError:
        return 0


def count_demo_users(conn: sqlite3.Connection) -> int:
    migrate_demo_schema(conn)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM users WHERE {_DEMO_USER_WHERE}"
    ).fetchone()
    if not row:
        return 0
    return int(row["n"] if hasattr(row, "keys") else row[0])


def delete_all_demo_users(conn: sqlite3.Connection) -> dict[str, Any]:
    """Remove all demo users and associated data; preserve admin accounts."""
    migrate_demo_schema(conn)
    demo_count = count_demo_users(conn)
    if demo_count == 0:
        return {"deleted": 0, "demo_users_found": 0, "rows_deleted": {}}

    demo_villages = [
        str(r[0] if isinstance(r, tuple) else r["demo_village_id"])
        for r in conn.execute(
            f"SELECT DISTINCT demo_village_id FROM users WHERE {_DEMO_USER_WHERE} "
            "AND demo_village_id IS NOT NULL"
        )
    ]

    rows_deleted: dict[str, int] = {}

    rows_deleted["family_relationships"] = _safe_execute(
        conn,
        f"""
        DELETE FROM family_relationships
         WHERE source_id IN (
                 SELECT id FROM family_members
                  WHERE user_private_id IN ({_DEMO_PID_SUB})
                    OR member_private_id IN ({_DEMO_PID_SUB})
               )
            OR target_id IN (
                 SELECT id FROM family_members
                  WHERE user_private_id IN ({_DEMO_PID_SUB})
                    OR member_private_id IN ({_DEMO_PID_SUB})
               )
        """,
    )

    for table, column in _DEMO_USER_REF_DELETES:
        key = f"{table}.{column}"
        n = _safe_delete_demo_refs(conn, table, column)
        if n:
            rows_deleted[key] = n

    rows_deleted["notifications"] = _safe_execute(
        conn,
        f"DELETE FROM notifications WHERE user_id IN ({_DEMO_ID_SUB})",
    )
    rows_deleted["qsi_user_name_preferences"] = _safe_execute(
        conn,
        f"DELETE FROM qsi_user_name_preferences WHERE user_id IN ({_DEMO_ID_SUB})",
    )
    rows_deleted["qsi_user_spins"] = _safe_execute(
        conn,
        f"DELETE FROM qsi_user_spins WHERE user_id IN ({_DEMO_ID_SUB})",
    )

    rows_deleted["wallets"] = _safe_execute(
        conn,
        f"""
        DELETE FROM wallets
         WHERE owner_type = 'user' AND owner_id IN ({_DEMO_PID_SUB})
        """,
    )

    rows_deleted["leadership_council"] = _safe_execute(
        conn,
        f"""
        DELETE FROM leadership_council
         WHERE current_holder_private_id IN ({_DEMO_PID_SUB})
        """,
    )
    rows_deleted["location_council"] = _safe_execute(
        conn,
        f"""
        DELETE FROM location_council
         WHERE male_head_private_id IN ({_DEMO_PID_SUB})
            OR female_head_private_id IN ({_DEMO_PID_SUB})
        """,
    )
    rows_deleted["village_council"] = _safe_execute(
        conn,
        f"""
        DELETE FROM village_council
         WHERE male_head_private_id IN ({_DEMO_PID_SUB})
            OR female_head_private_id IN ({_DEMO_PID_SUB})
        """,
    )

    if demo_villages:
        placeholders = ",".join("?" for _ in demo_villages)
        try:
            cur = conn.execute(
                f"DELETE FROM election_cycles WHERE village_id IN ({placeholders})",
                demo_villages,
            )
            rows_deleted["election_cycles"] = int(cur.rowcount or 0)
        except sqlite3.OperationalError:
            pass

    rows_deleted["election_cycles_winners"] = _safe_execute(
        conn,
        f"""
        DELETE FROM election_cycles
         WHERE male_winner_private_id IN ({_DEMO_PID_SUB})
            OR female_winner_private_id IN ({_DEMO_PID_SUB})
        """,
    )

    cur = conn.execute(f"DELETE FROM users WHERE {_DEMO_USER_WHERE}")
    deleted = int(cur.rowcount or 0)

    log_demo_action(conn, "delete_demo_users", f"deleted={deleted}")
    conn.commit()
    return {
        "deleted": deleted,
        "demo_users_found": demo_count,
        "rows_deleted": rows_deleted,
    }
