#!/usr/bin/env python3
"""Generate demo users across Indian villages (configurable scale)."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo_user_core import (
    count_villages,
    count_villages_in_state,
    generate_demo_users_batch,
    migrate_demo_schema,
)

DEFAULT_DB = ROOT / "indiaq.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Qumanity demo users")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to indiaq.db")
    parser.add_argument(
        "--users-per-village",
        type=int,
        default=1000,
        help="Users per village (default 1000)",
    )
    parser.add_argument(
        "--state",
        default="Delhi",
        help="Seed villages in this state only (default: Delhi). Use --all-states to ignore.",
    )
    parser.add_argument(
        "--all-states",
        action="store_true",
        help="Seed villages nationwide (not recommended for local testing)",
    )
    parser.add_argument(
        "--max-villages",
        type=int,
        default=None,
        help="Max villages to seed (optional cap within state)",
    )
    parser.add_argument(
        "--all-villages",
        action="store_true",
        help="All villages in selected state (or all India with --all-states)",
    )
    parser.add_argument("--village-id", help="Seed a single village only")
    parser.add_argument(
        "--activity-fraction",
        type=float,
        default=0.15,
        help="Fraction of users with posts/votes/wallets",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        migrate_demo_schema(conn)
        state_name = None if args.all_states else args.state
        if args.village_id:
            max_v = None
            state_name = None
        elif args.all_villages:
            max_v = None
        else:
            max_v = args.max_villages

        if state_name:
            n_state_v = count_villages_in_state(conn, state_name)
            print(f"Villages in {state_name}: {n_state_v:,}")
            projected_v = n_state_v if args.all_villages else (max_v or n_state_v)
        else:
            total_villages = count_villages(conn)
            print(f"Villages in DB (all states): {total_villages:,}")
            projected_v = total_villages if args.all_villages else (max_v or args.max_villages or 5)

        projected_users = projected_v * args.users_per_village
        print(f"Users per village: {args.users_per_village}")
        print(f"Projected users (approx): {projected_users:,}")
        if projected_users > 500_000:
            print("WARNING: Large seed — consider --max-villages for testing.", file=sys.stderr)

        start = time.time()
        totals = generate_demo_users_batch(
            conn,
            users_per_village=args.users_per_village,
            max_villages=max_v,
            village_id=args.village_id,
            state_name=state_name,
            activity_fraction=args.activity_fraction,
            progress_cb=lambda msg: print(msg, flush=True),
        )
        elapsed = time.time() - start
        print(f"Done in {elapsed:.1f}s: {totals}")
        print(f"Demo password for all users: DemoPass9!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
