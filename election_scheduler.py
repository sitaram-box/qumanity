#!/usr/bin/env python3
"""Quantum Punch — zodiac-based village council elections (prototype, 2026).

Automated cycle processing for a single target village. Call
``migrate_election_tables`` from app bootstrap; call ``process_election_cycles``
from a request hook or cron.
"""

from __future__ import annotations

import json
import random
import sqlite3
from calendar import monthrange
from datetime import date, timedelta
from typing import Callable

# --- Target scope (prototype) ------------------------------------------------
TARGET_VILLAGE_ID = "0.राम|IND/CS/DL.5.4.1E"

SendFn = Callable[[sqlite3.Connection, str, str, str], str]

ELEMENT_BY_SIGN: dict[str, str] = {
    "Aries": "Fire",
    "Leo": "Fire",
    "Sagittarius": "Fire",
    "Taurus": "Earth",
    "Virgo": "Earth",
    "Capricorn": "Earth",
    "Gemini": "Air",
    "Libra": "Air",
    "Aquarius": "Air",
    "Cancer": "Water",
    "Scorpio": "Water",
    "Pisces": "Water",
}

# Approximate 2026 sun-sign windows: each sign runs 15th → next 15th.
# Taurus = 15 May – 15 Jun 2026 per product brief.
ZODIAC_PERIOD_START_2026: list[tuple[str, date]] = [
    ("Sagittarius", date(2025, 12, 15)),
    ("Capricorn", date(2026, 1, 15)),
    ("Aquarius", date(2026, 2, 15)),
    ("Pisces", date(2026, 3, 15)),
    ("Aries", date(2026, 4, 15)),
    ("Taurus", date(2026, 5, 15)),
    ("Gemini", date(2026, 6, 15)),
    ("Cancer", date(2026, 7, 15)),
    ("Leo", date(2026, 8, 15)),
    ("Virgo", date(2026, 9, 15)),
    ("Libra", date(2026, 10, 15)),
    ("Scorpio", date(2026, 11, 15)),
    ("Sagittarius", date(2026, 12, 15)),
]


def element_for_sign(sign: str) -> str:
    return ELEMENT_BY_SIGN[sign]


def nomination_voting_bounds(start: date) -> tuple[date, date, date, date]:
    """Nomination 16th–22nd after cycle start; voting 23rd → 5th of next month."""
    nom_start = start + timedelta(days=1)
    nom_end = start + timedelta(days=7)
    y, m = start.year, start.month
    last = monthrange(y, m)[1]
    vot_start = date(y, m, min(23, last))
    if vot_start <= nom_end:
        vot_start = nom_end + timedelta(days=1)
    if m == 12:
        ny, nm = y + 1, 1
    else:
        ny, nm = y, m + 1
    vot_end = date(ny, nm, 5)
    return nom_start, nom_end, vot_start, vot_end


def sun_sign_for_election_day(d: date) -> tuple[str, date, date] | None:
    """Return (sign, period_start, period_end inclusive) for prototype calendar."""
    for i, (sign, start) in enumerate(ZODIAC_PERIOD_START_2026):
        if i + 1 < len(ZODIAC_PERIOD_START_2026):
            nxt = ZODIAC_PERIOD_START_2026[i + 1][1]
        else:
            nxt = date(2027, 1, 15)
        if start <= d < nxt:
            return sign, start, nxt - timedelta(days=1)
    return None


def _karma_sql_fragment(alias: str = "u") -> str:
    return (
        f"(COALESCE({alias}.mentor_level,0)+COALESCE({alias}.manager_level,0)+"
        f"COALESCE({alias}.leader_level,0)+COALESCE({alias}.agent_level,0))"
    )


