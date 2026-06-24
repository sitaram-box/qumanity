"""
Quantum Spiritual Interface (QSI) — Sacred Spin system for 12 Naam services.
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import qoin_core

UTC = timezone.utc

# ── Service catalogue ─────────────────────────────────────────────────────────

SERVICES: list[dict[str, Any]] = [
    {
        "service_id": 1,
        "service_name_en": "Nam Jap",
        "service_name_hi": "नाम जप",
        "translation": "Name Chanting / Repetition",
        "description": "Personal meditation, focus, inner peace",
        "icon": "🪷",
        "color": "#F59E0B",
        "category": "A",
        "spin_frequency": "unlimited",
        "karma_visible": False,
        "base_karma_points": 0,
    },
    {
        "service_id": 2,
        "service_name_en": "Nam Kirtan",
        "service_name_hi": "नाम कीर्तन",
        "translation": "Name Singing / Chanting (Group)",
        "description": "Collective spiritual practice, community bonding",
        "icon": "🎵",
        "color": "#3B82F6",
        "category": "A",
        "spin_frequency": "unlimited",
        "karma_visible": False,
        "base_karma_points": 0,
    },
    {
        "service_id": 3,
        "service_name_en": "Nam Nartan",
        "service_name_hi": "नाम नर्तन",
        "translation": "Name Dance / Movement",
        "description": "Joyful expression through movement and music",
        "icon": "💃",
        "color": "#10B981",
        "category": "A",
        "spin_frequency": "unlimited",
        "karma_visible": False,
        "base_karma_points": 0,
    },
    {
        "service_id": 4,
        "service_name_en": "Nam Satsang",
        "service_name_hi": "नाम सत्संग",
        "translation": "Name Fellowship / Gathering",
        "description": "Group discussion, sharing of spiritual wisdom",
        "icon": "🕉️",
        "color": "#8B5CF6",
        "category": "B",
        "spin_frequency": "once_per_service",
        "karma_visible": False,
        "base_karma_points": 50,
    },
    {
        "service_id": 5,
        "service_name_en": "Nam Katha",
        "service_name_hi": "नाम कथा",
        "translation": "Name Stories / Narratives",
        "description": "Listening to or sharing stories about the divine",
        "icon": "📖",
        "color": "#EC4899",
        "category": "B",
        "spin_frequency": "once_per_service",
        "karma_visible": True,
        "base_karma_points": 60,
    },
    {
        "service_id": 6,
        "service_name_en": "Nam Seva",
        "service_name_hi": "नाम सेवा",
        "translation": "Name Service / Volunteering",
        "description": "Selfless service offered in the spirit of the Name",
        "icon": "🙏",
        "color": "#EF4444",
        "category": "B",
        "spin_frequency": "once_per_service",
        "karma_visible": True,
        "base_karma_points": 80,
    },
    {
        "service_id": 7,
        "service_name_en": "Nam Shiksha",
        "service_name_hi": "नाम शिक्षा",
        "translation": "Name Education",
        "description": "Learning about spiritual traditions and wisdom",
        "icon": "📚",
        "color": "#06B6D4",
        "category": "C",
        "spin_frequency": "lifetime",
        "karma_visible": True,
        "base_karma_points": 100,
    },
    {
        "service_id": 8,
        "service_name_en": "Nam Swasthya",
        "service_name_hi": "नाम स्वास्थ्य",
        "translation": "Name Health",
        "description": "Healing practices, wellness, mental peace",
        "icon": "⚕️",
        "color": "#14B8A6",
        "category": "C",
        "spin_frequency": "lifetime",
        "karma_visible": True,
        "base_karma_points": 100,
    },
    {
        "service_id": 9,
        "service_name_en": "Nam Daan",
        "service_name_hi": "नाम दान",
        "translation": "Name Charity",
        "description": "Giving money, items, or time in the spirit of the Name",
        "icon": "🎁",
        "color": "#F97316",
        "category": "C",
        "spin_frequency": "lifetime",
        "karma_visible": True,
        "base_karma_points": 100,
    },
    {
        "service_id": 10,
        "service_name_en": "Nam Raksha",
        "service_name_hi": "नाम रक्षा",
        "translation": "Name Protection",
        "description": "Safety, protection of vulnerable beings, animal welfare",
        "icon": "🛡️",
        "color": "#6366F1",
        "category": "C",
        "spin_frequency": "lifetime",
        "karma_visible": True,
        "base_karma_points": 100,
    },
    {
        "service_id": 11,
        "service_name_en": "Nam Shodh",
        "service_name_hi": "नाम शोध",
        "translation": "Name Research",
        "description": "Spiritual inquiry, study, and exploration",
        "icon": "🔬",
        "color": "#A855F7",
        "category": "C",
        "spin_frequency": "lifetime",
        "karma_visible": True,
        "base_karma_points": 100,
    },
    {
        "service_id": 12,
        "service_name_en": "Nam Das",
        "service_name_hi": "नाम दास",
        "translation": "Name Servant / Devotee",
        "description": "Reserved for exceptional devotees — not accessible yet",
        "icon": "✨",
        "color": "#64748B",
        "category": "D",
        "spin_frequency": "not_accessible",
        "karma_visible": False,
        "base_karma_points": 0,
    },
]

ACTIVE_STATUSES = ("pending", "in_progress", "completed")
BLOCKING_STATUSES = ("pending", "in_progress", "completed", "verified")


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def migrate_qsi_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS qsi_service_categories (
            service_id INTEGER PRIMARY KEY,
            service_name_en TEXT NOT NULL,
            service_name_hi TEXT NOT NULL,
            translation TEXT,
            description TEXT,
            icon TEXT,
            color TEXT,
            category TEXT NOT NULL,
            spin_frequency TEXT NOT NULL,
            karma_visible INTEGER NOT NULL DEFAULT 0,
            base_karma_points INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS qsi_user_name_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            chosen_name TEXT NOT NULL,
            religion TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS qsi_user_spins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service_id INTEGER NOT NULL,
            chosen_name TEXT,
            spin_date TEXT NOT NULL,
            mode TEXT NOT NULL,
            duration_days INTEGER NOT NULL DEFAULT 0,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            attendance INTEGER NOT NULL DEFAULT 0,
            punctuality_score INTEGER NOT NULL DEFAULT 0,
            passion_score INTEGER NOT NULL DEFAULT 0,
            verification_status TEXT NOT NULL DEFAULT 'pending',
            verified_by INTEGER,
            karma_points_awarded INTEGER NOT NULL DEFAULT 0,
            karma_points_value INTEGER NOT NULL DEFAULT 0,
            hidden_karma_counter INTEGER NOT NULL DEFAULT 0,
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qsi_spins_user ON qsi_user_spins(user_id, service_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qsi_spins_status ON qsi_user_spins(status, verification_status)"
    )
    _seed_services(conn)
    _seed_karma_action(conn)
    conn.commit()


def _seed_services(conn: sqlite3.Connection) -> None:
    for svc in SERVICES:
        conn.execute(
            """
            INSERT INTO qsi_service_categories (
                service_id, service_name_en, service_name_hi, translation,
                description, icon, color, category, spin_frequency,
                karma_visible, base_karma_points
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(service_id) DO UPDATE SET
                service_name_en = excluded.service_name_en,
                service_name_hi = excluded.service_name_hi,
                translation = excluded.translation,
                description = excluded.description,
                icon = excluded.icon,
                color = excluded.color,
                category = excluded.category,
                spin_frequency = excluded.spin_frequency,
                karma_visible = excluded.karma_visible,
                base_karma_points = excluded.base_karma_points
            """,
            (
                svc["service_id"],
                svc["service_name_en"],
                svc["service_name_hi"],
                svc["translation"],
                svc["description"],
                svc["icon"],
                svc["color"],
                svc["category"],
                svc["spin_frequency"],
                1 if svc["karma_visible"] else 0,
                svc["base_karma_points"],
            ),
        )


def _seed_karma_action(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='karma_action_types'"
    ).fetchone()
    if not row:
        return
    conn.execute(
        """
        INSERT INTO karma_action_types (action_code, label, rupee_value, active)
        VALUES ('qsi_award', 'QSI Naam Service', 0, 1)
        ON CONFLICT(action_code) DO NOTHING
        """
    )


def get_service(service_id: int) -> dict[str, Any] | None:
    svc = next((s for s in SERVICES if s["service_id"] == service_id), None)
    return dict(svc) if svc else None


def list_services(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    migrate_qsi_schema(conn)
    rows = conn.execute(
        "SELECT * FROM qsi_service_categories ORDER BY service_id"
    ).fetchall()
    return [dict(r) for r in rows]


def get_user_name(conn: sqlite3.Connection, user_id: int) -> dict[str, Any] | None:
    migrate_qsi_schema(conn)
    row = conn.execute(
        "SELECT chosen_name, religion, updated_at FROM qsi_user_name_preferences WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return dict(row) if row else None


def set_user_name(
    conn: sqlite3.Connection,
    user_id: int,
    chosen_name: str,
    religion: str | None = None,
) -> dict[str, Any]:
    migrate_qsi_schema(conn)
    name = chosen_name.strip()
    if not name:
        raise ValueError("chosen_name is required")
    now = _now()
    conn.execute(
        """
        INSERT INTO qsi_user_name_preferences (user_id, chosen_name, religion, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            chosen_name = excluded.chosen_name,
            religion = excluded.religion,
            updated_at = excluded.updated_at
        """,
        (user_id, name, (religion or "").strip() or None, now),
    )
    return {"chosen_name": name, "religion": religion, "updated_at": now}


def _spin_row_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    try:
        data["details"] = json.loads(data.get("details") or "{}")
    except json.JSONDecodeError:
        data["details"] = {}
    svc = get_service(int(data["service_id"]))
    if svc:
        data["service"] = svc
    return data


def get_spin(conn: sqlite3.Connection, spin_id: int) -> dict[str, Any] | None:
    migrate_qsi_schema(conn)
    row = conn.execute(
        "SELECT * FROM qsi_user_spins WHERE id = ?",
        (spin_id,),
    ).fetchone()
    return _spin_row_dict(row) if row else None


def can_spin(conn: sqlite3.Connection, user_id: int, service_id: int) -> bool:
    svc = get_service(service_id)
    if not svc or svc["category"] == "D":
        return False
    migrate_qsi_schema(conn)
    freq = svc["spin_frequency"]
    if freq == "unlimited":
        return True
    if freq == "lifetime":
        row = conn.execute(
            "SELECT 1 FROM qsi_user_spins WHERE user_id = ? AND service_id = ? LIMIT 1",
            (user_id, service_id),
        ).fetchone()
        return row is None
    if freq == "once_per_service":
        row = conn.execute(
            """
            SELECT status FROM qsi_user_spins
            WHERE user_id = ? AND service_id = ?
              AND status IN ('pending', 'in_progress', 'completed', 'verified')
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, service_id),
        ).fetchone()
        if row is None:
            return True
        return str(row["status"]) == "karma_awarded"
    return False


