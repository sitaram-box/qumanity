"""Village Marketplace, Job Portal, Karma claims, and Business registration."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from flask import (
    Blueprint,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

import qoin_core

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BASE_DIR / "static" / "uploads"
KARMA_UPLOAD_DIR = UPLOAD_ROOT / "karma"
RESUME_UPLOAD_DIR = UPLOAD_ROOT / "resumes"
LISTING_UPLOAD_DIR = UPLOAD_ROOT / "listings"

MARKETPLACE_CATEGORIES: dict[str, list[str]] = {
    "Transport": [
        "Rickshaw",
        "Auto",
        "Bike Taxi",
        "Cab",
        "Goods Transport",
        "Tractor for hire",
    ],
    "Food": [
        "Vegetables",
        "Fruits",
        "Dairy",
        "Bakery",
        "Homemade Food",
        "Catering",
    ],
    "Education": [
        "Tuition (all subjects)",
        "Computer Training",
        "Language Classes",
        "Coaching",
    ],
    "Health": [
        "Nurse",
        "Caretaker",
        "Ayurveda",
        "Physiotherapy",
        "Ambulance service",
    ],
    "Repair & Services": [
        "Mobile Repair",
        "Electrician",
        "Plumber",
        "Carpenter",
        "Mechanic",
        "AC Repair",
    ],
    "Home & Personal": [
        "Tailoring",
        "Mehendi",
        "Beauty Services",
        "Cleaning",
        "Laundry",
    ],
    "Agriculture": [
        "Seeds",
        "Fertilizers",
        "Farm Equipment on rent",
        "Labour hiring",
    ],
    "Construction": [
        "Masons",
        "Labourers",
        "Plumbers (construction)",
        "Material supply",
    ],
    "Entertainment & Events": [
        "DJ",
        "Event Planning",
        "Decoration",
        "Photography",
    ],
    "Pet Services": ["Pet grooming", "Veterinary", "Pet food"],
}

JOB_CATEGORIES = list(MARKETPLACE_CATEGORIES.keys()) + ["Delivery", "General"]

SKILL_PRESETS = [
    "Plumbing",
    "Electrical work",
    "Driving",
    "Cooking",
    "Teaching",
    "Farming",
    "Tailoring",
    "Computer skills",
    "Healthcare",
    "Construction",
    "Delivery",
    "Customer service",
]

KARMA_ACTION_SEED: tuple[tuple[str, str, int, int, int, int], ...] = (
    ("plant_tree", "Plant a tree", 10, 1, 1, 180),
    ("teach_hour", "Teach 1 hour", 20, 1, 0, 0),
    ("help_elder", "Help elder (verified)", 15, 1, 0, 0),
    ("report_issue", "Report issue", 5, 0, 0, 0),
    ("clean_village", "Clean village area", 10, 1, 0, 0),
    ("council_day", "Serve on Village Council (per day)", 50, 1, 0, 0),
)

VILLAGE_PLATFORM_SQL = """
CREATE TABLE IF NOT EXISTS businesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_private_id TEXT NOT NULL,
    business_name TEXT NOT NULL,
    business_type TEXT NOT NULL,
    address TEXT,
    gst_number TEXT,
    pan_number TEXT,
    village_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    approved_by TEXT,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_businesses_owner ON businesses(owner_private_id);
CREATE INDEX IF NOT EXISTS idx_businesses_village_status ON businesses(village_id, status);

CREATE TABLE IF NOT EXISTS marketplace_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_private_id TEXT NOT NULL,
    business_id INTEGER,
    village_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    subcategory TEXT,
    listing_type TEXT NOT NULL DEFAULT 'product',
    price_rupees INTEGER NOT NULL,
    photos_json TEXT DEFAULT '[]',
    stock_qty INTEGER,
    delivery_available INTEGER NOT NULL DEFAULT 0,
    pickup_available INTEGER NOT NULL DEFAULT 1,
    avg_rating REAL NOT NULL DEFAULT 0,
    rating_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_listings_village ON marketplace_listings(village_id, status);
CREATE INDEX IF NOT EXISTS idx_listings_seller ON marketplace_listings(seller_private_id);

CREATE TABLE IF NOT EXISTS marketplace_cart (
    user_private_id TEXT NOT NULL,
    listing_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_private_id, listing_id)
);

CREATE TABLE IF NOT EXISTS marketplace_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_ref TEXT UNIQUE NOT NULL,
    buyer_private_id TEXT NOT NULL,
    seller_private_id TEXT NOT NULL,
    village_id TEXT NOT NULL,
    total_rupees INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    delivery_mode TEXT NOT NULL DEFAULT 'pickup',
    delivery_agent_private_id TEXT,
    escrow_transaction_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_orders_buyer ON marketplace_orders(buyer_private_id);
CREATE INDEX IF NOT EXISTS idx_orders_seller ON marketplace_orders(seller_private_id);

CREATE TABLE IF NOT EXISTS marketplace_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    listing_id INTEGER,
    title TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_rupees INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES marketplace_orders(id)
);

