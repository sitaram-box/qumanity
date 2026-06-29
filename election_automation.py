#!/usr/bin/env python3
"""Automated zodiac elections — demo simulation and monthly scheduling."""

from __future__ import annotations

import json
import logging
import random
import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import election_scheduler
import demo_user_core

logger = logging.getLogger("qumanity.election_automation")

PATH_PREFIX = "0.राम|"
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
VILLAGE_ONLY_MESSAGE = (
    "Elections are only active at Village level. Higher level elections coming soon."
)
LEVEL_CHILD: dict[str, str] = {
    "earth": "continent",
    "continent": "country",
    "country": "zone",
    "zone": "state",
    "state": "district",
    "district": "tehsil",
    "tehsil": "village",
}

ELECTION_AUTOMATION_DDL = """
CREATE TABLE IF NOT EXISTS location_council (
    level_type TEXT NOT NULL,
    location_id TEXT NOT NULL,
    zodiac_sign TEXT NOT NULL,
    male_head_private_id TEXT,
    female_head_private_id TEXT,
    election_cycle_id INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (level_type, location_id, zodiac_sign)
);
CREATE INDEX IF NOT EXISTS idx_location_council_loc
    ON location_council (level_type, location_id);
"""


def migrate_election_automation_schema(conn: sqlite3.Connection) -> None:
    election_scheduler.migrate_election_tables(conn)
    demo_user_core.migrate_demo_schema(conn)
    conn.executescript(ELECTION_AUTOMATION_DDL)
    for table, col, decl in (
        ("election_cycles", "level_type", "TEXT NOT NULL DEFAULT 'village'"),
        ("election_cycles", "year", "INTEGER"),
        ("election_cycles", "month", "INTEGER"),
        ("election_cycles", "voter_turnout", "INTEGER NOT NULL DEFAULT 0"),
        ("election_cycles", "total_voters", "INTEGER NOT NULL DEFAULT 0"),
        ("election_candidates", "total_votes", "INTEGER NOT NULL DEFAULT 0"),
        ("election_candidates", "is_winner", "INTEGER NOT NULL DEFAULT 0"),
        ("election_candidates", "position", "TEXT"),
    ):
        cols = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}
        if col in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def sun_sign_for_date(d: date) -> str:
    m, day = d.month, d.day
    if (m == 12 and day >= 22) or (m == 1 and day <= 19):
        return "Capricorn"
    if (m == 1 and day >= 20) or (m == 2 and day <= 18):
        return "Aquarius"
    if (m == 2 and day >= 19) or (m == 3 and day <= 20):
        return "Pisces"
    if (m == 3 and day >= 21) or (m == 4 and day <= 19):
        return "Aries"
    if (m == 4 and day >= 20) or (m == 5 and day <= 20):
        return "Taurus"
    if (m == 5 and day >= 21) or (m == 6 and day <= 20):
        return "Gemini"
    if (m == 6 and day >= 21) or (m == 7 and day <= 22):
        return "Cancer"
    if (m == 7 and day >= 23) or (m == 8 and day <= 22):
        return "Leo"
    if (m == 8 and day >= 23) or (m == 9 and day <= 22):
        return "Virgo"
    if (m == 9 and day >= 23) or (m == 10 and day <= 22):
        return "Libra"
    if (m == 10 and day >= 23) or (m == 11 and day <= 21):
        return "Scorpio"
    return "Sagittarius"


def voting_window_for_month(year: int, month: int) -> tuple[date, date]:
    """Voting open 1st–7th of calendar month (demo schedule)."""
    start = date(year, month, 1)
    end = date(year, month, min(7, monthrange(year, month)[1]))
    return start, end


def cycle_status_for_today(
    today: date, voting_start: date, voting_end: date
) -> str:
    if today < voting_start:
        return "upcoming"
    if today <= voting_end:
        return "voting"
    return "closed"


def raw_path(full_id: str) -> str:
    return demo_user_core.raw_path(full_id)


def full_id_from_raw(raw: str) -> str:
    return PATH_PREFIX + raw


def path_parent_suffix(path: str) -> str | None:
    if "." not in path:
        return None
    parts = path.split(".")
    if len(parts) < 2:
        return None
    return ".".join(parts[:-1])


def geo_path_to_state_path(any_geo_path: str) -> str:
    p = any_geo_path
    while True:
        nxt = path_parent_suffix(p)
        if nxt is None:
            break
        p = nxt
    if p.count("/") < 2:
        return p
    head, tail = p.rsplit("/", 1)
    letters = "".join(ch for ch in tail if ch.isalpha())
    return f"{head}.{letters}"


