"""
Posts lifecycle, votes, wallets, and Qoin rewards (SQLite).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

POST_LEVEL_ORDER = (
    "personal",
    "village",
    "tehsil",
    "district",
    "state",
    "country",
    "continent",
    "earth",
)

LEVEL_DAYS = 7
LEVEL_DAYS_BY_LEVEL = {
    "personal": 7,
    "village": 7,
    "tehsil": 7,
    "district": 7,
    "state": 7,
    "country": 7,
    "continent": 7,
    "earth": 7,
}

QOIN_SCORE_BRACKETS = (
    (0, 9, 1),
    (10, 19, 2),
    (20, 49, 5),
    (50, 99, 10),
    (100, 199, 20),
    (200, 499, 50),
    (500, 999, 100),
    (1000, 1999, 200),
    (2000, 4999, 500),
    (5000, 10**12, 2000),
)

LEVEL_BONUS_QOINS = 5

WALLET_DDL = """
CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0,
    UNIQUE(owner_type, owner_id)
);
CREATE INDEX IF NOT EXISTS idx_wallets_owner ON wallets(owner_type, owner_id);

CREATE TABLE IF NOT EXISTS qoin_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_qoin_user ON qoin_transactions(user_private_id);

CREATE TABLE IF NOT EXISTS post_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    voter_private_id TEXT NOT NULL,
    vote_value INTEGER NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id, voter_private_id)
);
CREATE INDEX IF NOT EXISTS idx_post_votes_post ON post_votes(post_id);
"""


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def ensure_wallet_and_vote_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(WALLET_DDL)


def ensure_posts_escalation_columns(conn: sqlite3.Connection) -> None:
    cols = _cols(conn, "posts")
    adds: list[tuple[str, str]] = [
        ("location_id", "TEXT"),
        ("current_level", "TEXT NOT NULL DEFAULT 'personal'"),
        ("level_start_time", "TIMESTAMP"),
        ("status", "TEXT NOT NULL DEFAULT 'live'"),
        ("total_score", "INTEGER NOT NULL DEFAULT 0"),
        ("previous_levels", "TEXT DEFAULT ''"),
        ("origin_village_id", "TEXT"),
        ("origin_tehsil_id", "TEXT"),
        ("origin_district_id", "TEXT"),
        ("origin_state_id", "TEXT"),
        ("origin_country_id", "TEXT"),
        ("origin_continent_id", "TEXT"),
        ("freeze_level", "TEXT"),
        ("qoins_settled", "INTEGER NOT NULL DEFAULT 0"),
        ("original_post_id", "INTEGER"),
        ("frozen_at_level", "TEXT"),
        ("archived_at_level", "TEXT"),
        ("level_end_time", "TIMESTAMP"),
    ]
    for name, decl in adds:
        if name not in cols:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {name} {decl}")
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_posts_current_level ON posts(current_level);
        CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
        CREATE INDEX IF NOT EXISTS idx_posts_location_id ON posts(location_id);
        CREATE INDEX IF NOT EXISTS idx_posts_level_start_time ON posts(level_start_time);
        CREATE INDEX IF NOT EXISTS idx_posts_level_status ON posts(current_level, status);
        CREATE INDEX IF NOT EXISTS idx_posts_freeze_level ON posts(freeze_level);
        CREATE INDEX IF NOT EXISTS idx_posts_user_status_level ON posts(user_private_id, status, current_level);
        CREATE INDEX IF NOT EXISTS idx_posts_original_post_id ON posts(original_post_id);
        """
    )
    if "location_id" in _cols(conn, "posts"):
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_id ON posts(id)"
            )
        except sqlite3.Error:
            pass
    # Legacy rows: old posts had location_id only
    conn.execute(
        """
        UPDATE posts SET origin_village_id = location_id
        WHERE (origin_village_id IS NULL OR TRIM(origin_village_id) = '')
          AND location_id IS NOT NULL AND TRIM(location_id) != ''
        """
    )
    conn.execute(
        """
        UPDATE posts SET status = 'completed', current_level = 'completed',
            qoins_settled = 1
        WHERE status = 'live' AND current_level = 'personal'
          AND level_start_time IS NULL
          AND (origin_tehsil_id IS NULL OR TRIM(origin_tehsil_id) = '')
          AND origin_village_id IS NOT NULL
        """
    )


