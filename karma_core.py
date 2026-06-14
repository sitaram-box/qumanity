"""
Karma ↔ Varna integration (category affinity and bonus multipliers).

Implementation lives in qoin_core + varna_core; this module is the stable import path.
"""

from __future__ import annotations

import sqlite3

import varna_core

KARMA_CATEGORY_AFFINITY: dict[str, str] = {
    "teach_hour": "vidya",
    "plant_tree": "seva",
    "council_day": "raksha",
    "report_issue": "raksha",
}


def migrate_karma_varna(conn: sqlite3.Connection) -> None:
    varna_core.migrate_varna_schema(conn)


def affinity_for_action(conn: sqlite3.Connection, action_code: str) -> str | None:
    row = conn.execute(
        "SELECT category_affinity FROM karma_action_types WHERE action_code = ?",
        (action_code,),
    ).fetchone()
    return str(row["category_affinity"]) if row and row["category_affinity"] else None


def apply_category_bonus(
    conn: sqlite3.Connection,
    user_private_id: str,
    action_code: str,
    base_amount: int,
) -> int:
    return varna_core.apply_karma_category_bonus(
        conn, user_private_id, action_code, base_amount
    )


# Karma Points wallet economy — re-exported from qoin_core during gradual migration.
# Import wallet helpers via karma_core or continue using qoin_core directly.
from qoin_core import *  # noqa: F403, F401
