"""Registration donation — distribution preview, storage, immediate location credit, vote activation."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable

import qoin_core

TIERS: tuple[str, ...] = (
    "earth",
    "continent",
    "country",
    "zone",
    "state",
    "district",
    "tehsil",
    "village",
    "referrer",
    "new_user",
)

LOCATION_TIERS: tuple[str, ...] = TIERS[:8]

NotifyFn = Callable[[sqlite3.Connection, str, str, str], None]

EARTH_WALLET_ID = "0"

# No-referral: ₹0 donation → system generates ₹1 (100 paise)
NO_REFERRAL_ZERO_EFFECTIVE_PAISE = 100


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _now() -> str:
    return qoin_core._now()


def migrate_donation_schema(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "users")
    additions: list[tuple[str, str]] = [
        ("is_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("registration_donation", "INTEGER NOT NULL DEFAULT 0"),
        ("first_vote_completed", "INTEGER NOT NULL DEFAULT 0"),
        ("reward_activated", "INTEGER NOT NULL DEFAULT 0"),
        ("pending_user_share", "INTEGER NOT NULL DEFAULT 0"),
        ("registration_donation_amount", "INTEGER NOT NULL DEFAULT 0"),
        ("user_share_credited", "INTEGER NOT NULL DEFAULT 0"),
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
        CREATE TABLE IF NOT EXISTS donation_distributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            new_user_private_id TEXT NOT NULL UNIQUE,
            referrer_private_id TEXT NOT NULL DEFAULT '',
            donation_amount INTEGER NOT NULL,
            distribution_json TEXT NOT NULL,
            payment_method TEXT,
            agent_private_id TEXT,
            activated INTEGER NOT NULL DEFAULT 0,
            has_referral INTEGER NOT NULL DEFAULT 0,
            locations_credited INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    dd_cols = _table_columns(conn, "donation_distributions")
    for col_name, decl in [
        ("has_referral", "INTEGER NOT NULL DEFAULT 0"),
        ("locations_credited", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col_name not in dd_cols:
            try:
                conn.execute(
                    f"ALTER TABLE donation_distributions ADD COLUMN {col_name} {decl}"
                )
            except sqlite3.OperationalError:
                pass

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS donation_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_private_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            payment_method TEXT,
            transaction_id TEXT,
            status TEXT DEFAULT 'pending',
            distribution_json TEXT,
            location_scope TEXT,
            location_id TEXT,
            donated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registration_donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_private_id TEXT NOT NULL UNIQUE,
            donation_amount INTEGER NOT NULL,
            effective_amount_paise INTEGER NOT NULL,
            has_referral INTEGER NOT NULL DEFAULT 0,
            referral_code TEXT,
            volunteer_private_id TEXT,
            location_distribution TEXT NOT NULL,
            user_pending_amount INTEGER NOT NULL,
            user_share_credited INTEGER NOT NULL DEFAULT 0,
            locations_credited INTEGER NOT NULL DEFAULT 0,
            system_generated INTEGER NOT NULL DEFAULT 0,
            payment_method TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            credited_at TIMESTAMP,
            FOREIGN KEY (user_private_id) REFERENCES users(private_id)
        )
        """
    )


def calculate_tier_shares(donation_amount: int) -> tuple[int, int, int]:
    """
    Return (per_location_rupees, referrer_share, new_user_share).
    Location share applies to each of the 8 geographic tiers.
    Used for WITH-referral registrations.
    """
    amount = max(0, int(donation_amount))
    if amount == 0:
        return 0, 1, 0
    if amount <= 2:
        referrer = amount // 2
        new_user = amount - referrer
        return 0, referrer, new_user
    if amount <= 10:
        if amount == 5:
            return 0, 3, 2
        if amount == 10:
            return 0, 6, 4
        referrer = amount // 2
        return 0, referrer, amount - referrer
    if amount <= 20:
        per_loc = 1
    elif amount <= 50:
        per_loc = 2
    elif amount <= 100:
        per_loc = 5
    elif amount <= 200:
        per_loc = 10
    else:
        raise ValueError("Donation must be between ₹0 and ₹200")
    location_total = per_loc * 8
    remaining = amount - location_total
    if remaining < 0:
        raise ValueError("Donation too small for location tier allocation")
    referrer = int(remaining * 0.6)
    new_user = remaining - referrer
    return per_loc, referrer, new_user