CREATE TABLE IF NOT EXISTS marketplace_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    reviewer_private_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS delivery_agents (
    user_private_id TEXT PRIMARY KEY,
    village_id TEXT NOT NULL,
    vehicle_type TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    approved_by TEXT,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS karma_claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_private_id TEXT NOT NULL,
    village_id TEXT NOT NULL,
    action_code TEXT NOT NULL,
    description TEXT,
    proof_path TEXT,
    gps_lat REAL,
    gps_lng REAL,
    witness_public_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    council_reviewer TEXT,
    council_comment TEXT,
    reviewed_at TIMESTAMP,
    followup_due_at TIMESTAMP,
    followup_proof_path TEXT,
    followup_status TEXT,
    amount_rupees INTEGER NOT NULL DEFAULT 0,
    amount_credited_upfront INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_karma_claims_village_status ON karma_claims(village_id, status);
CREATE INDEX IF NOT EXISTS idx_karma_claims_user ON karma_claims(user_private_id);

CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_private_id TEXT NOT NULL,
    employer_type TEXT NOT NULL,
    title TEXT NOT NULL,
    job_type TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    requirements TEXT,
    salary_qoins INTEGER NOT NULL,
    salary_period TEXT,
    location_village_id TEXT NOT NULL,
    openings INTEGER NOT NULL DEFAULT 1,
    deadline DATE,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_jobs_village ON job_postings(location_village_id, status);

CREATE TABLE IF NOT EXISTS job_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_posting_id INTEGER NOT NULL,
    applicant_private_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_posting_id) REFERENCES job_postings(id)
);
CREATE INDEX IF NOT EXISTS idx_job_apps_posting ON job_applications(job_posting_id);

