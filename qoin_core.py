"""Qoin wallet balances, donation splits, and transaction logging."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

# Fixed rupee donation → (user qoin values, village qoin value or None)
DONATION_SPLITS: dict[int, tuple[list[int], int | None]] = {
    1: ([1], None),
    2: ([1], 1),
    5: ([2, 2], 1),
    10: ([5, 3, 1], 2),
    20: ([5, 5, 5], 5),
    50: ([20, 20], 10),
    100: ([50, 20, 10], 20),
    200: ([100, 50], 50),
    500: ([200, 200], 100),
}

DENOMINATIONS = (500, 200, 100, 50, 20, 10, 5, 2, 1)


def split_donation(amount: int) -> tuple[list[dict[str, int]], dict[str, int] | None]:
    """Return user Qoins (list of {rupee_value}) and optional village Qoin."""
    if amount <= 0:
        raise ValueError("Donation amount must be positive")
    if amount in DONATION_SPLITS:
        user_vals, village_val = DONATION_SPLITS[amount]
        user_coins = [{"rupee_value": v} for v in user_vals]
        village_coin = {"rupee_value": village_val} if village_val else None
        return user_coins, village_coin
    # Greedy break for custom amounts (future): highest values to user, smallest to village
    remaining = amount
    parts: list[int] = []
    for d in DENOMINATIONS:
        while remaining >= d:
            parts.append(d)
            remaining -= d
    if not parts:
        raise ValueError("Invalid donation amount")
    if len(parts) == 1:
        return [{"rupee_value": parts[0]}], None
    village_val = parts[-1]
    user_vals = parts[:-1]
    return [{"rupee_value": v} for v in user_vals], {"rupee_value": village_val}


CASH_DONATIONS_SQL = """
CREATE TABLE IF NOT EXISTS cash_donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_private_id TEXT NOT NULL,
    agent_public_id TEXT NOT NULL,
    amount_rupees INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cash_donations_donor ON cash_donations(donor_private_id);
CREATE INDEX IF NOT EXISTS idx_cash_donations_agent ON cash_donations(agent_public_id);
"""


def migrate_cash_donations(conn: sqlite3.Connection) -> None:
    conn.executescript(CASH_DONATIONS_SQL)
    conn.commit()


def migrate_qoin_transactions(conn: sqlite3.Connection) -> None:
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(qoin_transactions)")}
    additions: list[tuple[str, str]] = [
        ("recipient_type", "TEXT"),
        ("recipient_id", "TEXT"),
        ("amount_in_qoins", "INTEGER"),
        ("rupee_value", "INTEGER"),
        ("type", "TEXT"),
        ("description", "TEXT"),
    ]
    for name, decl in additions:
        if name in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE qoin_transactions ADD COLUMN {name} {decl}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_wallet(conn: sqlite3.Connection, owner_type: str, owner_id: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO wallets (owner_type, owner_id, balance)
        VALUES (?, ?, 0)
        """,
        (owner_type, owner_id),
    )


def wallet_balance(conn: sqlite3.Connection, owner_type: str, owner_id: str) -> int:
    row = conn.execute(
        "SELECT balance FROM wallets WHERE owner_type = ? AND owner_id = ?",
        (owner_type, owner_id),
    ).fetchone()
    return int(row["balance"]) if row else 0


