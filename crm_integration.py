"""
CRM integration: HTTP client, local tables, sync helpers.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

import config
import jwt_auth

logger = logging.getLogger("qumanity.crm")

CRM_API_URL = os.environ.get("CRM_API_URL", "http://localhost:3000/api").rstrip("/")
QUMANITY_WEBHOOK_SECRET = os.environ.get("QUMANITY_WEBHOOK_SECRET", "")

CRM_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS crm_ticket_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    resolution_notes TEXT,
    satisfaction_rating INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crm_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL,
    buyer_private_id TEXT,
    payload_json TEXT NOT NULL,
    synced_to_crm INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def ensure_crm_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(CRM_TABLES_SQL)
    conn.commit()


def _crm_headers(user_row: dict[str, Any] | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if user_row:
        headers["Authorization"] = f"Bearer {jwt_auth.generate_jwt(user_row)}"
    elif QUMANITY_WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = QUMANITY_WEBHOOK_SECRET
    return headers


def sync_order_to_crm(order: dict[str, Any], user_row: dict[str, Any] | None = None) -> bool:
    """POST order payload to CRM. Returns True on success."""
    try:
        import requests
    except ImportError:
        logger.warning("requests not installed; order not synced to CRM")
        return False

    url = f"{CRM_API_URL}/orders"
    try:
        resp = requests.post(url, json=order, headers=_crm_headers(user_row), timeout=15)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("CRM order sync failed: %s", exc)
        return False


def sync_vendor_to_crm(vendor: dict[str, Any], user_row: dict[str, Any] | None = None) -> bool:
    try:
        import requests
    except ImportError:
        return False

    url = f"{CRM_API_URL}/vendors/sync"
    try:
        resp = requests.post(url, json=vendor, headers=_crm_headers(user_row), timeout=15)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("CRM vendor sync failed: %s", exc)
        return False


def sync_rating_to_crm(rating: dict[str, Any], user_row: dict[str, Any] | None = None) -> bool:
    try:
        import requests
    except ImportError:
        return False

    url = f"{CRM_API_URL}/ratings"
    try:
        resp = requests.post(url, json=rating, headers=_crm_headers(user_row), timeout=15)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("CRM rating sync failed: %s", exc)
        return False


def record_ticket_closed(
    conn: sqlite3.Connection,
    *,
    ticket_id: str,
    resolution_notes: str | None,
    satisfaction_rating: int | None,
) -> None:
    ensure_crm_tables(conn)
    conn.execute(
        """
        INSERT INTO crm_ticket_updates (ticket_id, resolution_notes, satisfaction_rating, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (
            ticket_id,
            resolution_notes,
            satisfaction_rating,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def create_local_order(
    conn: sqlite3.Connection,
    *,
    order_id: str,
    buyer_private_id: str,
    payload: dict[str, Any],
) -> None:
    ensure_crm_tables(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO crm_orders (order_id, buyer_private_id, payload_json, synced_to_crm)
        VALUES (?, ?, ?, ?)
        """,
        (order_id, buyer_private_id, json.dumps(payload), 0),
    )
    conn.commit()
