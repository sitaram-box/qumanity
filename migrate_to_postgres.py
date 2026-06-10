#!/usr/bin/env python3
"""
Migrate Qumanity SQLite database to PostgreSQL for CRM integration.

Usage (from project root):
    pip install psycopg2-binary python-dotenv
    python3 migrate_to_postgres.py

Environment (see .env.example):
    DB_HOST, DB_PORT, DB_DATABASE, DB_USER, DB_PASSWORD
    SQLITE_PATH or SQLITE_DB_PATH  (default: ./indiaq.db)

On macOS with Homebrew PostgreSQL, the default superuser is usually your
macOS login name — not 'postgres'. Set DB_USER in .env accordingly.
"""

from __future__ import annotations

import getpass
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = Path(
    os.getenv("SQLITE_PATH")
    or os.getenv("SQLITE_DB_PATH")
    or BASE_DIR / "indiaq.db"
)

# Order matters for FK dependencies (best-effort; missing tables are skipped).
TABLES = [
    "users",
    "wallets",
    "posts",
    "post_votes",
    "messages",
    "election_cycles",
    "election_candidates",
    "election_votes",
    "family_members",
    "family_relationships",
    "connection_requests",
    "pending_transactions",
    "weekly_statements",
    "registration_donations",
    "wallet_paise_ledger",
    "volunteers",
    "referral_agents",
    "donation_distributions",
    "donation_transactions",
    "karma_action_types",
    "karma_transactions",
    "leadership_council",
    "location_translations",
    "state_languages",
]

# Explicit PostgreSQL DDL for tables with composite keys or non-standard shapes.
TABLE_OVERRIDES: dict[str, str] = {
    "wallet_paise_ledger": """
        CREATE TABLE IF NOT EXISTS wallet_paise_ledger (
            wallet_type TEXT NOT NULL,
            wallet_id TEXT NOT NULL,
            balance_paise BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (wallet_type, wallet_id)
        )
    """,
}

CRM_DDL = """
CREATE TABLE IF NOT EXISTS crm_staff (
    id SERIAL PRIMARY KEY,
    private_id TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('agent', 'manager', 'leader', 'admin')),
    tehsil_id TEXT,
    district_id TEXT,
    state_id TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crm_ticket_updates (
    id SERIAL PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    resolution_notes TEXT,
    satisfaction_rating INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    ticket_id TEXT UNIQUE NOT NULL,
    subject TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open',
    assigned_to TEXT,
    assigned_to_name TEXT,
    created_by TEXT NOT NULL,
    created_by_name TEXT NOT NULL,
    created_by_type TEXT DEFAULT 'citizen',
    tehsil_id TEXT,
    district_id TEXT,
    state_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolution_time_seconds INTEGER,
    satisfaction_rating INTEGER
);

CREATE TABLE IF NOT EXISTS ticket_comments (
    id SERIAL PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    author_id TEXT,
    author_name TEXT,
    author_role TEXT,
    message TEXT NOT NULL,
    is_internal BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vendors (
    vendor_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    business_type TEXT,
    gst_number TEXT,
    address TEXT,
    tehsil_id TEXT,
    verification_status TEXT DEFAULT 'pending',
    verified_by TEXT,
    verified_at TIMESTAMP,
    average_rating DOUBLE PRECISION DEFAULT 0,
    total_ratings INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    vendor_id TEXT,
    name TEXT NOT NULL,
    description TEXT,
    price INTEGER NOT NULL,
    unit TEXT DEFAULT 'kg',
    stock_available INTEGER DEFAULT 0,
    is_available BOOLEAN DEFAULT TRUE,
    image_url TEXT,
    category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_id TEXT UNIQUE NOT NULL,
    buyer_private_id TEXT,
    buyer_name TEXT NOT NULL,
    buyer_address TEXT,
    buyer_tehsil_id TEXT,
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    subtotal INTEGER NOT NULL,
    delivery_charge INTEGER DEFAULT 0,
    total_amount INTEGER NOT NULL,
    delivery_agent_id TEXT,
    delivery_agent_name TEXT,
    order_status TEXT DEFAULT 'pending',
    payment_status TEXT DEFAULT 'pending',
    payment_method TEXT DEFAULT 'qoins',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ratings (
    id SERIAL PRIMARY KEY,
    order_id TEXT,
    rater_private_id TEXT,
    rated_private_id TEXT,
    rating_type TEXT NOT NULL,
    rating_value INTEGER CHECK (rating_value >= 1 AND rating_value <= 5),
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tickets_tehsil ON tickets(tehsil_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_orders_tehsil ON orders(buyer_tehsil_id);
CREATE INDEX IF NOT EXISTS idx_vendors_tehsil ON vendors(tehsil_id);
"""

