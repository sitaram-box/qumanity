"""
HTTP routes for Guna-Karma Varna system.
"""

from __future__ import annotations

from typing import Callable

from flask import Blueprint, g, jsonify, request

import varna_core

varna_bp = Blueprint("varna", __name__, url_prefix="/api/varna")


def register_varna_routes(
    app,
    get_db: Callable,
    login_required_decorator,
    admin_required_decorator,
) -> None:
    @varna_bp.route("/profile", methods=["GET"])
    @login_required_decorator
    def get_varna_profile():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        varna_core.migrate_varna_schema(conn)
        return jsonify({"success": True, **varna_core.profile_for_user(conn, pid)})

    @varna_bp.route("/explain", methods=["GET"])
    @login_required_decorator
    def explain_classification():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        return jsonify(
            varna_core.explain_classification(conn, pid)
        )

    @varna_bp.route("/eligible-roles", methods=["GET"])
    @login_required_decorator
    def get_eligible_roles():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        roles = varna_core.eligible_roles_for_user(conn, pid)
        primary = varna_core.get_primary_category(conn, pid)
        return jsonify(
            {
                "primary_category": primary,
                "category_type": varna_core.get_category_type(conn, pid),
                "eligible_roles": roles,
            }
        )

    @varna_bp.route("/appeal", methods=["POST"])
    @login_required_decorator
    def submit_appeal():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "").strip()
        if not reason:
            return jsonify({"error": "reason is required"}), 400
        appeal_id = varna_core.submit_appeal(
            conn,
            pid,
            reason,
            (data.get("evidence") or "").strip() or None,
        )
        conn.commit()
        return jsonify(
            {
                "success": True,
                "appeal_id": appeal_id,
                "message": "Appeal submitted. Council will review.",
            }
        )

    @varna_bp.route("/admin/stats", methods=["GET"])
    @admin_required_decorator
    def admin_varna_stats():
        conn = get_db()
        return jsonify(varna_core.admin_stats(conn))

    @varna_bp.route("/admin/appeals", methods=["GET"])
    @admin_required_decorator
    def admin_pending_appeals():
        conn = get_db()
        varna_core.migrate_varna_schema(conn)
        rows = conn.execute(
            """
            SELECT ca.*, u.first_name, u.last_name, u.public_id
            FROM category_appeals ca
            JOIN users u ON u.private_id = ca.user_private_id
            WHERE ca.status = 'pending'
            ORDER BY ca.created_at DESC
            """
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @varna_bp.route("/admin/appeal/<int:appeal_id>", methods=["POST"])
    @admin_required_decorator
    def admin_resolve_appeal(appeal_id: int):
        conn = get_db()
        data = request.get_json(silent=True) or {}
        action = (data.get("action") or "").strip().lower()
        if action not in {"approve", "reject"}:
            return jsonify({"error": "action must be approve or reject"}), 400
        varna_core.resolve_appeal(
            conn,
            appeal_id,
            action=action,
            reviewer_private_id=str(g.current_user["private_id"]),
            admin_notes=(data.get("notes") or "").strip(),
        )
        conn.commit()
        return jsonify({"success": True})

    @varna_bp.route("/admin/recalculate", methods=["POST"])
    @admin_required_decorator
    def admin_recalculate():
        conn = get_db()
        result = varna_core.recalculate_all_categories(
            conn, change_reason="admin_manual"
        )
        return jsonify({"success": True, **result})

    app.register_blueprint(varna_bp)

    @app.post("/api/admin/recalculate-categories")
    @admin_required_decorator
    def legacy_admin_recalc_categories():
        conn = get_db()
        result = varna_core.recalculate_all_categories(
            conn, change_reason="admin_manual"
        )
        return jsonify({"success": True, **result})