def hierarchy_for_village(village_id: str) -> dict[str, str]:
    vraw = raw_path(village_id)
    traw = path_parent_suffix(vraw) or ""
    draw = path_parent_suffix(traw) if traw else ""
    sraw = geo_path_to_state_path(vraw)
    return {
        "village": village_id,
        "tehsil": full_id_from_raw(traw) if traw else "",
        "district": full_id_from_raw(draw) if draw else "",
        "state": full_id_from_raw(sraw) if sraw else "",
        "zone": "",
        "country": full_id_from_raw("IND"),
        "continent": full_id_from_raw("AS"),
        "earth": full_id_from_raw("0"),
    }


def villages_with_demo_users(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT demo_village_id FROM users
        WHERE is_demo = 1 AND demo_village_id IS NOT NULL
        ORDER BY demo_village_id
        """
    ).fetchall()
    return [str(r["demo_village_id"]) for r in rows]


def _eligible_voters_sql(
    location_id: str,
    zodiac_sign: str,
    *,
    level_type: str = "village",
) -> tuple[str, list[Any]]:
    if level_type == "village":
        return (
            """
            SELECT private_id, gender FROM users
            WHERE is_demo = 1 AND current_location_id = ?
              AND sun_sign = ? AND age_group = 'Yuvak'
            """,
            [location_id, zodiac_sign],
        )
    # Higher levels: all demo users in descendant villages under location
    raw = raw_path(location_id)
    prefix = full_id_from_raw(raw)
    return (
        """
        SELECT private_id, gender FROM users
        WHERE is_demo = 1 AND current_location_id LIKE ?
          AND sun_sign = ? AND age_group = 'Yuvak'
        """,
        [prefix + "%", zodiac_sign],
    )


def _pick_random_candidates(
    conn: sqlite3.Connection,
    location_id: str,
    zodiac_sign: str,
    gender: str,
    *,
    level_type: str = "village",
    count: int | None = None,
) -> list[str]:
    sql, params = _eligible_voters_sql(location_id, zodiac_sign, level_type=level_type)
    sql += " AND gender = ? ORDER BY RANDOM()"
    params.append(gender)
    limit = count or random.randint(3, 5)
    rows = conn.execute(sql + f" LIMIT {limit}", tuple(params)).fetchall()
    return [str(r["private_id"]) for r in rows]


def _child_winners(
    conn: sqlite3.Connection,
    parent_level: str,
    parent_location_id: str,
    zodiac_sign: str,
    gender: str,
) -> list[str]:
    child_level = LEVEL_CHILD.get(parent_level)
    if not child_level:
        return []
    raw = raw_path(parent_location_id)
    prefix = full_id_from_raw(raw)
    rows = conn.execute(
        """
        SELECT male_head_private_id, female_head_private_id, location_id
        FROM location_council
        WHERE level_type = ? AND location_id LIKE ? AND zodiac_sign = ?
        """,
        (child_level, prefix + "%", zodiac_sign),
    ).fetchall()
    out: list[str] = []
    for r in rows:
        pid = (
            r["male_head_private_id"]
            if gender == "Male"
            else r["female_head_private_id"]
        )
        if pid:
            out.append(str(pid))
    return out


def _get_or_create_cycle(
    conn: sqlite3.Connection,
    level_type: str,
    location_id: str,
    zodiac_sign: str,
    year: int,
    month: int,
) -> sqlite3.Row:
    element = election_scheduler.element_for_sign(zodiac_sign)
    vot_s, vot_e = voting_window_for_month(year, month)
    start = vot_s
    end = date(year, month, monthrange(year, month)[1])
    nom_s = start
    nom_e = start
    row = conn.execute(
        """
        SELECT * FROM election_cycles
        WHERE village_id = ? AND zodiac_sign = ? AND year = ? AND month = ?
          AND COALESCE(level_type, 'village') = ?
        """,
        (location_id, zodiac_sign, year, month, level_type),
    ).fetchone()
    if row:
        return row
    conn.execute(
        """
        INSERT INTO election_cycles (
            village_id, zodiac_sign, element, level_type,
            start_date, end_date, nomination_start, nomination_end,
            voting_start, voting_end, status, year, month
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'upcoming', ?, ?)
        """,
        (
            location_id,
            zodiac_sign,
            element,
            level_type,
            start.isoformat(),
            end.isoformat(),
            nom_s.isoformat(),
            nom_e.isoformat(),
            vot_s.isoformat(),
            vot_e.isoformat(),
            year,
            month,
        ),
    )
    row = conn.execute(
        """
        SELECT * FROM election_cycles
        WHERE village_id = ? AND zodiac_sign = ? AND year = ? AND month = ?
          AND COALESCE(level_type, 'village') = ?
        """,
        (location_id, zodiac_sign, year, month, level_type),
    ).fetchone()
    return row


def _simulate_votes(
    conn: sqlite3.Connection,
    cycle_id: int,
    location_id: str,
    zodiac_sign: str,
    candidates_by_gender: dict[str, list[str]],
    *,
    level_type: str = "village",
) -> tuple[int, int]:
    sql, params = _eligible_voters_sql(location_id, zodiac_sign, level_type=level_type)
    voters = conn.execute(sql, tuple(params)).fetchall()
    turnout = 0
    total = len(voters)
    weights_m = _vote_weights(len(candidates_by_gender.get("Male", [])))
    weights_f = _vote_weights(len(candidates_by_gender.get("Female", [])))

    for voter in voters:
        gender = str(voter["gender"] or "")
        bucket = election_scheduler.election_bucket_gender(gender)
        if not bucket:
            continue
        pool = candidates_by_gender.get(bucket, [])
        if not pool:
            continue
        weights = weights_m if bucket == "Male" else weights_f
        if not weights:
            continue
        cand = random.choices(pool, weights=weights, k=1)[0]
        exists = conn.execute(
            """
            SELECT 1 FROM election_votes
            WHERE election_cycle_id = ? AND voter_private_id = ? AND gender = ?
            """,
            (cycle_id, str(voter["private_id"]), bucket),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO election_votes (
                election_cycle_id, voter_private_id, candidate_private_id, gender
            ) VALUES (?, ?, ?, ?)
            """,
            (cycle_id, str(voter["private_id"]), cand, bucket),
        )
        turnout += 1

    conn.execute(
        """
        UPDATE election_cycles SET voter_turnout = ?, total_voters = ? WHERE id = ?
        """,
        (turnout, total, cycle_id),
    )
    return turnout, total


