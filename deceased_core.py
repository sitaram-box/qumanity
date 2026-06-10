"""
Deceased users (Ancestors in Ākāśa / Space) and Akashic Records archive.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any

import planetary_core
import qoin_core

ELEMENT_ORDER = ("Fire", "Earth", "Air", "Water")


def is_mentor_user(conn: sqlite3.Connection, user_row: sqlite3.Row | None) -> bool:
    """True for Admin (Mentor) or anyone holding a filled ``mentor`` council slot."""
    if user_row is None:
        return False
    try:
        if int(user_row["is_admin"] or 0):
            return True
    except (KeyError, TypeError, ValueError):
        pass
    try:
        mentor_level = int(user_row["mentor_level"] or 0)
        if mentor_level > 0:
            return True
    except (KeyError, TypeError, ValueError):
        pass
    try:
        private_id = str(user_row["private_id"] or "").strip()
    except (KeyError, TypeError):
        private_id = ""
    if not private_id:
        return False
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM leadership_council
            WHERE current_holder_private_id = ?
              AND status = 'filled'
              AND LOWER(slot_designation) = 'mentor'
            """,
            (private_id,),
        ).fetchone()
        return bool(row and int(row["c"] or 0) > 0)
    except sqlite3.Error:
        return False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def archive_record(
    conn: sqlite3.Connection,
    *,
    record_type: str,
    data: dict[str, Any],
    original_id: int | None = None,
    user_private_id: str | None = None,
    location_id: str | None = None,
    archived_by: str = "system",
) -> int:
    planetary_core.migrate_space_schema(conn)
    cur = conn.execute(
        """
        INSERT INTO akashic_records (
            record_type, original_id, user_private_id, location_id, data, archived_by
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            record_type,
            original_id,
            user_private_id,
            location_id,
            json.dumps(data, default=str),
            archived_by,
        ),
    )
    return int(cur.lastrowid or 0)


def _karma_ledger_snapshot(conn: sqlite3.Connection, private_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, amount, reason, created_at
        FROM qoin_transactions
        WHERE user_private_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT 200
        """,
        (private_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _transfer_wallet_to_heir(
    conn: sqlite3.Connection,
    from_private_id: str,
    heir_private_id: str,
    *,
    moved_by: str,
) -> tuple[int, bool]:
    heir = conn.execute(
        "SELECT private_id FROM users WHERE private_id = ? AND COALESCE(is_deceased, 0) = 0",
        (heir_private_id,),
    ).fetchone()
    if not heir:
        return 0, False
    qoin_core.ensure_wallet(conn, "user", from_private_id)
    qoin_core.ensure_wallet(conn, "user", heir_private_id)
    balance_rupees = qoin_core.wallet_rupee_total(conn, "user", from_private_id)
    if balance_rupees <= 0:
        return 0, True
    counts = qoin_core.wallet_breakdown(conn, "user", from_private_id)
    denoms: list[int] = []
    for c in counts:
        denoms.extend([int(c["denom"])] * int(c["count"]))
    if not denoms:
        return 0, True
    ref = f"deceased-heir-{from_private_id}-{heir_private_id}"
    debited = qoin_core.debit_wallet_denoms(
        conn,
        "user",
        from_private_id,
        denoms,
        transaction_ref=ref,
        amount_rupees=balance_rupees,
    )
    if debited is None:
        return 0, False
    qoin_core.credit_wallet_denoms(
        conn,
        "user",
        heir_private_id,
        denoms,
        transaction_ref=ref,
        amount_rupees=balance_rupees,
    )
    conn.execute(
        """
        INSERT INTO qoin_transactions (user_private_id, amount, reason, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            heir_private_id,
            balance_rupees,
            f"Inherited Qoins from deceased {from_private_id} (by {moved_by})",
            _now_iso(),
        ),
    )
    return balance_rupees, True


def mark_user_deceased(
    conn: sqlite3.Connection,
    *,
    target_private_id: str,
    date_of_death: str,
    moved_by: str,
    obituary: str | None = None,
    heir_private_id: str | None = None,
) -> dict[str, Any]:
    """
    Move a live user into Space: archive posts, freeze wallet, optional heir transfer.
    """
    planetary_core.migrate_space_schema(conn)
    pid = str(target_private_id or "").strip().upper()
    if not pid:
        raise ValueError("user_private_id is required")
    user = conn.execute(
        "SELECT * FROM users WHERE private_id = ?",
        (pid,),
    ).fetchone()
    if not user:
        raise ValueError("User not found")
    if int(user["is_deceased"] or 0):
        raise ValueError("User is already marked deceased")

    final_balance = qoin_core.wallet_rupee_total(conn, "user", pid)
    transferred_to: str | None = None
    if heir_private_id:
        amt, ok = _transfer_wallet_to_heir(
            conn, pid, str(heir_private_id).strip().upper(), moved_by=moved_by
        )
        if ok:
            transferred_to = str(heir_private_id).strip().upper()
            final_balance = max(0, final_balance - amt)

    karma_archive = _karma_ledger_snapshot(conn, pid)
    loc_id = str(user["current_location_id"] or "")

    conn.execute(
        """
        INSERT INTO deceased_users (
            original_private_id, original_public_id, first_name, last_name,
            gender, date_of_birth, date_of_death, sun_sign, element,
            current_location_id, karma_ledger_archive, final_wallet_balance,
            wallet_transferred_to, obituary, moved_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(original_private_id) DO UPDATE SET
            date_of_death = excluded.date_of_death,
            obituary = excluded.obituary,
            final_wallet_balance = excluded.final_wallet_balance,
            wallet_transferred_to = excluded.wallet_transferred_to,
            moved_to_space_at = CURRENT_TIMESTAMP,
            moved_by = excluded.moved_by
        """,
        (
            pid,
            str(user["public_id"] or ""),
            str(user["first_name"] or ""),
            str(user["last_name"] or ""),
            user["gender"],
            user["date_of_birth"],
            date_of_death,
            user["sun_sign"],
            user["element"],
            loc_id or None,
            json.dumps(karma_archive, default=str),
            final_balance,
            transferred_to,
            obituary,
            moved_by,
        ),
    )

    posts = conn.execute(
        "SELECT * FROM posts WHERE user_private_id = ?",
        (pid,),
    ).fetchall()
    posts = [p for p in posts if not (dict(p).get("deleted_at"))]
    archived_posts = 0
    for post in posts:
        archive_record(
            conn,
            record_type="post",
            original_id=int(post["id"]),
            user_private_id=pid,
            location_id=post["location_id"],
            data=dict(post),
            archived_by=moved_by,
        )
        conn.execute(
            """
            UPDATE posts
            SET status = 'space_archived', archived_at_level = COALESCE(current_level, 'personal')
            WHERE id = ?
            """,
            (int(post["id"]),),
        )
        archived_posts += 1

    conn.execute(
        """
        UPDATE users
        SET is_deceased = 1,
            deceased_archived = 1,
            date_of_death = ?,
            wallet_frozen = 1,
            is_active = 0
        WHERE private_id = ?
        """,
        (date_of_death, pid),
    )

    return {
        "success": True,
        "private_id": pid,
        "archived_posts": archived_posts,
        "final_wallet_balance": final_balance,
        "wallet_transferred_to": transferred_to,
    }


def get_ancestors(
    conn: sqlite3.Connection,
    *,
    location_id: str | None = None,
    search: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    planetary_core.migrate_space_schema(conn)
    clauses = ["1=1"]
    params: list[Any] = []
    if location_id:
        clauses.append("current_location_id = ?")
        params.append(str(location_id).strip())
    if search:
        like = f"%{search.strip()}%"
        clauses.append(
            "(first_name LIKE ? OR last_name LIKE ? OR original_private_id LIKE ? OR original_public_id LIKE ?)"
        )
        params.extend([like, like, like, like])
    params.append(int(limit))
    rows = conn.execute(
        f"""
        SELECT id, original_private_id, original_public_id, first_name, last_name,
               gender, date_of_birth, date_of_death, sun_sign, element,
               current_location_id, final_wallet_balance, wallet_transferred_to,
               obituary, moved_to_space_at, moved_by
        FROM deceased_users
        WHERE {' AND '.join(clauses)}
        ORDER BY date_of_death DESC, moved_to_space_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_akashic_records(
    conn: sqlite3.Connection,
    *,
    record_type: str | None = None,
    location_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    planetary_core.migrate_space_schema(conn)
    clauses = ["1=1"]
    params: list[Any] = []
    if record_type:
        clauses.append("record_type = ?")
        params.append(record_type)
    if location_id:
        clauses.append("location_id = ?")
        params.append(location_id)
    if date_from:
        clauses.append("date(archived_at) >= date(?)")
        params.append(date_from)
    if date_to:
        clauses.append("date(archived_at) <= date(?)")
        params.append(date_to)
    params.append(int(limit))
    rows = conn.execute(
        f"""
        SELECT id, record_type, original_id, user_private_id, location_id,
               data, archived_at, archived_by
        FROM akashic_records
        WHERE {' AND '.join(clauses)}
        ORDER BY archived_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        try:
            item["data"] = json.loads(item["data"] or "{}")
        except json.JSONDecodeError:
            pass
        out.append(item)
    return out


def archive_old_election_results(conn: sqlite3.Connection, *, months: int = 6) -> int:
    """Monthly job — archive election results older than ``months``."""
    planetary_core.migrate_space_schema(conn)
    cutoff = (date.today() - timedelta(days=months * 30)).isoformat()
    try:
        rows = conn.execute(
            """
            SELECT * FROM election_cycles
            WHERE date(end_date) <= date(?) AND status IN ('completed', 'closed', 'finished')
            """,
            (cutoff,),
        ).fetchall()
    except sqlite3.Error:
        try:
            rows = conn.execute(
                """
                SELECT * FROM election_cycles
                WHERE date(end_date) <= date(?)
                """,
                (cutoff,),
            ).fetchall()
        except sqlite3.Error:
            return 0
    count = 0
    for row in rows:
        archive_record(
            conn,
            record_type="election",
            original_id=int(row["id"]),
            location_id=row["village_id"] if "village_id" in row.keys() else None,
            data=dict(row),
            archived_by="scheduler",
        )
        count += 1
    return count


def archive_old_transactions(conn: sqlite3.Connection, *, years: int = 1) -> int:
    """Yearly job — archive settled wallet transactions older than ``years``."""
    planetary_core.migrate_space_schema(conn)
    cutoff = (date.today() - timedelta(days=years * 365)).isoformat()
    rows = conn.execute(
        """
        SELECT * FROM wallet_transactions
        WHERE date(created_at) <= date(?)
        LIMIT 500
        """,
        (cutoff,),
    ).fetchall()
    count = 0
    for row in rows:
        archive_record(
            conn,
            record_type="transaction",
            original_id=int(row["id"]) if row["id"] is not None else None,
            data=dict(row),
            archived_by="scheduler",
        )
        count += 1
    return count
