#!/usr/bin/env python3
"""Background jobs — weekly Qoin settlement, monthly Varna recalculation."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Callable

import qoin_core

try:
    import varna_core
except ImportError:
    varna_core = None  # type: ignore

try:
    import planetary_core
except ImportError:
    planetary_core = None  # type: ignore

try:
    import identity_core
except ImportError:
    identity_core = None  # type: ignore

try:
    import deceased_core
except ImportError:
    deceased_core = None  # type: ignore

try:
    import pytz

    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    IST = None  # type: ignore

_last_settlement_week_key: str | None = None
_last_varna_recalc_month_key: str | None = None
_last_planetary_update_key: str | None = None
_last_age_update_key: str | None = None
_last_monthly_election_key: str | None = None


def _now_ist() -> datetime:
    if IST is not None:
        return datetime.now(IST)
    return datetime.now(timezone.utc)


def should_run_weekly_settlement(now: datetime | None = None) -> bool:
    """
    True once per calendar week after Sunday 23:59 IST (or local if pytz missing).
    """
    global _last_settlement_week_key
    ref = now or _now_ist()
    if ref.weekday() != 6:  # not Sunday
        return False
    if ref.hour < 23 or (ref.hour == 23 and ref.minute < 59):
        return False
    week_start, week_end = qoin_core.week_bounds_for_date(ref.date())
    key = f"{week_start.isoformat()}_{week_end.isoformat()}"
    if _last_settlement_week_key == key:
        return False
    return True


def mark_settlement_ran(week_start, week_end) -> None:
    global _last_settlement_week_key
    _last_settlement_week_key = f"{week_start}_{week_end}"


def run_weekly_settlement_if_due(
    conn: sqlite3.Connection,
    *,
    hierarchy_resolver: Callable[[str], list[dict[str, str]]] | None = None,
    notify_fn: Callable[[sqlite3.Connection, str, str, str], None] | None = None,
    force: bool = False,
) -> dict | None:
    """
    Run settlement when due (Sunday ≥23:59) or when ``force=True`` (admin).
    Returns result dict or None if skipped.
    """
    ref = _now_ist()
    week_start, week_end = qoin_core.week_bounds_for_date(ref.date())
    if not force and not should_run_weekly_settlement(ref):
        return None
    result = qoin_core.process_weekly_settlement(
        conn,
        week_start=week_start,
        week_end=week_end,
        triggered_by="scheduler" if not force else "admin",
        hierarchy_resolver=hierarchy_resolver,
        notify_fn=notify_fn,
    )
    mark_settlement_ran(week_start, week_end)
    conn.commit()
    return result


def should_run_monthly_varna_recalc(now: datetime | None = None) -> bool:
    """True once per calendar month on day 1 at or after 02:00 IST."""
    global _last_varna_recalc_month_key
    ref = now or _now_ist()
    if ref.day != 1 or ref.hour < 2:
        return False
    key = f"{ref.year}-{ref.month:02d}"
    if _last_varna_recalc_month_key == key:
        return False
    return True


def mark_varna_recalc_ran(now: datetime | None = None) -> None:
    global _last_varna_recalc_month_key
    ref = now or _now_ist()
    _last_varna_recalc_month_key = f"{ref.year}-{ref.month:02d}"


def run_monthly_varna_recalc_if_due(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
) -> dict | None:
    if varna_core is None:
        return None
    ref = _now_ist()
    if not force and not should_run_monthly_varna_recalc(ref):
        return None
    result = varna_core.recalculate_all_categories(conn)
    mark_varna_recalc_ran(ref)
    return result


def should_run_daily_planetary_update(now: datetime | None = None) -> bool:
    """True once per calendar day at or after 00:01 IST."""
    global _last_planetary_update_key
    ref = now or _now_ist()
    if ref.hour == 0 and ref.minute < 1:
        return False
    key = ref.date().isoformat()
    if _last_planetary_update_key == key:
        return False
    return True


def mark_planetary_update_ran(now: datetime | None = None) -> None:
    global _last_planetary_update_key
    ref = now or _now_ist()
    _last_planetary_update_key = ref.date().isoformat()


def run_daily_planetary_update_if_due(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
) -> dict | None:
    if planetary_core is None:
        return None
    ref = _now_ist()
    if not force and not should_run_daily_planetary_update(ref):
        return None
    result = planetary_core.update_daily_planetary_positions(conn)
    mark_planetary_update_ran(ref)
    return result


def run_akashic_archive_jobs_if_due(
    conn: sqlite3.Connection,
) -> dict | None:
    """Run periodic archive jobs (elections monthly, transactions yearly)."""
    if deceased_core is None:
        return None
    ref = _now_ist()
    out: dict[str, int] = {}
    if ref.day == 1 and ref.hour >= 3:
        out["elections_archived"] = deceased_core.archive_old_election_results(conn)
    if ref.month == 1 and ref.day == 1 and ref.hour >= 4:
        out["transactions_archived"] = deceased_core.archive_old_transactions(conn)
    return out or None


def should_run_daily_age_update(now: datetime | None = None) -> bool:
    """True once per calendar day at or after 02:00 IST."""
    global _last_age_update_key
    ref = now or _now_ist()
    if ref.hour < 2:
        return False
    key = ref.date().isoformat()
    if _last_age_update_key == key:
        return False
    return True


def mark_age_update_ran(now: datetime | None = None) -> None:
    global _last_age_update_key
    ref = now or _now_ist()
    _last_age_update_key = ref.date().isoformat()


def run_daily_age_category_update_if_due(
    conn: sqlite3.Connection,
    *,
    life_stage_from_age_fn: Callable,
    compute_age_fn: Callable,
    notify_fn: Callable | None = None,
    force: bool = False,
) -> dict | None:
    if identity_core is None:
        return None
    ref = _now_ist()
    if not force and not should_run_daily_age_update(ref):
        return None
    result = identity_core.run_daily_age_category_updates(
        conn,
        life_stage_from_age_fn=life_stage_from_age_fn,
        compute_age_fn=compute_age_fn,
        notify_fn=notify_fn,
    )
    mark_age_update_ran(ref)
    return result


def should_run_monthly_election(now: datetime | None = None) -> bool:
    """True once per calendar month on day 1 at or after 01:00 IST."""
    global _last_monthly_election_key
    ref = now or _now_ist()
    if ref.day != 1 or ref.hour < 1:
        return False
    key = f"{ref.year}-{ref.month:02d}"
    if _last_monthly_election_key == key:
        return False
    return True


def mark_monthly_election_ran(now: datetime | None = None) -> None:
    global _last_monthly_election_key
    ref = now or _now_ist()
    _last_monthly_election_key = f"{ref.year}-{ref.month:02d}"


def run_monthly_election_if_due(
    conn: sqlite3.Connection,
    *,
    force: bool = False,
) -> dict | None:
    try:
        import config
        if not (config.DEMO_MODE or config.ELECTIONS_AUTO_DEMO or config.ELECTIONS_ENABLED):
            return None
    except ImportError:
        return None
    try:
        import election_automation
    except ImportError:
        return None
    ref = _now_ist()
    if not force and not should_run_monthly_election(ref):
        return None
    result = election_automation.run_monthly_election_job(conn, today=ref.date())
    mark_monthly_election_ran(ref)
    return result


if __name__ == "__main__":
    import sys
    from pathlib import Path

    base = Path(__file__).resolve().parent
    db = base / "indiaq.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        qoin_core.migrate_qoin_economy_tables(conn)
        out = qoin_core.process_weekly_settlement(
            conn,
            triggered_by="cli",
        )
        conn.commit()
        print(out)
    finally:
        conn.close()
    sys.exit(0)