def _vote_weights(n: int) -> list[float]:
    if n <= 0:
        return []
    if n == 1:
        return [1.0]
    lead = 0.4
    rest = (1.0 - lead) / (n - 1)
    return [lead] + [rest] * (n - 1)


def _tally_winners(conn: sqlite3.Connection, cycle_id: int) -> tuple[str | None, str | None]:
    male_w = election_scheduler._pick_winner_for_gender(conn, cycle_id, "Male")
    female_w = election_scheduler._pick_winner_for_gender(conn, cycle_id, "Female")
    conn.execute(
        """
        UPDATE election_cycles
        SET male_winner_private_id = ?, female_winner_private_id = ?
        WHERE id = ?
        """,
        (male_w, female_w, cycle_id),
    )
    for gender, pid, pos in (
        ("Male", male_w, "Nayak"),
        ("Female", female_w, "Nayika"),
    ):
        if not pid:
            continue
        conn.execute(
            """
            UPDATE election_candidates
            SET is_winner = 0, position = NULL
            WHERE election_cycle_id = ? AND gender = ?
            """,
            (cycle_id, gender),
        )
        conn.execute(
            """
            UPDATE election_candidates
            SET is_winner = 1, position = ?
            WHERE election_cycle_id = ? AND candidate_private_id = ?
            """,
            (pos, cycle_id, pid),
        )
        vote_n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM election_votes
            WHERE election_cycle_id = ? AND candidate_private_id = ?
            """,
            (cycle_id, pid),
        ).fetchone()
        conn.execute(
            """
            UPDATE election_candidates SET total_votes = ?
            WHERE election_cycle_id = ? AND candidate_private_id = ?
            """,
            (int(vote_n["n"] or 0), cycle_id, pid),
        )
    return male_w, female_w


def _update_council(
    conn: sqlite3.Connection,
    level_type: str,
    location_id: str,
    zodiac_sign: str,
    cycle_id: int,
    male_w: str | None,
    female_w: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO location_council (
            level_type, location_id, zodiac_sign,
            male_head_private_id, female_head_private_id,
            election_cycle_id, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(level_type, location_id, zodiac_sign) DO UPDATE SET
            male_head_private_id = excluded.male_head_private_id,
            female_head_private_id = excluded.female_head_private_id,
            election_cycle_id = excluded.election_cycle_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (level_type, location_id, zodiac_sign, male_w, female_w, cycle_id),
    )
    if level_type == "village":
        conn.execute(
            """
            INSERT INTO village_council (
                village_id, zodiac_sign, male_head_private_id,
                female_head_private_id, election_cycle_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(village_id, zodiac_sign) DO UPDATE SET
                male_head_private_id = excluded.male_head_private_id,
                female_head_private_id = excluded.female_head_private_id,
                election_cycle_id = excluded.election_cycle_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (location_id, zodiac_sign, male_w, female_w, cycle_id),
        )
    try:
        import leadership_core

        leadership_core.ensure_location_slots(conn, level_type, location_id)
        if male_w:
            conn.execute(
                """
                UPDATE leadership_council
                SET current_holder_private_id = ?, status = 'filled', filled_at = ?
                WHERE level_type = ? AND location_id = ? AND slot_designation = 'nayak'
                """,
                (
                    male_w,
                    datetime.now(timezone.utc).isoformat(),
                    level_type,
                    location_id,
                ),
            )
        if female_w:
            conn.execute(
                """
                UPDATE leadership_council
                SET current_holder_private_id = ?, status = 'filled', filled_at = ?
                WHERE level_type = ? AND location_id = ? AND slot_designation = 'nayika'
                """,
                (
                    female_w,
                    datetime.now(timezone.utc).isoformat(),
                    level_type,
                    location_id,
                ),
            )
    except ImportError:
        pass