def get_wallet_balance(conn: sqlite3.Connection, owner_type: str, owner_id: str) -> int:
    row = conn.execute(
        "SELECT balance FROM wallets WHERE owner_type = ? AND owner_id = ?",
        (owner_type, owner_id),
    ).fetchone()
    return int(row["balance"]) if row else 0


def ensure_wallet(conn: sqlite3.Connection, owner_type: str, owner_id: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO wallets (owner_type, owner_id, balance)
        VALUES (?, ?, 0)
        """,
        (owner_type, owner_id),
    )


def credit_wallet(
    conn: sqlite3.Connection,
    owner_type: str,
    owner_id: str,
    amount: int,
    user_private_id: str,
    reason: str,
) -> None:
    if amount == 0:
        return
    ensure_wallet(conn, owner_type, owner_id)
    conn.execute(
        "UPDATE wallets SET balance = balance + ? WHERE owner_type = ? AND owner_id = ?",
        (amount, owner_type, owner_id),
    )
    if owner_type == "user":
        conn.execute(
            """
            INSERT INTO qoin_transactions (user_private_id, amount, reason)
            VALUES (?, ?, ?)
            """,
            (user_private_id, amount, reason),
        )


def qoins_for_final_score(score: int) -> int:
    s = max(0, int(score))
    for lo, hi, amt in QOIN_SCORE_BRACKETS:
        if lo <= s <= hi:
            return amt
    return 0


def recompute_post_score(conn: sqlite3.Connection, post_id: int) -> None:
    row = conn.execute(
        "SELECT COALESCE(SUM(vote_value), 0) AS s FROM post_votes WHERE post_id = ?",
        (post_id,),
    ).fetchone()
    total = int(row["s"]) if row else 0
    conn.execute(
        "UPDATE posts SET total_score = ? WHERE id = ?",
        (total, post_id),
    )


def origins_from_hierarchy(
    hierarchy: list[dict[str, str]],
    country_id: str | None = None,
    continent_id: str | None = None,
) -> dict[str, str | None]:
    cc = (country_id or "").strip().upper() or "IND"
    co = (continent_id or "").strip().upper() or "AS"
    m: dict[str, str | None] = {
        "village": None,
        "tehsil": None,
        "district": None,
        "state": None,
        "country": cc,
        "continent": co,
    }
    for item in hierarchy:
        sc = str(item.get("scope") or "")
        if sc in {"village", "tehsil", "district", "state"} and item.get("id"):
            m[sc] = str(item["id"])
    return m


def _level_idx(level: str) -> int:
    try:
        return POST_LEVEL_ORDER.index(level)
    except ValueError:
        return 0


def _parse_sqlite_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _frozen_level_name(level: str) -> str:
    return f"{level}_frozen"


def _archive_live_post(
    conn: sqlite3.Connection,
    post: sqlite3.Row,
    level: str,
    now: datetime,
) -> bool:
    """Move a live post to the author's Previous Posts (private history)."""
    ts = now.isoformat(timespec="seconds")
    res = conn.execute(
        """
        UPDATE posts
           SET status = 'archived',
               current_level = 'private_history',
               archived_at_level = ?,
               level_end_time = ?,
               qoins_settled = 1
         WHERE id = ? AND status = 'live'
        """,
        (level, ts, int(post["id"])),
    )
    return res.rowcount == 1


def _insert_archived_copy(
    conn: sqlite3.Connection,
    post: sqlite3.Row,
    level: str,
    now: datetime,
    *,
    original_post_id: int | None = None,
) -> None:
    """Duplicate a post row into the author's Previous Posts archive."""
    prev = (post["previous_levels"] or "").strip()
    archived_prev = prev + ("," if prev else "") + level + ":archived"
    ts = now.isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO posts (
            user_private_id, location_id, content, created_at,
            current_level, level_start_time, level_end_time, status, total_score,
            previous_levels, origin_village_id, origin_tehsil_id,
            origin_district_id, origin_state_id, origin_country_id,
            origin_continent_id, archived_at_level, original_post_id, qoins_settled
        ) VALUES (?, ?, ?, ?, 'private_history', ?, ?, 'archived', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            str(post["user_private_id"]),
            post["location_id"],
            post["content"],
            post["created_at"],
            post["level_start_time"],
            ts,
            int(post["total_score"] or 0),
            archived_prev,
            post["origin_village_id"],
            post["origin_tehsil_id"],
            post["origin_district_id"],
            post["origin_state_id"],
            post["origin_country_id"],
            post["origin_continent_id"],
            level,
            original_post_id,
        ),
    )