PERFORMANCE_INDEXES = [
    'CREATE INDEX IF NOT EXISTS idx_users_private_id ON users(private_id)',
    'CREATE INDEX IF NOT EXISTS idx_users_location ON users(current_location_id)',
    'CREATE INDEX IF NOT EXISTS idx_wallets_owner ON wallets(owner_type, owner_id)',
    'CREATE INDEX IF NOT EXISTS idx_tickets_tehsil ON tickets(tehsil_id)',
    'CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets(assigned_to)',
    'CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_private_id)',
    'CREATE INDEX IF NOT EXISTS idx_orders_tehsil ON orders(buyer_tehsil_id)',
    'CREATE INDEX IF NOT EXISTS idx_wallet_paise ON wallet_paise_ledger(wallet_type, wallet_id)',
]


def _macos_user() -> str:
    return os.getenv("USER") or os.getenv("LOGNAME") or getpass.getuser()


def _connection_configs() -> list[dict[str, str]]:
    """Build ordered list of PostgreSQL connection attempts."""
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "5432")
    database = os.getenv("DB_DATABASE", "qumanity_crm")
    env_user = os.getenv("DB_USER", "").strip()
    env_password = os.getenv("DB_PASSWORD", "")
    mac_user = _macos_user()

    configs: list[dict[str, str]] = []

    def add(label: str, user: str, password: str, db: str | None = None) -> None:
        if not user:
            return
        configs.append(
            {
                "_label": label,
                "host": host,
                "port": port,
                "database": db or database,
                "user": user,
                "password": password,
            }
        )

    if env_user:
        add(".env (DB_USER)", env_user, env_password)
    add(f"macOS user ({mac_user})", mac_user, "")
    add("postgres user", "postgres", env_password or os.getenv("POSTGRES_PASSWORD", "postgres"))
    if host == "localhost":
        add(f"macOS user via 127.0.0.1 ({mac_user})", mac_user, "")

    seen: set[tuple[str, str, str, str]] = set()
    unique: list[dict[str, str]] = []
    for cfg in configs:
        key = (cfg["host"], cfg["port"], cfg["database"], cfg["user"])
        if key not in seen:
            seen.add(key)
            unique.append(cfg)
    return unique