def _post_results_timeline(
    conn: sqlite3.Connection,
    location_id: str,
    zodiac_sign: str,
    male_w: str | None,
    female_w: str | None,
    level_type: str,
) -> None:
    content = (
        f"🗳️ {zodiac_sign} election results ({level_type}): "
        f"Nayak: {male_w or '—'} | Nayika: {female_w or '—'}"
    )
    author = male_w or female_w or "HU-014918240"
    try:
        conn.execute(
            """
            INSERT INTO posts (
                user_private_id, location_id, content, current_level, status, total_score,
                origin_village_id
            ) VALUES (?, ?, ?, ?, 'live', 0, ?)
            """,
            (
                author,
                location_id,
                content,
                level_type if level_type != "earth" else "earth",
                location_id if level_type == "village" else None,
            ),
        )
    except sqlite3.OperationalError:
        pass


def run_election_for_location(
    conn: sqlite3.Connection,
    level_type: str,
    location_id: str,
    zodiac_sign: str,
    year: int,
    month: int,
    *,
    simulate: bool = True,
) -> dict[str, Any]:
    migrate_election_automation_schema(conn)
    cycle = _get_or_create_cycle(
        conn, level_type, location_id, zodiac_sign, year, month
    )
    cycle_id = int(cycle["id"])
    candidates_by_gender: dict[str, list[str]] = {"Male": [], "Female": []}

    if level_type == "village":
        for gender in ("Male", "Female"):
            pool = _pick_random_candidates(
                conn, location_id, zodiac_sign, gender, level_type=level_type
            )
            candidates_by_gender[gender] = pool
    else:
        for gender in ("Male", "Female"):
            pool = _child_winners(
                conn, level_type, location_id, zodiac_sign, gender
            )
            if len(pool) < 3:
                pool = _pick_random_candidates(
                    conn,
                    location_id,
                    zodiac_sign,
                    gender,
                    level_type=level_type,
                    count=3,
                )
            candidates_by_gender[gender] = pool[:5]

    conn.execute(
        "DELETE FROM election_candidates WHERE election_cycle_id = ?",
        (cycle_id,),
    )
    conn.execute(
        "DELETE FROM election_votes WHERE election_cycle_id = ?",
        (cycle_id,),
    )

    for gender, pool in candidates_by_gender.items():
        pos = "Nayak" if gender == "Male" else "Nayika"
        for pid in pool:
            manifest = json.dumps(
                {"why_stand": "Demo candidate", "changes": "Serve the community"},
                ensure_ascii=False,
            )
            conn.execute(
                """
                INSERT INTO election_candidates (
                    election_cycle_id, candidate_private_id, gender,
                    manifest, status, position
                ) VALUES (?, ?, ?, ?, 'approved', ?)
                """,
                (cycle_id, pid, gender, manifest, pos),
            )

    if simulate:
        turnout, total = _simulate_votes(
            conn,
            cycle_id,
            location_id,
            zodiac_sign,
            candidates_by_gender,
            level_type=level_type,
        )
    else:
        turnout, total = 0, 0

    male_w, female_w = _tally_winners(conn, cycle_id)
    conn.execute(
        "UPDATE election_cycles SET status = 'closed' WHERE id = ?",
        (cycle_id,),
    )
    _update_council(
        conn, level_type, location_id, zodiac_sign, cycle_id, male_w, female_w
    )
    _post_results_timeline(
        conn, location_id, zodiac_sign, male_w, female_w, level_type
    )
    demo_user_core.log_demo_action(
        conn,
        "election_complete",
        f"{level_type}:{location_id} {zodiac_sign} {year}-{month:02d}",
    )
    conn.commit()
    return {
        "cycle_id": cycle_id,
        "level_type": level_type,
        "location_id": location_id,
        "zodiac_sign": zodiac_sign,
        "male_winner": male_w,
        "female_winner": female_w,
        "turnout": turnout,
        "total_voters": total,
    }


