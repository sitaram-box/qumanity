"""HTTP routes for Quadratic Voting (QV) referendums."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable

from flask import Blueprint, g, jsonify, render_template, request

import qv_core

qv_bp = Blueprint("qv_api", __name__, url_prefix="/api/qv")

# Simple in-memory rate limits: user_id -> {endpoint: [timestamps]}
_rate_buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))


def _rate_limit(user_id: str, endpoint: str, max_calls: int, window_sec: int) -> bool:
    """Return True if request is allowed."""
    now = datetime.now(timezone.utc).timestamp()
    bucket = _rate_buckets[user_id][endpoint]
    _rate_buckets[user_id][endpoint] = [t for t in bucket if now - t < window_sec]
    if len(_rate_buckets[user_id][endpoint]) >= max_calls:
        return False
    _rate_buckets[user_id][endpoint].append(now)
    return True


def register_qv_routes(
    app,
    get_db: Callable,
    login_required_decorator,
    is_admin_user_fn: Callable | None = None,
    send_system_message_fn: Callable | None = None,
) -> None:
    """Register QV API routes and HTML pages."""

    def _notify(conn, recipient: str, subject: str, body: str) -> None:
        if send_system_message_fn:
            send_system_message_fn(conn, recipient, subject, body)

    def _ctx() -> dict:
        return {
            "is_admin_fn": is_admin_user_fn,
            "notify_fn": _notify,
        }

    @qv_bp.route("/referendums", methods=["GET"])
    def list_referendums_api():
        conn = get_db()
        qv_core.migrate_qv_schema(conn)
        level = request.args.get("level")
        status = request.args.get("status")
        location_id = request.args.get("location_id")
        rows = qv_core.list_referendums(
            conn, level=level, status=status, location_id=location_id
        )
        return jsonify({"referendums": rows})

    @qv_bp.route("/referendums/<int:ref_id>", methods=["GET"])
    def get_referendum_api(ref_id: int):
        conn = get_db()
        ref = qv_core.get_referendum(conn, ref_id)
        if not ref:
            return jsonify({"error": "Referendum not found"}), 404
        return jsonify(ref)

    @qv_bp.route("/referendums", methods=["POST"])
    @login_required_decorator
    def create_referendum_api():
        conn = get_db()
        user = g.current_user
        if not qv_core.is_human_user(user):
            return jsonify({"error": "Demo accounts cannot propose referendums"}), 403
        data = request.get_json(silent=True) or {}
        pid = str(user["private_id"])
        if not _rate_limit(pid, "create", 5, 3600):
            return jsonify({"error": "Too many proposals. Try again later."}), 429
        title = (data.get("title") or "").strip()
        description = (data.get("description") or "").strip()
        level = (data.get("level") or "village").strip()
        location_id = (data.get("location_id") or "").strip()
        if not location_id:
            location_id = qv_core.resolve_location_for_level(conn, user, level) or ""
        try:
            rid = qv_core.create_referendum(
                conn, title, description, pid, level, location_id
            )
            conn.commit()
            return jsonify({"success": True, "referendum_id": rid}), 201
        except PermissionError as exc:
            return jsonify({"error": str(exc)}), 403
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @qv_bp.route("/referendums/<int:ref_id>/approve", methods=["PUT"])
    @login_required_decorator
    def approve_referendum_api(ref_id: int):
        conn = get_db()
        pid = str(g.current_user["private_id"])
        ok = qv_core.approve_referendum(conn, ref_id, pid, **_ctx())
        if not ok:
            return jsonify({"error": "Cannot approve this referendum"}), 403
        conn.commit()
        return jsonify({"success": True})

    @qv_bp.route("/referendums/<int:ref_id>/reject", methods=["PUT"])
    @login_required_decorator
    def reject_referendum_api(ref_id: int):
        conn = get_db()
        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "").strip()
        pid = str(g.current_user["private_id"])
        ok = qv_core.reject_referendum(conn, ref_id, pid, reason, **_ctx())
        if not ok:
            return jsonify({"error": "Cannot reject this referendum"}), 403
        conn.commit()
        return jsonify({"success": True})

    @qv_bp.route("/referendums/<int:ref_id>/vote", methods=["POST"])
    @login_required_decorator
    def cast_vote_api(ref_id: int):
        conn = get_db()
        user = g.current_user
        if not qv_core.is_human_user(user):
            return jsonify({"error": "Demo accounts cannot vote"}), 403
        pid = str(user["private_id"])
        if not _rate_limit(pid, "vote", 10, 60):
            return jsonify({"error": "Too many vote attempts. Slow down."}), 429
        data = request.get_json(silent=True) or {}
        try:
            votes = int(data.get("votes", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid vote count"}), 400
        result = qv_core.cast_vote(conn, ref_id, pid, votes)
        if result.get("success"):
            conn.commit()
            return jsonify(result)
        conn.rollback()
        return jsonify({"error": result.get("message", "Vote failed")}), 400

    @qv_bp.route("/referendums/<int:ref_id>/results", methods=["GET"])
    def referendum_results_api(ref_id: int):
        conn = get_db()
        res = qv_core.get_referendum_results(conn, ref_id)
        if not res:
            return jsonify({"error": "Results not available"}), 404
        return jsonify(res)

    @qv_bp.route("/credits/balance", methods=["GET"])
    @login_required_decorator
    def credit_balance_api():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        bal = qv_core.get_or_create_credit_balance(conn, pid)
        return jsonify(
            {
                "current_credits": int(bal.get("current_credits") or 0),
                "lifetime_earned": int(bal.get("lifetime_earned") or 0),
                "lifetime_spent": int(bal.get("lifetime_spent") or 0),
            }
        )

    @qv_bp.route("/credits/history", methods=["GET"])
    @login_required_decorator
    def credit_history_api():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        limit = min(int(request.args.get("limit", 50)), 200)
        rows = qv_core.get_credit_history(conn, pid, limit=limit)
        return jsonify({"transactions": rows})

    @qv_bp.route("/credits/convert", methods=["POST"])
    @login_required_decorator
    def credit_convert_api():
        conn = get_db()
        user = g.current_user
        if not qv_core.is_human_user(user):
            return jsonify({"error": "Not available for demo accounts"}), 403
        pid = str(user["private_id"])
        ym = datetime.now(timezone.utc).strftime("%Y-%m")
        summary = qv_core.auto_convert_karma_to_credits(conn, pid, ym)
        conn.commit()
        return jsonify({"success": True, "summary": summary})

    @app.route("/qv")
    @login_required_decorator
    def qv_dashboard_page():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        refs = qv_core.list_referendums(conn, status="active", limit=30)
        credits = qv_core.get_or_create_credit_balance(conn, pid)
        return render_template(
            "qv/qv_dashboard.html",
            referendums=refs,
            credits=credits,
            is_human=qv_core.is_human_user(user),
            levels=qv_core.LEVELS,
        )

    @app.route("/qv/referendum/<int:ref_id>")
    @login_required_decorator
    def qv_detail_page(ref_id: int):
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        ref = qv_core.get_referendum(conn, ref_id)
        if not ref:
            return render_template("error.html", error="Referendum not found"), 404
        can_review = qv_core.can_review_referendum(
            conn, ref_id, pid, is_admin_fn=is_admin_user_fn
        )
        credits = qv_core.get_credit_balance(conn, pid)
        results = qv_core.get_referendum_results(conn, ref_id)
        return render_template(
            "qv/qv_detail.html",
            referendum=ref,
            can_review=can_review,
            credits=credits,
            results=results,
            is_human=qv_core.is_human_user(user),
            user_private_id=pid,
        )

    @app.route("/qv/propose")
    @login_required_decorator
    def qv_propose_page():
        user = g.current_user
        if not qv_core.is_human_user(user):
            return render_template(
                "error.html", error="Demo accounts cannot propose referendums"
            ), 403
        return render_template("qv/qv_propose.html", levels=qv_core.LEVELS)

    @app.route("/qv/credits")
    @login_required_decorator
    def qv_credits_page():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        bal = qv_core.get_or_create_credit_balance(conn, pid)
        history = qv_core.get_credit_history(conn, pid, limit=100)
        return render_template(
            "qv/qv_credits.html", balance=bal, transactions=history
        )

    @app.route("/qv/results")
    @login_required_decorator
    def qv_results_page():
        conn = get_db()
        rows = qv_core.list_referendums(
            conn, status="resolved", limit=50
        ) + qv_core.list_referendums(conn, status="escalated", limit=50)
        return render_template("qv/qv_results.html", referendums=rows)

    @app.route("/admin/qv")
    @login_required_decorator
    def qv_admin_page():
        if is_admin_user_fn and not is_admin_user_fn(g.current_user):
            from flask import flash, redirect, url_for

            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        conn = get_db()
        rows = qv_core.list_referendums(conn, limit=200)
        return render_template("qv/qv_admin.html", referendums=rows)

    app.register_blueprint(qv_bp)
