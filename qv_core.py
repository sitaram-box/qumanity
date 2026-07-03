#!/usr/bin/env python3
"""Quadratic Voting (QV) referendum system — credits, referendums, escalation."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import election_automation
from db_path import execute_with_retry

LEVELS: tuple[str, ...] = (
    "village",
    "tehsil",
    "district",
    "state",
    "country",
    "earth",
)

LEVEL_ALIASES = {"nation": "country"}

PARENT_LEVEL: dict[str, str] = {
    "village": "tehsil",
    "tehsil": "district",
    "district": "state",
    "state": "country",
    "country": "earth",
}

ESCALATION_THRESHOLDS: dict[str, int] = {
    "village": 500,
    "tehsil": 1000,
    "district": 2000,
    "state": 5000,
    "country": 10000,
    "earth": 50000,
}

REVIEW_SLOTS: tuple[str, ...] = ("mentor", "nayak", "nayika", "manager")

CREDIT_CAPS: dict[str, int] = {
    "karma": 100,
    "service": 50,
    "council": 50,
    "recognition": 30,
}

CARRYOVER_CAP = 50
VOTING_DAYS = 7
WELCOME_BONUS = 50

QV_DDL = """
CREATE TABLE IF NOT EXISTS qv_referendums (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    location_id TEXT NOT NULL,
    level TEXT NOT NULL CHECK(level IN ('village','tehsil','district','state','country','earth')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','active','voting','resolved','closed','escalated')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    voting_start TIMESTAMP,
    voting_end TIMESTAMP,
    total_weighted_support INTEGER NOT NULL DEFAULT 0,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    escalated_from INTEGER REFERENCES qv_referendums(id)
);
CREATE INDEX IF NOT EXISTS idx_qv_ref_level_loc ON qv_referendums(level, location_id);
CREATE INDEX IF NOT EXISTS idx_qv_ref_status ON qv_referendums(status);

CREATE TABLE IF NOT EXISTS qv_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referendum_id INTEGER NOT NULL REFERENCES qv_referendums(id) ON DELETE CASCADE,
    voter_id TEXT NOT NULL,
    votes INTEGER NOT NULL CHECK(votes BETWEEN 1 AND 10),
    credits_used INTEGER NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(referendum_id, voter_id)
);
CREATE INDEX IF NOT EXISTS idx_qv_votes_ref ON qv_votes(referendum_id);

CREATE TABLE IF NOT EXISTS qv_credit_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL UNIQUE,
    current_credits INTEGER NOT NULL DEFAULT 0,
    lifetime_earned INTEGER NOT NULL DEFAULT 0,
    lifetime_spent INTEGER NOT NULL DEFAULT 0,
    last_reset_month TEXT
);

CREATE TABLE IF NOT EXISTS qv_credit_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN (
        'karma','service','council','recognition','bonus','voting','carryover','manual'
    )),
    amount INTEGER NOT NULL,
    description TEXT,
    referendum_id INTEGER REFERENCES qv_referendums(id),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_qv_credit_tx_user ON qv_credit_transactions(user_id, timestamp);

CREATE TABLE IF NOT EXISTS qv_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    referendum_id INTEGER NOT NULL UNIQUE REFERENCES qv_referendums(id),
    weighted_support INTEGER NOT NULL,
    rank INTEGER,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','approved','rejected','implemented')),
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def migrate_qv_schema(conn: sqlite3.Connection) -> None:
    """Create QV tables if they do not exist."""
    conn.executescript(QV_DDL)


def normalize_level(level: str) -> str:
    """Normalize level name (nation → country)."""
    lt = (level or "").strip().lower()
    return LEVEL_ALIASES.get(lt, lt)


def quadratic_cost(votes: int) -> int:
    """QV cost = votes squared."""
    return int(votes) * int(votes)


def strip_html(text: str) -> str:
    """Remove HTML tags from user input."""
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def is_human_user(user_row: sqlite3.Row | None) -> bool:
    """True for H_U and upgrade types; False for D_U demo accounts."""
    if user_row is None:
        return False
    at = str(user_row["account_type"] or "H_U").strip().upper()
    if at.startswith("D_U"):
        return False
    return True


