#!/usr/bin/env python3
"""
Verify Qumanity ↔ CRM integration.

Run: python3 verify_integration.py

Checks:
  1. PostgreSQL connection and key table row counts
  2. Flask app reachable
  3. CRM (NocoBase) reachable
  4. JWT encode/decode + CRM API auth (when CRM is running)
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

from migrate_to_postgres import pg_connect, table_row_count  # noqa: E402

FLASK_URL = os.getenv("FLASK_URL", f"http://127.0.0.1:{os.getenv('PORT', os.getenv('FLASK_RUN_PORT', '5001'))}")
CRM_URL = os.getenv("CRM_API_URL", "http://localhost:3000/api").rstrip("/").rsplit("/api", 1)[0]
JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY", "dev")

KEY_TABLES = [
    "users",
    "wallets",
    "wallet_paise_ledger",
    "tickets",
    "vendors",
    "orders",
    "ratings",
    "pending_transactions",
    "connection_requests",
    "election_cycles",
]


def check_postgres() -> bool:
    print("\nChecking PostgreSQL…")
    try:
        conn, cfg = pg_connect()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        tables = [row[0] for row in cur.fetchall()]
        print(f"  Connected as {cfg.get('user')} → {cfg.get('database')}")
        print(f"  Tables found: {len(tables)}")

        for table in KEY_TABLES:
            count = table_row_count(cur, table)
            if count is None:
                print(f"    - {table}: (missing)")
            else:
                print(f"    - {table}: {count} rows")

        cur.close()
        conn.close()
        return True
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return False


def check_http(name: str, url: str, ok_statuses: tuple[int, ...] = (200, 302, 401, 403)) -> bool:
    print(f"\nChecking {name}…")
    try:
        import requests
    except ImportError:
        print("  SKIP: pip install requests")
        return False

    try:
        resp = requests.get(url, timeout=5, allow_redirects=True)
        if resp.status_code in ok_statuses:
            print(f"  OK: {url} → HTTP {resp.status_code}")
            return True
        print(f"  WARN: {url} → HTTP {resp.status_code}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"  FAIL: {name} not reachable at {url}")
        return False
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return False


def check_jwt_local() -> bool:
    print("\nTesting JWT (local encode/decode)…")
    try:
        import jwt_auth
    except ImportError as exc:
        print(f"  FAIL: {exc}")
        return False

    sample_user = {
        "private_id": "TEST_USER",
        "first_name": "Test",
        "last_name": "Admin",
        "is_admin": 1,
        "account_type": "H_U_ADMIN",
        "current_location_id": "VIL001",
    }
    try:
        token = jwt_auth.generate_jwt(sample_user)
        payload = jwt_auth.decode_jwt(token)
        role = payload.get("role")
        print(f"  OK: token issued, role={role}")
        return True
    except Exception as exc:
        print(f"  FAIL: {exc}")
        if not JWT_SECRET or JWT_SECRET == "dev":
            print("  Hint: set JWT_SECRET in .env")
        return False


def check_jwt_crm() -> bool:
    print("\nTesting JWT with CRM API…")
    try:
        import requests
        import jwt_auth
    except ImportError:
        print("  SKIP: requests / jwt_auth not available")
        return False

    sample_user = {
        "private_id": "TEST_AGENT",
        "first_name": "CRM",
        "last_name": "Agent",
        "is_admin": 0,
        "account_type": "AGENT",
        "current_location_id": "TEH001",
        "tehsil_id": "TEH001",
    }
    token = jwt_auth.generate_jwt(sample_user)
    headers = {"Authorization": f"Bearer {token}"}

    try:
        resp = requests.get(f"{CRM_URL}/api/tickets", headers=headers, timeout=5)
        if resp.status_code == 200:
            print("  OK: CRM accepted JWT token")
            return True
        if resp.status_code == 401:
            print("  FAIL: CRM rejected JWT — check JWT_SECRET matches in both .env files")
            return False
        print(f"  WARN: CRM returned HTTP {resp.status_code}")
        return resp.status_code < 500
    except requests.exceptions.ConnectionError:
        print(f"  SKIP: CRM not running at {CRM_URL}")
        print("  Start: cd crm/qumanity-crm && nocobase dev")
        return False
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return False


def check_flask_crm_routes() -> bool:
    print("\nChecking Flask CRM routes…")
    try:
        import requests
    except ImportError:
        return False

    url = f"{FLASK_URL.rstrip('/')}/api/crm/ticket-updates"
    try:
        resp = requests.get(url, timeout=5, allow_redirects=False)
        if resp.status_code in (401, 302):
            print("  OK: /api/crm/ticket-updates exists (auth required)")
            return True
        if resp.status_code == 200:
            print("  OK: /api/crm/ticket-updates reachable")
            return True
        print(f"  WARN: unexpected status {resp.status_code}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"  SKIP: Flask not running at {FLASK_URL}")
        return False
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return False


def main() -> int:
    print("=" * 60)
    print("Qumanity-CRM Integration Verification")
    print("=" * 60)
    print(f"Flask URL: {FLASK_URL}")
    print(f"CRM URL:   {CRM_URL}")

    results: list[tuple[str, bool]] = [
        ("PostgreSQL", check_postgres()),
        ("Flask app", check_http("Flask", FLASK_URL)),
        ("CRM app", check_http("CRM", CRM_URL)),
        ("JWT local", check_jwt_local()),
        ("Flask CRM routes", check_flask_crm_routes()),
        ("JWT → CRM", check_jwt_crm()),
    ]

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    for name, ok in results:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}")

    required = [results[0], results[3]]  # PostgreSQL + JWT local
    optional = [results[1], results[2], results[4], results[5]]
    core_ok = all(ok for _, ok in required)
    all_ok = all(ok for _, ok in results)

    if all_ok:
        print("\nAll systems ready!")
        print("  1. Qumanity:  ", FLASK_URL)
        print("  2. CRM:       ", CRM_URL)
        print("  3. Get token: GET /api/auth/crm-token (after Flask login)")
    elif core_ok:
        print("\nCore database migration OK.")
        print("Start services for full integration test:")
        print("  python3 app.py")
        print("  cd crm/qumanity-crm && nocobase dev")
        print("  python3 verify_integration.py")
    else:
        print("\nSome core checks failed:")
        print("  brew services start postgresql@15")
        print("  python3 complete_migration.py")
        print("  Set JWT_SECRET in .env")

    return 0 if core_ok else 1


if __name__ == "__main__":
    sys.exit(main())