def pg_connect():
    """
    Connect to PostgreSQL, trying several common macOS / Homebrew configurations.
    Returns (connection, config_used).
    """
    import psycopg2
    from psycopg2 import OperationalError

    configs = _connection_configs()
    if not configs:
        raise RuntimeError("No PostgreSQL connection configs available.")

    last_error: Exception | None = None
    for i, raw in enumerate(configs, 1):
        label = raw.get("_label", f"config {i}")
        connect_kwargs = {k: v for k, v in raw.items() if not k.startswith("_")}
        user = connect_kwargs["user"]
        db = connect_kwargs["database"]
        print(f"Trying connection {i}: {label} (user={user}, db={db})")
        try:
            conn = psycopg2.connect(**connect_kwargs)
            print(f"  Connected successfully as '{user}'")
            return conn, connect_kwargs
        except OperationalError as exc:
            last_error = exc
            err = str(exc).lower()
            print(f"  Failed: {exc}")
            if "does not exist" in err and db not in ("postgres", "template1"):
                try:
                    ensure_database_exists(connect_kwargs)
                    conn = psycopg2.connect(**connect_kwargs)
                    print(f"  Connected after creating database '{db}'")
                    return conn, connect_kwargs
                except Exception as create_exc:
                    last_error = create_exc
                    print(f"  Could not create database: {create_exc}")

    raise RuntimeError(
        "Could not connect to PostgreSQL.\n\n"
        "Common fixes on macOS (Homebrew):\n"
        "  1. Start PostgreSQL:  brew services start postgresql@15\n"
        "  2. Create database:     createdb qumanity_crm\n"
        "  3. Set .env DB_USER to your macOS username (run: whoami)\n"
        f"Last error: {last_error}"
    )


def ensure_database_exists(config: dict[str, str]) -> None:
    """Create target database if missing (requires superuser)."""
    import psycopg2
    from psycopg2 import OperationalError
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    target_db = config["database"]
    admin_cfg = {**config, "database": "postgres"}
    try:
        conn = psycopg2.connect(**admin_cfg)
    except OperationalError:
        admin_cfg["database"] = "template1"
        conn = psycopg2.connect(**admin_cfg)

    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
    if not cur.fetchone():
        print(f"Database '{target_db}' not found — creating…")
        cur.execute(f'CREATE DATABASE "{target_db}"')
        print(f"  Created database '{target_db}'")
    cur.close()
    conn.close()


def sqlite_type_to_pg(sqlite_type: str) -> str:
    t = (sqlite_type or "TEXT").upper()
    if "INT" in t:
        return "BIGINT"
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return "DOUBLE PRECISION"
    if "BLOB" in t:
        return "BYTEA"
    if "BOOL" in t:
        return "BOOLEAN"
    return "TEXT"


def pg_table_exists(pg_cur, table: str) -> bool:
    pg_cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = %s)",
        (table,),
    )
    return bool(pg_cur.fetchone()[0])


def sqlite_table_names(sqlite_cur) -> list[str]:
    sqlite_cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in sqlite_cur.fetchall()]


def ensure_pg_table(
    pg_cur,
    table: str,
    columns_meta: list[tuple],
    *,
    force_recreate: bool = False,
) -> None:
    """
    Create PostgreSQL table from SQLite PRAGMA metadata.

    Handles composite primary keys (e.g. wallet_paise_ledger) and explicit
    TABLE_OVERRIDES for known edge cases.
    """
    if force_recreate and pg_table_exists(pg_cur, table):
        pg_cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')

    if pg_table_exists(pg_cur, table):
        return

    if table in TABLE_OVERRIDES:
        pg_cur.execute(TABLE_OVERRIDES[table])
        print(f"  created {table} (override DDL)")
        return

    pk_cols = [row[1] for row in columns_meta if row[5]]
    col_defs: list[str] = []

    for _cid, name, ctype, notnull, _default_val, pk in columns_meta:
        pg_type = sqlite_type_to_pg(ctype)
        nn = " NOT NULL" if notnull else ""

        if len(pk_cols) == 1 and pk and name == pk_cols[0]:
            if "INT" in (ctype or "").upper():
                col_defs.append(f'"{name}" SERIAL PRIMARY KEY')
            else:
                col_defs.append(f'"{name}" {pg_type} PRIMARY KEY')
        elif len(pk_cols) > 1 and pk:
            col_defs.append(f'"{name}" {pg_type}{nn}')
        else:
            col_defs.append(f'"{name}" {pg_type}{nn}')

    if len(pk_cols) > 1:
        pk_list = ", ".join(f'"{c}"' for c in pk_cols)
        col_defs.append(f"PRIMARY KEY ({pk_list})")

    ddl = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(col_defs)})'
    pg_cur.execute(ddl)