def _freeze_and_ascend(
    conn: sqlite3.Connection,
    post: sqlite3.Row,
    level: str,
    now: datetime,
) -> bool:
    """Freeze the current-level row and insert a fresh live copy at the next level."""
    pid = int(post["id"])
    score = int(post["total_score"] or 0)
    author = str(post["user_private_id"])
    prev = (post["previous_levels"] or "").strip()
    idx = _level_idx(level)
    if idx >= len(POST_LEVEL_ORDER) - 1:
        return False
    new_level = POST_LEVEL_ORDER[idx + 1]
    new_prev = prev + ("," if prev else "") + level
    ts = now.isoformat(timespec="seconds")
    frozen_level = _frozen_level_name(level)

    res = conn.execute(
        """
        UPDATE posts
           SET status = 'frozen',
               current_level = ?,
               freeze_level = ?,
               frozen_at_level = ?,
               level_end_time = ?,
               previous_levels = ?,
               qoins_settled = 1
         WHERE id = ? AND status = 'live'
        """,
        (frozen_level, level, level, ts, new_prev, pid),
    )
    if res.rowcount != 1:
        return False

    conn.execute(
        """
        INSERT INTO posts (
            user_private_id, location_id, content, created_at,
            current_level, level_start_time, status, total_score,
            previous_levels, origin_village_id, origin_tehsil_id,
            origin_district_id, origin_state_id, origin_country_id,
            origin_continent_id, original_post_id, qoins_settled
        ) VALUES (?, ?, ?, ?, ?, ?, 'live', 0, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            author,
            post["location_id"],
            post["content"],
            post["created_at"],
            new_level,
            ts,
            new_prev,
            post["origin_village_id"],
            post["origin_tehsil_id"],
            post["origin_district_id"],
            post["origin_state_id"],
            post["origin_country_id"],
            post["origin_continent_id"],
            pid,
        ),
    )
    amt = qoins_for_final_score(score)
    credit_wallet(
        conn,
        "user",
        author,
        amt,
        author,
        f"post#{pid} escalated from {level} to {new_level}",
    )
    return True


def _complete_earth_journey(
    conn: sqlite3.Connection,
    post: sqlite3.Row,
    now: datetime,
) -> bool:
    """Finish an earth-level post: freeze on CEB and archive a copy for the author."""
    pid = int(post["id"])
    score = int(post["total_score"] or 0)
    author = str(post["user_private_id"])
    prev = (post["previous_levels"] or "").strip()
    new_prev = prev + ("," if prev else "") + "earth"
    ts = now.isoformat(timespec="seconds")

    res = conn.execute(
        """
        UPDATE posts
           SET status = 'frozen',
               current_level = 'earth_frozen',
               freeze_level = 'earth',
               frozen_at_level = 'earth',
               level_end_time = ?,
               previous_levels = ?,
               qoins_settled = 1
         WHERE id = ? AND status = 'live'
        """,
        (ts, new_prev, pid),
    )
    if res.rowcount != 1:
        return False

    _insert_archived_copy(conn, post, "earth", now, original_post_id=pid)
    amt = qoins_for_final_score(score)
    credit_wallet(
        conn,
        "user",
        author,
        amt,
        author,
        f"post#{pid} journey complete",
    )
    return True


def escalate_posts(conn: sqlite3.Connection, now: datetime | None = None) -> None:
    """Advance, freeze, or archive posts whose current level window has ended."""
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff_tpl = (now - timedelta(days=LEVEL_DAYS)).isoformat(timespec="seconds")

    cur = conn.execute(
        """
        SELECT * FROM posts
        WHERE status = 'live'
          AND level_start_time IS NOT NULL
          AND datetime(level_start_time) <= datetime(?)
          AND current_level IN (
            'personal', 'village', 'tehsil', 'district',
            'state', 'country', 'continent', 'earth'
          )
        """,
        (cutoff_tpl,),
    )
    rows = cur.fetchall()
    for post in rows:
        try:
            score = int(post["total_score"] or 0)
            level = str(post["current_level"] or "personal").strip().lower()
            started_at = _parse_sqlite_datetime(post["level_start_time"])
            level_days = LEVEL_DAYS_BY_LEVEL.get(level, LEVEL_DAYS)
            if started_at is None or now < started_at + timedelta(days=level_days):
                continue

            idx = _level_idx(level)
            if idx >= len(POST_LEVEL_ORDER) - 1:
                if score <= 0:
                    _archive_live_post(conn, post, "earth", now)
                else:
                    _complete_earth_journey(conn, post, now)
                continue

            if score <= 0:
                _archive_live_post(conn, post, level, now)
                continue

            _freeze_and_ascend(conn, post, level, now)
        except sqlite3.Error:
            continue
    conn.commit()


def connected_peer_private_ids(
    conn: sqlite3.Connection, user_private_id: str
) -> set[str]:
    """Private IDs of users connected to ``user_private_id`` for PCB audience.

    Includes accepted family/social connections (both directions) and nuclear
    family links via ``family_members.account_public_id`` (bidirectional).
    """
    me = str(user_private_id or "").strip()
    peers: set[str] = set()
    if not me:
        return peers
    cur = conn.execute(
        """
        SELECT from_user_private_id AS a, to_user_private_id AS b
          FROM connection_requests
         WHERE status = 'accepted'
           AND request_type IN ('family', 'social')
           AND (from_user_private_id = ? OR to_user_private_id = ?)
        """,
        (me, me),
    )
    for row in cur:
        a = str(row["a"] or "").strip()
        b = str(row["b"] or "").strip()
        if a == me and b:
            peers.add(b)
        elif b == me and a:
            peers.add(a)

    fm_cols = _cols(conn, "family_members")
    mt_clause = ""
    if "member_type" in fm_cols:
        mt_clause = " AND LOWER(TRIM(COALESCE(fm.member_type, 'nuclear'))) = 'nuclear' "
    cur2 = conn.execute(
        f"""
        SELECT u.private_id AS oid
          FROM family_members fm
          JOIN users u ON LOWER(TRIM(u.public_id)) = LOWER(TRIM(fm.account_public_id))
         WHERE fm.user_private_id = ?
           AND TRIM(COALESCE(fm.account_public_id, '')) != ''
           {mt_clause}
        """,
        (me,),
    )
    for row in cur2:
        oid = str(row["oid"] or "").strip()
        if oid and oid != me:
            peers.add(oid)

    pub_row = conn.execute(
        "SELECT public_id FROM users WHERE private_id = ?", (me,)
    ).fetchone()
    my_pub = str(pub_row["public_id"] or "").strip() if pub_row else ""
    if my_pub:
        mt_clause_rev = ""
        if "member_type" in fm_cols:
            mt_clause_rev = (
                " AND LOWER(TRIM(COALESCE(fm2.member_type, 'nuclear'))) = 'nuclear' "
            )
        cur3 = conn.execute(
            f"""
            SELECT fm2.user_private_id AS oid
              FROM family_members fm2
             WHERE LOWER(TRIM(fm2.account_public_id)) = LOWER(?)
               AND TRIM(COALESCE(fm2.account_public_id, '')) != ''
               {mt_clause_rev}
            """,
            (my_pub,),
        )
        for row in cur3:
            oid = str(row["oid"] or "").strip()
            if oid and oid != me:
                peers.add(oid)

    peers.discard(me)
    return peers


def user_in_post_vote_scope(
    conn: sqlite3.Connection,
    post: sqlite3.Row,
    user: sqlite3.Row,
) -> bool:
    level = str(post["current_level"] or "")
    if level == "personal":
        vid = str(user["private_id"] or "").strip()
        aid = str(post["user_private_id"] or "").strip()
        if not vid or not aid:
            return False
        if vid == aid:
            return True
        return aid in connected_peer_private_ids(conn, vid)
    if level == "earth":
        return True
    uv = (user["current_location_id"] or "").strip()
    if not uv and level in {"village", "tehsil", "district", "state"}:
        return False
    if level == "village":
        return uv == (post["origin_village_id"] or "").strip()
    if level == "tehsil":
        tid = (post["origin_tehsil_id"] or "").strip()
        return bool(tid) and (uv == tid or uv.startswith(tid + "."))
    if level == "district":
        did = (post["origin_district_id"] or "").strip()
        return bool(did) and (uv == did or uv.startswith(did + ".") or did in uv)
    if level == "state":
        sid = (post["origin_state_id"] or "").strip()
        return bool(sid) and (uv == sid or uv.startswith(sid + ".") or sid in uv)
    if level == "country":
        return (user["current_country_id"] or "").strip() == (
            post["origin_country_id"] or ""
        ).strip()
    if level == "continent":
        return (user["current_continent_id"] or "").strip() == (
            post["origin_continent_id"] or ""
        ).strip()
    return False


def location_wallet_key(scope: str, geo_id: str) -> str:
    return f"{scope}|{geo_id.strip()}"


def posts_for_geo_feed(
    conn: sqlite3.Connection,
    scope: str,
    geo_id: str,
    voter_private_id: str | None = None,
) -> list[sqlite3.Row]:
    if scope == "india":
        scope = "country"
        geo_id = "IND"
    # Personal posts must never leak into geo feeds. Refuse the scope outright.
    if scope == "personal":
        return []
    gid = geo_id.strip()
    col = {
        "village": "origin_village_id",
        "tehsil": "origin_tehsil_id",
        "district": "origin_district_id",
        "state": "origin_state_id",
        "country": "origin_country_id",
        "continent": "origin_continent_id",
        "earth": None,
    }.get(scope)
    if scope == "earth":
        extra = (
            " AND LOWER(TRIM(COALESCE(p.current_level,''))) NOT IN ('personal','personal_history','private_history')"
            " AND LOWER(TRIM(COALESCE(p.current_level,''))) NOT LIKE 'personal\\_%' ESCAPE '\\'"
        )
        if "deleted_at" in _cols(conn, "posts"):
            extra += " AND (p.deleted_at IS NULL)"
        q = f"""
            SELECT p.*, u.public_id AS author_public_id, u.first_name AS author_first,
                   u.last_name AS author_last, v.vote_value AS current_user_vote
            FROM posts p
            JOIN users u ON u.private_id = p.user_private_id
            LEFT JOIN post_votes v
              ON v.post_id = p.id AND v.voter_private_id = ?
            WHERE p.status = 'live'
              AND p.current_level = 'earth'
              {extra}
            ORDER BY datetime(p.created_at) DESC, p.id DESC
            LIMIT 100
        """
        return list(conn.execute(q, (voter_private_id or "",)))
    if not col:
        return []
    extra = (
        " AND LOWER(TRIM(COALESCE(p.current_level,''))) NOT IN ('personal','personal_history','private_history')"
        " AND LOWER(TRIM(COALESCE(p.current_level,''))) NOT LIKE 'personal\\_%' ESCAPE '\\'"
    )
    if "deleted_at" in _cols(conn, "posts"):
        extra += " AND (p.deleted_at IS NULL)"
    q = f"""
        SELECT p.*, u.public_id AS author_public_id, u.first_name AS author_first,
               u.last_name AS author_last, v.vote_value AS current_user_vote
        FROM posts p
        JOIN users u ON u.private_id = p.user_private_id
        LEFT JOIN post_votes v
          ON v.post_id = p.id AND v.voter_private_id = ?
        WHERE p.status = 'live'
          AND TRIM(p.current_level) = ?
          AND p.current_level != 'personal'
          {extra}
          AND TRIM(p.{col}) = ?
        ORDER BY datetime(p.created_at) DESC, p.id DESC
        LIMIT 100
    """
    return list(conn.execute(q, (voter_private_id or "", scope, gid)))


def user_vote_on_post(
    conn: sqlite3.Connection, post_id: int, voter_pid: str, value: int
) -> tuple[bool, str]:
    if value not in (-1, 0, 1):
        return False, "invalid vote"
    post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        return False, "post not found"
    if str(post["status"]) != "live":
        return False, "post not votable"
    voter = conn.execute(
        "SELECT * FROM users WHERE private_id = ?", (voter_pid,)
    ).fetchone()
    if not voter:
        return False, "voter not found"
    if str(post["user_private_id"]) == str(voter_pid):
        return False, "cannot vote on your own post"
    if not user_in_post_vote_scope(conn, post, voter):
        return False, "out of scope"
    conn.execute(
        """
        INSERT INTO post_votes (post_id, voter_private_id, vote_value)
        VALUES (?, ?, ?)
        ON CONFLICT(post_id, voter_private_id) DO UPDATE SET
            vote_value = excluded.vote_value,
            voted_at = CURRENT_TIMESTAMP
        """,
        (post_id, voter_pid, value),
    )
    recompute_post_score(conn, post_id)
    conn.commit()
    return True, "ok"