def location_chain_for_referendum(
    conn: sqlite3.Connection, level: str, location_id: str
) -> list[tuple[str, str]]:
    """Return (level, location_id) pairs from referendum scope up to earth."""
    lt = normalize_level(level)
    loc = (location_id or "").strip()
    if not loc:
        return []
    if lt == "village":
        h = election_automation.hierarchy_for_village(loc)
        order = ("village", "tehsil", "district", "state", "country", "earth")
        out: list[tuple[str, str]] = []
        for key in order:
            lid = str(h.get(key) or "").strip()
            if lid:
                out.append((key, lid))
        if ("earth", "0.राम|0") not in out:
            out.append(("earth", "0.राम|0"))
        return out
    chain: list[tuple[str, str]] = [(lt, loc)]
    cur = lt
    while cur in PARENT_LEVEL:
        parent = PARENT_LEVEL[cur]
        parent_loc = _parent_location_id(conn, cur, loc)
        if parent_loc:
            chain.append((parent, parent_loc))
            loc = parent_loc
        cur = parent
    return chain


def _parent_location_id(
    conn: sqlite3.Connection | None, level: str, location_id: str
) -> str:
    """Resolve parent location id from village hierarchy when possible."""
    if level == "village":
        h = election_automation.hierarchy_for_village(location_id)
        return str(h.get("tehsil") or "")
    if level == "tehsil":
        h = election_automation.hierarchy_for_village(
            _village_under_tehsil(conn, location_id)
        )
        return str(h.get("district") or "")
    if level == "district":
        h = election_automation.hierarchy_for_village(
            _village_under_district(conn, location_id)
        )
        return str(h.get("state") or "")
    if level == "state":
        return str(election_automation.hierarchy_for_village(
            _village_under_state(conn, location_id)
        ).get("country") or "0.राम|IND")
    if level == "country":
        return "0.राम|0"
    return ""


def _village_under_tehsil(conn: sqlite3.Connection | None, tehsil_id: str) -> str:
    if conn is None:
        return ""
    row = conn.execute(
        """
        SELECT current_location_id FROM users
        WHERE current_location_id LIKE ? AND TRIM(current_location_id) != ''
        LIMIT 1
        """,
        (tehsil_id + "%",),
    ).fetchone()
    return str(row["current_location_id"]) if row else ""


def _village_under_district(conn: sqlite3.Connection | None, district_id: str) -> str:
    if conn is None:
        return ""
    row = conn.execute(
        """
        SELECT current_location_id FROM users
        WHERE current_location_id LIKE ? LIMIT 1
        """,
        (district_id + "%",),
    ).fetchone()
    return str(row["current_location_id"]) if row else ""


def _village_under_state(conn: sqlite3.Connection | None, state_id: str) -> str:
    if conn is None:
        return ""
    row = conn.execute(
        """
        SELECT current_location_id FROM users
        WHERE current_location_id LIKE ? LIMIT 1
        """,
        (state_id + "%",),
    ).fetchone()
    return str(row["current_location_id"]) if row else ""


def resolve_location_for_level(
    conn: sqlite3.Connection, user_row: sqlite3.Row, level: str
) -> str | None:
    """Map requested level to location_id from user's present geography."""
    lt = normalize_level(level)
    if lt not in LEVELS:
        return None
    try:
        vid = str(user_row["current_location_id"] or "").strip()
    except (KeyError, TypeError):
        vid = ""
    if not vid and lt != "earth":
        return None
    if lt == "earth":
        return "0.राम|0"
    h = election_automation.hierarchy_for_village(vid) if vid else {}
    mapping = {
        "village": vid,
        "tehsil": h.get("tehsil"),
        "district": h.get("district"),
        "state": h.get("state"),
        "country": h.get("country") or "0.राम|IND",
    }
    loc = str(mapping.get(lt) or "").strip()
    return loc or None


