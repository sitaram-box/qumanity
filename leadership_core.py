#!/usr/bin/env python3
"""Quantum Punch Council — leadership slots per geographic level."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

# Prototype: single Mentor identity stored as system_admin; UI shows "Admin" only.
MENTOR_HOLDER_PLACEHOLDER = "system_admin"
MENTOR_DISPLAY_NAME = "Admin"

SLOT_DESIGNATIONS: tuple[str, ...] = ("mentor", "nayak", "nayika", "manager", "agent")

LEVEL_TYPES: tuple[str, ...] = (
    "earth",
    "continent",
    "country",
    "zone",
    "state",
    "district",
    "tehsil",
    "village",
)

# Display order: top (Mentor) → bottom (Agent)
SLOT_HIERARCHY_ORDER: tuple[str, ...] = ("mentor", "nayak", "nayika", "manager", "agent")

LEVEL_LABEL: dict[str, str] = {
    "earth": "Earth",
    "continent": "Continent",
    "country": "Country",
    "zone": "Zone",
    "state": "State",
    "district": "District",
    "tehsil": "Tehsil",
    "village": "Village",
}

ROLE_LABEL: dict[str, str] = {
    "mentor": "Mentor",
    "nayak": "Nayak",
    "nayika": "Nayika",
    "manager": "Manager",
    "agent": "Agent",
}

LEADERSHIP_DDL = """
CREATE TABLE IF NOT EXISTS leadership_council (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level_type TEXT NOT NULL,
    location_id TEXT NOT NULL,
    slot_designation TEXT NOT NULL,
    current_holder_private_id TEXT,
    filled_at TIMESTAMP,
    term_end TIMESTAMP,
    status TEXT DEFAULT 'empty',
    UNIQUE (level_type, location_id, slot_designation)
);
CREATE INDEX IF NOT EXISTS idx_leadership_council_loc
    ON leadership_council (level_type, location_id);
"""


def migrate_leadership_council(conn: sqlite3.Connection) -> None:
    conn.executescript(LEADERSHIP_DDL)


def slot_title(level_type: str, designation: str) -> str:
    prefix = LEVEL_LABEL.get(level_type, level_type.capitalize())
    role = ROLE_LABEL.get(designation, designation.capitalize())
    return f"{prefix} {role}"


def display_name_for_slot(row: sqlite3.Row | dict[str, Any] | None) -> str:
    if not row:
        return "Vacant"
    desig = str(row.get("slot_designation") if isinstance(row, dict) else row["slot_designation"])
    status = str(row.get("status") if isinstance(row, dict) else row["status"] or "")
    holder = row.get("current_holder_private_id") if isinstance(row, dict) else row["current_holder_private_id"]
    if desig == "mentor":
        if holder == MENTOR_HOLDER_PLACEHOLDER or status == "filled":
            return MENTOR_DISPLAY_NAME
        return MENTOR_DISPLAY_NAME
    if status == "filled" and holder:
        return "Filled"
    return "Vacant"


def ensure_location_slots(
    conn: sqlite3.Connection, level_type: str, location_id: str
) -> None:
    loc = (location_id or "").strip()
    lt = (level_type or "").strip().lower()
    if not loc or lt not in LEVEL_TYPES:
        return
    now = datetime.now(timezone.utc).isoformat()
    for desig in SLOT_DESIGNATIONS:
        existing = conn.execute(
            """
            SELECT id, status, current_holder_private_id FROM leadership_council
            WHERE level_type = ? AND location_id = ? AND slot_designation = ?
            """,
            (lt, loc, desig),
        ).fetchone()
        if existing:
            if desig == "mentor" and not existing["current_holder_private_id"]:
                conn.execute(
                    """
                    UPDATE leadership_council
                    SET current_holder_private_id = ?, status = 'filled', filled_at = ?
                    WHERE id = ?
                    """,
                    (MENTOR_HOLDER_PLACEHOLDER, now, int(existing["id"])),
                )
            continue
        if desig == "mentor":
            conn.execute(
                """
                INSERT INTO leadership_council (
                    level_type, location_id, slot_designation,
                    current_holder_private_id, filled_at, status
                ) VALUES (?, ?, ?, ?, ?, 'filled')
                """,
                (lt, loc, desig, MENTOR_HOLDER_PLACEHOLDER, now),
            )
        else:
            conn.execute(
                """
                INSERT INTO leadership_council (
                    level_type, location_id, slot_designation, status
                ) VALUES (?, ?, ?, 'empty')
                """,
                (lt, loc, desig),
            )


def seed_mentor_slots(conn: sqlite3.Connection) -> None:
    """Ensure Earth mentor row and any location passed via ensure_location_slots."""
    ensure_location_slots(conn, "earth", "0")


def get_leadership_for_location(
    conn: sqlite3.Connection, level_type: str, location_id: str
) -> dict[str, Any]:
    lt = (level_type or "").strip().lower()
    loc = (location_id or "").strip()
    if lt not in LEVEL_TYPES:
        raise ValueError(f"Invalid level_type: {level_type}")
    if not loc:
        raise ValueError("location_id is required")
    ensure_location_slots(conn, lt, loc)
    conn.commit()
    rows = conn.execute(
        """
        SELECT slot_designation, current_holder_private_id, status, filled_at, term_end
        FROM leadership_council
        WHERE level_type = ? AND location_id = ?
        """,
        (lt, loc),
    ).fetchall()
    by_desig = {str(r["slot_designation"]): dict(r) for r in rows}
    slots: list[dict[str, Any]] = []
    for desig in SLOT_HIERARCHY_ORDER:
        row = by_desig.get(desig)
        slots.append(
            {
                "designation": desig,
                "title": slot_title(lt, desig),
                "display_name": display_name_for_slot(row),
                "status": str(row["status"]) if row else "empty",
                "hierarchy_rank": SLOT_HIERARCHY_ORDER.index(desig) + 1,
                "selection_method": (
                    "appointed"
                    if desig in ("mentor", "manager", "agent")
                    else "elected"
                ),
                "can_appoint": desig != "mentor",
            }
        )
    return {
        "level_type": lt,
        "location_id": loc,
        "level_label": LEVEL_LABEL.get(lt, lt.capitalize()),
        "slots": slots,
    }
