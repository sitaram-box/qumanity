"""
Vedic Varna classification — Guna + Karma based (not birth / Jaati).

Chaturvarnyam maya srishtam guna-karma-vibhagashah (Bhagavad Gita 4.13)

Categories (equal, non-hierarchical):
  vidya  (Brahmana) — knowledge, education, advisory
  raksha (Kshatriya) — governance, justice, security
  artha  (Vaishya) — commerce, economy
  seva   (Shudra) — service, care, delivery
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from typing import Any, Callable

CALCULATION_VERSION = 1

CATEGORIES: tuple[str, ...] = ("vidya", "raksha", "artha", "seva")

CATEGORY_LABELS: dict[str, str] = {
    "vidya": "Vidya (Wisdom)",
    "raksha": "Raksha (Protection)",
    "artha": "Artha (Commerce)",
    "seva": "Seva (Service)",
    "sarvanga": "Sarvanga (Balanced)",
}

CATEGORY_SANSKRIT: dict[str, str] = {
    "vidya": "विद्या",
    "raksha": "रक्षा",
    "artha": "अर्थ",
    "seva": "सेवा",
}

# Functional colors (not hierarchical ranking)
CATEGORY_COLORS: dict[str, str] = {
    "vidya": "var(--qb-varna-vidya)",
    "raksha": "var(--qb-varna-raksha)",
    "artha": "var(--qb-varna-artha)",
    "seva": "var(--qb-varna-seva)",
}

ROLE_CATEGORY_MAP: dict[str, str] = {
    "mentor": "vidya",
    "nayak": "raksha",
    "nayika": "raksha",
    "manager": "artha",
    "agent": "seva",
}

ELIGIBLE_ROLES: dict[str, list[str]] = {
    "vidya": ["Mentor", "Spiritual Guide", "Judge"],
    "raksha": ["Nayak", "Nayika", "Security Head", "Dispute Resolver"],
    "artha": ["Manager", "Treasurer", "Commerce Head"],
    "seva": ["Agent", "Service Coordinator", "Welfare Officer"],
    "sarvanga": ["Council Member", "Advisor", "Coordinator"],
}

KARMA_BONUS_MULTIPLIERS: dict[str, float] = {
    "vidya": 1.5,
    "raksha": 1.5,
    "artha": 1.3,
    "seva": 1.3,
}

FORBIDDEN_CLASSIFICATION_FIELDS = frozenset(
    {"caste", "jaati", "gotra", "family_name", "ancestry"}
)

VARNA_DDL = """
CREATE TABLE IF NOT EXISTS category_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    vidya_score REAL,
    raksha_score REAL,
    artha_score REAL,
    seva_score REAL,
    primary_category TEXT,
    secondary_category TEXT,
    category_type TEXT,
    calculation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    calculation_version INTEGER,
    change_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_category_history_user
    ON category_history(user_private_id, calculation_date DESC);

CREATE TABLE IF NOT EXISTS category_appeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by TEXT,
    reviewed_at TIMESTAMP,
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_category_appeals_status
    ON category_appeals(status, created_at DESC);