def user_can_propose_at_level(
    conn: sqlite3.Connection, user_row: sqlite3.Row, level: str, location_id: str
) -> bool:
    """User may propose at their level or any parent level in hierarchy."""
    lt = normalize_level(level)
    resolved = resolve_location_for_level(conn, user_row, lt)
    if not resolved or resolved != location_id.strip():
        return False
    if lt == "earth":
        return True
    try:
        vid = str(user_row["current_location_id"] or "").strip()
    except (KeyError, TypeError):
        vid = ""
    if not vid:
        return False
    chain = location_chain_for_referendum(conn, "village", vid)
    allowed = {lid for _, lid in chain}
    return location_id.strip() in allowed


# ── Credit system ──────────────────────────────────────────────────────────


def get_or_create_credit_balance(conn: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    """Fetch or initialize a user's QV credit balance."""
    migrate_qv_schema(conn)
    uid = (user_id or "").strip()
    row = conn.execute(
        "SELECT * FROM qv_credit_balances WHERE user_id = ?", (uid,)
    ).fetchone()
    if row:
        return _row_to_dict(row) or {}
    now_month = datetime.now(timezone.utc).strftime("%Y-%m")
    execute_with_retry(
        conn,
        """
        INSERT INTO qv_credit_balances (user_id, current_credits, last_reset_month)
        VALUES (?, 0, ?)
        """,
        (uid, now_month),
    )
    row = conn.execute(
        "SELECT * FROM qv_credit_balances WHERE user_id = ?", (uid,)
    ).fetchone()
    return _row_to_dict(row) or {}


def get_credit_balance(conn: sqlite3.Connection, user_id: str) -> int:
    """Return current available QV credits."""
    bal = get_or_create_credit_balance(conn, user_id)
    return int(bal.get("current_credits") or 0)


def add_credits(
    conn: sqlite3.Connection,
    user_id: str,
    amount: int,
    source: str,
    description: str = "",
    referendum_id: int | None = None,
) -> bool:
    """Atomically add credits and log transaction."""
    if amount <= 0:
        return False
    migrate_qv_schema(conn)
    get_or_create_credit_balance(conn, user_id)
    execute_with_retry(
        conn,
        """
        UPDATE qv_credit_balances
        SET current_credits = current_credits + ?,
            lifetime_earned = lifetime_earned + ?
        WHERE user_id = ?
        """,
        (amount, amount, user_id),
    )
    execute_with_retry(
        conn,
        """
        INSERT INTO qv_credit_transactions (user_id, source, amount, description, referendum_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, source, amount, description, referendum_id),
    )
    return True


def deduct_credits(
    conn: sqlite3.Connection,
    user_id: str,
    amount: int,
    referendum_id: int,
    votes: int,
) -> bool:
    """Atomically deduct credits if sufficient balance exists."""
    if amount <= 0:
        return False
    migrate_qv_schema(conn)
    bal = get_credit_balance(conn, user_id)
    if bal < amount:
        return False
    execute_with_retry(
        conn,
        """
        UPDATE qv_credit_balances
        SET current_credits = current_credits - ?,
            lifetime_spent = lifetime_spent + ?
        WHERE user_id = ? AND current_credits >= ?
        """,
        (amount, amount, user_id, amount),
    )
    changed = conn.execute("SELECT changes()").fetchone()[0]
    if not changed:
        return False
    execute_with_retry(
        conn,
        """
        INSERT INTO qv_credit_transactions (user_id, source, amount, description, referendum_id)
        VALUES (?, 'voting', ?, ?, ?)
        """,
        (user_id, -amount, f"QV vote: {votes} votes", referendum_id),
    )
    return True


def get_credit_history(
    conn: sqlite3.Connection, user_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Return transaction history ordered by timestamp DESC."""
    migrate_qv_schema(conn)
    rows = conn.execute(
        """
        SELECT * FROM qv_credit_transactions
        WHERE user_id = ?
        ORDER BY datetime(timestamp) DESC, id DESC
        LIMIT ?
        """,
        (user_id, int(limit)),
    ).fetchall()
    return [_row_to_dict(r) for r in rows if r]


def calculate_monthly_credits(
    conn: sqlite3.Connection, user_id: str, year_month: str
) -> dict[str, int]:
    """
    Calculate credits earned for a given month from karma, service, council, recognition.
    """
    migrate_qv_schema(conn)
    y, m = year_month.split("-")
    start = f"{y}-{m}-01"
    if int(m) == 12:
        end = f"{int(y)+1}-01-01"
    else:
        end = f"{y}-{int(m)+1:02d}-01"

    karma_row = conn.execute(
        """
        SELECT COALESCE(SUM(amount_rupees), 0) AS s FROM karma_transactions
        WHERE user_private_id = ? AND verified = 1
          AND datetime(created_at) >= datetime(?)
          AND datetime(created_at) < datetime(?)
        """,
        (user_id, start, end),
    ).fetchone()
    karma = min(int(karma_row["s"] or 0), CREDIT_CAPS["karma"])

    service = 0  # No verified service-hour ledger yet

    council_row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM leadership_council
        WHERE current_holder_private_id = ? AND status = 'filled'
          AND datetime(COALESCE(filled_at, '1970-01-01')) >= datetime(?)
          AND datetime(COALESCE(filled_at, '1970-01-01')) < datetime(?)
        """,
        (user_id, start, end),
    ).fetchone()
    council = min(int(council_row["c"] or 0) * 10, CREDIT_CAPS["council"])

    rec_row = conn.execute(
        """
        SELECT COUNT(*) AS c FROM post_votes pv
        JOIN posts p ON p.id = pv.post_id
        WHERE p.user_private_id = ? AND pv.vote_value = 1
          AND datetime(pv.voted_at) >= datetime(?)
          AND datetime(pv.voted_at) < datetime(?)
        """,
        (user_id, start, end),
    ).fetchone()
    recognition = min(int(rec_row["c"] or 0) * 5, CREDIT_CAPS["recognition"])

    total = karma + service + council + recognition
    return {
        "karma": karma,
        "service": service,
        "council": council,
        "recognition": recognition,
        "total": total,
    }


def auto_convert_karma_to_credits(
    conn: sqlite3.Connection, user_id: str, year_month: str
) -> dict[str, Any]:
    """
    Monthly reset: earn credits from previous month, apply carryover cap.
    """
    migrate_qv_schema(conn)
    bal = get_or_create_credit_balance(conn, user_id)
    carry = min(int(bal.get("current_credits") or 0), CARRYOVER_CAP)
    if carry > 0 and carry < int(bal.get("current_credits") or 0):
        excess = int(bal["current_credits"]) - carry
        execute_with_retry(
            conn,
            """
            UPDATE qv_credit_balances SET current_credits = ? WHERE user_id = ?
            """,
            (carry, user_id),
        )
        execute_with_retry(
            conn,
            """
            INSERT INTO qv_credit_transactions (user_id, source, amount, description)
            VALUES (?, 'carryover', ?, 'Carryover cap applied')
            """,
            (user_id, -excess),
        )

    earned = calculate_monthly_credits(conn, user_id, year_month)
    if earned["total"] > 0:
        add_credits(
            conn,
            user_id,
            earned["total"],
            "karma",
            f"Monthly QV credits for {year_month}",
        )
    execute_with_retry(
        conn,
        "UPDATE qv_credit_balances SET last_reset_month = ? WHERE user_id = ?",
        (datetime.now(timezone.utc).strftime("%Y-%m"), user_id),
    )
    return {"carryover": carry, **earned}


def grant_welcome_bonus(conn: sqlite3.Connection, user_id: str) -> bool:
    """One-time welcome bonus for new users."""
    migrate_qv_schema(conn)
    row = conn.execute(
        """
        SELECT 1 FROM qv_credit_transactions
        WHERE user_id = ? AND source = 'bonus' AND description LIKE 'Welcome%'
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if row:
        return False
    return add_credits(conn, user_id, WELCOME_BONUS, "bonus", "Welcome bonus")


# ── Referendum lifecycle ───────────────────────────────────────────────────


def create_referendum(
    conn: sqlite3.Connection,
    title: str,
    description: str,
    proposer_id: str,
    level: str,
    location_id: str,
) -> int:
    """Create draft referendum after validation."""
    migrate_qv_schema(conn)
    title = strip_html(title)[:255]
    description = strip_html(description)[:5000]
    lt = normalize_level(level)
    if lt not in LEVELS:
        raise ValueError("Invalid level")
    loc = (location_id or "").strip()
    if not title or not description or not loc:
        raise ValueError("Title, description, and location are required")
    user = conn.execute(
        "SELECT * FROM users WHERE private_id = ?", (proposer_id,)
    ).fetchone()
    if not user or not is_human_user(user):
        raise PermissionError("Only registered human users may propose referendums")
    if not user_can_propose_at_level(conn, user, lt, loc):
        raise PermissionError("Cannot propose at this geographic level")
    cur = conn.execute(
        """
        INSERT INTO qv_referendums (title, description, proposed_by, location_id, level, status)
        VALUES (?, ?, ?, ?, ?, 'draft')
        """,
        (title, description, proposer_id, loc, lt),
    )
    return int(cur.lastrowid)


def can_review_referendum(
    conn: sqlite3.Connection,
    referendum_id: int,
    council_member_id: str,
    *,
    is_admin_fn: Callable[[sqlite3.Row], bool] | None = None,
) -> bool:
    """Council mentor/nayak/nayika/manager at referendum level or parent scope."""
    migrate_qv_schema(conn)
    ref = conn.execute(
        "SELECT * FROM qv_referendums WHERE id = ?", (int(referendum_id),)
    ).fetchone()
    if not ref:
        return False
    user = conn.execute(
        "SELECT * FROM users WHERE private_id = ?", (council_member_id,)
    ).fetchone()
    if not user:
        return False
    if is_admin_fn and is_admin_fn(user):
        return True
    chain = location_chain_for_referendum(conn, str(ref["level"]), str(ref["location_id"]))
    if not chain and str(ref["level"]) == "earth":
        chain = [("earth", str(ref["location_id"]))]
    slots = ",".join("?" for _ in REVIEW_SLOTS)
    for lt, lid in chain:
        row = conn.execute(
            f"""
            SELECT 1 FROM leadership_council
            WHERE level_type = ? AND location_id = ?
              AND slot_designation IN ({slots})
              AND current_holder_private_id = ? AND status = 'filled'
            LIMIT 1
            """,
            (lt, lid, *REVIEW_SLOTS, council_member_id),
        ).fetchone()
        if row:
            return True
    return False


def _post_referendum_timeline(
    conn: sqlite3.Connection, referendum: sqlite3.Row, *, event: str
) -> None:
    """Insert a public timeline post for referendum events."""
    title = str(referendum["title"])
    level = str(referendum["level"])
    loc = str(referendum["location_id"])
    if event == "active":
        content = f"📊 QV Referendum open for voting: {title}"
    elif event == "resolved":
        content = f"✅ QV Referendum resolved: {title} (weighted support: {referendum['total_weighted_support']})"
    else:
        content = f"📋 QV Referendum: {title}"
    author = str(referendum["proposed_by"])
    try:
        conn.execute(
            """
            INSERT INTO posts (
                user_private_id, location_id, content, current_level, status, total_score
            ) VALUES (?, ?, ?, ?, 'live', 0)
            """,
            (author, loc, content, level),
        )
    except sqlite3.OperationalError:
        pass


def approve_referendum(
    conn: sqlite3.Connection, referendum_id: int, council_member_id: str, **ctx: Any
) -> bool:
    """Set status active with 7-day voting window."""
    migrate_qv_schema(conn)
    if not can_review_referendum(
        conn, referendum_id, council_member_id, is_admin_fn=ctx.get("is_admin_fn")
    ):
        return False
    ref = conn.execute(
        "SELECT * FROM qv_referendums WHERE id = ? AND status = 'draft'",
        (int(referendum_id),),
    ).fetchone()
    if not ref:
        return False
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=VOTING_DAYS)
    notes = f"Approved by {council_member_id} at {_now_iso()}"
    execute_with_retry(
        conn,
        """
        UPDATE qv_referendums
        SET status = 'active', voting_start = ?, voting_end = ?,
            resolution_notes = ?
        WHERE id = ?
        """,
        (now.isoformat(), end.isoformat(), notes, int(referendum_id)),
    )
    ref = conn.execute("SELECT * FROM qv_referendums WHERE id = ?", (int(referendum_id),)).fetchone()
    if ref:
        _post_referendum_timeline(conn, ref, event="active")
        notify = ctx.get("notify_fn")
        if notify:
            notify(
                conn,
                str(ref["proposed_by"]),
                "Referendum approved",
                f'Your referendum "{ref["title"]}" is now open for voting.',
            )
    return True


def reject_referendum(
    conn: sqlite3.Connection,
    referendum_id: int,
    council_member_id: str,
    reason: str,
    **ctx: Any,
) -> bool:
    """Close referendum with rejection reason."""
    migrate_qv_schema(conn)
    if not can_review_referendum(
        conn, referendum_id, council_member_id, is_admin_fn=ctx.get("is_admin_fn")
    ):
        return False
    reason = strip_html(reason)[:2000]
    execute_with_retry(
        conn,
        """
        UPDATE qv_referendums
        SET status = 'closed', resolution_notes = ?, resolved_at = ?
        WHERE id = ? AND status = 'draft'
        """,
        (reason, _now_iso(), int(referendum_id)),
    )
    changed = conn.execute("SELECT changes()").fetchone()[0]
    if changed and ctx.get("notify_fn"):
        ref = conn.execute("SELECT * FROM qv_referendums WHERE id = ?", (int(referendum_id),)).fetchone()
        if ref:
            ctx["notify_fn"](
                conn,
                str(ref["proposed_by"]),
                "Referendum rejected",
                reason or "Your referendum was not approved.",
            )
    return bool(changed)


def _recalc_weighted_support(conn: sqlite3.Connection, referendum_id: int) -> int:
    row = conn.execute(
        """
        SELECT COALESCE(SUM(votes * votes), 0) AS w FROM qv_votes WHERE referendum_id = ?
        """,
        (int(referendum_id),),
    ).fetchone()
    weighted = int(row["w"] or 0)
    execute_with_retry(
        conn,
        "UPDATE qv_referendums SET total_weighted_support = ? WHERE id = ?",
        (weighted, int(referendum_id)),
    )
    return weighted


def cast_vote(
    conn: sqlite3.Connection, referendum_id: int, voter_id: str, votes: int
) -> dict[str, Any]:
    """Cast or update a quadratic vote."""
    migrate_qv_schema(conn)
    votes = int(votes)
    if votes < 1 or votes > 10:
        return {"success": False, "message": "Votes must be between 1 and 10"}
    cost = quadratic_cost(votes)
    ref = conn.execute(
        "SELECT * FROM qv_referendums WHERE id = ?", (int(referendum_id),)
    ).fetchone()
    if not ref:
        return {"success": False, "message": "Referendum not found"}
    if str(ref["status"]) != "active":
        return {"success": False, "message": "Voting is not open for this referendum"}
    if str(ref["proposed_by"]) == voter_id:
        return {"success": False, "message": "You cannot vote on your own proposal"}
    now = datetime.now(timezone.utc)
    try:
        start = datetime.fromisoformat(str(ref["voting_start"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(ref["voting_end"]).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return {"success": False, "message": "Invalid voting window"}
    if not (start <= now <= end):
        return {"success": False, "message": "Voting period has ended or not started"}

    existing = conn.execute(
        "SELECT * FROM qv_votes WHERE referendum_id = ? AND voter_id = ?",
        (int(referendum_id), voter_id),
    ).fetchone()
    if existing:
        old_cost = int(existing["credits_used"])
        if old_cost != cost:
            refund = old_cost - cost
            if refund > 0:
                add_credits(conn, voter_id, refund, "voting", "Vote change refund", referendum_id)
            elif refund < 0:
                if not deduct_credits(conn, voter_id, -refund, referendum_id, votes):
                    return {"success": False, "message": "Insufficient QV credits"}
        execute_with_retry(
            conn,
            """
            UPDATE qv_votes SET votes = ?, credits_used = ?, timestamp = CURRENT_TIMESTAMP
            WHERE referendum_id = ? AND voter_id = ?
            """,
            (votes, cost, int(referendum_id), voter_id),
        )
    else:
        if not deduct_credits(conn, voter_id, cost, referendum_id, votes):
            return {
                "success": False,
                "message": "Insufficient QV credits",
                "credits_remaining": get_credit_balance(conn, voter_id),
            }
        execute_with_retry(
            conn,
            """
            INSERT INTO qv_votes (referendum_id, voter_id, votes, credits_used)
            VALUES (?, ?, ?, ?)
            """,
            (int(referendum_id), voter_id, votes, cost),
        )
    weighted = _recalc_weighted_support(conn, referendum_id)
    remaining = get_credit_balance(conn, voter_id)
    return {
        "success": True,
        "credits_remaining": remaining,
        "credits_used": cost,
        "weighted_support": weighted,
        "message": "Vote recorded",
    }


def calculate_results(conn: sqlite3.Connection, referendum_id: int) -> dict[str, Any]:
    """Finalize referendum results."""
    migrate_qv_schema(conn)
    weighted = _recalc_weighted_support(conn, referendum_id)
    voters = conn.execute(
        "SELECT COUNT(*) AS c FROM qv_votes WHERE referendum_id = ?",
        (int(referendum_id),),
    ).fetchone()
    total_voters = int(voters["c"] or 0)
    execute_with_retry(
        conn,
        """
        INSERT INTO qv_results (referendum_id, weighted_support, status)
        VALUES (?, ?, 'pending')
        ON CONFLICT(referendum_id) DO UPDATE SET
            weighted_support = excluded.weighted_support,
            calculated_at = CURRENT_TIMESTAMP
        """,
        (int(referendum_id), weighted),
    )
    execute_with_retry(
        conn,
        """
        UPDATE qv_referendums SET status = 'resolved', resolved_at = ? WHERE id = ?
        """,
        (_now_iso(), int(referendum_id)),
    )
    ref = conn.execute("SELECT * FROM qv_referendums WHERE id = ?", (int(referendum_id),)).fetchone()
    if ref:
        _post_referendum_timeline(conn, ref, event="resolved")
    return {
        "weighted_support": weighted,
        "rank": 1,
        "total_voters": total_voters,
    }


def get_active_referendums(
    conn: sqlite3.Connection,
    level: str | None = None,
    location_id: str | None = None,
    status: str | None = "active",
) -> list[dict[str, Any]]:
    """Return referendums filtered by level and/or location."""
    migrate_qv_schema(conn)
    sql = "SELECT * FROM qv_referendums WHERE 1=1"
    params: list[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if level:
        sql += " AND level = ?"
        params.append(normalize_level(level))
    if location_id:
        sql += " AND location_id = ?"
        params.append(location_id.strip())
    sql += " ORDER BY datetime(created_at) DESC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_dict(r) for r in rows if r]


def get_referendum(conn: sqlite3.Connection, referendum_id: int) -> dict[str, Any] | None:
    """Return single referendum with vote summary."""
    migrate_qv_schema(conn)
    ref = conn.execute(
        "SELECT * FROM qv_referendums WHERE id = ?", (int(referendum_id),)
    ).fetchone()
    if not ref:
        return None
    out = _row_to_dict(ref) or {}
    votes = conn.execute(
        """
        SELECT voter_id, votes, credits_used, timestamp FROM qv_votes
        WHERE referendum_id = ? ORDER BY credits_used DESC
        """,
        (int(referendum_id),),
    ).fetchall()
    out["votes"] = [_row_to_dict(v) for v in votes]
    out["vote_count"] = len(votes)
    return out


def get_referendum_results(conn: sqlite3.Connection, referendum_id: int) -> dict[str, Any] | None:
    """Return results row plus referendum metadata."""
    migrate_qv_schema(conn)
    ref = get_referendum(conn, referendum_id)
    if not ref:
        return None
    if ref["status"] not in ("resolved", "escalated", "closed"):
        return None
    res = conn.execute(
        "SELECT * FROM qv_results WHERE referendum_id = ?", (int(referendum_id),)
    ).fetchone()
    out = dict(ref)
    out["result"] = _row_to_dict(res)
    return out


def check_escalation(conn: sqlite3.Connection, referendum_id: int) -> bool:
    """Escalate to parent level if weighted support meets threshold."""
    migrate_qv_schema(conn)
    ref = conn.execute(
        "SELECT * FROM qv_referendums WHERE id = ?", (int(referendum_id),)
    ).fetchone()
    if not ref or str(ref["status"]) != "resolved":
        return False
    level = str(ref["level"])
    if level == "earth":
        return False
    threshold = ESCALATION_THRESHOLDS.get(level, 0)
    weighted = int(ref["total_weighted_support"] or 0)
    if weighted < threshold:
        return False
    parent_level = PARENT_LEVEL.get(level)
    if not parent_level:
        return False
    parent_loc = _parent_location_id(conn, level, str(ref["location_id"]))
    if not parent_loc:
        return False
    cur = conn.execute(
        """
        INSERT INTO qv_referendums (
            title, description, proposed_by, location_id, level, status, escalated_from
        ) VALUES (?, ?, ?, ?, ?, 'draft', ?)
        """,
        (
            ref["title"],
            ref["description"],
            ref["proposed_by"],
            parent_loc,
            parent_level,
            int(referendum_id),
        ),
    )
    execute_with_retry(
        conn,
        "UPDATE qv_referendums SET status = 'escalated' WHERE id = ?",
        (int(referendum_id),),
    )
    return cur.lastrowid is not None


def list_referendums(
    conn: sqlite3.Connection,
    *,
    level: str | None = None,
    status: str | None = None,
    location_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List referendums with optional filters."""
    migrate_qv_schema(conn)
    sql = "SELECT * FROM qv_referendums WHERE 1=1"
    params: list[Any] = []
    if level:
        sql += " AND level = ?"
        params.append(normalize_level(level))
    if status:
        sql += " AND status = ?"
        params.append(status)
    if location_id:
        sql += " AND location_id = ?"
        params.append(location_id.strip())
    sql += " ORDER BY datetime(created_at) DESC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [_row_to_dict(r) for r in rows if r]


def dashboard_qv_summary(conn: sqlite3.Connection, user_id: str) -> dict[str, int]:
    """Credits balance, active referendum count, and unvoted active count for dashboard."""
    migrate_qv_schema(conn)
    credits = get_credit_balance(conn, user_id)
    active = conn.execute(
        "SELECT COUNT(*) AS c FROM qv_referendums WHERE status = 'active'"
    ).fetchone()
    active_count = int(active["c"] or 0)
    unvoted = conn.execute(
        """
        SELECT COUNT(*) AS c FROM qv_referendums r
        WHERE r.status = 'active'
          AND r.proposed_by != ?
          AND NOT EXISTS (
            SELECT 1 FROM qv_votes v
            WHERE v.referendum_id = r.id AND v.voter_id = ?
          )
        """,
        (user_id, user_id),
    ).fetchone()
    return {
        "current_credits": credits,
        "active_referendums": active_count,
        "unvoted_active": int(unvoted["c"] or 0),
    }


def close_expired_referendums(conn: sqlite3.Connection) -> list[int]:
    """Close active referendums past voting_end; return processed ids."""
    migrate_qv_schema(conn)
    now = _now_iso()
    rows = conn.execute(
        """
        SELECT id FROM qv_referendums
        WHERE status = 'active' AND voting_end IS NOT NULL
          AND datetime(voting_end) < datetime(?)
        """,
        (now,),
    ).fetchall()
    done: list[int] = []
    for row in rows:
        rid = int(row["id"])
        calculate_results(conn, rid)
        check_escalation(conn, rid)
        done.append(rid)
    return done
