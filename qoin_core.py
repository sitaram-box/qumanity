"""Qoin economy — fixed denominations, weekly settlement, nested wallets, karma."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

# Fixed rupee denominations (Indian coins/notes)
DENOMINATIONS: tuple[int, ...] = (2000, 500, 200, 100, 50, 20, 10, 5, 2, 1)

# Legacy donation split preview (registration UI hints)
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

NESTED_WALLET_LEVELS: tuple[str, ...] = ("village", "tehsil", "district", "state", "nation")
DONATION_COUNCIL_SHARE_PCT = 20  # each of 5 levels gets 20% of the council half

DEFAULT_KARMA_ACTIONS: tuple[tuple[str, str, int], ...] = (
    ("plant_tree", "Plant a tree (verified)", 10),
    ("teach_hour", "Teach 1 hour", 20),
    ("council_day", "Serve on Village Council (per day)", 50),
    ("report_issue", "Report a verified issue", 5),
)

KIOSK_WALLET_OWNER_TYPE = "kiosk"
GOVERNANCE_WALLET_OWNER_TYPE = "governance"
GOVERNANCE_WALLET_OWNER_ID = "mint"

PENDING_TRANSACTIONS_SQL = """
CREATE TABLE IF NOT EXISTS pending_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT UNIQUE NOT NULL,
    from_user_id TEXT,
    to_user_id TEXT,
    to_wallet_type TEXT,
    to_wallet_id TEXT,
    amount_rupees INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled INTEGER NOT NULL DEFAULT 0,
    settled_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pending_txn_settled ON pending_transactions(settled, created_at);
CREATE INDEX IF NOT EXISTS idx_pending_txn_from ON pending_transactions(from_user_id);
CREATE INDEX IF NOT EXISTS idx_pending_txn_to ON pending_transactions(to_user_id);

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_type TEXT NOT NULL,
    wallet_id TEXT NOT NULL,
    transaction_ref TEXT NOT NULL,
    amount_rupees INTEGER NOT NULL,
    qoins_list TEXT,
    balance_after TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wallet_txn_owner ON wallet_transactions(wallet_type, wallet_id, created_at);

CREATE TABLE IF NOT EXISTS weekly_statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    statement_data TEXT NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_private_id, week_start, week_end)
);
CREATE INDEX IF NOT EXISTS idx_weekly_stmt_user ON weekly_statements(user_private_id, week_end DESC);

