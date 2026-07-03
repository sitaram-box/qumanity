"""
Public platform pages & APIs from the Qumanity refactor prompt.
Registers demo dashboard, metrics, security, karma ledger, pilot, feedback, OpenAPI.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

import feedback_core
import identity_core
import pilot_core
from flask import Flask, jsonify, render_template, request, session
from seeders.demo_village_seeder import DEMO_DATA, get_demo_data

BASE_DIR = Path(__file__).resolve().parent


def _load_demo_data() -> dict[str, Any]:
    json_path = BASE_DIR / "data" / "demo_village.json"
    if json_path.is_file():
        try:
            return json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return get_demo_data()


def register(
    app: Flask,
    *,
    get_db: Callable[[], sqlite3.Connection],
    login_required: Callable,
) -> None:
    """Attach routes to the Flask app."""

    @app.route("/demo")
    def demo_dashboard_page():
        return render_template(
            "demo_dashboard.html",
            demo=_load_demo_data(),
            show_public_nav=True,
        )

    @app.route("/how-karma-works")
    def how_karma_works_page():
        return render_template("how_karma_works.html", show_public_nav=True)

    @app.route("/security")
    def security_page():
        return render_template("security.html", show_public_nav=True)

    @app.route("/metrics")
    def metrics_page():
        conn = get_db()
        user_count = int(
            conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0
        )
        village_count = 0
        try:
            village_count = int(
                conn.execute("SELECT COUNT(*) FROM village").fetchone()[0] or 0
            )
        except sqlite3.Error:
            pass
        return render_template(
            "metrics.html",
            show_public_nav=True,
            platform_metrics={
                "users_registered": user_count,
                "villages_in_db": village_count,
                "demo_karma_issued": 1_245_000,
                "demo_issues_resolved": 342,
                "demo_active_councils": 12,
            },
        )

    @app.route("/karma-ledger")
    def karma_ledger_page():
        return render_template("karma_ledger.html", show_public_nav=True)

    @app.route("/panchayat-onboarding")
    def panchayat_onboarding_page():
        return render_template("panchayat_onboarding.html", show_public_nav=True)

    @app.route("/api/docs")
    @app.route("/api/docs/")
    def api_docs_page():
        return render_template("api_docs.html", show_public_nav=True)

    @app.route("/api/openapi.json")
    def api_openapi_json():
        spec_path = BASE_DIR / "docs" / "openapi.yml"
        if not spec_path.is_file():
            return jsonify({"error": "OpenAPI spec not found"}), 404
        try:
            import yaml  # optional dependency

            return jsonify(yaml.safe_load(spec_path.read_text(encoding="utf-8")))
        except Exception:
            return (
                spec_path.read_text(encoding="utf-8"),
                200,
                {"Content-Type": "text/yaml; charset=utf-8"},
            )

    @app.route("/api/demo/village")
    def api_demo_village():
        return jsonify({"demo": _load_demo_data()})

    @app.route("/api/feedback", methods=["POST"])
    def api_feedback_submit():
        payload = request.get_json(silent=True) or {}
        conn = get_db()
        user_private_id = None
        pk = session.get("user_pk")
        if pk:
            row = conn.execute(
                "SELECT private_id FROM users WHERE id = ?", (int(pk),)
            ).fetchone()
            if row:
                user_private_id = str(row["private_id"])
        fid = feedback_core.submit_feedback(
            conn,
            page_path=str(payload.get("page_path") or request.referrer or "/"),
            rating=payload.get("rating"),
            message=str(payload.get("message") or ""),
            category=str(payload.get("category") or ""),
            user_private_id=user_private_id,
        )
        conn.commit()
        return jsonify({"ok": True, "id": fid})

    @app.route("/api/pilot/villages")
    def api_pilot_villages():
        conn = get_db()
        return jsonify({"villages": pilot_core.list_pilot_villages(conn)})

    @app.route("/api/pilot/feedback", methods=["POST"])
    def api_pilot_feedback():
        payload = request.get_json(silent=True) or {}
        village_id = str(payload.get("village_id") or "").strip()
        if not village_id:
            return jsonify({"error": "village_id required"}), 400
        conn = get_db()
        citizen_id = None
        pk = session.get("user_pk")
        if pk:
            row = conn.execute(
                "SELECT private_id FROM users WHERE id = ?", (int(pk),)
            ).fetchone()
            if row:
                citizen_id = str(row["private_id"])
        fid = pilot_core.submit_pilot_feedback(
            conn,
            village_id=village_id,
            category=str(payload.get("category") or ""),
            rating=payload.get("rating"),
            comment=str(payload.get("comment") or ""),
            citizen_id=citizen_id,
        )
        conn.commit()
        return jsonify({"ok": True, "id": fid})

    @app.route("/api/pilot/metrics")
    def api_pilot_metrics():
        village_id = (request.args.get("village_id") or "").strip() or None
        conn = get_db()
        return jsonify({"metrics": pilot_core.get_pilot_metrics(conn, village_id)})

    @app.route("/api/metrics/public")
    def api_metrics_public():
        conn = get_db()
        users = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] or 0)
        return jsonify(
            {
                "users_registered": users,
                "demo_data": DEMO_DATA,
            }
        )

    @app.route("/api/identity/level")
    @login_required
    def api_identity_level():
        from flask import g

        user = g.current_user
        identity_core.ensure_auth_level_column(get_db())
        level = identity_core.infer_auth_level(user)
        return jsonify(identity_core.auth_level_progress(level))

    app.logger.info("platform_extensions: demo, metrics, security, pilot, feedback routes registered")

    try:
        conn = get_db()
        feedback_core.ensure_schema(conn)
        pilot_core.ensure_schema(conn)
        identity_core.ensure_auth_level_column(conn)
        conn.commit()
    except Exception as exc:
        app.logger.warning("platform_extensions schema init: %s", exc)
