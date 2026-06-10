"""
JWT helpers for Qumanity ↔ CRM integration.

Tokens are issued by Flask on login and validated by NocoBase CRM plugins.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import config

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None  # type: ignore[assignment]

JWT_SECRET = os.environ.get("JWT_SECRET") or config.SECRET_KEY
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "24"))


def _require_jwt() -> None:
    if pyjwt is None:
        raise RuntimeError("PyJWT is required: pip install PyJWT")


def crm_role_for_user(user_row: dict[str, Any]) -> str:
    """Map Qumanity account_type / admin flag to CRM role."""
    if int(user_row.get("is_admin") or 0):
        return "admin"
    account = (user_row.get("account_type") or "").upper()
    if account in {"MANAGER", "H_U_ADMIN"}:
        return "manager"
    if account in {"AGENT", "VOLUNTEER", "DELIVERY_AGENT"}:
        return "agent"
    if account in {"LEADER", "NAYAK", "NAYIKA"}:
        return "leader"
    return "citizen"


def location_hierarchy_from_user(user_row: dict[str, Any]) -> dict[str, str | None]:
    """Best-effort tehsil/district/state from user row (extend with DB lookup if needed)."""
    loc = user_row.get("current_location_id") or user_row.get("birth_location_id")
    return {
        "tehsil_id": user_row.get("tehsil_id") or loc,
        "district_id": user_row.get("district_id"),
        "state_id": user_row.get("state_id") or user_row.get("current_country_id"),
    }


def generate_jwt(user_row: dict[str, Any]) -> str:
    """Build a signed JWT for CRM API calls."""
    _require_jwt()
    loc = location_hierarchy_from_user(user_row)
    name = f'{user_row.get("first_name", "")} {user_row.get("last_name", "")}'.strip()
    payload = {
        "private_id": user_row.get("private_id"),
        "name": name or user_row.get("private_id"),
        "role": crm_role_for_user(user_row),
        "tehsil_id": loc.get("tehsil_id"),
        "district_id": loc.get("district_id"),
        "state_id": loc.get("state_id"),
        "account_type": user_row.get("account_type"),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> dict[str, Any]:
    _require_jwt()
    return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
