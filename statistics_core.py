"""Geography statistics — child-location breakdowns for statistics pages."""

from __future__ import annotations

import sqlite3
from typing import Any, Callable

LIFE_STAGE_ORDER: tuple[str, ...] = ("Balak", "Yuvak", "Vridh", "Sanyas")
ZODIAC_SIGNS_ORDER: tuple[str, ...] = (
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
)

# Parent scope → child scope for breakdown tables
CHILD_SCOPE: dict[str, str] = {
    "earth": "continent",
    "continent": "country",
    "country": "zone",
    "zone": "state",
    "state": "district",
    "district": "tehsil",
    "tehsil": "village",
    "india": "state",
}

CHILD_LABEL: dict[str, str] = {
    "earth": "Continents",
    "continent": "Countries",
    "country": "Zones",
    "zone": "States",
    "state": "Districts",
    "district": "Tehsils",
    "tehsil": "Villages",
    "india": "States",
}


def zodiac_summary(sign_rows: list[dict[str, Any]], limit: int = 12) -> str:
    parts: list[str] = []
    for row in sign_rows:
        ct = int(row.get("count") or 0)
        if ct <= 0:
            continue
        lab = str(row.get("label") or "")
        short = SUN_SIGN_TWO_LETTER.get(lab, lab[:2])
        parts.append(f"{short}: {ct}")
    if not parts:
        return "—"
    if len(parts) > limit:
        return ", ".join(parts[:limit]) + "…"
    return ", ".join(parts)


# Import after module constants to avoid circular import at load — set by app bootstrap
SUN_SIGN_TWO_LETTER: dict[str, str] = {
    "Aries": "Ar",
    "Taurus": "Ta",
    "Gemini": "Ge",
    "Cancer": "Ca",
    "Leo": "Le",
    "Virgo": "Vi",
    "Libra": "Li",
    "Scorpio": "Sc",
    "Sagittarius": "Sg",
    "Capricorn": "Cp",
    "Aquarius": "Aq",
    "Pisces": "Pi",
}


def _gender_counts_from_rows(
    gender_rows: list[dict[str, Any]], total: int
) -> dict[str, int]:
    raw = {str(r["label"]): int(r["count"]) for r in gender_rows}
    male = raw.get("Male", 0)
    female = raw.get("Female", 0)
    other = max(0, total - male - female)
    return {"Male": male, "Female": female, "Other": other}


def child_locations_for_parent(
    conn: sqlite3.Connection,
    parent_scope: str,
    parent_id: str,
    *,
    global_children_fn: Callable[[sqlite3.Connection, str], list[dict[str, str]]],
    india_children_fn: Callable[[sqlite3.Connection, str], list[dict[str, str]]],
) -> list[dict[str, str]]:
    scope = (parent_scope or "").strip().lower()
    pid = (parent_id or "").strip()
    pup = pid.upper()
    if scope == "earth":
        rows = global_children_fn(conn, pid or "0")
        if not rows and pup != "EARTH":
            rows = global_children_fn(conn, "EARTH")
        return rows
    if scope == "continent":
        return global_children_fn(conn, pid)
    if scope == "country":
        return global_children_fn(conn, pid)
    if scope == "india":
        return india_children_fn(conn, "IND")
    return india_children_fn(conn, pid)


def child_location_stats_rows(
    conn: sqlite3.Connection,
    parent_scope: str,
    parent_id: str,
    *,
    location_statistics_bundle_fn: Callable[..., dict[str, Any]],
    global_children_fn: Callable[[sqlite3.Connection, str], list[dict[str, str]]],
    india_children_fn: Callable[[sqlite3.Connection, str], list[dict[str, str]]],
    stats_url_fn: Callable[[str, str], str],
    max_children: int = 2000,
) -> dict[str, Any]:
    """Aggregate stats for parent + per-child bundles."""
    scope = (parent_scope or "").strip().lower()
    pid = (parent_id or "").strip()
    bundle_geo_id: str | None = None if scope == "india" else pid
    parent_bundle = location_statistics_bundle_fn(conn, scope, bundle_geo_id)
    child_scope = CHILD_SCOPE.get(scope)
    children_meta = (
        child_locations_for_parent(
            conn,
            scope,
            pid,
            global_children_fn=global_children_fn,
            india_children_fn=india_children_fn,
        )
        if child_scope
        else []
    )
    if len(children_meta) > max_children:
        children_meta = children_meta[:max_children]

    child_rows: list[dict[str, Any]] = []
    for ch in children_meta:
        cid = str(ch["id"])
        cname = str(ch.get("name") or cid)
        bundle = location_statistics_bundle_fn(conn, child_scope, cid)
        total = int(bundle.get("total_users") or 0)
        gcounts = _gender_counts_from_rows(bundle.get("gender") or [], total)
        child_rows.append(
            {
                "id": cid,
                "name": cname,
                "scope": child_scope,
                "stats_url": stats_url_fn(child_scope, cid),
                "total_users": total,
                "male": gcounts["Male"],
                "female": gcounts["Female"],
                "other": gcounts["Other"],
                "gender": bundle.get("gender") or [],
                "age_group": bundle.get("age_group") or [],
                "sun_sign": bundle.get("sun_sign") or [],
                "zodiac_summary": zodiac_summary(bundle.get("sun_sign") or []),
            }
        )

    child_rows.sort(key=lambda r: (-int(r["total_users"]), str(r["name"]).casefold()))

    return {
        "parent_scope": scope,
        "parent_id": pid,
        "child_scope": child_scope,
        "child_label": CHILD_LABEL.get(scope, "Locations"),
        "parent_stats": parent_bundle,
        "children": child_rows,
        "children_truncated": len(children_meta) >= max_children,
    }