def calculate_no_referral_distribution(
    donation_amount_rupees: int,
    *,
    location_context: dict[str, str],
    new_user_private_id: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    No-referral distribution: 80% split equally across 8 locations, 20% to user after vote.
    ₹0 donation → system generates ₹1 (100 paise).
    """
    raw = max(0, int(donation_amount_rupees))
    if raw == 0:
        total_paise = NO_REFERRAL_ZERO_EFFECTIVE_PAISE
        system_generated = True
    else:
        if raw > 200:
            raise ValueError("Donation must be between ₹0 and ₹200")
        total_paise = raw * 100
        system_generated = False

    location_total_paise = total_paise * 80 // 100
    per_location_paise = location_total_paise // 8
    location_remainder = location_total_paise - (per_location_paise * 8)
    user_paise = total_paise * 20 // 100 + location_remainder

    distribution: list[dict[str, Any]] = []
    location_distribution: dict[str, int] = {}
    for tier in LOCATION_TIERS:
        wallet_id = str(location_context.get(tier) or "").strip()
        location_distribution[tier] = per_location_paise
        distribution.append(
            {
                "tier": tier,
                "wallet_type": tier,
                "wallet_id": wallet_id,
                "amount_paise": per_location_paise,
                "rupee_amount": per_location_paise / 100.0,
                "credit_timing": "immediate",
            }
        )
    distribution.append(
        {
            "tier": "new_user",
            "wallet_type": "user",
            "wallet_id": str(new_user_private_id or "").strip(),
            "amount_paise": user_paise,
            "rupee_amount": user_paise / 100.0,
            "credit_timing": "after_first_vote",
        }
    )
    meta = {
        "donation_amount_rupees": raw,
        "effective_rupees": total_paise / 100.0,
        "effective_amount_paise": total_paise,
        "user_pending_paise": user_paise,
        "user_pending_amount": user_paise,
        "location_total_paise": location_total_paise,
        "per_location_paise": per_location_paise,
        "location_distribution": location_distribution,
        "system_generated": system_generated,
        "has_referral": False,
    }
    return distribution, meta


def build_location_context(
    *,
    village_id: str = "",
    country_id: str = "",
    continent_id: str = "",
    zone_id: str = "",
    state_id: str = "",
    district_id: str = "",
    tehsil_id: str = "",
) -> dict[str, str]:
    return {
        "earth": EARTH_WALLET_ID,
        "continent": (continent_id or "").strip(),
        "country": (country_id or "IND").strip().upper() or "IND",
        "zone": (zone_id or "").strip(),
        "state": (state_id or "").strip(),
        "district": (district_id or "").strip(),
        "tehsil": (tehsil_id or "").strip(),
        "village": (village_id or "").strip(),
    }


def calculate_donation_distribution(
    donation_amount: int,
    *,
    location_context: dict[str, str],
    referrer_private_id: str = "",
    new_user_private_id: str = "",
) -> list[dict[str, Any]]:
    """Route to no-referral or with-referral distribution rules."""
    referrer_pid = str(referrer_private_id or "").strip()
    if not referrer_pid:
        distribution, _meta = calculate_no_referral_distribution(
            donation_amount,
            location_context=location_context,
            new_user_private_id=new_user_private_id,
        )
        return distribution

    per_loc, referrer_share, new_user_share = calculate_tier_shares(donation_amount)
    distribution: list[dict[str, Any]] = []
    for tier in LOCATION_TIERS:
        wallet_id = str(location_context.get(tier) or "").strip()
        distribution.append(
            {
                "tier": tier,
                "wallet_type": tier,
                "wallet_id": wallet_id,
                "rupee_amount": per_loc if per_loc > 0 and wallet_id else 0,
                "amount_paise": (per_loc * 100) if per_loc > 0 and wallet_id else 0,
                "credit_timing": "after_first_vote",
            }
        )
    distribution.append(
        {
            "tier": "referrer",
            "wallet_type": "user",
            "wallet_id": referrer_pid,
            "rupee_amount": referrer_share,
            "amount_paise": referrer_share * 100,
            "credit_timing": "after_first_vote",
        }
    )
    distribution.append(
        {
            "tier": "new_user",
            "wallet_type": "user",
            "wallet_id": str(new_user_private_id or "").strip(),
            "rupee_amount": new_user_share,
            "amount_paise": new_user_share * 100,
            "credit_timing": "after_first_vote",
        }
    )
    for item in distribution:
        rupees = int(item.get("rupee_amount") or 0)
        item["qoins"] = (
            qoin_core.min_qoins_for_amount(rupees) if rupees > 0 else []
        )
    return distribution


def preview_donation(
    donation_amount: int,
    distribution: list[dict[str, Any]],
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = sum(
        float(x.get("rupee_amount") or 0) for x in distribution
    )
    if meta and meta.get("effective_rupees"):
        total = float(meta["effective_rupees"])
    out: dict[str, Any] = {
        "donation_amount": int(donation_amount),
        "distribution": distribution,
        "total_rupees": round(total, 2),
    }
    if meta:
        out.update(
            {
                "has_referral": meta.get("has_referral", False),
                "system_generated": meta.get("system_generated", False),
                "effective_rupees": meta.get("effective_rupees"),
                "user_pending_rupees": (meta.get("user_pending_paise", 0) / 100.0),
                "location_share_rupees": (meta.get("location_total_paise", 0) / 100.0),
                "per_location_rupees": (meta.get("per_location_paise", 0) / 100.0),
            }
        )
    return out


def preview_no_referral_donation(
    donation_amount: int,
    *,
    location_context: dict[str, str],
    new_user_private_id: str = "",
) -> dict[str, Any]:
    distribution, meta = calculate_no_referral_distribution(
        donation_amount,
        location_context=location_context,
        new_user_private_id=new_user_private_id,
    )
    return preview_donation(donation_amount, distribution, meta=meta)


def store_registration_donation(
    conn: sqlite3.Connection,
    *,
    user_private_id: str,
    donation_amount_rupees: int,
    meta: dict[str, Any],
    distribution: list[dict[str, Any]],
    payment_method: str = "",
    referral_code: str = "",
) -> None:
    migrate_donation_schema(conn)
    pid = str(user_private_id)
    conn.execute(
        """
        INSERT INTO registration_donations (
            user_private_id, donation_amount, effective_amount_paise,
            has_referral, referral_code, location_distribution,
            user_pending_amount, locations_credited, system_generated, payment_method
        ) VALUES (?, ?, ?, 0, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(user_private_id) DO UPDATE SET
            donation_amount = excluded.donation_amount,
            effective_amount_paise = excluded.effective_amount_paise,
            location_distribution = excluded.location_distribution,
            user_pending_amount = excluded.user_pending_amount,
            locations_credited = excluded.locations_credited,
            system_generated = excluded.system_generated,
            payment_method = excluded.payment_method
        """,
        (
            pid,
            int(donation_amount_rupees),
            int(meta.get("effective_amount_paise") or 0),
            (referral_code or "").strip(),
            json.dumps(meta.get("location_distribution") or {}),
            int(meta.get("user_pending_paise") or 0),
            1 if meta.get("system_generated") else 0,
            (payment_method or "").strip().lower(),
        ),
    )
    conn.execute(
        """
        UPDATE users
        SET registration_donation = ?,
            registration_donation_amount = ?,
            pending_user_share = ?,
            reward_activated = 0,
            user_share_credited = 0
        WHERE private_id = ?
        """,
        (
            int(donation_amount_rupees),
            int(donation_amount_rupees),
            int(meta.get("user_pending_paise") or 0),
            pid,
        ),
    )
    conn.execute(
        """
        INSERT INTO donation_distributions (
            new_user_private_id, referrer_private_id, donation_amount,
            distribution_json, payment_method, activated,
            has_referral, locations_credited
        ) VALUES (?, '', ?, ?, ?, 0, 0, 1)
        ON CONFLICT(new_user_private_id) DO UPDATE SET
            donation_amount = excluded.donation_amount,
            distribution_json = excluded.distribution_json,
            payment_method = excluded.payment_method,
            has_referral = 0,
            locations_credited = 1
        """,
        (
            pid,
            int(donation_amount_rupees),
            json.dumps(distribution),
            (payment_method or "").strip().lower(),
        ),
    )


def process_no_referral_registration(
    conn: sqlite3.Connection,
    *,
    user_private_id: str,
    donation_amount_rupees: int,
    location_context: dict[str, str],
    payment_method: str = "",
    referral_code: str = "",
) -> dict[str, Any]:
    """Calculate distribution, credit locations immediately, store pending user share."""
    migrate_donation_schema(conn)
    distribution, meta = calculate_no_referral_distribution(
        donation_amount_rupees,
        location_context=location_context,
        new_user_private_id=user_private_id,
    )
    qoin_core.credit_location_wallets_from_distribution(
        conn,
        distribution,
        ref_suffix=str(user_private_id),
        location_tiers_only=True,
    )
    store_registration_donation(
        conn,
        user_private_id=user_private_id,
        donation_amount_rupees=donation_amount_rupees,
        meta=meta,
        distribution=distribution,
        payment_method=payment_method,
        referral_code=referral_code,
    )
    return {"distribution": distribution, "meta": meta}


def store_pending_distribution(
    conn: sqlite3.Connection,
    *,
    new_user_private_id: str,
    referrer_private_id: str,
    donation_amount: int,
    distribution: list[dict[str, Any]],
    payment_method: str = "",
    agent_private_id: str | None = None,
) -> None:
    migrate_donation_schema(conn)
    has_referral = bool(str(referrer_private_id or "").strip())
    conn.execute(
        """
        INSERT INTO donation_distributions (
            new_user_private_id, referrer_private_id, donation_amount,
            distribution_json, payment_method, agent_private_id, activated,
            has_referral, locations_credited
        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0)
        ON CONFLICT(new_user_private_id) DO UPDATE SET
            referrer_private_id = excluded.referrer_private_id,
            donation_amount = excluded.donation_amount,
            distribution_json = excluded.distribution_json,
            payment_method = excluded.payment_method,
            agent_private_id = excluded.agent_private_id,
            has_referral = excluded.has_referral,
            locations_credited = excluded.locations_credited
        """,
        (
            new_user_private_id,
            referrer_private_id,
            int(donation_amount),
            json.dumps(distribution),
            (payment_method or "").strip().lower(),
            agent_private_id,
            1 if has_referral else 0,
        ),
    )
    conn.execute(
        """
        UPDATE users
        SET registration_donation = ?, referred_by = ?
        WHERE private_id = ?
        """,
        (int(donation_amount), referrer_private_id, new_user_private_id),
    )


def _wallet_owner_type(tier: str) -> str:
    if tier in {"referrer", "new_user"}:
        return "user"
    if tier == "country":
        return "nation"
    return tier


def _credit_distribution_item(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    *,
    ref_suffix: str,
) -> None:
    amount = int(item.get("rupee_amount") or 0)
    paise = int(item.get("amount_paise") or 0)
    if amount <= 0 and paise <= 0:
        return
    wallet_id = str(item.get("wallet_id") or "").strip()
    if not wallet_id:
        return
    tier = str(item.get("tier") or "")
    owner_type = _wallet_owner_type(tier)
    if paise > 0 and amount <= 0:
        qoin_core.credit_wallet_paise(
            conn,
            owner_type,
            wallet_id,
            paise,
            transaction_ref=f"reg-donation-{ref_suffix}-{tier}",
        )
        return
    denoms = qoin_core.min_qoins_for_amount(amount)
    qoin_core.credit_wallet_denoms(
        conn,
        owner_type,
        wallet_id,
        denoms,
        transaction_ref=f"reg-donation-{ref_suffix}-{tier}",
        amount_rupees=amount,
    )


def activate_user_reward_after_vote(
    conn: sqlite3.Connection,
    user_private_id: str,
    *,
    notify_fn: NotifyFn | None = None,
) -> bool:
    """Credit pending user share after first village election vote."""
    return activate_rewards(conn, user_private_id, notify_fn=notify_fn)


def activate_rewards(
    conn: sqlite3.Connection,
    user_private_id: str,
    *,
    notify_fn: NotifyFn | None = None,
) -> bool:
    """Credit pending user (and referrer) shares after first village election vote."""
    migrate_donation_schema(conn)
    pid = str(user_private_id)
    row = conn.execute(
        "SELECT reward_activated, pending_user_share FROM users WHERE private_id = ?",
        (pid,),
    ).fetchone()
    if not row or int(row["reward_activated"] or 0) == 1:
        return False

    reg_row = conn.execute(
        """
        SELECT user_pending_amount, user_share_credited, system_generated, donation_amount
        FROM registration_donations
        WHERE user_private_id = ?
        """,
        (pid,),
    ).fetchone()

    dist_row = conn.execute(
        """
        SELECT id, distribution_json, referrer_private_id, donation_amount,
               has_referral, locations_credited
        FROM donation_distributions
        WHERE new_user_private_id = ? AND activated = 0
        """,
        (pid,),
    ).fetchone()

    if not dist_row and not reg_row:
        conn.execute(
            """
            UPDATE users
            SET reward_activated = 1, first_vote_completed = 1
            WHERE private_id = ?
            """,
            (pid,),
        )
        return False

    ref_suffix = str(dist_row["id"]) if dist_row else pid
    user_credited = False
    pending_paise = int(reg_row["user_pending_amount"] or 0) if reg_row else 0

    if pending_paise > 0 and reg_row and not int(reg_row["user_share_credited"] or 0):
        qoin_core.credit_wallet_paise(
            conn,
            "user",
            pid,
            pending_paise,
            transaction_ref=f"reg-reward-vote-{ref_suffix}",
        )
        conn.execute(
            """
            UPDATE registration_donations
            SET user_share_credited = 1, credited_at = ?
            WHERE user_private_id = ?
            """,
            (_now(), pid),
        )
        user_credited = True

    if dist_row:
        distribution = json.loads(str(dist_row["distribution_json"] or "[]"))
        locations_already_credited = int(dist_row["locations_credited"] or 0) == 1
        for item in distribution:
            tier = str(item.get("tier") or "")
            if tier == "new_user":
                if user_credited:
                    continue
                item = {**item, "wallet_id": pid}
                _credit_distribution_item(conn, item, ref_suffix=ref_suffix)
            elif tier == "referrer":
                _credit_distribution_item(conn, item, ref_suffix=ref_suffix)
            elif not locations_already_credited and tier in LOCATION_TIERS:
                _credit_distribution_item(conn, item, ref_suffix=ref_suffix)

        conn.execute(
            "UPDATE donation_distributions SET activated = 1 WHERE id = ?",
            (int(dist_row["id"]),),
        )
        referrer_pid = str(dist_row["referrer_private_id"] or "")
        amount = int(dist_row["donation_amount"] or 0)
        if notify_fn and referrer_pid:
            notify_fn(
                conn,
                referrer_pid,
                "Referral rewards activated",
                f"A user you referred completed their first village vote. "
                f"Registration donation rewards (₹{amount}) have been credited.",
            )

    conn.execute(
        """
        UPDATE users
        SET reward_activated = 1,
            first_vote_completed = 1,
            is_verified = 1,
            user_share_credited = 1
        WHERE private_id = ?
        """,
        (pid,),
    )

    if notify_fn and user_credited:
        pending_rupees = pending_paise / 100.0
        notify_fn(
            conn,
            pid,
            "Registration reward — Qoins credited",
            (
                f"Congratulations! Your registration reward of ₹{pending_rupees:.2f} "
                f"has been credited after your first village vote."
            ),
        )
    elif notify_fn and dist_row and not user_credited:
        notify_fn(
            conn,
            pid,
            "Welcome rewards activated",
            "Your registration rewards have been credited after your first village vote.",
        )
    return True


def record_donation_transaction(
    conn: sqlite3.Connection,
    *,
    user_private_id: str,
    amount: int,
    payment_method: str,
    transaction_id: str,
    status: str,
    distribution: list[dict[str, Any]] | None = None,
    location_scope: str = "",
    location_id: str = "",
) -> int:
    migrate_donation_schema(conn)
    conn.execute(
        """
        INSERT INTO donation_transactions (
            user_private_id, amount, payment_method, transaction_id,
            status, distribution_json, location_scope, location_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_private_id,
            int(amount),
            (payment_method or "").strip().lower(),
            transaction_id,
            status,
            json.dumps(distribution or []),
            location_scope,
            location_id,
        ),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