def eligible_service_ids(conn: sqlite3.Connection, user_id: int) -> list[int]:
    return [
        s["service_id"]
        for s in SERVICES
        if s["category"] != "D" and can_spin(conn, user_id, s["service_id"])
    ]


def spin_wheel(
    conn: sqlite3.Connection,
    user_id: int,
    chosen_name: str,
    *,
    target_service_id: int | None = None,
) -> dict[str, Any]:
    migrate_qsi_schema(conn)
    eligible = eligible_service_ids(conn, user_id)
    if not eligible:
        raise ValueError("No services available to spin right now")
    if target_service_id is not None:
        if target_service_id not in eligible:
            raise ValueError("Cannot spin for this service right now")
        service_id = target_service_id
    else:
        service_id = random.choice(eligible)
    svc = get_service(service_id)
    if not svc:
        raise ValueError("Invalid service")
    now = _now()
    spin_id = conn.execute(
        """
        INSERT INTO qsi_user_spins (
            user_id, service_id, chosen_name, spin_date, mode,
            status, details, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'get', 'pending', '{}', ?, ?)
        """,
        (user_id, service_id, chosen_name.strip(), now, now, now),
    ).lastrowid
    row = conn.execute(
        "SELECT * FROM qsi_user_spins WHERE id = ?",
        (spin_id,),
    ).fetchone()
    result = _spin_row_dict(row)
    result["service"] = svc
    return result