CREATE TABLE IF NOT EXISTS varna_raw_scores (
    user_private_id TEXT PRIMARY KEY,
    container_id TEXT,
    container_type TEXT DEFAULT 'village',
    vidya_raw REAL DEFAULT 0,
    raksha_raw REAL DEFAULT 0,
    artha_raw REAL DEFAULT 0,
    seva_raw REAL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS varna_system_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def migrate_varna_schema(conn: sqlite3.Connection) -> None:
    """Add users columns, history/appeals tables, karma affinity."""
    conn.executescript(VARNA_DDL)

    if _table_exists(conn, "users"):
        user_cols = _cols(conn, "users")
        additions: list[tuple[str, str]] = [
            ("vidya_score", "REAL DEFAULT 0"),
            ("raksha_score", "REAL DEFAULT 0"),
            ("artha_score", "REAL DEFAULT 0"),
            ("seva_score", "REAL DEFAULT 0"),
            ("primary_category", "TEXT"),
            ("secondary_category", "TEXT"),
            ("category_type", "TEXT"),
            ("category_last_updated", "TIMESTAMP"),
            ("category_calculation_version", "INTEGER DEFAULT 1"),
        ]
        for col, decl in additions:
            if col not in user_cols:
                try:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
                except sqlite3.OperationalError:
                    pass

    if _table_exists(conn, "posts"):
        post_cols = _cols(conn, "posts")
        if "content_category" not in post_cols:
            try:
                conn.execute(
                    "ALTER TABLE posts ADD COLUMN content_category TEXT"
                )
            except sqlite3.OperationalError:
                pass

    if _table_exists(conn, "karma_action_types"):
        kat_cols = _cols(conn, "karma_action_types")
        if "category_affinity" not in kat_cols:
            try:
                conn.execute(
                    "ALTER TABLE karma_action_types ADD COLUMN category_affinity TEXT"
                )
            except sqlite3.OperationalError:
                pass
        _seed_karma_affinities(conn)

    conn.commit()


def _seed_karma_affinities(conn: sqlite3.Connection) -> None:
    mapping = {
        "teach_hour": "vidya",
        "plant_tree": "seva",
        "council_day": "raksha",
        "report_issue": "raksha",
    }
    for code, affinity in mapping.items():
        conn.execute(
            """
            UPDATE karma_action_types SET category_affinity = ?
            WHERE action_code = ?
            """,
            (affinity, code),
        )
    # Label-based fallback for legacy rows
    conn.execute(
        """
        UPDATE karma_action_types SET category_affinity = 'vidya'
        WHERE category_affinity IS NULL AND label LIKE '%Teach%'
        """
    )
    conn.execute(
        """
        UPDATE karma_action_types SET category_affinity = 'raksha'
        WHERE category_affinity IS NULL AND (
            label LIKE '%Council%' OR label LIKE '%Report%'
        )
        """
    )
    conn.execute(
        """
        UPDATE karma_action_types SET category_affinity = 'seva'
        WHERE category_affinity IS NULL AND label LIKE '%tree%'
        """
    )


def validate_no_birth_bias(user_data: dict[str, Any]) -> bool:
    for field in FORBIDDEN_CLASSIFICATION_FIELDS:
        if user_data.get(field):
            raise ValueError(
                f"Field '{field}' cannot be used for Varna classification"
            )
    return True


def _user_container_id(user_row: sqlite3.Row | dict[str, Any]) -> tuple[str, str]:
    loc = str(
        user_row.get("current_location_id")
        if isinstance(user_row, dict)
        else user_row["current_location_id"]
        or ""
    ).strip()
    if loc:
        return loc, "village"
    country = str(
        user_row.get("current_country_id")
        if isinstance(user_row, dict)
        else user_row["current_country_id"]
        or "IND"
    ).strip()
    return country or "IND", "country"


def calculate_raw_scores(
    conn: sqlite3.Connection, user_private_id: str
) -> dict[str, float]:
    """Compute unnormalized category points from verified actions."""
    pid = str(user_private_id)
    scores = {c: 0.0 for c in CATEGORIES}

    # --- Vidya: teaching karma, educational posts, upvotes, mentor service ---
    if _table_exists(conn, "karma_transactions"):
        teach = conn.execute(
            """
            SELECT COUNT(*) AS n FROM karma_transactions kt
            JOIN karma_action_types kat ON kat.action_code = kt.action_code
            WHERE kt.user_private_id = ? AND kt.verified = 1
              AND (kat.category_affinity = 'vidya' OR kat.action_code = 'teach_hour')
            """,
            (pid,),
        ).fetchone()
        scores["vidya"] += min(300, int(teach["n"] or 0) * 3)

    if _table_exists(conn, "posts"):
        edu_posts = conn.execute(
            """
            SELECT COUNT(*) AS n FROM posts
            WHERE user_private_id = ? AND status = 'live'
              AND content_category = 'educational'
            """,
            (pid,),
        ).fetchone()
        scores["vidya"] += min(100, int(edu_posts["n"] or 0) * 5)

        upvotes = conn.execute(
            """
            SELECT COALESCE(SUM(pv.vote_value), 0) AS s
            FROM post_votes pv
            JOIN posts p ON p.id = pv.post_id
            WHERE p.user_private_id = ? AND pv.vote_value > 0
            """,
            (pid,),
        ).fetchone()
        scores["vidya"] += min(100, int(upvotes["s"] or 0) * 2)

    if _table_exists(conn, "leadership_council"):
        mentor_days = conn.execute(
            """
            SELECT COUNT(*) AS n FROM leadership_council
            WHERE current_holder_private_id = ?
              AND slot_designation = 'mentor' AND status = 'filled'
            """,
            (pid,),
        ).fetchone()
        scores["vidya"] += min(200, int(mentor_days["n"] or 0) * 10)

    # --- Raksha: council, security posts, election votes received ---
    if _table_exists(conn, "karma_transactions"):
        raksha_k = conn.execute(
            """
            SELECT COUNT(*) AS n FROM karma_transactions kt
            JOIN karma_action_types kat ON kat.action_code = kt.action_code
            WHERE kt.user_private_id = ? AND kt.verified = 1
              AND kat.category_affinity = 'raksha'
            """,
            (pid,),
        ).fetchone()
        scores["raksha"] += min(100, int(raksha_k["n"] or 0) * 5)

    if _table_exists(conn, "leadership_council"):
        council = conn.execute(
            """
            SELECT COUNT(*) AS n FROM leadership_council
            WHERE current_holder_private_id = ?
              AND slot_designation IN ('nayak', 'nayika', 'manager')
              AND status = 'filled'
            """,
            (pid,),
        ).fetchone()
        scores["raksha"] += min(250, int(council["n"] or 0) * 5)

    if _table_exists(conn, "posts"):
        sec = conn.execute(
            """
            SELECT COUNT(*) AS n FROM posts
            WHERE user_private_id = ? AND content_category = 'security'
            """,
            (pid,),
        ).fetchone()
        scores["raksha"] += min(120, int(sec["n"] or 0) * 8)

    if _table_exists(conn, "election_votes") and _table_exists(conn, "election_candidates"):
        ev = conn.execute(
            """
            SELECT COUNT(*) AS n FROM election_votes ev
            JOIN election_candidates ec ON ec.id = ev.candidate_id
            WHERE ec.user_private_id = ?
            """,
            (pid,),
        ).fetchone()
        scores["raksha"] += min(100, int(ev["n"] or 0) * 2)

    # --- Artha: commerce volume, vendor, deliveries, ratings ---
    if _table_exists(conn, "qoin_transactions"):
        vol = conn.execute(
            """
            SELECT COALESCE(SUM(ABS(amount)), 0) AS s FROM qoin_transactions
            WHERE user_private_id = ? AND amount > 0
            """,
            (pid,),
        ).fetchone()
        scores["artha"] += min(300, int(vol["s"] or 0) // 100)

    if _table_exists(conn, "marketplace_listings"):
        products = conn.execute(
            """
            SELECT COUNT(*) AS n FROM marketplace_listings
            WHERE seller_private_id = ?
            """,
            (pid,),
        ).fetchone()
        scores["artha"] += min(100, int(products["n"] or 0) * 10)

    if _table_exists(conn, "businesses"):
        biz = conn.execute(
            """
            SELECT COUNT(*) AS n FROM businesses
            WHERE owner_private_id = ? AND status = 'approved'
            """,
            (pid,),
        ).fetchone()
        scores["artha"] += min(80, int(biz["n"] or 0) * 20)

    if _table_exists(conn, "marketplace_reviews"):
        ratings = conn.execute(
            """
            SELECT COUNT(*) AS n FROM marketplace_reviews mr
            JOIN marketplace_orders mo ON mo.id = mr.order_id
            WHERE mo.seller_private_id = ? AND mr.rating >= 4
            """,
            (pid,),
        ).fetchone()
        scores["artha"] += min(100, int(ratings["n"] or 0) * 2)

    # --- Seva: service karma, delivery, CRM tickets ---
    if _table_exists(conn, "karma_transactions"):
        seva_k = conn.execute(
            """
            SELECT COUNT(*) AS n FROM karma_transactions kt
            JOIN karma_action_types kat ON kat.action_code = kt.action_code
            WHERE kt.user_private_id = ? AND kt.verified = 1
              AND kat.category_affinity = 'seva'
            """,
            (pid,),
        ).fetchone()
        scores["seva"] += min(400, int(seva_k["n"] or 0) * 4)

    if _table_exists(conn, "marketplace_orders"):
        deliveries = conn.execute(
            """
            SELECT COUNT(*) AS n FROM marketplace_orders
            WHERE delivery_agent_private_id = ? AND status = 'delivered'
            """,
            (pid,),
        ).fetchone()
        scores["seva"] += min(150, int(deliveries["n"] or 0) * 3)

    if _table_exists(conn, "crm_ticket_updates"):
        pass  # citizen-facing; agents tracked via karma

    return scores


def classify_user(scores: dict[str, float]) -> tuple[str, str | None, str]:
    """Return (primary_category, secondary_category, category_type)."""
    if not any(scores.values()):
        return "", None, "unassigned"

    spread = max(scores.values()) - min(scores.values())
    if spread <= 20:
        return "sarvanga", None, "balanced"

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top, second, _third = ranked[0], ranked[1], ranked[2]
    diff_1_2 = top[1] - second[1]

    if diff_1_2 >= 30:
        return top[0], None, "pure"
    if diff_1_2 <= 15:
        return f"{top[0]}-{second[0]}", None, "hybrid"
    return top[0], second[0], "primary_secondary"


def normalize_scores_in_container(
    conn: sqlite3.Connection,
    container_id: str,
    container_type: str = "village",
) -> None:
    """Min-max normalize raw scores to 0–100 within a geographic container."""
    migrate_varna_schema(conn)
    users = conn.execute(
        """
        SELECT private_id, current_location_id, current_country_id
        FROM users
        WHERE account_type NOT LIKE 'D_U%'
        """
    ).fetchall()

    bucket: list[str] = []
    for u in users:
        cid, ctype = _user_container_id(dict(u))
        if cid == container_id and ctype == container_type:
            bucket.append(str(u["private_id"]))

    if not bucket:
        return

    raw_by_user: dict[str, dict[str, float]] = {}
    for pid in bucket:
        raw = calculate_raw_scores(conn, pid)
        raw_by_user[pid] = raw
        conn.execute(
            """
            INSERT INTO varna_raw_scores (
                user_private_id, container_id, container_type,
                vidya_raw, raksha_raw, artha_raw, seva_raw, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_private_id) DO UPDATE SET
                container_id = excluded.container_id,
                container_type = excluded.container_type,
                vidya_raw = excluded.vidya_raw,
                raksha_raw = excluded.raksha_raw,
                artha_raw = excluded.artha_raw,
                seva_raw = excluded.seva_raw,
                updated_at = excluded.updated_at
            """,
            (
                pid,
                container_id,
                container_type,
                raw["vidya"],
                raw["raksha"],
                raw["artha"],
                raw["seva"],
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    for cat in CATEGORIES:
        vals = [raw_by_user[p][cat] for p in bucket]
        lo, hi = min(vals), max(vals)
        for pid in bucket:
            raw_val = raw_by_user[pid][cat]
            if hi > lo:
                norm = (raw_val - lo) / (hi - lo) * 100.0
            else:
                norm = 50.0 if raw_val > 0 else 0.0
            raw_by_user[pid][f"{cat}_norm"] = norm

    now = datetime.now(timezone.utc).isoformat()
    for pid in bucket:
        norm_scores = {
            c: raw_by_user[pid].get(f"{c}_norm", 0.0) for c in CATEGORIES
        }
        primary, secondary, ctype = classify_user(norm_scores)
        conn.execute(
            f"""
            UPDATE users SET
                vidya_score = ?, raksha_score = ?, artha_score = ?, seva_score = ?,
                primary_category = ?, secondary_category = ?, category_type = ?,
                category_last_updated = ?, category_calculation_version = ?
            WHERE private_id = ?
            """,
            (
                norm_scores["vidya"],
                norm_scores["raksha"],
                norm_scores["artha"],
                norm_scores["seva"],
                primary or None,
                secondary,
                ctype,
                now,
                CALCULATION_VERSION,
                pid,
            ),
        )
        conn.execute(
            """
            INSERT INTO category_history (
                user_private_id, vidya_score, raksha_score, artha_score, seva_score,
                primary_category, secondary_category, category_type,
                calculation_version, change_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pid,
                norm_scores["vidya"],
                norm_scores["raksha"],
                norm_scores["artha"],
                norm_scores["seva"],
                primary or None,
                secondary,
                ctype,
                CALCULATION_VERSION,
                "monthly_recalc",
            ),
        )


def get_all_containers(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT DISTINCT current_location_id AS cid, 'village' AS ctype
        FROM users
        WHERE current_location_id IS NOT NULL AND TRIM(current_location_id) != ''
        UNION
        SELECT DISTINCT current_country_id, 'country' FROM users
        WHERE (current_location_id IS NULL OR TRIM(current_location_id) = '')
          AND current_country_id IS NOT NULL
        """
    ).fetchall()
    return [(str(r["cid"]), str(r["ctype"])) for r in rows if r["cid"]]


def recalculate_all_categories(
    conn: sqlite3.Connection,
    *,
    change_reason: str = "monthly_recalc",
) -> dict[str, Any]:
    migrate_varna_schema(conn)
    containers = get_all_containers(conn)
    if not containers:
        containers = [("IND", "country")]

    for cid, ctype in containers:
        normalize_scores_in_container(conn, cid, ctype)

    conn.execute(
            """
            INSERT INTO varna_system_meta (key, value) VALUES ('last_recalc', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (datetime.now(timezone.utc).isoformat(),),
        )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    return {"users_processed": int(count), "containers": len(containers), "reason": change_reason}


def recalculate_user_category(
    conn: sqlite3.Connection,
    user_private_id: str,
    *,
    change_reason: str = "manual_recalc",
) -> dict[str, Any]:
    migrate_varna_schema(conn)
    row = conn.execute(
        "SELECT * FROM users WHERE private_id = ?",
        (user_private_id,),
    ).fetchone()
    if not row:
        raise ValueError("User not found")
    validate_no_birth_bias(dict(row))
    cid, ctype = _user_container_id(dict(row))
    normalize_scores_in_container(conn, cid, ctype)
    conn.commit()
    return profile_for_user(conn, user_private_id)


def get_score_breakdown(
    conn: sqlite3.Connection, user_private_id: str
) -> list[dict[str, Any]]:
    """Transparency: contributing factors for the user's raw scores."""
    pid = str(user_private_id)
    items: list[dict[str, Any]] = []

    if _table_exists(conn, "karma_transactions"):
        for row in conn.execute(
            """
            SELECT kat.label, kat.category_affinity, COUNT(*) AS n
            FROM karma_transactions kt
            JOIN karma_action_types kat ON kat.action_code = kt.action_code
            WHERE kt.user_private_id = ? AND kt.verified = 1
            GROUP BY kat.action_code
            """,
            (pid,),
        ):
            aff = row["category_affinity"] or "multiple"
            weight = {"vidya": 3, "raksha": 5, "seva": 4, "artha": 1}.get(aff, 1)
            pts = int(row["n"]) * weight
            items.append(
                {
                    "description": str(row["label"]),
                    "category": aff,
                    "count": int(row["n"]),
                    "points": pts,
                }
            )

    if _table_exists(conn, "leadership_council"):
        n = conn.execute(
            """
            SELECT COUNT(*) AS c FROM leadership_council
            WHERE current_holder_private_id = ? AND status = 'filled'
            """,
            (pid,),
        ).fetchone()["c"]
        if n:
            items.append(
                {
                    "description": "Council / leadership service",
                    "category": "raksha",
                    "count": int(n),
                    "points": int(n) * 5,
                }
            )

    return items


def profile_for_user(
    conn: sqlite3.Connection, user_private_id: str
) -> dict[str, Any]:
    migrate_varna_schema(conn)
    row = conn.execute(
        "SELECT * FROM users WHERE private_id = ?",
        (user_private_id,),
    ).fetchone()
    if not row:
        return {}
    return {
        "primary_category": row["primary_category"] or "",
        "secondary_category": row["secondary_category"] or "",
        "category_type": row["category_type"] or "unassigned",
        "scores": {
            "vidya": float(row["vidya_score"] or 0),
            "raksha": float(row["raksha_score"] or 0),
            "artha": float(row["artha_score"] or 0),
            "seva": float(row["seva_score"] or 0),
        },
        "labels": CATEGORY_LABELS,
        "sanskrit": CATEGORY_SANSKRIT,
        "score_breakdown": get_score_breakdown(conn, user_private_id),
        "last_updated": row["category_last_updated"],
        "history": get_category_history(conn, user_private_id, limit=6),
    }


def get_category_history(
    conn: sqlite3.Connection, user_private_id: str, *, limit: int = 6
) -> list[dict[str, Any]]:
    if not _table_exists(conn, "category_history"):
        return []
    rows = conn.execute(
        """
        SELECT * FROM category_history
        WHERE user_private_id = ?
        ORDER BY calculation_date DESC
        LIMIT ?
        """,
        (user_private_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_primary_category(conn: sqlite3.Connection, user_private_id: str) -> str:
    row = conn.execute(
        "SELECT primary_category FROM users WHERE private_id = ?",
        (user_private_id,),
    ).fetchone()
    if not row or not row["primary_category"]:
        return ""
    primary = str(row["primary_category"])
    if "-" in primary:
        return primary.split("-")[0]
    return primary


def get_category_type(conn: sqlite3.Connection, user_private_id: str) -> str:
    row = conn.execute(
        "SELECT category_type FROM users WHERE private_id = ?",
        (user_private_id,),
    ).fetchone()
    return str(row["category_type"] or "") if row else ""


def get_secondary_category(conn: sqlite3.Connection, user_private_id: str) -> str | None:
    row = conn.execute(
        "SELECT secondary_category, primary_category, category_type FROM users WHERE private_id = ?",
        (user_private_id,),
    ).fetchone()
    if not row:
        return None
    if row["secondary_category"]:
        return str(row["secondary_category"])
    primary = str(row["primary_category"] or "")
    if row["category_type"] == "hybrid" and "-" in primary:
        return primary.split("-", 1)[1]
    return None


def eligible_roles_for_user(
    conn: sqlite3.Connection, user_private_id: str
) -> list[str]:
    primary = get_primary_category(conn, user_private_id)
    ctype = get_category_type(conn, user_private_id)
    roles: set[str] = set()

    if primary in ELIGIBLE_ROLES:
        roles.update(ELIGIBLE_ROLES[primary])
    elif primary == "sarvanga":
        roles.update(ELIGIBLE_ROLES["sarvanga"])

    if ctype == "hybrid":
        sec = get_secondary_category(conn, user_private_id)
        if sec and sec in ELIGIBLE_ROLES:
            roles.update(ELIGIBLE_ROLES[sec])

    if not roles:
        roles.add("Council Member")
    return sorted(roles)


def can_nominate_for_council(
    conn: sqlite3.Connection, user_private_id: str, role: str
) -> bool:
    """Filter election nominations by Guna-Karma category (not birth)."""
    required = ROLE_CATEGORY_MAP.get(role.lower())
    if not required:
        return True

    primary = get_primary_category(conn, user_private_id)
    if not primary:
        return True  # insufficient data — do not block

    if primary == "sarvanga":
        return True

    if primary == required:
        return True

    ctype = get_category_type(conn, user_private_id)
    if ctype == "hybrid":
        sec = get_secondary_category(conn, user_private_id)
        return required in {primary, sec}

    if ctype == "primary_secondary":
        sec = get_secondary_category(conn, user_private_id)
        return required in {primary, sec}

    return False


def apply_karma_category_bonus(
    conn: sqlite3.Connection,
    user_private_id: str,
    action_code: str,
    base_amount: int,
) -> int:
    """Bonus multiplier when action aligns with user's dominant category."""
    migrate_varna_schema(conn)
    row = conn.execute(
        "SELECT category_affinity FROM karma_action_types WHERE action_code = ?",
        (action_code,),
    ).fetchone()
    if not row or not row["category_affinity"]:
        return base_amount

    affinity = str(row["category_affinity"])
    if affinity == "multiple":
        return base_amount

    primary = get_primary_category(conn, user_private_id)
    if not primary:
        return base_amount

    match = affinity == primary
    if not match and get_category_type(conn, user_private_id) == "hybrid":
        sec = get_secondary_category(conn, user_private_id)
        match = affinity in {primary, sec}

    if match:
        mult = KARMA_BONUS_MULTIPLIERS.get(affinity, 1.0)
        return int(round(base_amount * mult))
    return base_amount


def admin_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    migrate_varna_schema(conn)
    dist = {c: 0 for c in CATEGORIES}
    dist["sarvanga"] = 0
    dist["unassigned"] = 0

    for row in conn.execute(
        "SELECT primary_category FROM users WHERE primary_category IS NOT NULL"
    ):
        p = str(row["primary_category"] or "")
        if p == "sarvanga":
            dist["sarvanga"] += 1
        elif p.startswith("vidya"):
            dist["vidya"] += 1
        elif p.startswith("raksha"):
            dist["raksha"] += 1
        elif p.startswith("artha"):
            dist["artha"] += 1
        elif p.startswith("seva"):
            dist["seva"] += 1
        elif p:
            dist["unassigned"] += 1

    unassigned = conn.execute(
        """
        SELECT COUNT(*) AS n FROM users
        WHERE primary_category IS NULL OR TRIM(primary_category) = ''
        """
    ).fetchone()["n"]
    dist["unassigned"] += int(unassigned)

    pending = 0
    if _table_exists(conn, "category_appeals"):
        pending = int(
            conn.execute(
                "SELECT COUNT(*) AS n FROM category_appeals WHERE status = 'pending'"
            ).fetchone()["n"]
        )

    return {"distribution": dist, "pending_appeals": pending}


def submit_appeal(
    conn: sqlite3.Connection,
    user_private_id: str,
    reason: str,
    evidence: str | None = None,
) -> int:
    migrate_varna_schema(conn)
    cur = conn.execute(
        """
        INSERT INTO category_appeals (user_private_id, reason, evidence)
        VALUES (?, ?, ?)
        """,
        (user_private_id, reason, evidence),
    )
    return int(cur.lastrowid or 0)


def resolve_appeal(
    conn: sqlite3.Connection,
    appeal_id: int,
    *,
    action: str,
    reviewer_private_id: str,
    admin_notes: str = "",
) -> None:
    migrate_varna_schema(conn)
    row = conn.execute(
        "SELECT user_private_id FROM category_appeals WHERE id = ?",
        (appeal_id,),
    ).fetchone()
    if not row:
        raise ValueError("Appeal not found")

    status = "approved" if action == "approve" else "rejected"
    conn.execute(
        """
        UPDATE category_appeals
        SET status = ?, reviewed_by = ?, reviewed_at = ?, admin_notes = ?
        WHERE id = ?
        """,
        (
            status,
            reviewer_private_id,
            datetime.now(timezone.utc).isoformat(),
            admin_notes,
            appeal_id,
        ),
    )
    if status == "approved":
        recalculate_user_category(
            conn,
            str(row["user_private_id"]),
            change_reason="manual_appeal",
        )


def explain_classification(
    conn: sqlite3.Connection, user_private_id: str
) -> dict[str, Any]:
    prof = profile_for_user(conn, user_private_id)
    return {
        "primary_category": prof.get("primary_category"),
        "how_it_was_determined": (
            "Based on your verified actions and contributions (Karma), "
            "not birth, Jaati, or family name."
        ),
        "contributing_factors": prof.get("score_breakdown", []),
        "recalculation_schedule": "Monthly on the 1st (or when council approves an appeal)",
        "appeal_process": 'Use "Appeal Classification" on your Private Account dashboard',
        "right_to_privacy": "Individual scores are visible only to you; councils see aggregates",
    }
