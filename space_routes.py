"""
HTTP routes for Ākāśa (Space): planetary positions and Mentor-only Ancestors / Akashic Records.
"""

from __future__ import annotations

import csv
import io
import json
from functools import wraps
from typing import Callable

from flask import Response, g, jsonify, render_template, request, session

import deceased_core
import element_core
import global_core
import planetary_core


def register_space_routes(
    app,
    get_db: Callable,
    login_required_decorator,
    *,
    is_admin_user_fn: Callable,
) -> None:
    def _mentor_required(view):
        @wraps(view)
        @login_required_decorator
        def wrapped(*args, **kwargs):
            conn = get_db()
            user = g.current_user
            if not deceased_core.is_mentor_user(conn, user) and not is_admin_user_fn(user):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Unauthorized — Mentor access only"}), 403
                return (
                    render_template(
                        "mentor_space.html",
                        tab="denied",
                        ancestors=[],
                        records=[],
                        is_mentor=False,
                    ),
                    403,
                )
            return view(*args, **kwargs)

        return wrapped

    @app.route("/api/planetary/current", methods=["GET", "POST"])
    def get_current_planetary_positions():
        conn = get_db()
        lang = str(session.get("preferred_language") or "en")

        if request.method == "POST":
            if not session.get("user_pk"):
                return jsonify({"error": "Unauthorized"}), 403
            data = request.get_json(silent=True) or {}
            tab = str(data.get("tab") or "private").strip().lower()

            if tab in ("private", "personal"):
                pid = str(g.current_user["private_id"] or "").strip()
                result = planetary_core.get_user_birth_planets_grouped(
                    conn, pid, language=lang
                )
                if not any(result.values()):
                    try:
                        row = conn.execute(
                            """
                            SELECT date_of_birth, birth_time, birth_latitude, birth_longitude
                            FROM users WHERE private_id = ?
                            """,
                            (pid,),
                        ).fetchone()
                        if row:
                            planetary_core.save_user_birth_planets(
                                conn,
                                pid,
                                date_of_birth=str(row["date_of_birth"] or "2000-01-01"),
                                birth_time=str(row["birth_time"] or "12:00"),
                                latitude=float(row["birth_latitude"])
                                if row["birth_latitude"] is not None
                                else None,
                                longitude=float(row["birth_longitude"])
                                if row["birth_longitude"] is not None
                                else None,
                            )
                            conn.commit()
                            result = planetary_core.get_user_birth_planets_grouped(
                                conn, pid, language=lang
                            )
                    except (TypeError, ValueError):
                        pass
                return jsonify(result)

            location_id = (data.get("location_id") or "").strip() or None
            location_type = (data.get("location_type") or "").strip() or None
            result = planetary_core.get_live_planetary_positions(
                conn,
                location_id=location_id,
                location_type=location_type,
                language=lang,
            )
            return jsonify(result)

        location_id = (request.args.get("location_id") or "").strip() or None
        location_type = (request.args.get("location_type") or "").strip() or None
        result = planetary_core.get_current_planetary_positions(
            conn,
            language=lang,
            location_id=location_id,
            location_type=location_type,
        )
        return jsonify(result)

    @app.route("/api/planetary/location-coordinates", methods=["GET"])
    @login_required_decorator
    def get_location_coordinates_api():
        conn = get_db()
        location_id = (request.args.get("location_id") or "").strip()
        location_type = (request.args.get("location_type") or "").strip()
        lat, lon = planetary_core.resolve_location_coordinates(
            conn, location_id, location_type
        )
        return jsonify(
            {
                "location_id": location_id,
                "location_type": location_type,
                "latitude": lat,
                "longitude": lon,
            }
        )

    @app.route("/api/element/stats", methods=["POST"])
    @login_required_decorator
    def get_element_stats_api():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        element = str(data.get("element") or "Fire").strip().title()
        if element not in global_core.ELEMENT_SIGNS:
            return jsonify({"error": "Invalid element"}), 400
        result = global_core.get_element_stats(
            conn,
            element=element,
            location_id=(data.get("location_id") or "").strip() or None,
            location_type=(data.get("location_type") or "").strip() or None,
            tab=str(data.get("tab") or "private").strip().lower(),
        )
        return jsonify(result)

    @app.route("/api/element/popup/<element>", methods=["GET"])
    @login_required_decorator
    def get_element_popup_api(element: str):
        """Popup data: member counts per sign and ruling planets for an element tab."""
        conn = get_db()
        element_core.migrate_element_core_schema(conn)
        el = str(element or "Fire").strip().title()
        if el not in global_core.ELEMENT_SIGNS:
            return jsonify({"error": "Invalid element"}), 400
        tab = str(request.args.get("active_tab") or request.args.get("tab") or "private").strip().lower()
        location_id = (request.args.get("location_id") or "").strip() or None
        location_type = (request.args.get("location_type") or "").strip() or None
        result = element_core.get_element_popup_data(
            conn,
            element=el,
            location_id=location_id,
            location_type=location_type,
            tab=tab,
        )
        return jsonify(result)

    @app.route("/api/planetary/user/<private_id>", methods=["GET"])
    @login_required_decorator
    def get_user_birth_planets(private_id):
        conn = get_db()
        lang = str(session.get("preferred_language") or "en")
        viewer = g.current_user
        target = str(private_id or "").strip().upper()
        viewer_pid = str(viewer["private_id"] or "").strip().upper()
        if target != viewer_pid and not is_admin_user_fn(viewer):
            if not deceased_core.is_mentor_user(conn, viewer):
                return jsonify({"error": "Unauthorized"}), 403
        result = planetary_core.get_user_birth_planets_grouped(conn, target, language=lang)
        if not any(result.values()):
            try:
                row = conn.execute(
                    "SELECT date_of_birth, birth_time, birth_latitude, birth_longitude FROM users WHERE private_id = ?",
                    (target,),
                ).fetchone()
                if row:
                    planetary_core.save_user_birth_planets(
                        conn,
                        target,
                        date_of_birth=str(row["date_of_birth"] or "2000-01-01"),
                        birth_time=str(row["birth_time"] or "12:00"),
                        latitude=float(row["birth_latitude"]) if row["birth_latitude"] is not None else None,
                        longitude=float(row["birth_longitude"]) if row["birth_longitude"] is not None else None,
                    )
                    conn.commit()
                    result = planetary_core.get_user_birth_planets_grouped(conn, target, language=lang)
            except (TypeError, ValueError):
                pass
        return jsonify(result)

    @app.post("/api/mentor/mark-deceased")
    @_mentor_required
    def mark_user_deceased():
        conn = get_db()
        data = request.get_json(silent=True) or {}
        user_id = (data.get("user_private_id") or "").strip().upper()
        date_of_death = (data.get("date_of_death") or "").strip()
        if not user_id or not date_of_death:
            return jsonify({"error": "user_private_id and date_of_death are required"}), 400
        try:
            result = deceased_core.mark_user_deceased(
                conn,
                target_private_id=user_id,
                date_of_death=date_of_death,
                moved_by=str(g.current_user["private_id"] or ""),
                obituary=(data.get("obituary") or "").strip() or None,
                heir_private_id=(data.get("heir_private_id") or "").strip().upper() or None,
            )
            conn.commit()
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    @app.get("/api/mentor/ancestors")
    @_mentor_required
    def get_ancestors_api():
        conn = get_db()
        location_id = (request.args.get("location_id") or "").strip() or None
        search = (request.args.get("search") or "").strip() or None
        ancestors = deceased_core.get_ancestors(
            conn, location_id=location_id, search=search
        )
        return jsonify({"ancestors": ancestors})

    @app.get("/api/mentor/akashic-records")
    @_mentor_required
    def get_akashic_records_api():
        conn = get_db()
        records = deceased_core.get_akashic_records(
            conn,
            record_type=(request.args.get("record_type") or "").strip() or None,
            location_id=(request.args.get("location_id") or "").strip() or None,
            date_from=(request.args.get("date_from") or "").strip() or None,
            date_to=(request.args.get("date_to") or "").strip() or None,
        )
        return jsonify({"records": records})

    @app.get("/api/mentor/akashic-records/export")
    @_mentor_required
    def export_akashic_records():
        conn = get_db()
        fmt = (request.args.get("format") or "json").lower()
        records = deceased_core.get_akashic_records(
            conn,
            record_type=(request.args.get("record_type") or "").strip() or None,
            location_id=(request.args.get("location_id") or "").strip() or None,
            date_from=(request.args.get("date_from") or "").strip() or None,
            date_to=(request.args.get("date_to") or "").strip() or None,
            limit=5000,
        )
        if fmt == "csv":
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                ["id", "record_type", "original_id", "user_private_id", "location_id", "archived_at", "archived_by"]
            )
            for r in records:
                writer.writerow(
                    [
                        r.get("id"),
                        r.get("record_type"),
                        r.get("original_id"),
                        r.get("user_private_id"),
                        r.get("location_id"),
                        r.get("archived_at"),
                        r.get("archived_by"),
                    ]
                )
            return Response(
                buf.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=akashic_records.csv"},
            )
        payload = json.dumps({"records": records}, indent=2, default=str)
        return Response(
            payload,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=akashic_records.json"},
        )

    @app.route("/space/ancestors")
    @_mentor_required
    def space_ancestors_page():
        conn = get_db()
        location_id = (request.args.get("location_id") or "").strip() or None
        search = (request.args.get("search") or "").strip() or None
        ancestors = deceased_core.get_ancestors(
            conn, location_id=location_id, search=search
        )
        return render_template(
            "mentor_space.html",
            tab="ancestors",
            ancestors=ancestors,
            records=[],
            is_mentor=True,
            search=search or "",
            location_id=location_id or "",
        )

    @app.route("/space/akashic-records")
    @_mentor_required
    def space_akashic_page():
        conn = get_db()
        record_type = (request.args.get("record_type") or "").strip() or None
        location_id = (request.args.get("location_id") or "").strip() or None
        date_from = (request.args.get("date_from") or "").strip() or None
        date_to = (request.args.get("date_to") or "").strip() or None
        records = deceased_core.get_akashic_records(
            conn,
            record_type=record_type,
            location_id=location_id,
            date_from=date_from,
            date_to=date_to,
        )
        return render_template(
            "mentor_space.html",
            tab="akashic",
            ancestors=[],
            records=records,
            is_mentor=True,
            record_type=record_type or "",
            location_id=location_id or "",
            date_from=date_from or "",
            date_to=date_to or "",
        )