def _category_of(service_id: int) -> str:
    svc = get_service(service_id)
    return svc["category"] if svc else ""


def calculate_karma(spin: dict[str, Any], svc: dict[str, Any]) -> int:
    cat = svc["category"]
    mode = spin.get("mode") or "get"
    if cat == "A":
        return 0
    if cat == "B":
        duration = max(int(spin.get("duration_days") or 0), 1)
        attendance = max(int(spin.get("attendance") or 0), 1)
        punctuality = max(int(spin.get("punctuality_score") or 0), 1)
        passion = max(int(spin.get("passion_score") or 0), 1)
        base = int((duration * attendance * punctuality * passion) / 100)
        if mode == "provide":
            base = int(base * 1.5)
        return max(base, 1)
    if cat == "C":
        base = int(svc.get("base_karma_points") or 100)
        if mode == "provide":
            return base
        return max(base // 10, 10)
    return 0


def award_karma(
    conn: sqlite3.Connection,
    user_private_id: str,
    amount: int,
    description: str,
) -> None:
    if amount <= 0:
        return
    qoin_core.migrate_qoin_economy_tables(conn)
    _seed_karma_action(conn)
    conn.execute(
        """
        INSERT INTO karma_transactions (
            user_private_id, action_code, amount_rupees, description, verified, created_at, settled
        ) VALUES (?, 'qsi_award', ?, ?, 1, ?, 0)
        """,
        (user_private_id, amount, description, _now()),
    )


def start_service(
    conn: sqlite3.Connection,
    spin_id: int,
    user_id: int,
    *,
    mode: str,
    duration_days: int = 0,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    migrate_qsi_schema(conn)
    row = conn.execute(
        "SELECT * FROM qsi_user_spins WHERE id = ? AND user_id = ?",
        (spin_id, user_id),
    ).fetchone()
    if not row:
        raise ValueError("Spin not found")
    spin = dict(row)
    if spin["status"] not in ("pending", "in_progress"):
        raise ValueError("Service cannot be started in current status")
    svc = get_service(int(spin["service_id"]))
    if not svc:
        raise ValueError("Invalid service")
    mode_norm = (mode or "get").strip().lower()
    if mode_norm not in ("get", "provide"):
        raise ValueError("mode must be get or provide")
    cat = svc["category"]
    duration = int(duration_days or 0)
    if cat == "B":
        if duration <= 0:
            raise ValueError("duration_days must be positive for this service")
    elif cat == "C":
        duration = 0
    else:
        duration = 0
    now = _now()
    start = now
    end = None
    if duration > 0:
        end_dt = datetime.now(UTC) + timedelta(days=duration)
        end = end_dt.replace(microsecond=0).isoformat()
    details_json = json.dumps(details or {}, ensure_ascii=False)
    status = "in_progress"
    if cat == "A":
        status = "completed"
    conn.execute(
        """
        UPDATE qsi_user_spins SET
            mode = ?, duration_days = ?, start_date = ?, end_date = ?,
            status = ?, details = ?, updated_at = ?
        WHERE id = ?
        """,
        (mode_norm, duration, start, end, status, details_json, now, spin_id),
    )
    if cat == "A":
        hidden = 1
        details_data = details or {}
        rep = int(details_data.get("repetition_count") or 1)
        mala = int(details_data.get("mala_count") or 1)
        hidden = max(rep * mala, 1)
        conn.execute(
            """
            UPDATE qsi_user_spins SET
                hidden_karma_counter = hidden_karma_counter + ?,
                verification_status = 'approved',
                updated_at = ?
            WHERE id = ?
            """,
            (hidden, now, spin_id),
        )
    updated = get_spin(conn, spin_id)
    return updated or {}


def update_service_progress(
    conn: sqlite3.Connection,
    spin_id: int,
    user_id: int,
    *,
    attendance: int | None = None,
    details_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    migrate_qsi_schema(conn)
    row = conn.execute(
        "SELECT * FROM qsi_user_spins WHERE id = ? AND user_id = ?",
        (spin_id, user_id),
    ).fetchone()
    if not row:
        raise ValueError("Spin not found")
    spin = dict(row)
    if spin["status"] not in ACTIVE_STATUSES:
        raise ValueError("Cannot update this spin")
    now = _now()
    if attendance is not None:
        conn.execute(
            "UPDATE qsi_user_spins SET attendance = ?, updated_at = ? WHERE id = ?",
            (max(int(attendance), 0), now, spin_id),
        )
    if details_patch:
        try:
            current = json.loads(spin.get("details") or "{}")
        except json.JSONDecodeError:
            current = {}
        current.update(details_patch)
        conn.execute(
            "UPDATE qsi_user_spins SET details = ?, updated_at = ? WHERE id = ?",
            (json.dumps(current, ensure_ascii=False), now, spin_id),
        )
    return get_spin(conn, spin_id) or {}


def complete_service(
    conn: sqlite3.Connection,
    spin_id: int,
    user_id: int,
) -> dict[str, Any]:
    migrate_qsi_schema(conn)
    row = conn.execute(
        "SELECT * FROM qsi_user_spins WHERE id = ? AND user_id = ?",
        (spin_id, user_id),
    ).fetchone()
    if not row:
        raise ValueError("Spin not found")
    spin = dict(row)
    if spin["status"] not in ("in_progress", "completed"):
        raise ValueError("Service is not in progress")
    svc = get_service(int(spin["service_id"]))
    if not svc:
        raise ValueError("Invalid service")
    if svc["category"] == "A":
        raise ValueError("Category A services complete instantly on start")
    now = _now()
    conn.execute(
        "UPDATE qsi_user_spins SET status = 'completed', updated_at = ? WHERE id = ?",
        (now, spin_id),
    )
    return get_spin(conn, spin_id) or {}


def verify_service(
    conn: sqlite3.Connection,
    spin_id: int,
    admin_user_id: int,
    *,
    punctuality_score: int,
    passion_score: int,
    approve: bool = True,
    rejection_reason: str | None = None,
) -> dict[str, Any]:
    migrate_qsi_schema(conn)
    row = conn.execute(
        "SELECT * FROM qsi_user_spins WHERE id = ?",
        (spin_id,),
    ).fetchone()
    if not row:
        raise ValueError("Spin not found")
    spin = dict(row)
    svc = get_service(int(spin["service_id"]))
    if not svc:
        raise ValueError("Invalid service")
    if svc["category"] not in ("B", "C"):
        raise ValueError("Verification only applies to category B and C services")
    if spin["status"] not in ("completed", "verified"):
        raise ValueError("Service must be completed before verification")
    now = _now()
    if not approve:
        conn.execute(
            """
            UPDATE qsi_user_spins SET
                verification_status = 'rejected',
                verified_by = ?,
                status = 'completed',
                updated_at = ?
            WHERE id = ?
            """,
            (admin_user_id, now, spin_id),
        )
        details = json.loads(spin.get("details") or "{}")
        details["rejection_reason"] = rejection_reason or "Rejected by reviewer"
        conn.execute(
            "UPDATE qsi_user_spins SET details = ? WHERE id = ?",
            (json.dumps(details, ensure_ascii=False), spin_id),
        )
        return get_spin(conn, spin_id) or {}
    punctuality = max(min(int(punctuality_score), 5), 1)
    passion = max(min(int(passion_score), 5), 1)
    duration = max(int(spin.get("duration_days") or 0), 1)
    attendance = int(spin.get("attendance") or 0)
    min_attendance = int(duration * 0.8)
    if svc["category"] == "B" and attendance < min_attendance:
        raise ValueError(
            f"Insufficient attendance ({attendance}/{min_attendance} required)"
        )
    if punctuality < 3 or passion < 3:
        raise ValueError("Punctuality and passion scores must be at least 3")
    conn.execute(
        """
        UPDATE qsi_user_spins SET
            punctuality_score = ?,
            passion_score = ?,
            verification_status = 'approved',
            verified_by = ?,
            status = 'verified',
            updated_at = ?
        WHERE id = ?
        """,
        (punctuality, passion, admin_user_id, now, spin_id),
    )
    updated_spin = get_spin(conn, spin_id) or {}
    _maybe_award_karma(conn, updated_spin, svc)
    return get_spin(conn, spin_id) or {}


def _maybe_award_karma(
    conn: sqlite3.Connection,
    spin: dict[str, Any],
    svc: dict[str, Any],
) -> None:
    if int(spin.get("karma_points_awarded") or 0):
        return
    if spin.get("verification_status") != "approved":
        return
    end_date = spin.get("end_date")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(str(end_date).replace("Z", "+00:00"))
            if datetime.now(UTC) < end_dt:
                return
        except ValueError:
            pass
    user_row = conn.execute(
        "SELECT private_id FROM users WHERE id = ?",
        (spin["user_id"],),
    ).fetchone()
    if not user_row:
        return
    karma = calculate_karma(spin, svc)
    now = _now()
    conn.execute(
        """
        UPDATE qsi_user_spins SET
            karma_points_awarded = 1,
            karma_points_value = ?,
            status = 'karma_awarded',
            updated_at = ?
        WHERE id = ?
        """,
        (karma, now, spin["id"]),
    )
    if karma > 0 and svc.get("karma_visible"):
        label = svc.get("service_name_en") or "Naam Service"
        award_karma(
            conn,
            str(user_row["private_id"]),
            karma,
            f"QSI {label} ({spin.get('mode') or 'get'})",
        )


def process_pending_karma_awards(conn: sqlite3.Connection) -> int:
    """Award karma for verified spins whose end_date has passed."""
    migrate_qsi_schema(conn)
    rows = conn.execute(
        """
        SELECT * FROM qsi_user_spins
        WHERE verification_status = 'approved'
          AND karma_points_awarded = 0
          AND status = 'verified'
        """
    ).fetchall()
    count = 0
    for row in rows:
        spin = dict(row)
        svc = get_service(int(spin["service_id"]))
        if not svc:
            continue
        before = int(spin.get("karma_points_awarded") or 0)
        _maybe_award_karma(conn, spin, svc)
        after_row = conn.execute(
            "SELECT karma_points_awarded FROM qsi_user_spins WHERE id = ?",
            (spin["id"],),
        ).fetchone()
        if after_row and int(after_row["karma_points_awarded"]) and not before:
            count += 1
    return count


def user_history(
    conn: sqlite3.Connection,
    user_id: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    migrate_qsi_schema(conn)
    rows = conn.execute(
        """
        SELECT * FROM qsi_user_spins
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [_spin_row_dict(r) for r in rows]


def leaderboard(
    conn: sqlite3.Connection,
    *,
    service_id: int | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    migrate_qsi_schema(conn)
    if service_id:
        rows = conn.execute(
            """
            SELECT s.user_id, u.public_id, u.display_name,
                   SUM(s.karma_points_value) AS total_karma,
                   COUNT(*) AS spin_count
            FROM qsi_user_spins s
            JOIN users u ON u.id = s.user_id
            WHERE s.service_id = ? AND s.karma_points_value > 0
            GROUP BY s.user_id
            ORDER BY total_karma DESC
            LIMIT ?
            """,
            (service_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT s.user_id, u.public_id, u.display_name,
                   SUM(s.karma_points_value) AS total_karma,
                   COUNT(*) AS spin_count
            FROM qsi_user_spins s
            JOIN users u ON u.id = s.user_id
            WHERE s.karma_points_value > 0
            GROUP BY s.user_id
            ORDER BY total_karma DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def admin_pending_verifications(
    conn: sqlite3.Connection,
    limit: int = 100,
) -> list[dict[str, Any]]:
    migrate_qsi_schema(conn)
    rows = conn.execute(
        """
        SELECT s.*, u.public_id, u.display_name, u.private_id
        FROM qsi_user_spins s
        JOIN users u ON u.id = s.user_id
        WHERE s.status = 'completed'
          AND s.verification_status = 'pending'
        ORDER BY s.updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        item = _spin_row_dict(r)
        item["public_id"] = r["public_id"]
        item["display_name"] = r["display_name"]
        item["private_id"] = r["private_id"]
        out.append(item)
    return out


def admin_all_spins(
    conn: sqlite3.Connection,
    limit: int = 200,
) -> list[dict[str, Any]]:
    migrate_qsi_schema(conn)
    rows = conn.execute(
        """
        SELECT s.*, u.public_id, u.display_name
        FROM qsi_user_spins s
        JOIN users u ON u.id = s.user_id
        ORDER BY s.created_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        item = _spin_row_dict(r)
        item["public_id"] = r["public_id"]
        item["display_name"] = r["display_name"]
        out.append(item)
    return out