CREATE TABLE IF NOT EXISTS karma_action_types (
    action_code TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    rupee_value INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS karma_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    action_code TEXT NOT NULL,
    amount_rupees INTEGER NOT NULL,
    description TEXT,
    verified INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settled INTEGER NOT NULL DEFAULT 0,
    settled_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_karma_txn_user ON karma_transactions(user_private_id, settled);

CREATE TABLE IF NOT EXISTS settlement_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    users_settled INTEGER NOT NULL DEFAULT 0,
    insufficient_users TEXT,
    triggered_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

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

WALLET_PAISE_LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS wallet_paise_ledger (
    wallet_type TEXT NOT NULL,
    wallet_id TEXT NOT NULL,
    balance_paise INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (wallet_type, wallet_id)
);
"""


def min_qoins_for_amount(amount: int) -> list[int]:
    """Greedy decomposition into fixed denominations (largest first)."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    remaining = int(amount)
    out: list[int] = []
    for d in DENOMINATIONS:
        while remaining >= d:
            out.append(d)
            remaining -= d
    if remaining != 0:
        raise ValueError(f"Cannot represent ₹{amount} with fixed denominations")
    return out


def total_rupees_from_denoms(denoms: list[int]) -> int:
    return sum(int(x) for x in denoms)


def denoms_to_counts(denoms: list[int]) -> list[dict[str, int]]:
    counts: dict[int, int] = {}
    for d in denoms:
        counts[d] = counts.get(d, 0) + 1
    return [{"denom": d, "count": counts[d]} for d in sorted(counts.keys(), reverse=True)]


def counts_to_denoms(counts: list[dict[str, int]]) -> list[int]:
    out: list[int] = []
    for item in counts:
        d = int(item.get("denom") or item.get("rupee_value") or 0)
        c = int(item.get("count") or 0)
        if d > 0 and c > 0:
            out.extend([d] * c)
    return out


def _encryption_key() -> bytes:
    raw = os.environ.get(
        "QOIN_WALLET_ENCRYPTION_KEY",
        "dev-insecure-qoin-key-change-me",
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def encrypt_json(obj: Any) -> str:
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    key = _encryption_key()
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(xored).decode("ascii")


def decrypt_json(blob: str | None) -> Any:
    if not blob:
        return []
    try:
        raw = base64.urlsafe_b64decode(blob.encode("ascii"))
    except (ValueError, TypeError):
        return []
    key = _encryption_key()
    plain = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    try:
        return json.loads(plain.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def migrate_qoin_economy_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(PENDING_TRANSACTIONS_SQL)
    conn.executescript(WALLET_PAISE_LEDGER_SQL)
    cols = _cols(conn, "wallets")
    if "qoins_encrypted" not in cols:
        try:
            conn.execute("ALTER TABLE wallets ADD COLUMN qoins_encrypted TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    _seed_karma_action_types(conn)
    ensure_wallet(conn, GOVERNANCE_WALLET_OWNER_TYPE, GOVERNANCE_WALLET_OWNER_ID)
    ensure_wallet(conn, KIOSK_WALLET_OWNER_TYPE, "platform")


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


def _seed_karma_action_types(conn: sqlite3.Connection) -> None:
    for code, label, val in DEFAULT_KARMA_ACTIONS:
        conn.execute(
            """
            INSERT OR IGNORE INTO karma_action_types (action_code, label, rupee_value, active)
            VALUES (?, ?, ?, 1)
            """,
            (code, label, val),
        )


def ensure_wallet(conn: sqlite3.Connection, owner_type: str, owner_id: str) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO wallets (owner_type, owner_id, balance, qoins_encrypted)
        VALUES (?, ?, 0, ?)
        """,
        (owner_type, owner_id, encrypt_json([])),
    )


def _read_wallet_counts(
    conn: sqlite3.Connection, owner_type: str, owner_id: str
) -> list[dict[str, int]]:
    ensure_wallet(conn, owner_type, owner_id)
    row = conn.execute(
        """
        SELECT balance, qoins_encrypted FROM wallets
        WHERE owner_type = ? AND owner_id = ?
        """,
        (owner_type, owner_id),
    ).fetchone()
    if not row:
        return []
    enc = row["qoins_encrypted"] if "qoins_encrypted" in row.keys() else None
    counts = decrypt_json(enc)
    if counts:
        return [
            {"denom": int(c.get("denom") or c.get("rupee_value") or 0), "count": int(c.get("count") or 0)}
            for c in counts
            if int(c.get("denom") or c.get("rupee_value") or 0) > 0 and int(c.get("count") or 0) > 0
        ]
    # Legacy integer balance → ₹1 Qoins
    legacy = int(row["balance"] or 0)
    if legacy > 0:
        migrated = [{"denom": 1, "count": legacy}]
        _write_wallet_counts(conn, owner_type, owner_id, migrated)
        return migrated
    return []


def _write_wallet_counts(
    conn: sqlite3.Connection,
    owner_type: str,
    owner_id: str,
    counts: list[dict[str, int]],
) -> None:
    total_coins = sum(int(c["count"]) for c in counts)
    conn.execute(
        """
        UPDATE wallets SET balance = ?, qoins_encrypted = ?
        WHERE owner_type = ? AND owner_id = ?
        """,
        (total_coins, encrypt_json(counts), owner_type, owner_id),
    )


def wallet_balance(conn: sqlite3.Connection, owner_type: str, owner_id: str) -> int:
    counts = _read_wallet_counts(conn, owner_type, owner_id)
    return sum(int(c["count"]) for c in counts)


def wallet_rupee_total(conn: sqlite3.Connection, owner_type: str, owner_id: str) -> int:
    counts = _read_wallet_counts(conn, owner_type, owner_id)
    return sum(int(c["denom"]) * int(c["count"]) for c in counts)


def wallet_breakdown(
    conn: sqlite3.Connection, owner_type: str, owner_id: str
) -> list[dict[str, int]]:
    counts = _read_wallet_counts(conn, owner_type, owner_id)
    return sorted(counts, key=lambda x: int(x["denom"]), reverse=True)


def _denoms_from_counts(counts: list[dict[str, int]]) -> list[int]:
    return counts_to_denoms(counts)


def _add_denoms_to_counts(counts: list[dict[str, int]], denoms: list[int]) -> list[dict[str, int]]:
    m = {int(c["denom"]): int(c["count"]) for c in counts}
    for d in denoms:
        m[d] = m.get(d, 0) + 1
    return [{"denom": d, "count": m[d]} for d in sorted(m.keys(), reverse=True) if m[d] > 0]


def _remove_denoms_from_counts(
    counts: list[dict[str, int]], denoms: list[int]
) -> list[dict[str, int]] | None:
    m = {int(c["denom"]): int(c["count"]) for c in counts}
    for d in denoms:
        if m.get(d, 0) < 1:
            return None
        m[d] -= 1
        if m[d] == 0:
            del m[d]
    return [{"denom": d, "count": m[d]} for d in sorted(m.keys(), reverse=True)]


def credit_wallet_denoms(
    conn: sqlite3.Connection,
    owner_type: str,
    owner_id: str,
    denoms: list[int],
    *,
    transaction_ref: str,
    amount_rupees: int,
) -> list[dict[str, int]]:
    ensure_wallet(conn, owner_type, owner_id)
    counts = _read_wallet_counts(conn, owner_type, owner_id)
    new_counts = _add_denoms_to_counts(counts, denoms)
    _write_wallet_counts(conn, owner_type, owner_id, new_counts)
    conn.execute(
        """
        INSERT INTO wallet_transactions (
            wallet_type, wallet_id, transaction_ref, amount_rupees,
            qoins_list, balance_after, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_type,
            owner_id,
            transaction_ref,
            amount_rupees,
            encrypt_json(denoms_to_counts(denoms)),
            encrypt_json(new_counts),
            _now(),
        ),
    )
    return new_counts


def credit_registration_tier_wallet(
    conn: sqlite3.Connection,
    tier: str,
    wallet_id: str,
    amount_rupees: int,
    *,
    transaction_ref: str,
) -> list[dict[str, int]] | None:
    """Credit one 10-tier registration donation recipient (earth…village or user)."""
    amount = int(amount_rupees)
    if amount <= 0 or not str(wallet_id or "").strip():
        return None
    owner_type = "nation" if tier == "country" else ("user" if tier in {"referrer", "new_user"} else tier)
    denoms = min_qoins_for_amount(amount)
    return credit_wallet_denoms(
        conn,
        owner_type,
        str(wallet_id).strip(),
        denoms,
        transaction_ref=transaction_ref,
        amount_rupees=amount,
    )


def _location_owner_type(tier: str) -> str:
    if tier == "country":
        return "nation"
    return tier


def credit_wallet_paise(
    conn: sqlite3.Connection,
    owner_type: str,
    owner_id: str,
    paise: int,
    *,
    transaction_ref: str,
) -> int:
    """
    Credit a wallet using paise. Accumulates sub-rupee balances; converts to Qoins
    when balance reaches 100 paise or more. Returns remaining paise balance.
    """
    migrate_qoin_economy_tables(conn)
    amount_paise = int(paise)
    if amount_paise <= 0 or not str(owner_id or "").strip():
        return 0
    ot = str(owner_type).strip()
    oid = str(owner_id).strip()
    ensure_wallet(conn, ot, oid)
    conn.execute(
        """
        INSERT INTO wallet_paise_ledger (wallet_type, wallet_id, balance_paise, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(wallet_type, wallet_id) DO UPDATE SET
            balance_paise = balance_paise + excluded.balance_paise,
            updated_at = excluded.updated_at
        """,
        (ot, oid, amount_paise, _now()),
    )
    row = conn.execute(
        """
        SELECT balance_paise FROM wallet_paise_ledger
        WHERE wallet_type = ? AND wallet_id = ?
        """,
        (ot, oid),
    ).fetchone()
    balance = int(row["balance_paise"] or 0) if row else amount_paise
    whole_rupees = balance // 100
    remainder = balance % 100
    if whole_rupees > 0:
        credit_wallet_denoms(
            conn,
            ot,
            oid,
            min_qoins_for_amount(whole_rupees),
            transaction_ref=transaction_ref,
            amount_rupees=whole_rupees,
        )
        conn.execute(
            """
            UPDATE wallet_paise_ledger
            SET balance_paise = ?, updated_at = ?
            WHERE wallet_type = ? AND wallet_id = ?
            """,
            (remainder, _now(), ot, oid),
        )
        return remainder
    return balance


def credit_location_wallets_from_distribution(
    conn: sqlite3.Connection,
    distribution: list[dict[str, Any]],
    *,
    ref_suffix: str,
    location_tiers_only: bool = True,
) -> None:
    """Credit geographic tiers immediately using paise-precision ledger."""
    migrate_qoin_economy_tables(conn)
    for item in distribution:
        tier = str(item.get("tier") or "")
        if location_tiers_only and tier not in LOCATION_TIERS:
            continue
        wallet_id = str(item.get("wallet_id") or "").strip()
        if not wallet_id:
            continue
        paise = int(item.get("amount_paise") or 0)
        if paise <= 0:
            rupees = item.get("rupee_amount")
            if rupees:
                paise = int(round(float(rupees) * 100))
        if paise <= 0:
            continue
        owner_type = _location_owner_type(tier) if tier in LOCATION_TIERS else (
            "user" if tier in {"referrer", "new_user"} else tier
        )
        credit_wallet_paise(
            conn,
            owner_type,
            wallet_id,
            paise,
            transaction_ref=f"reg-loc-{ref_suffix}-{tier}",
        )


LOCATION_TIERS: tuple[str, ...] = (
    "earth",
    "continent",
    "country",
    "zone",
    "state",
    "district",
    "tehsil",
    "village",
)


def debit_wallet_denoms(
    conn: sqlite3.Connection,
    owner_type: str,
    owner_id: str,
    denoms: list[int],
    *,
    transaction_ref: str,
    amount_rupees: int,
) -> list[dict[str, int]] | None:
    ensure_wallet(conn, owner_type, owner_id)
    counts = _read_wallet_counts(conn, owner_type, owner_id)
    new_counts = _remove_denoms_from_counts(counts, denoms)
    if new_counts is None:
        return None
    _write_wallet_counts(conn, owner_type, owner_id, new_counts)
    conn.execute(
        """
        INSERT INTO wallet_transactions (
            wallet_type, wallet_id, transaction_ref, amount_rupees,
            qoins_list, balance_after, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            owner_type,
            owner_id,
            transaction_ref,
            -abs(amount_rupees),
            encrypt_json(denoms_to_counts(denoms)),
            encrypt_json(new_counts),
            _now(),
        ),
    )
    return new_counts


def new_transaction_id() -> str:
    return f"TXN-{uuid.uuid4().hex[:16].upper()}"


def record_pending_transaction(
    conn: sqlite3.Connection,
    *,
    from_user_id: str | None,
    to_user_id: str | None = None,
    to_wallet_type: str | None = None,
    to_wallet_id: str | None = None,
    amount_rupees: int,
    transaction_type: str,
    description: str = "",
    transaction_id: str | None = None,
) -> str:
    migrate_qoin_economy_tables(conn)
    if amount_rupees <= 0:
        raise ValueError("amount_rupees must be positive")
    txid = transaction_id or new_transaction_id()
    conn.execute(
        """
        INSERT INTO pending_transactions (
            transaction_id, from_user_id, to_user_id,
            to_wallet_type, to_wallet_id, amount_rupees,
            transaction_type, description, created_at, settled
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            txid,
            from_user_id,
            to_user_id,
            to_wallet_type,
            to_wallet_id,
            amount_rupees,
            transaction_type,
            description,
            _now(),
        ),
    )
    return txid


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


def split_donation(amount: int) -> tuple[list[dict[str, int]], dict[str, int] | None]:
    """Preview helper for legacy UI — maps to weekly pending donation."""
    if amount <= 0:
        raise ValueError("Donation amount must be positive")
    if amount in DONATION_SPLITS:
        user_vals, village_val = DONATION_SPLITS[amount]
        user_coins = [{"rupee_value": v} for v in user_vals]
        village_coin = {"rupee_value": village_val} if village_val else None
        return user_coins, village_coin
    denoms = min_qoins_for_amount(amount)
    ethical = denoms[: max(1, len(denoms) // 2)]
    council = denoms[len(ethical) :]
    village_val = council[0] if council else None
    return [{"rupee_value": v} for v in ethical], (
        {"rupee_value": village_val} if village_val else None
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
    """Record donation as pending (settled weekly)."""
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
    meta = json.dumps({"village_id": village_id, "method": method_norm})
    record_pending_transaction(
        conn,
        from_user_id=donor_private_id,
        amount_rupees=amount_rupees,
        transaction_type="donation",
        description=f"Donation ₹{amount_rupees} ({method_norm}) {meta}",
        transaction_id=new_transaction_id(),
    )
    user_coins, village_coin = split_donation(amount_rupees)
    return {
        "amount_rupees": amount_rupees,
        "method": method_norm,
        "agent_public_id": agent_public_id,
        "user_coins": user_coins,
        "village_coin": village_coin,
        "pending": True,
        "user_balance": wallet_balance(conn, "user", donor_private_id),
        "user_rupee_total": wallet_rupee_total(conn, "user", donor_private_id),
        "village_balance": wallet_balance(conn, "village", village_id) if village_id else 0,
        "village_rupee_total": wallet_rupee_total(conn, "village", village_id)
        if village_id
        else 0,
    }


def record_commercial_transaction(
    conn: sqlite3.Connection,
    *,
    buyer_private_id: str,
    seller_private_id: str,
    amount_rupees: int,
    description: str = "",
) -> str:
    return record_pending_transaction(
        conn,
        from_user_id=buyer_private_id,
        to_user_id=seller_private_id,
        amount_rupees=amount_rupees,
        transaction_type="commercial",
        description=description or f"Commercial ₹{amount_rupees}",
    )


def record_subscription_transaction(
    conn: sqlite3.Connection,
    *,
    payer_private_id: str,
    amount_rupees: int,
    description: str = "",
) -> str:
    return record_pending_transaction(
        conn,
        from_user_id=payer_private_id,
        to_wallet_type=KIOSK_WALLET_OWNER_TYPE,
        to_wallet_id="platform",
        amount_rupees=amount_rupees,
        transaction_type="subscription",
        description=description or f"Subscription ₹{amount_rupees}",
    )


def record_karma_action(
    conn: sqlite3.Connection,
    *,
    user_private_id: str,
    action_code: str,
    description: str = "",
    verified: bool = True,
) -> dict[str, Any]:
    migrate_qoin_economy_tables(conn)
    row = conn.execute(
        """
        SELECT action_code, label, rupee_value, active
        FROM karma_action_types WHERE action_code = ? AND active = 1
        """,
        (action_code,),
    ).fetchone()
    if not row:
        raise ValueError(f"Unknown or inactive karma action: {action_code}")
    amount = int(row["rupee_value"])
    try:
        import varna_core

        amount = varna_core.apply_karma_category_bonus(
            conn, user_private_id, action_code, amount
        )
    except Exception:
        pass
    conn.execute(
        """
        INSERT INTO karma_transactions (
            user_private_id, action_code, amount_rupees, description, verified, created_at, settled
        ) VALUES (?, ?, ?, ?, ?, ?, 0)
        """,
        (
            user_private_id,
            action_code,
            amount,
            description or str(row["label"]),
            1 if verified else 0,
            _now(),
        ),
    )
    kid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    result = {
        "karma_transaction_id": kid,
        "action_code": action_code,
        "label": str(row["label"]),
        "amount_rupees": amount,
        "pending_qoins": min_qoins_for_amount(amount),
    }
    if verified:
        try:
            import referral_core

            referral_core.process_referral_on_karma(
                conn,
                user_private_id=user_private_id,
                action_code=action_code,
                amount_rupees=amount,
            )
        except Exception:
            pass
    return result


def week_bounds_for_date(d: date | None = None) -> tuple[date, date]:
    """ISO week ending Sunday (week_start Monday, week_end Sunday)."""
    ref = d or datetime.now(timezone.utc).date()
    # Monday = 0 … Sunday = 6
    week_start = ref - timedelta(days=ref.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _parse_meta_village(description: str) -> str | None:
    if not description:
        return None
    try:
        if "{" in description:
            chunk = description[description.index("{") :]
            meta = json.loads(chunk)
            vid = meta.get("village_id")
            return str(vid).strip() if vid else None
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _hierarchy_wallet_ids(
    hierarchy: list[dict[str, str]],
) -> dict[str, str]:
    """Map village/tehsil/district/state/nation ids from hierarchy list."""
    out: dict[str, str] = {"nation": "IND"}
    for item in hierarchy:
        scope = str(item.get("scope") or "").strip().lower()
        fid = str(item.get("id") or "").strip()
        if scope in NESTED_WALLET_LEVELS and fid:
            out[scope] = fid
    return out


def _allocate_equal_parts(total: int, parts: int) -> list[int]:
    if parts <= 0:
        return []
    base = total // parts
    rem = total % parts
    return [base + (1 if i < rem else 0) for i in range(parts)]


def _settle_donation_pending(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    hierarchy_resolver: Callable[[str], list[dict[str, str]]] | None,
) -> None:
    amount = int(row["amount_rupees"])
    donor = str(row["from_user_id"] or "")
    tx_ref = str(row["transaction_id"])
    ethical_half = amount // 2
    council_half = amount - ethical_half
    if donor and ethical_half > 0:
        denoms = min_qoins_for_amount(ethical_half)
        credit_wallet_denoms(
            conn, "user", donor, denoms,
            transaction_ref=tx_ref, amount_rupees=ethical_half,
        )
    village_id = _parse_meta_village(str(row["description"] or ""))
    if not village_id and hierarchy_resolver and donor:
        hier = hierarchy_resolver(donor)
        village_id = hier.get("village") if isinstance(hier, dict) else None
        if not village_id and hier:
            wallets = _hierarchy_wallet_ids(hier) if isinstance(hier, list) else {}
            village_id = wallets.get("village")
    if council_half <= 0:
        return
    if hierarchy_resolver and donor:
        hier_list = hierarchy_resolver(donor)
        if isinstance(hier_list, list):
            wallets = _hierarchy_wallet_ids(hier_list)
        else:
            wallets = hier_list if isinstance(hier_list, dict) else {}
    elif village_id:
        wallets = {"village": village_id, "nation": "IND"}
    else:
        wallets = {"nation": "IND"}
    shares = _allocate_equal_parts(council_half, len(NESTED_WALLET_LEVELS))
    for level, share in zip(NESTED_WALLET_LEVELS, shares):
        if share <= 0:
            continue
        wid = wallets.get(level) or ("IND" if level == "nation" else None)
        if not wid:
            continue
        denoms = min_qoins_for_amount(share)
        credit_wallet_denoms(
            conn, level, wid, denoms,
            transaction_ref=tx_ref, amount_rupees=share,
        )


def _user_net_rupees_for_week(
    conn: sqlite3.Connection,
    user_id: str,
    week_start: date,
    week_end: date,
) -> int:
    ws = week_start.isoformat()
    we = week_end.isoformat()
    credit = conn.execute(
        """
        SELECT COALESCE(SUM(amount_rupees), 0) AS s FROM pending_transactions
        WHERE settled = 0 AND to_user_id = ?
          AND transaction_type IN ('commercial', 'contribution', 'karma')
          AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        """,
        (user_id, ws, we),
    ).fetchone()
    debit = conn.execute(
        """
        SELECT COALESCE(SUM(amount_rupees), 0) AS s FROM pending_transactions
        WHERE settled = 0 AND from_user_id = ?
          AND transaction_type IN ('commercial', 'subscription')
          AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        """,
        (user_id, ws, we),
    ).fetchone()
    return int(credit["s"]) - int(debit["s"])


def _users_with_week_activity(
    conn: sqlite3.Connection,
    week_start: date,
    week_end: date,
) -> set[str]:
    ws, we = week_start.isoformat(), week_end.isoformat()
    users: set[str] = set()
    for row in conn.execute(
        """
        SELECT DISTINCT from_user_id AS uid FROM pending_transactions
        WHERE settled = 0 AND from_user_id IS NOT NULL
          AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        UNION
        SELECT DISTINCT to_user_id FROM pending_transactions
        WHERE settled = 0 AND to_user_id IS NOT NULL
          AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        """,
        (ws, we, ws, we),
    ):
        if row["uid"]:
            users.add(str(row["uid"]))
    for row in conn.execute(
        """
        SELECT DISTINCT user_private_id FROM karma_transactions
        WHERE settled = 0
          AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        """,
        (ws, we),
    ):
        users.add(str(row["user_private_id"]))
    return users


def _build_statement_for_user(
    conn: sqlite3.Connection,
    user_id: str,
    week_start: date,
    week_end: date,
    *,
    insufficient: bool = False,
) -> dict[str, Any]:
    ws, we = week_start.isoformat(), week_end.isoformat()
    opening = wallet_breakdown(conn, "user", user_id)
    pending_rows = conn.execute(
        """
        SELECT * FROM pending_transactions
        WHERE settled = 0
          AND (from_user_id = ? OR to_user_id = ?)
          AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        ORDER BY datetime(created_at)
        """,
        (user_id, user_id, ws, we),
    ).fetchall()
    karma_rows = conn.execute(
        """
        SELECT kt.*, ka.label AS action_label
        FROM karma_transactions kt
        LEFT JOIN karma_action_types ka ON ka.action_code = kt.action_code
        WHERE kt.user_private_id = ? AND kt.settled = 0
          AND date(kt.created_at) >= date(?) AND date(kt.created_at) <= date(?)
        ORDER BY datetime(kt.created_at)
        """,
        (user_id, ws, we),
    ).fetchall()
    net = _user_net_rupees_for_week(conn, user_id, week_start, week_end)
    karma_earnings = [
        {
            "action_code": str(r["action_code"]),
            "label": str(r["action_label"] or r["description"] or r["action_code"]),
            "amount_rupees": int(r["amount_rupees"]),
            "qoins": min_qoins_for_amount(int(r["amount_rupees"])),
            "created_at": str(r["created_at"]),
        }
        for r in karma_rows
    ]
    txns = [
        {
            "transaction_id": str(r["transaction_id"]),
            "type": str(r["transaction_type"]),
            "amount_rupees": int(r["amount_rupees"]),
            "direction": "credit" if str(r["to_user_id"]) == user_id else "debit",
            "description": str(r["description"] or ""),
            "created_at": str(r["created_at"]),
        }
        for r in pending_rows
    ]
    closing = wallet_breakdown(conn, "user", user_id)
    return {
        "week_start": ws,
        "week_end": we,
        "opening_balance": opening,
        "closing_balance": closing,
        "transactions": txns,
        "karma_earnings": karma_earnings,
        "summary": {
            "net_rupees": net,
            "qoins_to_receive": min_qoins_for_amount(net) if net > 0 else [],
            "qoins_to_debit": min_qoins_for_amount(-net) if net < 0 else [],
        },
        "insufficient_funds": insufficient,
    }


def process_weekly_settlement(
    conn: sqlite3.Connection,
    *,
    week_start: date | None = None,
    week_end: date | None = None,
    triggered_by: str = "scheduler",
    hierarchy_resolver: Callable[[str], list[dict[str, str]]] | None = None,
    notify_fn: Callable[[sqlite3.Connection, str, str, str], None] | None = None,
) -> dict[str, Any]:
    """
    End-of-week settlement: net pending → Qoin transfers, statements, mark settled.
    """
    migrate_qoin_economy_tables(conn)
    if week_start is None or week_end is None:
        week_start, week_end = week_bounds_for_date()
    ws, we = week_start.isoformat(), week_end.isoformat()

    pending_rows = conn.execute(
        """
        SELECT * FROM pending_transactions
        WHERE settled = 0 AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        ORDER BY id
        """,
        (ws, we),
    ).fetchall()

    insufficient_users: list[str] = []
    users_settled = 0

    # Mint karma from governance container first
    karma_rows = conn.execute(
        """
        SELECT * FROM karma_transactions
        WHERE settled = 0 AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        """,
        (ws, we),
    ).fetchall()
    for kr in karma_rows:
        uid = str(kr["user_private_id"])
        amt = int(kr["amount_rupees"])
        denoms = min_qoins_for_amount(amt)
        ref = f"KARMA-SETTLE-{kr['id']}"
        credit_wallet_denoms(
            conn, "user", uid, denoms,
            transaction_ref=ref, amount_rupees=amt,
        )
        conn.execute(
            "UPDATE karma_transactions SET settled = 1, settled_at = ? WHERE id = ?",
            (_now(), int(kr["id"])),
        )

    # Donation splits + wallet-target pending (subscription → kiosk)
    for row in pending_rows:
        ttype = str(row["transaction_type"])
        if ttype == "donation":
            _settle_donation_pending(conn, row, hierarchy_resolver)
        elif ttype == "subscription":
            wid = str(row["to_wallet_id"] or "platform")
            denoms = min_qoins_for_amount(int(row["amount_rupees"]))
            credit_wallet_denoms(
                conn, KIOSK_WALLET_OWNER_TYPE, wid, denoms,
                transaction_ref=str(row["transaction_id"]),
                amount_rupees=int(row["amount_rupees"]),
            )
        elif row["to_wallet_type"] and row["to_wallet_id"]:
            wtype = str(row["to_wallet_type"])
            wid = str(row["to_wallet_id"])
            denoms = min_qoins_for_amount(int(row["amount_rupees"]))
            credit_wallet_denoms(
                conn, wtype, wid, denoms,
                transaction_ref=str(row["transaction_id"]),
                amount_rupees=int(row["amount_rupees"]),
            )

    active_users = _users_with_week_activity(conn, week_start, week_end)

    for uid in sorted(active_users):
        opening_snapshot = wallet_breakdown(conn, "user", uid)
        net = _user_net_rupees_for_week(conn, uid, week_start, week_end)
        insufficient = False
        if net > 0:
            denoms = min_qoins_for_amount(net)
            credit_wallet_denoms(
                conn, "user", uid, denoms,
                transaction_ref=f"SETTLE-{ws}-{uid}",
                amount_rupees=net,
            )
        elif net < 0:
            denoms = min_qoins_for_amount(-net)
            result = debit_wallet_denoms(
                conn, "user", uid, denoms,
                transaction_ref=f"SETTLE-{ws}-{uid}",
                amount_rupees=net,
            )
            if result is None:
                insufficient = True
                insufficient_users.append(uid)
                _write_wallet_counts(conn, "user", uid, opening_snapshot)
                if notify_fn:
                    notify_fn(
                        conn,
                        uid,
                        "Weekly settlement — insufficient Qoins",
                        f"Your net obligation for week ending {we} is ₹{-net}. "
                        "Please add Qoins before the next settlement.",
                    )
        stmt = _build_statement_for_user(
            conn, uid, week_start, week_end, insufficient=insufficient,
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO weekly_statements (
                user_private_id, week_start, week_end, statement_data, generated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (uid, ws, we, json.dumps(stmt), _now()),
        )
        users_settled += 1

    now_ts = _now()
    conn.execute(
        """
        UPDATE pending_transactions SET settled = 1, settled_at = ?
        WHERE settled = 0 AND date(created_at) >= date(?) AND date(created_at) <= date(?)
        """,
        (now_ts, ws, we),
    )
    conn.execute(
        """
        INSERT INTO settlement_runs (week_start, week_end, users_settled, insufficient_users, triggered_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ws,
            we,
            users_settled,
            json.dumps(insufficient_users),
            triggered_by,
        ),
    )
    return {
        "week_start": ws,
        "week_end": we,
        "users_settled": users_settled,
        "insufficient_users": insufficient_users,
        "pending_cleared": len(pending_rows),
    }


def list_weekly_statements(
    conn: sqlite3.Connection, user_private_id: str, *, limit: int = 52
) -> list[dict[str, Any]]:
    migrate_qoin_economy_tables(conn)
    cur = conn.execute(
        """
        SELECT id, week_start, week_end, generated_at
        FROM weekly_statements
        WHERE user_private_id = ?
        ORDER BY week_end DESC
        LIMIT ?
        """,
        (user_private_id, limit),
    )
    return [
        {
            "id": int(r["id"]),
            "week_start": str(r["week_start"]),
            "week_end": str(r["week_end"]),
            "generated_at": str(r["generated_at"]),
        }
        for r in cur
    ]


def get_weekly_statement(
    conn: sqlite3.Connection,
    user_private_id: str,
    *,
    statement_id: int | None = None,
    week_end: str | None = None,
) -> dict[str, Any] | None:
    migrate_qoin_economy_tables(conn)
    if statement_id:
        row = conn.execute(
            """
            SELECT * FROM weekly_statements
            WHERE id = ? AND user_private_id = ?
            """,
            (statement_id, user_private_id),
        ).fetchone()
    elif week_end:
        row = conn.execute(
            """
            SELECT * FROM weekly_statements
            WHERE user_private_id = ? AND week_end = ?
            """,
            (user_private_id, week_end),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT * FROM weekly_statements
            WHERE user_private_id = ?
            ORDER BY week_end DESC LIMIT 1
            """,
            (user_private_id,),
        ).fetchone()
    if not row:
        return None
    data = json.loads(str(row["statement_data"]))
    return {
        "id": int(row["id"]),
        "week_start": str(row["week_start"]),
        "week_end": str(row["week_end"]),
        "generated_at": str(row["generated_at"]),
        "statement": data,
    }


def statement_html_report(statement_payload: dict[str, Any]) -> str:
    """Render weekly statement as HTML for in-app viewer / future PDF export."""
    stmt = statement_payload.get("statement") or statement_payload
    ws = stmt.get("week_start", "")
    we = stmt.get("week_end", "")

    def chips(counts: list[dict[str, int]]) -> str:
        if not counts:
            return "<span class='qb-stmt-muted'>—</span>"
        return "".join(
            f"<span class='qb-qoin-chip'>₹{c['denom']}×{c['count']}</span>"
            for c in counts
        )

    rows = ""
    for t in stmt.get("transactions") or []:
        sign = "+" if t.get("direction") == "credit" else "−"
        rows += (
            f"<tr><td>{t.get('created_at','')}</td>"
            f"<td>{t.get('type','')}</td>"
            f"<td>{sign}₹{t.get('amount_rupees',0)}</td>"
            f"<td>{t.get('description','')}</td></tr>"
        )
    karma_rows = ""
    for k in stmt.get("karma_earnings") or []:
        qoins = ", ".join(f"₹{d}" for d in k.get("qoins") or [])
        karma_rows += (
            f"<tr><td>{k.get('label','')}</td>"
            f"<td>₹{k.get('amount_rupees',0)}</td>"
            f"<td>{qoins}</td></tr>"
        )
    insuff = ""
    if stmt.get("insufficient_funds"):
        insuff = "<p class='qb-stmt-warn'>Insufficient funds — debits could not be fully applied.</p>"
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Qoin Statement {ws} – {we}</title>
<link rel="stylesheet" href="/static/dashboard.css"/></head>
<body class="qb-statement-report">
<header><h1>Weekly Account Statement</h1><p>{ws} → {we}</p></header>
{insuff}
<section><h2>Opening balance</h2><div class="qb-qoin-chips">{chips(stmt.get('opening_balance') or [])}</div></section>
<section><h2>Transactions</h2>
<table class="qb-stmt-table"><thead><tr><th>When</th><th>Type</th><th>Amount</th><th>Detail</th></tr></thead>
<tbody>{rows or "<tr><td colspan='4'>No transactions</td></tr>"}</tbody></table></section>
<section><h2>Karma earnings this week</h2>
<table class="qb-stmt-table"><thead><tr><th>Action</th><th>₹</th><th>Qoins</th></tr></thead>
<tbody>{karma_rows or "<tr><td colspan='3'>None</td></tr>"}</tbody></table></section>
<section><h2>Closing balance</h2><div class="qb-qoin-chips">{chips(stmt.get('closing_balance') or [])}</div></section>
</body></html>"""


def pending_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    migrate_qoin_economy_tables(conn)
    row = conn.execute(
        """
        SELECT COUNT(*) AS n, COALESCE(SUM(amount_rupees), 0) AS rupees
        FROM pending_transactions WHERE settled = 0
        """
    ).fetchone()
    karma = conn.execute(
        "SELECT COUNT(*) AS n FROM karma_transactions WHERE settled = 0"
    ).fetchone()
    return {
        "pending_count": int(row["n"]) if row else 0,
        "pending_rupees": int(row["rupees"]) if row else 0,
        "unsettled_karma": int(karma["n"]) if karma else 0,
    }


def nested_wallets_summary(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    migrate_qoin_economy_tables(conn)
    cur = conn.execute(
        """
        SELECT owner_type, owner_id, balance FROM wallets
        WHERE owner_type IN ('village','tehsil','district','state','nation','kiosk','governance')
        ORDER BY owner_type, owner_id
        """
    )
    out: list[dict[str, Any]] = []
    for r in cur:
        ot, oid = str(r["owner_type"]), str(r["owner_id"])
        out.append(
            {
                "owner_type": ot,
                "owner_id": oid,
                "balance_qoins": wallet_balance(conn, ot, oid),
                "total_rupees": wallet_rupee_total(conn, ot, oid),
                "coins": wallet_breakdown(conn, ot, oid),
            }
        )
    return out


def circulation_total(conn: sqlite3.Connection) -> dict[str, Any]:
    migrate_qoin_economy_tables(conn)
    total_qoins = 0
    total_rupees = 0
    cur = conn.execute("SELECT owner_type, owner_id FROM wallets")
    for r in cur:
        ot, oid = str(r["owner_type"]), str(r["owner_id"])
        total_qoins += wallet_balance(conn, ot, oid)
        total_rupees += wallet_rupee_total(conn, ot, oid)
    return {"total_qoins": total_qoins, "total_rupees": total_rupees}


def karma_action_types_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    migrate_qoin_economy_tables(conn)
    cur = conn.execute(
        "SELECT action_code, label, rupee_value, active FROM karma_action_types ORDER BY rupee_value DESC"
    )
    return [
        {
            "action_code": str(r["action_code"]),
            "label": str(r["label"]),
            "rupee_value": int(r["rupee_value"]),
            "active": bool(int(r["active"])),
        }
        for r in cur
    ]


def upsert_karma_action_type(
    conn: sqlite3.Connection,
    *,
    action_code: str,
    label: str,
    rupee_value: int,
    active: bool = True,
) -> None:
    migrate_qoin_economy_tables(conn)
    conn.execute(
        """
        INSERT INTO karma_action_types (action_code, label, rupee_value, active, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(action_code) DO UPDATE SET
            label = excluded.label,
            rupee_value = excluded.rupee_value,
            active = excluded.active,
            updated_at = excluded.updated_at
        """,
        (action_code.strip(), label.strip(), rupee_value, 1 if active else 0, _now()),
    )


def user_pending_karma(
    conn: sqlite3.Connection, user_private_id: str
) -> list[dict[str, Any]]:
    migrate_qoin_economy_tables(conn)
    cur = conn.execute(
        """
        SELECT kt.id, kt.action_code, kt.amount_rupees, kt.description, kt.created_at,
               ka.label AS action_label
        FROM karma_transactions kt
        LEFT JOIN karma_action_types ka ON ka.action_code = kt.action_code
        WHERE kt.user_private_id = ? AND kt.settled = 0
        ORDER BY datetime(kt.created_at) DESC
        """,
        (user_private_id,),
    )
    return [
        {
            "id": int(r["id"]),
            "action_code": str(r["action_code"]),
            "label": str(r["action_label"] or r["description"]),
            "amount_rupees": int(r["amount_rupees"]),
            "pending_qoins": min_qoins_for_amount(int(r["amount_rupees"])),
            "created_at": str(r["created_at"]),
        }
        for r in cur
    ]


def user_transactions(
    conn: sqlite3.Connection, user_private_id: str, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Recent wallet ledger entries (post-settlement)."""
    migrate_qoin_economy_tables(conn)
    cur = conn.execute(
        """
        SELECT id, transaction_ref, amount_rupees, created_at
        FROM wallet_transactions
        WHERE wallet_type = 'user' AND wallet_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT ?
        """,
        (user_private_id, limit),
    )
    return [
        {
            "id": int(r["id"]),
            "transaction_ref": str(r["transaction_ref"]),
            "amount_rupees": int(r["amount_rupees"]),
            "created_at": str(r["created_at"]),
        }
        for r in cur
    ]


def credit_signup_bonus(conn: sqlite3.Connection, user_private_id: str) -> None:
    """Immediate ₹1 Qoin for activation (outside weekly batch)."""
    credit_wallet_denoms(
        conn, "user", user_private_id, [1],
        transaction_ref="SIGNUP-BONUS",
        amount_rupees=1,
    )
    migrate_qoin_transactions(conn)
    conn.execute(
        """
        INSERT INTO qoin_transactions (
            user_private_id, amount, reason,
            recipient_type, recipient_id, amount_in_qoins, rupee_value, type, description, created_at
        ) VALUES (?, 1, ?, 'user', ?, 1, 1, 'signup_bonus', ?, ?)
        """,
        (
            user_private_id,
            "Account activation bonus",
            user_private_id,
            "Account activation bonus (1 Qoin, ₹1)",
            _now(),
        ),
    )


def village_donation_report(
    conn: sqlite3.Connection, village_id: str
) -> dict[str, Any]:
    migrate_qoin_economy_tables(conn)
    bal = wallet_breakdown(conn, "village", village_id)
    rows = conn.execute(
        """
        SELECT transaction_ref, amount_rupees, created_at
        FROM wallet_transactions
        WHERE wallet_type = 'village' AND wallet_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT 50
        """,
        (village_id,),
    ).fetchall()
    return {
        "village_id": village_id,
        "total_qoins": wallet_balance(conn, "village", village_id),
        "total_rupees": wallet_rupee_total(conn, "village", village_id),
        "coins": bal,
        "recent": [
            {
                "transaction_ref": str(r["transaction_ref"]),
                "amount_rupees": int(r["amount_rupees"]),
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ],
    }


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
    """Legacy immediate credit — prefer pending + weekly settlement."""
    denoms = min_qoins_for_amount(int(rupee_value))
    credit_wallet_denoms(
        conn, recipient_type, recipient_id, denoms,
        transaction_ref=tx_type,
        amount_rupees=int(rupee_value),
    )
    migrate_qoin_transactions(conn)
    conn.execute(
        """
        INSERT INTO qoin_transactions (
            user_private_id, amount, reason,
            recipient_type, recipient_id, amount_in_qoins, rupee_value, type, description, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            donor_private_id,
            len(denoms),
            description,
            recipient_type,
            recipient_id,
            len(denoms),
            rupee_value,
            tx_type,
            description,
            _now(),
        ),
    )