def zodiac_sign_for_month(year: int, month: int) -> str:
    """Sun sign active on the 1st of the calendar month."""
    return sun_sign_for_date(date(year, month, 1))


def run_village_elections_for_month(
    conn: sqlite3.Connection,
    year: int,
    month: int,
    *,
    simulate: bool = True,
    progress_cb: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    zodiac_sign = zodiac_sign_for_month(year, month)
    villages = villages_with_demo_users(conn)
    results: list[dict[str, Any]] = []
    for vid in villages:
        res = run_election_for_location(
            conn, "village", vid, zodiac_sign, year, month, simulate=simulate
        )
        results.append(res)
        if progress_cb:
            progress_cb(f"Village election {vid}")
    return results


def run_hierarchy_elections_for_month(
    conn: sqlite3.Connection,
    year: int,
    month: int,
    *,
    simulate: bool = True,
) -> list[dict[str, Any]]:
    zodiac_sign = zodiac_sign_for_month(year, month)
    villages = villages_with_demo_users(conn)
    locations: dict[tuple[str, str], None] = {}
    for vid in villages:
        hier = hierarchy_for_village(vid)
        for lt in ("tehsil", "district", "state", "country", "continent", "earth"):
            loc = hier.get(lt, "")
            if loc:
                locations[(lt, loc)] = None

    results: list[dict[str, Any]] = []
    for level_type in ("tehsil", "district", "state", "country", "continent", "earth"):
        for loc_id in sorted({k[1] for k in locations if k[0] == level_type}):
            res = run_election_for_location(
                conn,
                level_type,
                loc_id,
                zodiac_sign,
                year,
                month,
                simulate=simulate,
            )
            results.append(res)
    return results


def run_monthly_election_job(
    conn: sqlite3.Connection,
    *,
    today: date | None = None,
    simulate: bool = True,
    include_hierarchy: bool = False,
) -> dict[str, Any]:
    today = today or date.today()
    year, month = today.year, today.month
    migrate_election_automation_schema(conn)
    demo_user_core.log_demo_action(
        conn, "monthly_election_start", f"{year}-{month:02d}"
    )
    village_results = run_village_elections_for_month(
        conn, year, month, simulate=simulate
    )
    hierarchy_results: list[dict[str, Any]] = []
    if include_hierarchy:
        hierarchy_results = run_hierarchy_elections_for_month(
            conn, year, month, simulate=simulate
        )
    summary = {
        "year": year,
        "month": month,
        "zodiac_sign": zodiac_sign_for_month(year, month),
        "village_elections": len(village_results),
        "hierarchy_elections": len(hierarchy_results),
    }
    demo_user_core.log_demo_action(conn, "monthly_election_done", json.dumps(summary))
    conn.commit()
    return summary


def elections_active_for_level(level_type: str) -> bool:
    return (level_type or "").strip().lower() == "village"


def get_widget_payload(
    conn: sqlite3.Connection,
    level_type: str,
    location_id: str,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    migrate_election_automation_schema(conn)
    today = today or date.today()
    lt = (level_type or "village").strip().lower()
    loc = (location_id or "").strip()
    active_sign = sun_sign_for_date(today)
    year, month = today.year, today.month
    vot_s, vot_e = voting_window_for_month(year, month)
    status = cycle_status_for_today(today, vot_s, vot_e)

    cycle = None
    if loc:
        cycle_row = conn.execute(
            """
            SELECT * FROM election_cycles
            WHERE village_id = ? AND COALESCE(level_type, 'village') = ?
              AND year = ? AND month = ?
            """,
            (loc, lt, year, month),
        ).fetchone()
        if cycle_row:
            cid = int(cycle_row["id"])
            candidates = []
            for r in conn.execute(
                """
                SELECT c.id, c.candidate_private_id, c.gender, c.position,
                       c.is_winner, c.total_votes,
                       u.first_name, u.last_name, u.public_id
                FROM election_candidates c
                JOIN users u ON u.private_id = c.candidate_private_id
                WHERE c.election_cycle_id = ? AND c.status = 'approved'
                ORDER BY c.gender, c.total_votes DESC
                """,
                (cid,),
            ):
                vote_n = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM election_votes
                    WHERE election_cycle_id = ? AND candidate_private_id = ?
                    """,
                    (cid, r["candidate_private_id"]),
                ).fetchone()
                candidates.append(
                    {
                        "id": int(r["id"]),
                        "name": f"{r['first_name']} {r['last_name']}".strip(),
                        "public_id": str(r["public_id"] or ""),
                        "gender": str(r["gender"]),
                        "position": str(r["position"] or ""),
                        "vote_count": int(vote_n["n"] or r["total_votes"] or 0),
                        "is_winner": bool(r["is_winner"]),
                    }
                )
            cycle = {
                "id": cid,
                "zodiac_sign": str(cycle_row["zodiac_sign"]),
                "status": str(cycle_row["status"] or status),
                "voting_start": str(cycle_row["voting_start"]),
                "voting_end": str(cycle_row["voting_end"]),
                "voter_turnout": int(cycle_row["voter_turnout"] or 0),
                "total_voters": int(cycle_row["total_voters"] or 0),
                "male_winner": cycle_row["male_winner_private_id"],
                "female_winner": cycle_row["female_winner_private_id"],
                "candidates": candidates,
            }

    past = []
    if loc:
        for r in conn.execute(
            """
            SELECT zodiac_sign, year, month, status, male_winner_private_id,
                   female_winner_private_id, voter_turnout, total_voters
            FROM election_cycles
            WHERE village_id = ? AND COALESCE(level_type, 'village') = ?
              AND status = 'closed'
            ORDER BY year DESC, month DESC
            LIMIT 12
            """,
            (loc, lt),
        ):
            past.append(
                {
                    "zodiac_sign": str(r["zodiac_sign"]),
                    "year": int(r["year"] or 0),
                    "month": int(r["month"] or 0),
                    "male_winner": r["male_winner_private_id"],
                    "female_winner": r["female_winner_private_id"],
                    "turnout": int(r["voter_turnout"] or 0),
                    "total_voters": int(r["total_voters"] or 0),
                }
            )

    leaders = []
    if loc:
        for r in conn.execute(
            """
            SELECT zodiac_sign, male_head_private_id, female_head_private_id
            FROM location_council
            WHERE level_type = ? AND location_id = ?
            ORDER BY zodiac_sign
            """,
            (lt, loc),
        ):
            leaders.append(
                {
                    "zodiac_sign": str(r["zodiac_sign"]),
                    "nayak": r["male_head_private_id"],
                    "nayika": r["female_head_private_id"],
                }
            )

    countdown_end = vot_e.isoformat() if status == "voting" else None
    voting_active = elections_active_for_level(lt)
    return {
        "level_type": lt,
        "location_id": loc,
        "active_zodiac_sign": active_sign,
        "phase": status if voting_active else "inactive",
        "voting_active": voting_active,
        "inactive_message": VILLAGE_ONLY_MESSAGE if not voting_active else "",
        "voting_window": {
            "start": vot_s.isoformat(),
            "end": vot_e.isoformat(),
        },
        "countdown_end": countdown_end if voting_active else None,
        "cycle": cycle if voting_active else None,
        "past_results": past if voting_active else [],
        "current_leaders": leaders if voting_active else [],
        "elections_enabled": True,
    }


def get_automation_logs(
    conn: sqlite3.Connection, limit: int = 50
) -> list[dict[str, str]]:
    migrate_election_automation_schema(conn)
    rows = conn.execute(
        """
        SELECT action, details, created_at FROM demo_automation_log
        ORDER BY id DESC LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [
        {
            "action": str(r["action"]),
            "details": str(r["details"] or ""),
            "created_at": str(r["created_at"] or ""),
        }
        for r in rows
    ]