ELECTION_DDL = """
CREATE TABLE IF NOT EXISTS election_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    village_id TEXT NOT NULL,
    zodiac_sign TEXT NOT NULL,
    element TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    nomination_start DATE NOT NULL,
    nomination_end DATE NOT NULL,
    voting_start DATE NOT NULL,
    voting_end DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'upcoming',
    male_winner_private_id TEXT,
    female_winner_private_id TEXT,
    nomination_notice_sent INTEGER NOT NULL DEFAULT 0,
    voting_notice_sent INTEGER NOT NULL DEFAULT 0,
    results_notice_sent INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(village_id, zodiac_sign, start_date)
);

CREATE TABLE IF NOT EXISTS election_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    election_cycle_id INTEGER NOT NULL,
    candidate_private_id TEXT NOT NULL,
    gender TEXT NOT NULL,
    manifest TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (election_cycle_id) REFERENCES election_cycles(id),
    UNIQUE(election_cycle_id, candidate_private_id)
);

CREATE TABLE IF NOT EXISTS election_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    election_cycle_id INTEGER NOT NULL,
    voter_private_id TEXT NOT NULL,
    candidate_private_id TEXT NOT NULL,
    gender TEXT NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (election_cycle_id) REFERENCES election_cycles(id),
    UNIQUE(election_cycle_id, voter_private_id, gender)
);

CREATE TABLE IF NOT EXISTS village_council (
    village_id TEXT NOT NULL,
    zodiac_sign TEXT NOT NULL,
    male_head_private_id TEXT,
    female_head_private_id TEXT,
    election_cycle_id INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (village_id, zodiac_sign),
    FOREIGN KEY (election_cycle_id) REFERENCES election_cycles(id)
);

CREATE INDEX IF NOT EXISTS idx_election_cycles_village ON election_cycles(village_id, status);
CREATE INDEX IF NOT EXISTS idx_election_cycles_dates ON election_cycles(village_id, start_date);
CREATE INDEX IF NOT EXISTS idx_election_candidates_cycle ON election_candidates(election_cycle_id);
CREATE INDEX IF NOT EXISTS idx_election_votes_cycle ON election_votes(election_cycle_id);
"""


def migrate_election_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(ELECTION_DDL)
    for table, col, decl in (
        ("election_cycles", "village_id", "TEXT NOT NULL DEFAULT ''"),
        ("election_cycles", "nomination_notice_sent", "INTEGER NOT NULL DEFAULT 0"),
        ("election_cycles", "voting_notice_sent", "INTEGER NOT NULL DEFAULT 0"),
        ("election_cycles", "results_notice_sent", "INTEGER NOT NULL DEFAULT 0"),
    ):
        cols = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}
        if col in cols:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        except sqlite3.OperationalError:
            pass
    try:
        conn.execute(
            """
            UPDATE election_cycles SET village_id = ?
            WHERE village_id IS NULL OR TRIM(village_id) = ''
            """,
            (TARGET_VILLAGE_ID,),
        )
    except sqlite3.OperationalError:
        pass
    conn.commit()


def _eligible_voters(
    conn: sqlite3.Connection, village_id: str, zodiac_sign: str
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            f"""
            SELECT private_id, first_name, last_name, public_id, sun_sign, gender,
                   {_karma_sql_fragment("u")} AS karma_index
            FROM users u
            WHERE TRIM(u.current_location_id) = TRIM(?)
              AND u.sun_sign = ?
            """,
            (village_id, zodiac_sign),
        )
    )


def _notify_eligible(
    conn: sqlite3.Connection,
    village_id: str,
    zodiac_sign: str,
    subject: str,
    body: str,
    send_fn: SendFn | None,
) -> None:
    if not send_fn:
        return
    for row in _eligible_voters(conn, village_id, zodiac_sign):
        send_fn(conn, str(row["private_id"]), subject, body)


