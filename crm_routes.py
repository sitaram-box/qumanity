"""
Flask routes for Qumanity ↔ CRM integration.

Register in app.py (near the bottom, before if __name__):

    from crm_routes import register_crm_routes
    register_crm_routes(app, get_db, login_required, g)
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from typing import Any, Callable

from flask import Blueprint, g, jsonify, request, session

import crm_integration
import jwt_auth

crm_bp = Blueprint("crm", __name__, url_prefix="/api")


def register_crm_routes(
    app,
    get_db: Callable,
    login_required_decorator,
    flask_g,
) -> None:
    """Attach CRM blueprint to the Flask app."""

    @crm_bp.route("/auth/crm-token", methods=["GET"])
    @login_required_decorator
    def api_crm_token():
        """Return JWT for CRM dashboard (store in localStorage as qumanity_token)."""
        user = flask_g.current_user
        token = jwt_auth.generate_jwt(dict(user))
        return jsonify({"token": token, "role": jwt_auth.crm_role_for_user(dict(user))})

    @crm_bp.route("/webhooks/ticket-closed", methods=["POST"])
    def webhook_ticket_closed():
        secret = request.headers.get("X-Webhook-Secret")
        if secret != crm_integration.QUMANITY_WEBHOOK_SECRET:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json(silent=True) or {}
        ticket_id = data.get("ticket_id")
        if not ticket_id:
            return jsonify({"error": "ticket_id required"}), 400

        conn = get_db()
        crm_integration.record_ticket_closed(
            conn,
            ticket_id=ticket_id,
            resolution_notes=data.get("resolution_notes"),
            satisfaction_rating=data.get("satisfaction_rating"),
        )
        return jsonify({"success": True})

    @crm_bp.route("/orders/create", methods=["POST"])
    @login_required_decorator
    def create_order():
        """Create marketplace order locally and sync to CRM."""
        data = request.get_json(silent=True) or {}
        conn = get_db()
        user = dict(flask_g.current_user)

        order_id = f"ORD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{random.randint(1000, 9999)}"
        payload = {
            "order_id": order_id,
            "buyer_private_id": user.get("private_id"),
            "buyer_name": data.get("buyer_name") or f'{user.get("first_name")} {user.get("last_name")}',
            "buyer_address": data.get("buyer_address", ""),
            "buyer_tehsil_id": data.get("buyer_tehsil_id") or user.get("current_location_id"),
            "items": data.get("items", []),
            "subtotal": int(data.get("subtotal", 0)),
            "delivery_charge": int(data.get("delivery_charge", 0)),
            "total_amount": int(data.get("total_amount", 0)),
            "order_status": "pending",
            "payment_status": data.get("payment_status", "pending"),
            "payment_method": data.get("payment_method", "qoins"),
        }

        crm_integration.create_local_order(
            conn,
            order_id=order_id,
            buyer_private_id=str(user.get("private_id")),
            payload=payload,
        )
        synced = crm_integration.sync_order_to_crm(payload, user)

        if synced:
            conn.execute(
                "UPDATE crm_orders SET synced_to_crm = 1 WHERE order_id = ?",
                (order_id,),
            )
            conn.commit()

        return jsonify({"order_id": order_id, "success": True, "synced_to_crm": synced})

    @crm_bp.route("/vendors/register", methods=["POST"])
    @login_required_decorator
    def register_vendor_crm():
        data = request.get_json(silent=True) or {}
        user = dict(flask_g.current_user)
        vendor = {
            "vendor_id": user.get("private_id"),
            "business_name": data.get("business_name", ""),
            "business_type": data.get("business_type", "other"),
            "gst_number": data.get("gst_number"),
            "address": data.get("address", ""),
            "tehsil_id": data.get("tehsil_id") or user.get("current_location_id"),
        }
        ok = crm_integration.sync_vendor_to_crm(vendor, user)
        return jsonify({"success": ok})

    @crm_bp.route("/ratings/submit", methods=["POST"])
    @login_required_decorator
    def submit_rating_crm():
        data = request.get_json(silent=True) or {}
        user = dict(flask_g.current_user)
        rating = {
            "order_id": data.get("order_id"),
            "rater_private_id": user.get("private_id"),
            "rated_private_id": data.get("rated_private_id"),
            "rating_type": data.get("rating_type", "product_quality"),
            "rating_value": int(data.get("rating_value", 5)),
            "comment": data.get("comment"),
        }
        ok = crm_integration.sync_rating_to_crm(rating, user)
        return jsonify({"success": ok})

    @crm_bp.route("/crm/ticket-updates", methods=["GET"])
    @login_required_decorator
    def list_ticket_updates():
        """Citizen dashboard: ticket closure notifications from CRM."""
        conn = get_db()
        crm_integration.ensure_crm_tables(conn)
        rows = conn.execute(
            """
            SELECT ticket_id, resolution_notes, satisfaction_rating, updated_at
            FROM crm_ticket_updates
            ORDER BY updated_at DESC
            LIMIT 50
            """
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    app.register_blueprint(crm_bp)