def migrate_table(
    sqlite_cur,
    pg_cur,
    pg_conn,
    table: str,
    *,
    force_recreate: bool = False,
) -> int:
    sqlite_cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    if not sqlite_cur.fetchone():
        print(f"  skip {table} (not in SQLite)")
        return 0

    sqlite_cur.execute(f"PRAGMA table_info({table})")
    meta = sqlite_cur.fetchall()
    if not meta:
        return 0

    ensure_pg_table(pg_cur, table, meta, force_recreate=force_recreate)
    pg_conn.commit()

    columns = [row[1] for row in meta]
    quoted = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))

    sqlite_cur.execute(f'SELECT {", ".join(columns)} FROM "{table}"')
    rows = sqlite_cur.fetchall()
    if not rows:
        print(f"  {table}: 0 rows")
        return 0

    inserted = 0
    for row in rows:
        values = [row[c] for c in columns]
        try:
            pg_cur.execute(
                f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                values,
            )
            inserted += pg_cur.rowcount
        except Exception as exc:
            pg_conn.rollback()
            print(f"  WARN row in {table}: {exc}")
            continue
    pg_conn.commit()
    print(f"  {table}: migrated {len(rows)} rows ({inserted} inserted)")
    return len(rows)


def create_performance_indexes(pg_cur, pg_conn) -> None:
    print("\nCreating performance indexes…")
    for index_sql in PERFORMANCE_INDEXES:
        try:
            pg_cur.execute(index_sql)
            pg_conn.commit()
        except Exception as exc:
            pg_conn.rollback()
            print(f"  index skipped: {exc}")


def table_row_count(pg_cur, table: str) -> int | None:
    try:
        pg_cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        return int(pg_cur.fetchone()[0])
    except Exception:
        return None


def print_setup_help() -> None:
    mac_user = _macos_user()
    print(
        f"""
PostgreSQL setup:
  brew services start postgresql@15
  createdb qumanity_crm
  DB_USER={mac_user} DB_PASSWORD= python3 migrate_to_postgres.py
"""
    )


def main() -> int:
    print("=" * 60)
    print("Qumanity SQLite → PostgreSQL Migration")
    print("=" * 60)

    if not SQLITE_PATH.is_file():
        print(f"ERROR: SQLite database not found at {SQLITE_PATH}")
        return 1

    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("ERROR: pip install psycopg2-binary")
        return 1

    print(f"SQLite: {SQLITE_PATH}")

    try:
        sqlite_conn = sqlite3.connect(SQLITE_PATH)
        sqlite_conn.row_factory = sqlite3.Row
        sqlite_cur = sqlite_conn.cursor()
        print("Connected to SQLite")
    except Exception as exc:
        print(f"Failed to connect to SQLite: {exc}")
        return 1

    try:
        pg_conn, used_config = pg_connect()
    except Exception as exc:
        print(f"\nFailed to connect to PostgreSQL:\n{exc}")
        print_setup_help()
        return 1

    pg_cur = pg_conn.cursor()

    print("\nCreating CRM tables…")
    pg_cur.execute(CRM_DDL)
    pg_conn.commit()

    print("\nMigrating Qumanity tables…")
    for table in TABLES:
        print(f"→ {table}")
        force = table == "wallet_paise_ledger"
        migrate_table(sqlite_cur, pg_cur, pg_conn, table, force_recreate=force)

    create_performance_indexes(pg_cur, pg_conn)

    pg_cur.close()
    pg_conn.close()
    sqlite_conn.close()

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)
    user = used_config.get("user", "")
    db = used_config.get("database", "qumanity_crm")
    print(f"\nDATABASE_URL=postgresql://{user}@127.0.0.1:5432/{db}")
    print("Next: python3 complete_migration.py  (if any tables were skipped)")
    print("      python3 verify_integration.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