CREATE TABLE IF NOT EXISTS job_seeker_profiles (
    user_private_id TEXT PRIMARY KEY,
    skills TEXT,
    experience TEXT,
    education TEXT,
    availability TEXT,
    resume_path TEXT,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employment_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_private_id TEXT NOT NULL,
    employee_private_id TEXT NOT NULL,
    job_posting_id INTEGER,
    title TEXT NOT NULL,
    salary_qoins INTEGER NOT NULL,
    salary_period TEXT,
    start_date DATE,
    end_date DATE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employment_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id INTEGER NOT NULL,
    rater_private_id TEXT NOT NULL,
    ratee_private_id TEXT NOT NULL,
    rating_type TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_id) REFERENCES employment_contracts(id)
);
"""

bp = Blueprint("village_platform", __name__)

_now: Callable[[], str] | None = None
_user_village_id: Callable[[Any], str] | None = None
_is_council: Callable[[sqlite3.Connection, str, str], bool] | None = None
_approved_business: Callable[[sqlite3.Connection, str], sqlite3.Row | None] | None = None
_send_system_message: Callable[..., str] | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def migrate_village_platform_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(VILLAGE_PLATFORM_SQL)
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(karma_action_types)")}
    for col, decl in (
        ("requires_verification", "INTEGER NOT NULL DEFAULT 1"),
        ("requires_followup", "INTEGER NOT NULL DEFAULT 0"),
        ("followup_days", "INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in cols:
            try:
                conn.execute(
                    f"ALTER TABLE karma_action_types ADD COLUMN {col} {decl}"
                )
            except sqlite3.OperationalError:
                pass
    for code, label, val, req_v, req_f, fup in KARMA_ACTION_SEED:
        conn.execute(
            """
            INSERT INTO karma_action_types (
                action_code, label, rupee_value, active,
                requires_verification, requires_followup, followup_days
            ) VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(action_code) DO UPDATE SET
                label = excluded.label,
                rupee_value = excluded.rupee_value,
                requires_verification = excluded.requires_verification,
                requires_followup = excluded.requires_followup,
                followup_days = excluded.followup_days
            """,
            (code, label, val, req_v, req_f, fup),
        )
    conn.commit()
    for d in (KARMA_UPLOAD_DIR, RESUME_UPLOAD_DIR, LISTING_UPLOAD_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _json_load(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _user_row_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {k: row[k] for k in row.keys()}


def _listing_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = _user_row_dict(row)
    d["photos"] = _json_load(str(row["photos_json"] or ""), [])
    d["delivery_available"] = bool(int(row["delivery_available"] or 0))
    d["pickup_available"] = bool(int(row["pickup_available"] or 0))
    return d


def _save_upload(file_storage, folder: Path, prefix: str) -> str | None:
    if not file_storage or not file_storage.filename:
        return None
    name = secure_filename(file_storage.filename)
    if not name:
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".pdf"}:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{prefix}_{uuid.uuid4().hex}{ext}"
    path = folder / fname
    file_storage.save(path)
    return f"uploads/{folder.name}/{fname}"


def register(app, *, deps: dict[str, Callable[..., Any]]) -> None:
    global _now, _user_village_id, _is_council, _approved_business, _send_system_message
    _now = deps.get("_utc_now", _utc_now)
    _user_village_id = deps["user_village_id"]
    _is_council = deps["is_council_member"]
    _approved_business = deps["approved_business_for_user"]
    _send_system_message = deps.get("send_system_message")

    login_required = deps["login_required"]
    get_db = deps["get_db"]
    user_in_indian_village = deps["user_in_indian_village"]
    location_display_label = deps.get("location_display_label", lambda _c, x: x)
    ensure_economic_account = deps.get("ensure_economic_account")

    @app.route("/marketplace")
    @login_required
    def marketplace_page():
        conn = get_db()
        user = g.current_user
        if not user_in_indian_village(conn, user):
            return redirect(url_for("dashboard"))
        vid = _user_village_id(user)
        return render_template(
            "marketplace.html",
            user=user,
            village_id=vid,
            village_label=location_display_label(conn, vid),
            categories=MARKETPLACE_CATEGORIES,
        )

    @app.route("/job-portal")
    @login_required
    def job_portal_page():
        conn = get_db()
        user = g.current_user
        if not user_in_indian_village(conn, user):
            return redirect(url_for("dashboard"))
        vid = _user_village_id(user)
        biz = _approved_business(conn, str(user["private_id"]))
        council = _is_council(conn, str(user["private_id"]), vid)
        return render_template(
            "job_portal.html",
            user=user,
            village_id=vid,
            village_label=location_display_label(conn, vid),
            job_categories=JOB_CATEGORIES,
            skill_presets=SKILL_PRESETS,
            can_post_jobs=bool(biz or council),
        )

    @bp.get("/api/village/categories")
    @login_required
    def api_marketplace_categories():
        return jsonify({"categories": MARKETPLACE_CATEGORIES})

    @bp.get("/api/marketplace/listings")
    @login_required
    def api_listings_search():
        conn = get_db()
        user = g.current_user
        vid = _user_village_id(user)
        q = (request.args.get("q") or "").strip().lower()
        category = (request.args.get("category") or "").strip()
        min_price = request.args.get("min_price", type=int)
        max_price = request.args.get("max_price", type=int)
        min_rating = request.args.get("min_rating", type=float)
        delivery_only = request.args.get("delivery") == "1"

        sql = """
            SELECT l.*, u.public_id AS seller_public_id,
                   u.first_name || ' ' || u.last_name AS seller_name,
                   b.business_name, b.status AS business_status
            FROM marketplace_listings l
            JOIN users u ON u.private_id = l.seller_private_id
            LEFT JOIN businesses b ON b.id = l.business_id
            WHERE l.village_id = ? AND l.status = 'active'
        """
        params: list[Any] = [vid]
        if category:
            sql += " AND l.category = ?"
            params.append(category)
        if min_price is not None:
            sql += " AND l.price_rupees >= ?"
            params.append(min_price)
        if max_price is not None:
            sql += " AND l.price_rupees <= ?"
            params.append(max_price)
        if min_rating is not None:
            sql += " AND l.avg_rating >= ?"
            params.append(min_rating)
        if delivery_only:
            sql += " AND l.delivery_available = 1"
        if q:
            sql += " AND (LOWER(l.title) LIKE ? OR LOWER(l.description) LIKE ? OR LOWER(l.subcategory) LIKE ?)"
            like = f"%{q}%"
            params.extend([like, like, like])
        sql += " ORDER BY l.avg_rating DESC, l.created_at DESC LIMIT 100"
        rows = [_listing_dict(r) for r in conn.execute(sql, params)]
        for row in rows:
            row["verified_seller"] = row.get("business_status") == "approved"
        return jsonify({"listings": rows, "village_id": vid})

    @bp.post("/api/marketplace/listings")
    @login_required
    def api_listing_create():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        biz = _approved_business(conn, pid)
        if not biz:
            return jsonify({"error": "Approved business registration required to sell"}), 403
        vid = _user_village_id(user)
        title = (request.form.get("title") or "").strip()
        category = (request.form.get("category") or "").strip()
        subcategory = (request.form.get("subcategory") or "").strip()
        listing_type = (request.form.get("listing_type") or "product").strip()
        try:
            price = int(request.form.get("price_rupees") or 0)
        except ValueError:
            price = 0
        if not title or not category or price <= 0:
            return jsonify({"error": "title, category, and price required"}), 400
        photos: list[str] = []
        for key in ("photo1", "photo2", "photo3"):
            saved = _save_upload(request.files.get(key), LISTING_UPLOAD_DIR, pid)
            if saved:
                photos.append(saved)
        stock_raw = request.form.get("stock_qty")
        stock = int(stock_raw) if stock_raw not in (None, "") else None
        conn.execute(
            """
            INSERT INTO marketplace_listings (
                seller_private_id, business_id, village_id, title, description,
                category, subcategory, listing_type, price_rupees, photos_json,
                stock_qty, delivery_available, pickup_available, status, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?)
            """,
            (
                pid,
                int(biz["id"]),
                vid,
                title,
                (request.form.get("description") or "").strip(),
                category,
                subcategory,
                listing_type,
                price,
                json.dumps(photos),
                stock,
                1 if request.form.get("delivery_available") == "1" else 0,
                1 if request.form.get("pickup_available", "1") == "1" else 0,
                _now(),
            ),
        )
        conn.commit()
        return jsonify({"ok": True, "id": int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])})

    @bp.put("/api/marketplace/listings/<int:listing_id>")
    @login_required
    def api_listing_update(listing_id: int):
        conn = get_db()
        pid = str(g.current_user["private_id"])
        row = conn.execute(
            "SELECT * FROM marketplace_listings WHERE id = ? AND seller_private_id = ?",
            (listing_id, pid),
        ).fetchone()
        if not row:
            return jsonify({"error": "Listing not found"}), 404
        payload = request.get_json(silent=True) or {}
        title = (payload.get("title") or row["title"]).strip()
        price = int(payload.get("price_rupees") or row["price_rupees"])
        status = (payload.get("status") or row["status"]).strip()
        conn.execute(
            """
            UPDATE marketplace_listings
            SET title = ?, description = ?, price_rupees = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                title,
                (payload.get("description") or row["description"] or "").strip(),
                price,
                status,
                _now(),
                listing_id,
            ),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.delete("/api/marketplace/listings/<int:listing_id>")
    @login_required
    def api_listing_delete(listing_id: int):
        conn = get_db()
        pid = str(g.current_user["private_id"])
        cur = conn.execute(
            """
            UPDATE marketplace_listings SET status = 'deleted', updated_at = ?
            WHERE id = ? AND seller_private_id = ?
            """,
            (_now(), listing_id, pid),
        )
        conn.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "Listing not found"}), 404
        return jsonify({"ok": True})

    @bp.get("/api/marketplace/cart")
    @login_required
    def api_cart_get():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        rows = conn.execute(
            """
            SELECT c.quantity, l.*
            FROM marketplace_cart c
            JOIN marketplace_listings l ON l.id = c.listing_id
            WHERE c.user_private_id = ? AND l.status = 'active'
            """,
            (pid,),
        ).fetchall()
        items = []
        total = 0
        for r in rows:
            item = _listing_dict(r)
            item["quantity"] = int(r["quantity"])
            item["line_total"] = item["quantity"] * int(r["price_rupees"])
            total += item["line_total"]
            items.append(item)
        return jsonify({"items": items, "total_rupees": total})

    @bp.post("/api/marketplace/cart")
    @login_required
    def api_cart_add():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        payload = request.get_json(silent=True) or {}
        listing_id = int(payload.get("listing_id") or 0)
        qty = max(1, int(payload.get("quantity") or 1))
        listing = conn.execute(
            "SELECT id FROM marketplace_listings WHERE id = ? AND status = 'active'",
            (listing_id,),
        ).fetchone()
        if not listing:
            return jsonify({"error": "Listing not found"}), 404
        conn.execute(
            """
            INSERT INTO marketplace_cart (user_private_id, listing_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(user_private_id, listing_id) DO UPDATE SET quantity = quantity + excluded.quantity
            """,
            (pid, listing_id, qty),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.delete("/api/marketplace/cart/<int:listing_id>")
    @login_required
    def api_cart_remove(listing_id: int):
        conn = get_db()
        conn.execute(
            "DELETE FROM marketplace_cart WHERE user_private_id = ? AND listing_id = ?",
            (str(g.current_user["private_id"]), listing_id),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.post("/api/marketplace/checkout")
    @login_required
    def api_checkout():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        payload = request.get_json(silent=True) or {}
        delivery_mode = (payload.get("delivery_mode") or "pickup").strip()
        cart_rows = conn.execute(
            """
            SELECT c.quantity, l.*
            FROM marketplace_cart c
            JOIN marketplace_listings l ON l.id = c.listing_id
            WHERE c.user_private_id = ? AND l.status = 'active'
            """,
            (pid,),
        ).fetchall()
        if not cart_rows:
            return jsonify({"error": "Cart is empty"}), 400
        seller = str(cart_rows[0]["seller_private_id"])
        if any(str(r["seller_private_id"]) != seller for r in cart_rows):
            return jsonify({"error": "Checkout one seller at a time"}), 400
        total = sum(int(r["quantity"]) * int(r["price_rupees"]) for r in cart_rows)
        activity_village = str(cart_rows[0]["village_id"])
        if ensure_economic_account and activity_village != _user_village_id(user):
            ensure_economic_account(conn, user, activity_village)
        order_ref = f"ORD-{uuid.uuid4().hex[:12].upper()}"
        txid = qoin_core.record_commercial_transaction(
            conn,
            buyer_private_id=pid,
            seller_private_id=seller,
            amount_rupees=total,
            description=f"Marketplace order {order_ref} (escrow pending delivery)",
        )
        conn.execute(
            """
            INSERT INTO marketplace_orders (
                order_ref, buyer_private_id, seller_private_id, village_id,
                total_rupees, status, delivery_mode, escrow_transaction_id, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                order_ref,
                pid,
                seller,
                _user_village_id(user),
                total,
                "pending",
                delivery_mode,
                txid,
                _now(),
            ),
        )
        order_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        for r in cart_rows:
            conn.execute(
                """
                INSERT INTO marketplace_order_items (
                    order_id, listing_id, title, quantity, unit_price_rupees
                ) VALUES (?,?,?,?,?)
                """,
                (
                    order_id,
                    int(r["id"]),
                    str(r["title"]),
                    int(r["quantity"]),
                    int(r["price_rupees"]),
                ),
            )
        conn.execute(
            "DELETE FROM marketplace_cart WHERE user_private_id = ?",
            (pid,),
        )
        if _send_system_message:
            _send_system_message(
                conn,
                seller,
                f"New marketplace order {order_ref}",
                f"You have a new order for ₹{total}. Accept or reject in Village Marketplace.",
            )
        conn.commit()
        return jsonify({"ok": True, "order_ref": order_ref, "order_id": order_id})

    @bp.get("/api/marketplace/orders")
    @login_required
    def api_orders_list():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        role = (request.args.get("role") or "buyer").strip()
        if role == "seller":
            rows = conn.execute(
                """
                SELECT * FROM marketplace_orders
                WHERE seller_private_id = ?
                ORDER BY datetime(created_at) DESC LIMIT 50
                """,
                (pid,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM marketplace_orders
                WHERE buyer_private_id = ?
                ORDER BY datetime(created_at) DESC LIMIT 50
                """,
                (pid,),
            ).fetchall()
        return jsonify({"orders": [_user_row_dict(r) for r in rows]})

    @bp.post("/api/marketplace/orders/<int:order_id>/status")
    @login_required
    def api_order_status(order_id: int):
        conn = get_db()
        pid = str(g.current_user["private_id"])
        payload = request.get_json(silent=True) or {}
        new_status = (payload.get("status") or "").strip()
        allowed = {
            "pending",
            "accepted",
            "rejected",
            "in_delivery",
            "delivered",
            "completed",
            "cancelled",
        }
        if new_status not in allowed:
            return jsonify({"error": "Invalid status"}), 400
        order = conn.execute(
            "SELECT * FROM marketplace_orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not order:
            return jsonify({"error": "Order not found"}), 404
        if new_status in {"accepted", "rejected"} and str(order["seller_private_id"]) != pid:
            return jsonify({"error": "Only seller can accept/reject"}), 403
        if new_status in {"completed", "delivered"} and str(order["buyer_private_id"]) != pid:
            if new_status == "completed" and str(order["buyer_private_id"]) == pid:
                pass
            elif new_status == "delivered" and str(order["delivery_agent_private_id"]) == pid:
                pass
            elif str(order["buyer_private_id"]) != pid:
                return jsonify({"error": "Not allowed"}), 403
        conn.execute(
            "UPDATE marketplace_orders SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, _now(), order_id),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.post("/api/marketplace/reviews")
    @login_required
    def api_review_create():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        payload = request.get_json(silent=True) or {}
        order_id = int(payload.get("order_id") or 0)
        target_type = (payload.get("target_type") or "product").strip()
        rating = int(payload.get("rating") or 0)
        if rating < 1 or rating > 5:
            return jsonify({"error": "Rating must be 1–5"}), 400
        order = conn.execute(
            "SELECT * FROM marketplace_orders WHERE id = ? AND buyer_private_id = ?",
            (order_id, pid),
        ).fetchone()
        if not order:
            return jsonify({"error": "Order not found"}), 404
        conn.execute(
            """
            INSERT INTO marketplace_reviews (
                order_id, reviewer_private_id, target_type, rating, comment
            ) VALUES (?,?,?,?,?)
            """,
            (order_id, pid, target_type, rating, (payload.get("comment") or "").strip()),
        )
        if target_type == "product":
            conn.execute(
                """
                UPDATE marketplace_listings
                SET avg_rating = (
                    SELECT AVG(rating) FROM marketplace_reviews r
                    JOIN marketplace_order_items oi ON oi.order_id = r.order_id
                    WHERE r.target_type = 'product' AND oi.listing_id = marketplace_listings.id
                ),
                rating_count = rating_count + 1
                WHERE id IN (SELECT listing_id FROM marketplace_order_items WHERE order_id = ?)
                """,
                (order_id,),
            )
        conn.commit()
        return jsonify({"ok": True})

    @bp.post("/api/marketplace/delivery-agents/apply")
    @login_required
    def api_delivery_agent_apply():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        payload = request.get_json(silent=True) or {}
        conn.execute(
            """
            INSERT INTO delivery_agents (user_private_id, village_id, vehicle_type, status)
            VALUES (?, ?, ?, 'pending')
            ON CONFLICT(user_private_id) DO UPDATE SET
                vehicle_type = excluded.vehicle_type,
                village_id = excluded.village_id
            """,
            (pid, vid, (payload.get("vehicle_type") or "").strip()),
        )
        conn.commit()
        return jsonify({"ok": True, "status": "pending"})

    @bp.get("/api/marketplace/delivery-requests")
    @login_required
    def api_delivery_requests():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        agent = conn.execute(
            "SELECT status FROM delivery_agents WHERE user_private_id = ?",
            (pid,),
        ).fetchone()
        if not agent or str(agent["status"]) != "approved":
            return jsonify({"error": "Approved delivery agent required"}), 403
        rows = conn.execute(
            """
            SELECT * FROM marketplace_orders
            WHERE village_id = ? AND delivery_mode = 'delivery'
              AND status IN ('accepted', 'in_delivery')
            ORDER BY datetime(created_at) DESC LIMIT 30
            """,
            (vid,),
        ).fetchall()
        return jsonify({"orders": [_user_row_dict(r) for r in rows]})

    @bp.post("/api/karma/claims")
    @login_required
    def api_karma_claim_submit():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        action_code = (request.form.get("action_code") or "").strip()
        action = conn.execute(
            """
            SELECT action_code, label, rupee_value, requires_verification,
                   requires_followup, followup_days
            FROM karma_action_types WHERE action_code = ? AND active = 1
            """,
            (action_code,),
        ).fetchone()
        if not action:
            return jsonify({"error": "Unknown action"}), 400
        if ensure_economic_account and vid != _user_village_id(user):
            ensure_economic_account(conn, user, vid)
        proof = _save_upload(request.files.get("proof"), KARMA_UPLOAD_DIR, pid)
        lat = request.form.get("gps_lat")
        lng = request.form.get("gps_lng")
        followup_due = None
        if int(action["requires_followup"] or 0):
            days = int(action["followup_days"] or 180)
            followup_due = (date.today() + timedelta(days=days)).isoformat()
        amount = int(action["rupee_value"])
        conn.execute(
            """
            INSERT INTO karma_claims (
                user_private_id, village_id, action_code, description, proof_path,
                gps_lat, gps_lng, witness_public_id, status, followup_due_at,
                amount_rupees, amount_credited_upfront
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pid,
                vid,
                action_code,
                (request.form.get("description") or "").strip(),
                proof,
                float(lat) if lat else None,
                float(lng) if lng else None,
                (request.form.get("witness_public_id") or "").strip() or None,
                "pending" if int(action["requires_verification"] or 0) else "approved",
                followup_due,
                amount,
                0,
            ),
        )
        claim_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        karma_recorded = False
        if not int(action["requires_verification"] or 0):
            qoin_core.record_karma_action(
                conn,
                user_private_id=pid,
                action_code=action_code,
                description=f"Auto-approved claim #{claim_id}",
                verified=True,
            )
            karma_recorded = True
        conn.commit()
        return jsonify(
            {
                "ok": True,
                "claim_id": claim_id,
                "karma_recorded": karma_recorded,
                "action_code": action_code,
                "action_label": str(action["label"]),
                "amount_rupees": amount,
            }
        )

    @bp.get("/api/karma/claims")
    @login_required
    def api_karma_claims_mine():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        rows = conn.execute(
            """
            SELECT k.*, ka.label AS action_label
            FROM karma_claims k
            LEFT JOIN karma_action_types ka ON ka.action_code = k.action_code
            WHERE k.user_private_id = ?
            ORDER BY datetime(k.created_at) DESC LIMIT 50
            """,
            (pid,),
        ).fetchall()
        return jsonify({"claims": [_user_row_dict(r) for r in rows]})

    @bp.get("/api/karma/claims/pending")
    @login_required
    def api_karma_claims_pending_council():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        if not _is_council(conn, pid, vid):
            return jsonify({"error": "Village Council access required"}), 403
        rows = conn.execute(
            """
            SELECT k.*, u.public_id, u.first_name, u.last_name, ka.label AS action_label
            FROM karma_claims k
            JOIN users u ON u.private_id = k.user_private_id
            LEFT JOIN karma_action_types ka ON ka.action_code = k.action_code
            WHERE k.village_id = ? AND k.status = 'pending'
            ORDER BY datetime(k.created_at) ASC
            """,
            (vid,),
        ).fetchall()
        return jsonify({"claims": [_user_row_dict(r) for r in rows]})

    @bp.post("/api/karma/claims/<int:claim_id>/review")
    @login_required
    def api_karma_claim_review(claim_id: int):
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        if not _is_council(conn, pid, vid):
            return jsonify({"error": "Village Council access required"}), 403
        payload = request.get_json(silent=True) or {}
        decision = (payload.get("status") or "").strip()
        if decision not in {"approved", "rejected", "partially_approved"}:
            return jsonify({"error": "status must be approved, rejected, or partially_approved"}), 400
        claim = conn.execute(
            "SELECT * FROM karma_claims WHERE id = ? AND village_id = ?",
            (claim_id, vid),
        ).fetchone()
        if not claim:
            return jsonify({"error": "Claim not found"}), 404
        action = conn.execute(
            "SELECT * FROM karma_action_types WHERE action_code = ?",
            (claim["action_code"],),
        ).fetchone()
        amount = int(claim["amount_rupees"])
        upfront = 0
        if decision in {"approved", "partially_approved"} and action:
            if claim["action_code"] == "plant_tree" and decision == "partially_approved":
                upfront = amount // 2
                qoin_core.record_karma_action(
                    conn,
                    user_private_id=str(claim["user_private_id"]),
                    action_code=str(claim["action_code"]),
                    description=f"Tree planting upfront 50% claim #{claim_id}",
                    verified=True,
                )
            else:
                qoin_core.record_karma_action(
                    conn,
                    user_private_id=str(claim["user_private_id"]),
                    action_code=str(claim["action_code"]),
                    description=f"Council approved claim #{claim_id}",
                    verified=True,
                )
                upfront = amount
        conn.execute(
            """
            UPDATE karma_claims
            SET status = ?, council_reviewer = ?, council_comment = ?,
                reviewed_at = ?, amount_credited_upfront = ?
            WHERE id = ?
            """,
            (
                decision,
                pid,
                (payload.get("comment") or "").strip(),
                _now(),
                upfront,
                claim_id,
            ),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.post("/api/karma/claims/<int:claim_id>/followup")
    @login_required
    def api_karma_followup(claim_id: int):
        conn = get_db()
        pid = str(g.current_user["private_id"])
        claim = conn.execute(
            "SELECT * FROM karma_claims WHERE id = ? AND user_private_id = ?",
            (claim_id, pid),
        ).fetchone()
        if not claim:
            return jsonify({"error": "Claim not found"}), 404
        proof = _save_upload(request.files.get("proof"), KARMA_UPLOAD_DIR, pid)
        conn.execute(
            """
            UPDATE karma_claims
            SET followup_proof_path = ?, followup_status = 'pending_review'
            WHERE id = ?
            """,
            (proof, claim_id),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.post("/api/businesses/register")
    @login_required
    def api_business_register():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        payload = request.get_json(silent=True) or {}
        if not payload.get("terms_accepted"):
            return jsonify({"error": "Terms must be accepted"}), 400
        name = (payload.get("business_name") or "").strip()
        btype = (payload.get("business_type") or "").strip()
        if not name or not btype:
            return jsonify({"error": "business_name and business_type required"}), 400
        conn.execute(
            """
            INSERT INTO businesses (
                owner_private_id, business_name, business_type, address,
                gst_number, pan_number, village_id, status
            ) VALUES (?,?,?,?,?,?,?,'pending')
            """,
            (
                pid,
                name,
                btype,
                (payload.get("address") or "").strip(),
                (payload.get("gst_number") or "").strip() or None,
                (payload.get("pan_number") or "").strip() or None,
                _user_village_id(user),
            ),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.get("/api/businesses/mine")
    @login_required
    def api_business_mine():
        conn = get_db()
        row = _approved_business(conn, str(g.current_user["private_id"]))
        pending = conn.execute(
            """
            SELECT * FROM businesses
            WHERE owner_private_id = ?
            ORDER BY datetime(created_at) DESC LIMIT 1
            """,
            (str(g.current_user["private_id"]),),
        ).fetchone()
        return jsonify(
            {
                "approved": _user_row_dict(row) if row else None,
                "latest": _user_row_dict(pending) if pending else None,
            }
        )

    @bp.get("/api/businesses/pending")
    @login_required
    def api_business_pending():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        if not _is_council(conn, pid, vid):
            return jsonify({"error": "Village Council access required"}), 403
        rows = conn.execute(
            """
            SELECT b.*, u.public_id, u.first_name, u.last_name
            FROM businesses b
            JOIN users u ON u.private_id = b.owner_private_id
            WHERE b.village_id = ? AND b.status = 'pending'
            ORDER BY datetime(b.created_at) ASC
            """,
            (vid,),
        ).fetchall()
        return jsonify({"businesses": [_user_row_dict(r) for r in rows]})

    @bp.post("/api/businesses/<int:business_id>/review")
    @login_required
    def api_business_review(business_id: int):
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        if not _is_council(conn, pid, vid):
            return jsonify({"error": "Village Council access required"}), 403
        payload = request.get_json(silent=True) or {}
        status = (payload.get("status") or "").strip()
        if status not in {"approved", "rejected"}:
            return jsonify({"error": "status must be approved or rejected"}), 400
        conn.execute(
            """
            UPDATE businesses
            SET status = ?, approved_by = ?, approved_at = ?
            WHERE id = ? AND village_id = ?
            """,
            (status, pid, _now(), business_id, vid),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.get("/api/jobs")
    @login_required
    def api_jobs_list():
        conn = get_db()
        vid = _user_village_id(g.current_user)
        category = (request.args.get("category") or "").strip()
        job_type = (request.args.get("job_type") or "").strip()
        sql = """
            SELECT j.*, u.public_id AS employer_public_id,
                   u.first_name || ' ' || u.last_name AS employer_name
            FROM job_postings j
            JOIN users u ON u.private_id = j.employer_private_id
            WHERE j.location_village_id = ? AND j.status = 'open'
        """
        params: list[Any] = [vid]
        if category:
            sql += " AND j.category = ?"
            params.append(category)
        if job_type:
            sql += " AND j.job_type = ?"
            params.append(job_type)
        sql += " ORDER BY datetime(j.created_at) DESC LIMIT 100"
        return jsonify({"jobs": [_user_row_dict(r) for r in conn.execute(sql, params)]})

    @bp.post("/api/jobs")
    @login_required
    def api_job_create():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        biz = _approved_business(conn, pid)
        council = _is_council(conn, pid, vid)
        payload = request.get_json(silent=True) or {}
        employer_type = (payload.get("employer_type") or ("council" if council else "business")).strip()
        if employer_type == "business" and not biz:
            return jsonify({"error": "Approved business or Council role required"}), 403
        if employer_type == "council" and not council:
            return jsonify({"error": "Council role required for council postings"}), 403
        title = (payload.get("title") or "").strip()
        if not title:
            return jsonify({"error": "title required"}), 400
        try:
            salary = int(payload.get("salary_qoins") or 0)
        except (TypeError, ValueError):
            salary = 0
        conn.execute(
            """
            INSERT INTO job_postings (
                employer_private_id, employer_type, title, job_type, category,
                description, requirements, salary_qoins, salary_period,
                location_village_id, openings, deadline, status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'open')
            """,
            (
                pid,
                employer_type,
                title,
                (payload.get("job_type") or "Full-time").strip(),
                (payload.get("category") or "General").strip(),
                (payload.get("description") or "").strip(),
                (payload.get("requirements") or "").strip(),
                salary,
                (payload.get("salary_period") or "month").strip(),
                vid,
                int(payload.get("openings") or 1),
                (payload.get("deadline") or None),
            ),
        )
        conn.commit()
        return jsonify({"ok": True, "id": int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])})

    @bp.post("/api/jobs/<int:job_id>/apply")
    @login_required
    def api_job_apply(job_id: int):
        conn = get_db()
        pid = str(g.current_user["private_id"])
        job = conn.execute(
            "SELECT id FROM job_postings WHERE id = ? AND status = 'open'",
            (job_id,),
        ).fetchone()
        if not job:
            return jsonify({"error": "Job not found"}), 404
        conn.execute(
            """
            INSERT INTO job_applications (job_posting_id, applicant_private_id, status)
            VALUES (?, ?, 'pending')
            """,
            (job_id, pid),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.get("/api/jobs/<int:job_id>/applications")
    @login_required
    def api_job_applications(job_id: int):
        conn = get_db()
        pid = str(g.current_user["private_id"])
        job = conn.execute(
            "SELECT * FROM job_postings WHERE id = ?",
            (job_id,),
        ).fetchone()
        if not job or str(job["employer_private_id"]) != pid:
            return jsonify({"error": "Not allowed"}), 403
        rows = conn.execute(
            """
            SELECT a.*, u.public_id, u.first_name, u.last_name,
                   p.skills, p.experience, p.education, p.availability
            FROM job_applications a
            JOIN users u ON u.private_id = a.applicant_private_id
            LEFT JOIN job_seeker_profiles p ON p.user_private_id = a.applicant_private_id
            WHERE a.job_posting_id = ?
            ORDER BY datetime(a.applied_at) DESC
            """,
            (job_id,),
        ).fetchall()
        out = []
        for r in rows:
            d = _user_row_dict(r)
            d["skills"] = _json_load(str(r["skills"] or ""), [])
            d["experience"] = _json_load(str(r["experience"] or ""), [])
            d["education"] = _json_load(str(r["education"] or ""), [])
            out.append(d)
        return jsonify({"applications": out})

    @bp.post("/api/jobs/applications/<int:app_id>/status")
    @login_required
    def api_application_status(app_id: int):
        conn = get_db()
        pid = str(g.current_user["private_id"])
        payload = request.get_json(silent=True) or {}
        status = (payload.get("status") or "").strip()
        if status not in {"shortlisted", "rejected", "hired"}:
            return jsonify({"error": "Invalid status"}), 400
        app_row = conn.execute(
            """
            SELECT a.*, j.employer_private_id, j.title, j.salary_qoins, j.salary_period, j.id AS job_id
            FROM job_applications a
            JOIN job_postings j ON j.id = a.job_posting_id
            WHERE a.id = ?
            """,
            (app_id,),
        ).fetchone()
        if not app_row or str(app_row["employer_private_id"]) != pid:
            return jsonify({"error": "Not allowed"}), 403
        conn.execute(
            "UPDATE job_applications SET status = ? WHERE id = ?",
            (status, app_id),
        )
        if status == "hired":
            conn.execute(
                """
                INSERT INTO employment_contracts (
                    employer_private_id, employee_private_id, job_posting_id,
                    title, salary_qoins, salary_period, start_date, status
                ) VALUES (?,?,?,?,?,?,?, 'active')
                """,
                (
                    pid,
                    str(app_row["applicant_private_id"]),
                    int(app_row["job_id"]),
                    str(app_row["title"]),
                    int(app_row["salary_qoins"]),
                    str(app_row["salary_period"] or "month"),
                    date.today().isoformat(),
                ),
            )
            conn.execute(
                "UPDATE job_postings SET status = 'filled' WHERE id = ?",
                (int(app_row["job_id"]),),
            )
            if _send_system_message:
                _send_system_message(
                    conn,
                    str(app_row["applicant_private_id"]),
                    f"Hired: {app_row['title']}",
                    "Congratulations — the employer marked your application as hired.",
                )
        conn.commit()
        return jsonify({"ok": True})

    @bp.get("/api/jobs/seeker-profile")
    @login_required
    def api_seeker_profile_get():
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM job_seeker_profiles WHERE user_private_id = ?",
            (str(g.current_user["private_id"]),),
        ).fetchone()
        if not row:
            return jsonify({"profile": None})
        d = _user_row_dict(row)
        d["skills"] = _json_load(str(row["skills"] or ""), [])
        d["experience"] = _json_load(str(row["experience"] or ""), [])
        d["education"] = _json_load(str(row["education"] or ""), [])
        return jsonify({"profile": d})

    @bp.post("/api/jobs/seeker-profile")
    @login_required
    def api_seeker_profile_save():
        conn = get_db()
        pid = str(g.current_user["private_id"])
        payload = request.get_json(silent=True) or {}
        resume = _save_upload(request.files.get("resume"), RESUME_UPLOAD_DIR, pid)
        existing = conn.execute(
            "SELECT resume_path FROM job_seeker_profiles WHERE user_private_id = ?",
            (pid,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO job_seeker_profiles (
                user_private_id, skills, experience, education, availability, resume_path, updated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(user_private_id) DO UPDATE SET
                skills = excluded.skills,
                experience = excluded.experience,
                education = excluded.education,
                availability = excluded.availability,
                resume_path = COALESCE(excluded.resume_path, job_seeker_profiles.resume_path),
                updated_at = excluded.updated_at
            """,
            (
                pid,
                json.dumps(payload.get("skills") or []),
                json.dumps(payload.get("experience") or []),
                json.dumps(payload.get("education") or []),
                (payload.get("availability") or "").strip(),
                resume or (str(existing["resume_path"]) if existing else None),
                _now(),
            ),
        )
        conn.commit()
        return jsonify({"ok": True})

    @bp.get("/api/village/hub-status")
    @login_required
    def api_village_hub_status():
        conn = get_db()
        user = g.current_user
        pid = str(user["private_id"])
        vid = _user_village_id(user)
        council = _is_council(conn, pid, vid)
        biz = conn.execute(
            "SELECT status FROM businesses WHERE owner_private_id = ? ORDER BY id DESC LIMIT 1",
            (pid,),
        ).fetchone()
        return jsonify(
            {
                "village_id": vid,
                "is_council": council,
                "business_status": str(biz["status"]) if biz else None,
                "marketplace_url": url_for("marketplace_page"),
                "job_portal_url": url_for("job_portal_page"),
            }
        )

    app.register_blueprint(bp)
