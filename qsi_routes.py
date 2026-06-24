"""
HTTP routes for Quantum Spiritual Interface (QSI).
"""

from __future__ import annotations

from typing import Callable

from flask import Blueprint, g, jsonify, render_template, request

import qsi_core

qsi_bp = Blueprint("qsi_api", __name__, url_prefix="/api/qsi")


def register_qsi_routes(
    app,
    get_db: Callable,
    login_required_decorator,
    admin_required_decorator,
    admin_page_required_decorator,
    is_admin_user_fn: Callable,
) -> None:
    @qsi_bp.route("/services", methods=["GET"])
    def list_services():
        conn = get_db()
        qsi_core.migrate_qsi_schema(conn)
        services = qsi_core.list_services(conn)
        return jsonify({"success": True, "services": services})

    @qsi_bp.route("/user-name", methods=["GET"])
    @login_required_decorator
    def get_user_name():
        conn = get_db()
        user_id = int(g.current_user["id"])
        pref = qsi_core.get_user_name(conn, user_id)
        return jsonify({"success": True, "preference": pref})

    @qsi_bp.route("/user-name", methods=["POST"])
    @login_required_decorator
    def set_user_name():
        conn = get_db()
        user_id = int(g.current_user["id"])
        data = request.get_json(silent=True) or {}
        try:
            pref = qsi_core.set_user_name(
                conn,
                user_id,
                str(data.get("chosen_name") or ""),
                str(data.get("religion") or "") or None,
            )
            conn.commit()
            return jsonify({"success": True, "preference": pref})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    @qsi_bp.route("/spin", methods=["POST"])
    @login_required_decorator
    def spin_wheel():
        conn = get_db()
        user_id = int(g.current_user["id"])
        data = request.get_json(silent=True) or {}
        pref = qsi_core.get_user_name(conn, user_id)
        chosen = (data.get("chosen_name") or "").strip()
        if not chosen and pref:
            chosen = pref.get("chosen_name") or ""
        if not chosen:
            return jsonify(
                {
                    "success": False,
                    "error": "Set your chosen Name before spinning",
                    "needs_name": True,
                }
            ), 400
        target = data.get("service_id")
        try:
            result = qsi_core.spin_wheel(
                conn,
                user_id,
                chosen,
                target_service_id=int(target) if target else None,
            )
            conn.commit()
            return jsonify({"success": True, "spin": result})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    @qsi_bp.route("/spin/service", methods=["POST"])
    @login_required_decorator
    def spin_until_service():
        conn = get_db()
        user_id = int(g.current_user["id"])
        data = request.get_json(silent=True) or {}
        service_id = int(data.get("service_id") or 0)
        if service_id < 1 or service_id > 12:
            return jsonify({"success": False, "error": "Invalid service_id"}), 400
        pref = qsi_core.get_user_name(conn, user_id)
        chosen = (data.get("chosen_name") or "").strip()
        if not chosen and pref:
            chosen = pref.get("chosen_name") or ""
        if not chosen:
            return jsonify({"success": False, "error": "Set your chosen Name first"}), 400
        try:
            result = qsi_core.spin_wheel(
                conn,
                user_id,
                chosen,
                target_service_id=service_id,
            )
            conn.commit()
            return jsonify({"success": True, "spin": result})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    @qsi_bp.route("/service/start", methods=["POST"])
    @login_required_decorator
    def start_service():
        conn = get_db()
        user_id = int(g.current_user["id"])
        data = request.get_json(silent=True) or {}
        spin_id = int(data.get("spin_id") or 0)
        if not spin_id:
            return jsonify({"success": False, "error": "spin_id required"}), 400
        try:
            result = qsi_core.start_service(
                conn,
                spin_id,
                user_id,
                mode=str(data.get("mode") or "get"),
                duration_days=int(data.get("duration_days") or 0),
                details=data.get("details") if isinstance(data.get("details"), dict) else {},
            )
            conn.commit()
            return jsonify({"success": True, "spin": result})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    @qsi_bp.route("/service/update", methods=["POST"])
    @login_required_decorator
    def update_service():
        conn = get_db()
        user_id = int(g.current_user["id"])
        data = request.get_json(silent=True) or {}
        spin_id = int(data.get("spin_id") or 0)
        if not spin_id:
            return jsonify({"success": False, "error": "spin_id required"}), 400
        attendance = data.get("attendance")
        details_patch = data.get("details") if isinstance(data.get("details"), dict) else None
        try:
            result = qsi_core.update_service_progress(
                conn,
                spin_id,
                user_id,
                attendance=int(attendance) if attendance is not None else None,
                details_patch=details_patch,
            )
            conn.commit()
            return jsonify({"success": True, "spin": result})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    @qsi_bp.route("/service/complete", methods=["POST"])
    @login_required_decorator
    def complete_service():
        conn = get_db()
        user_id = int(g.current_user["id"])
        data = request.get_json(silent=True) or {}
        spin_id = int(data.get("spin_id") or 0)
        if not spin_id:
            return jsonify({"success": False, "error": "spin_id required"}), 400
        try:
            result = qsi_core.complete_service(conn, spin_id, user_id)
            conn.commit()
            return jsonify({"success": True, "spin": result})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    @qsi_bp.route("/service/verify", methods=["POST"])
    @admin_required_decorator
    def verify_service():
        conn = get_db()
        admin_id = int(g.current_user["id"])
        data = request.get_json(silent=True) or {}
        spin_id = int(data.get("spin_id") or 0)
        if not spin_id:
            return jsonify({"success": False, "error": "spin_id required"}), 400
        approve = bool(data.get("approve", True))
        try:
            result = qsi_core.verify_service(
                conn,
                spin_id,
                admin_id,
                punctuality_score=int(data.get("punctuality_score") or 3),
                passion_score=int(data.get("passion_score") or 3),
                approve=approve,
                rejection_reason=str(data.get("reason") or ""),
            )
            conn.commit()
            return jsonify({"success": True, "spin": result})
        except ValueError as exc:
            return jsonify({"success": False, "error": str(exc)}), 400

    @qsi_bp.route("/history", methods=["GET"])
    @login_required_decorator
    def history():
        conn = get_db()
        user_id = int(g.current_user["id"])
        limit = min(int(request.args.get("limit") or 50), 200)
        items = qsi_core.user_history(conn, user_id, limit=limit)
        return jsonify({"success": True, "history": items})

    @qsi_bp.route("/history/<int:spin_id>", methods=["GET"])
    @login_required_decorator
    def history_detail(spin_id: int):
        conn = get_db()
        user_id = int(g.current_user["id"])
        spin = qsi_core.get_spin(conn, spin_id)
        if not spin or int(spin["user_id"]) != user_id:
            return jsonify({"success": False, "error": "Not found"}), 404
        return jsonify({"success": True, "spin": spin})

    @qsi_bp.route("/leaderboard", methods=["GET"])
    def leaderboard():
        conn = get_db()
        service_id = request.args.get("service_id")
        sid = int(service_id) if service_id else None
        items = qsi_core.leaderboard(conn, service_id=sid)
        return jsonify({"success": True, "leaderboard": items})

    @qsi_bp.route("/leaderboard/overall", methods=["GET"])
    def leaderboard_overall():
        conn = get_db()
        items = qsi_core.leaderboard(conn)
        return jsonify({"success": True, "leaderboard": items})

    @qsi_bp.route("/admin/pending", methods=["GET"])
    @admin_required_decorator
    def admin_pending():
        conn = get_db()
        items = qsi_core.admin_pending_verifications(conn)
        return jsonify({"success": True, "pending": items})

    @qsi_bp.route("/admin/spins", methods=["GET"])
    @admin_required_decorator
    def admin_spins():
        conn = get_db()
        items = qsi_core.admin_all_spins(conn)
        return jsonify({"success": True, "spins": items})

    @app.route("/qsi/history")
    @login_required_decorator
    def qsi_history_page():
        conn = get_db()
        user_id = int(g.current_user["id"])
        qsi_core.migrate_qsi_schema(conn)
        history = qsi_core.user_history(conn, user_id)
        pref = qsi_core.get_user_name(conn, user_id)
        return render_template(
            "qsi/history.html",
            history=history,
            name_preference=pref,
            is_admin=is_admin_user_fn(g.current_user),
        )

    @app.route("/admin/qsi")
    @admin_page_required_decorator
    def qsi_admin_page():
        conn = get_db()
        qsi_core.migrate_qsi_schema(conn)
        pending = qsi_core.admin_pending_verifications(conn)
        spins = qsi_core.admin_all_spins(conn, limit=100)
        return render_template(
            "admin/qsi_admin.html",
            pending=pending,
            spins=spins,
        )

    app.register_blueprint(qsi_bp)
