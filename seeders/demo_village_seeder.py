#!/usr/bin/env python3
"""Seed demo data for Demo Gram (Panchayat) preview dashboard."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db_path import resolve_database_path

DEMO_VILLAGE_ID = "demo-gram-panchayat"
DEMO_VILLAGE_NAME = "Demo Gram (Panchayat)"

DEMO_DATA: dict = {
    "village_id": DEMO_VILLAGE_ID,
    "name": DEMO_VILLAGE_NAME,
    "district": "Demo District",
    "state": "Demo State",
    "population": 1247,
    "karma_total": 45230,
    "active_issues": 3,
    "budget_allocated": 250000,
    "budget_spent": 180000,
    "budget_remaining": 70000,
    "next_election_days": 12,
    "next_election_from": "Leo",
    "next_election_to": "Virgo",
    "council": [
        {"name": "Council Member I", "sign": "Aries", "element": "Fire", "karma": 1240},
        {"name": "Council Member II", "sign": "Taurus", "element": "Earth", "karma": 980},
        {"name": "Council Member III", "sign": "Gemini", "element": "Air", "karma": 850},
        {"name": "Council Member IV", "sign": "Cancer", "element": "Water", "karma": 720},
        {"name": "Council Member V", "sign": "Leo", "element": "Fire", "karma": 1100},
    ],
    "issues": [
        {
            "id": "issue-road",
            "title": "Repair main road",
            "status": "Voting Open",
            "yes_pct": 67,
            "no_pct": 33,
            "ends_in_days": 2,
        },
        {
            "id": "issue-pump",
            "title": "Install water pump",
            "status": "Approved, Awaiting Funds",
            "yes_pct": 82,
            "no_pct": 18,
            "ends_in_days": None,
        },
        {
            "id": "issue-wall",
            "title": "School boundary wall",
            "status": "Proposed",
            "yes_pct": 0,
            "no_pct": 0,
            "ends_in_days": None,
        },
    ],
    "karma_leaders": [
        {"rank": 1, "citizen_hash": "#42", "points": 1240},
        {"rank": 2, "citizen_hash": "#18", "points": 980},
        {"rank": 3, "citizen_hash": "#7", "points": 850},
        {"rank": 4, "citizen_hash": "#31", "points": 720},
        {"rank": 5, "citizen_hash": "#55", "points": 690},
    ],
    "events": [
        {"title": "Zodiac Council Transition", "date": "Aug 15"},
        {"title": "Budget Review", "date": "Aug 20"},
        {"title": "Karma Distribution", "date": "Aug 30"},
    ],
}


def get_demo_data() -> dict:
    return dict(DEMO_DATA)


def seed_pilot_marker(conn: sqlite3.Connection) -> None:
    """Mark demo village in pilot table if pilot_core schema exists."""
    try:
        import pilot_core

        pilot_core.ensure_schema(conn)
        pilot_core.register_pilot_village(
            conn,
            village_id=DEMO_VILLAGE_ID,
            coordinator_name="Demo Coordinator",
            status="demo",
        )
    except Exception:
        pass


def main() -> None:
    db_path = resolve_database_path(ROOT)
    print(f"Demo village seeder — data for: {DEMO_VILLAGE_NAME}")
    out = ROOT / "data" / "demo_village.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(DEMO_DATA, indent=2), encoding="utf-8")
    print(f"✅ Wrote {out}")

    if db_path.is_file():
        conn = sqlite3.connect(db_path)
        try:
            seed_pilot_marker(conn)
            conn.commit()
            print("✅ Pilot marker updated (if schema available)")
        finally:
            conn.close()
    else:
        print(f"⚠️ Database not found at {db_path} — JSON export only")


if __name__ == "__main__":
    main()