def wallet_rupee_total(
    conn: sqlite3.Connection, owner_type: str, owner_id: str
) -> int:
    if owner_type == "user":
        row = conn.execute(
            """
            SELECT COALESCE(SUM(
                CASE
                    WHEN recipient_type = 'user' AND recipient_id = ?
                         AND COALESCE(rupee_value, 0) > 0 THEN rupee_value
                    WHEN recipient_type IS NULL AND user_private_id = ?
                         AND amount > 0 THEN amount
                    ELSE 0
                END
            ), 0) AS s
            FROM qoin_transactions
            """,
            (owner_id, owner_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(rupee_value), 0) AS s
            FROM qoin_transactions
            WHERE recipient_type = ? AND recipient_id = ?
              AND COALESCE(rupee_value, 0) > 0
            """,
            (owner_type, owner_id),
        ).fetchone()
    return int(row["s"]) if row else 0


def record_transaction(
    conn: sqlite3.Connection,
    *,
    donor_private_id: str,
    recipient_type: str,
    recipient_id: str,
    rupee_value: int,
    tx_type: str,
    description: str,
) -> None:
    """Credit one Qoin and log transaction."""
    ensure_wallet(conn, recipient_type, recipient_id)
    conn.execute(
        """
        UPDATE wallets SET balance = balance + 1
        WHERE owner_type = ? AND owner_id = ?
        """,
        (recipient_type, recipient_id),
    )
    conn.execute(
        """
        INSERT INTO qoin_transactions (
            user_private_id, amount, reason,
            recipient_type, recipient_id, amount_in_qoins, rupee_value, type, description, created_at
        ) VALUES (?, 1, ?, ?, ?, 1, ?, ?, ?, ?)
        """,
        (
            donor_private_id,
            description,
            recipient_type,
            recipient_id,
            rupee_value,
            tx_type,
            description,
            _now(),
        ),
    )


def record_cash_donation(
    conn: sqlite3.Connection,
    *,
    donor_private_id: str,
    agent_public_id: str,
    amount_rupees: int,
) -> None:
    migrate_cash_donations(conn)
    conn.execute(
        """
        INSERT INTO cash_donations (donor_private_id, agent_public_id, amount_rupees, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (donor_private_id, agent_public_id, amount_rupees, _now()),
    )


def process_donation(
    conn: sqlite3.Connection,
    *,
    donor_private_id: str,
    amount_rupees: int,
    village_id: str | None,
    method: str = "upi",
    agent_public_id: str | None = None,
) -> dict[str, Any]:
    method_norm = (method or "upi").strip().lower()
    if method_norm == "cash":
        if not agent_public_id:
            raise ValueError("Agent Account ID is required for cash donations")
        record_cash_donation(
            conn,
            donor_private_id=donor_private_id,
            agent_public_id=agent_public_id,
            amount_rupees=amount_rupees,
        )
    user_coins, village_coin = split_donation(amount_rupees)
    for coin in user_coins:
        record_transaction(
            conn,
            donor_private_id=donor_private_id,
            recipient_type="user",
            recipient_id=donor_private_id,
            rupee_value=int(coin["rupee_value"]),
            tx_type="donation_user",
            description=f"Donation ₹{amount_rupees} — user Qoin ₹{coin['rupee_value']}",
        )
    if village_coin and village_id:
        record_transaction(
            conn,
            donor_private_id=donor_private_id,
            recipient_type="village",
            recipient_id=village_id,
            rupee_value=int(village_coin["rupee_value"]),
            tx_type="donation_village",
            description=f"Donation ₹{amount_rupees} — village Qoin ₹{village_coin['rupee_value']}",
        )
    return {
        "amount_rupees": amount_rupees,
        "method": method_norm,
        "agent_public_id": agent_public_id,
        "user_coins": user_coins,
        "village_coin": village_coin,
        "user_balance": wallet_balance(conn, "user", donor_private_id),
        "user_rupee_total": wallet_rupee_total(conn, "user", donor_private_id),
        "village_balance": wallet_balance(conn, "village", village_id) if village_id else 0,
        "village_rupee_total": wallet_rupee_total(conn, "village", village_id)
        if village_id
        else 0,
    }


def user_transactions(
    conn: sqlite3.Connection, user_private_id: str, *, limit: int = 50
) -> list[dict[str, Any]]:
    migrate_qoin_transactions(conn)
    cur = conn.execute(
        """
        SELECT id, amount, reason, rupee_value, type, description, created_at,
               recipient_type, recipient_id
        FROM qoin_transactions
        WHERE user_private_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        (user_private_id, limit),
    )
    out: list[dict[str, Any]] = []
    for r in cur:
        out.append(
            {
                "id": int(r["id"]),
                "amount": int(r["amount"] or 0),
                "reason": str(r["reason"] or r["description"] or ""),
                "rupee_value": int(r["rupee_value"] or 0) if r["rupee_value"] else None,
                "type": str(r["type"] or ""),
                "created_at": str(r["created_at"] or ""),
                "recipient_type": str(r["recipient_type"] or ""),
                "recipient_id": str(r["recipient_id"] or ""),
            }
        )
    return out


def credit_signup_bonus(conn: sqlite3.Connection, user_private_id: str) -> None:
    """Admin/demo-created accounts: 1 Qoin worth ₹1."""
    record_transaction(
        conn,
        donor_private_id=user_private_id,
        recipient_type="user",
        recipient_id=user_private_id,
        rupee_value=1,
        tx_type="signup_bonus",
        description="Account activation bonus (1 Qoin, ₹1)",
    )


def village_donation_report(
    conn: sqlite3.Connection, village_id: str
) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT id, user_private_id, rupee_value, description, created_at
        FROM qoin_transactions
        WHERE recipient_type = 'village' AND recipient_id = ?
          AND type = 'donation_village'
        ORDER BY datetime(created_at) DESC
        LIMIT 50
        """,
        (village_id,),
    ).fetchall()
    sum_row = conn.execute(
        """
        SELECT COUNT(*) AS n, COALESCE(SUM(rupee_value), 0) AS rupees
        FROM qoin_transactions
        WHERE recipient_type = 'village' AND recipient_id = ?
          AND type = 'donation_village'
        """,
        (village_id,),
    ).fetchone()
    return {
        "village_id": village_id,
        "total_qoins": int(sum_row["n"]) if sum_row else 0,
        "total_rupees": int(sum_row["rupees"]) if sum_row else 0,
        "recent": [
            {
                "id": int(r["id"]),
                "donor_private_id": str(r["user_private_id"] or ""),
                "rupee_value": int(r["rupee_value"] or 0),
                "description": str(r["description"] or ""),
                "created_at": str(r["created_at"] or ""),
            }
            for r in rows
        ],
    }