def _cycle_row_for_period(
    conn: sqlite3.Connection, village_id: str, sign: str, period_start: date
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM election_cycles
        WHERE village_id = ? AND zodiac_sign = ? AND start_date = ?
        """,
        (village_id, sign, period_start.isoformat()),
    ).fetchone()


def _derive_cycle_status(today: date, nom_s: date, nom_e: date, vot_s: date, vot_e: date) -> str:
    if today < nom_s:
        return "upcoming"
    if today <= nom_e:
        return "nomination"
    if today < vot_s:
        return "nomination"
    if today <= vot_e:
        return "voting"
    return "closed"


def _pick_winner_for_gender(
    conn: sqlite3.Connection, cycle_id: int, gender: str
) -> str | None:
    kf = _karma_sql_fragment("u")
    tallies = conn.execute(
        f"""
        SELECT v.candidate_private_id AS pid,
               COUNT(*) AS c,
               MAX({kf}) AS karma
        FROM election_votes v
        JOIN users u ON u.private_id = v.candidate_private_id
        WHERE v.election_cycle_id = ? AND v.gender = ?
        GROUP BY v.candidate_private_id
        """,
        (cycle_id, gender),
    ).fetchall()
    if not tallies:
        return None
    best_votes = max(int(t["c"]) for t in tallies)
    top = [t for t in tallies if int(t["c"]) == best_votes]
    top.sort(key=lambda t: int(t["karma"] or 0), reverse=True)
    if len(top) == 1:
        return str(top[0]["pid"])
    rnd = random.Random(cycle_id * 31 + (1 if gender == "Male" else 2))
    return str(rnd.choice(top)["pid"])


def _finalize_cycle(
    conn: sqlite3.Connection,
    cycle_id: int,
    village_id: str,
    zodiac_sign: str,
    send_fn: SendFn | None,
) -> None:
    row = conn.execute(
        "SELECT * FROM election_cycles WHERE id = ?", (cycle_id,)
    ).fetchone()
    if not row:
        return

    prev_m = row["male_winner_private_id"]
    prev_f = row["female_winner_private_id"]
    male_w = prev_m or _pick_winner_for_gender(conn, cycle_id, "Male")
    female_w = prev_f or _pick_winner_for_gender(conn, cycle_id, "Female")

    conn.execute(
        """
        UPDATE election_cycles
        SET male_winner_private_id = COALESCE(?, male_winner_private_id),
            female_winner_private_id = COALESCE(?, female_winner_private_id)
        WHERE id = ?
        """,
        (male_w, female_w, cycle_id),
    )
    fresh = conn.execute(
        "SELECT male_winner_private_id, female_winner_private_id, results_notice_sent "
        "FROM election_cycles WHERE id = ?",
        (cycle_id,),
    ).fetchone()
    if not fresh:
        return

    mv = fresh["male_winner_private_id"]
    fv = fresh["female_winner_private_id"]

    conn.execute(
        """
        INSERT INTO village_council (
            village_id, zodiac_sign,
            male_head_private_id, female_head_private_id,
            election_cycle_id, updated_at
        ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(village_id, zodiac_sign) DO UPDATE SET
            male_head_private_id = excluded.male_head_private_id,
            female_head_private_id = excluded.female_head_private_id,
            election_cycle_id = excluded.election_cycle_id,
            updated_at = CURRENT_TIMESTAMP
        """,
        (village_id, zodiac_sign, mv, fv, cycle_id),
    )

    if send_fn:
        if mv and not prev_m:
            send_fn(
                conn,
                str(mv),
                f"Quantum Punch: {zodiac_sign} — you were elected",
                "You are the male zodiac head for Rohini Sector-24 (Quantum Punch) "
                f"for the {zodiac_sign} cycle.",
            )
        if fv and not prev_f:
            send_fn(
                conn,
                str(fv),
                f"Quantum Punch: {zodiac_sign} — you were elected",
                "You are the female zodiac head for Rohini Sector-24 (Quantum Punch) "
                f"for the {zodiac_sign} cycle.",
            )

        if not int(fresh["results_notice_sent"] or 0):
            body = (
                f"The {zodiac_sign} Quantum Punch election has closed.\n"
                f"Male head: {mv or '(none)'}\n"
                f"Female head: {fv or '(none)'}"
            )
            seen: set[str] = set()
            for u in _eligible_voters(conn, village_id, zodiac_sign):
                pid = str(u["private_id"])
                if pid not in seen:
                    seen.add(pid)
                    send_fn(
                        conn,
                        pid,
                        f"Quantum Punch: {zodiac_sign} results",
                        body,
                    )
            conn.execute(
                "UPDATE election_cycles SET results_notice_sent = 1 WHERE id = ?",
                (cycle_id,),
            )


def process_election_cycles(
    conn: sqlite3.Connection,
    *,
    send_system_message_fn: SendFn | None = None,
    today: date | None = None,
) -> None:
    """Advance statuses, create missing cycles, send notices, close and tally."""
    today = today or date.today()
    migrate_election_tables(conn)
    village_id = TARGET_VILLAGE_ID

    active = sun_sign_for_election_day(today)
    if active:
        sign, p_start, p_end = active
        el = element_for_sign(sign)
        nom_s, nom_e, vot_s, vot_e = nomination_voting_bounds(p_start)
        if _cycle_row_for_period(conn, village_id, sign, p_start) is None:
            conn.execute(
                """
                INSERT OR IGNORE INTO election_cycles (
                    village_id, zodiac_sign, element,
                    start_date, end_date,
                    nomination_start, nomination_end,
                    voting_start, voting_end,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    village_id,
                    sign,
                    el,
                    p_start.isoformat(),
                    p_end.isoformat(),
                    nom_s.isoformat(),
                    nom_e.isoformat(),
                    vot_s.isoformat(),
                    vot_e.isoformat(),
                    "upcoming",
                ),
            )

    for cycle in conn.execute(
        "SELECT * FROM election_cycles WHERE village_id = ?", (village_id,)
    ):
        cid = int(cycle["id"])
        zs = str(cycle["zodiac_sign"])
        vs = date.fromisoformat(str(cycle["voting_start"]))
        ve = date.fromisoformat(str(cycle["voting_end"]))
        ns = date.fromisoformat(str(cycle["nomination_start"]))
        ne = date.fromisoformat(str(cycle["nomination_end"]))
        st = _derive_cycle_status(today, ns, ne, vs, ve)
        prev = str(cycle["status"] or "")
        conn.execute(
            "UPDATE election_cycles SET status = ? WHERE id = ?",
            (st, cid),
        )

        if (
            st == "nomination"
            and prev in ("", "upcoming")
            and not int(cycle["nomination_notice_sent"] or 0)
        ):
            _notify_eligible(
                conn,
                village_id,
                zs,
                f"Quantum Punch: {zs} nominations open",
                "You may stand for Village Council (Quantum Punch) for your zodiac month. "
                "Open Public Account → Village → Quantum Punch Elections to nominate yourself.",
                send_system_message_fn,
            )
            conn.execute(
                "UPDATE election_cycles SET nomination_notice_sent = 1 WHERE id = ?",
                (cid,),
            )

        if st == "voting" and not int(cycle["voting_notice_sent"] or 0):
            _notify_eligible(
                conn,
                village_id,
                zs,
                f"Quantum Punch: {zs} voting open",
                "Voting is open for your zodiac council election. "
                "Use the Quantum Punch Elections card on your Village tab.",
                send_system_message_fn,
            )
            conn.execute(
                "UPDATE election_cycles SET voting_notice_sent = 1 WHERE id = ?",
                (cid,),
            )

        if st == "closed":
            _finalize_cycle(conn, cid, village_id, zs, send_system_message_fn)

    conn.commit()


def election_bucket_gender(user_gender: str) -> str | None:
    g = (user_gender or "").strip()
    if g in ("Male", "Male born female"):
        return "Male"
    if g in ("Female", "Female born male"):
        return "Female"
    return None


def parse_manifest(manifest_raw: str | None) -> dict[str, str]:
    if not manifest_raw:
        return {}
    try:
        o = json.loads(manifest_raw)
        if isinstance(o, dict):
            return {str(k): str(v) for k, v in o.items()}
    except json.JSONDecodeError:
        pass
    return {"text": str(manifest_raw)}
