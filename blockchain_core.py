"""Idempotent blockchain-ready schema migrations (Phase 2 stubs)."""

from __future__ import annotations

import sqlite3

BLOCKCHAIN_SYNC_DDL = """
CREATE TABLE IF NOT EXISTS blockchain_sync (
    id INTEGER PRIMARY KEY,
    last_processed_block INTEGER DEFAULT 0,
    last_sync_timestamp INTEGER DEFAULT 0,
    chain_name TEXT DEFAULT 'polygon',
    sync_status TEXT DEFAULT 'idle'
);
"""


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _cols(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, col: str, decl: str) -> None:
    if col in _cols(conn, table):
        return
    try:
        conn.execute(f"ALTER TABLE [{table}] ADD COLUMN {col} {decl}")
    except sqlite3.OperationalError:
        pass


def migrate_blockchain_schema(conn: sqlite3.Connection) -> None:
    """Add blockchain hash columns and sync table if missing."""
    conn.executescript(BLOCKCHAIN_SYNC_DDL)

    if _table_exists(conn, "blockchain_sync"):
        row = conn.execute("SELECT COUNT(*) FROM blockchain_sync").fetchone()
        if row and int(row[0]) == 0:
            conn.execute(
                """
                INSERT INTO blockchain_sync (
                    last_processed_block, last_sync_timestamp, chain_name, sync_status
                ) VALUES (0, 0, 'polygon', 'idle')
                """
            )

    for col, decl in (
        ("blockchain_user_hash", "TEXT DEFAULT NULL"),
        ("user_registration_tx_hash", "TEXT DEFAULT NULL"),
        ("last_sync_block", "INTEGER DEFAULT 0"),
        ("identity_commitment", "TEXT DEFAULT NULL"),
        ("karma_points", "INTEGER NOT NULL DEFAULT 0"),
    ):
        _add_column(conn, "users", col, decl)

    for col, decl in (
        ("content_hash", "TEXT DEFAULT NULL"),
        ("blockchain_timestamp", "INTEGER DEFAULT NULL"),
        ("transaction_hash", "TEXT DEFAULT NULL"),
        ("author_signature", "TEXT DEFAULT NULL"),
    ):
        _add_column(conn, "posts", col, decl)

    # Project uses post_votes (not votes)
    for col, decl in (
        ("vote_hash", "TEXT DEFAULT NULL"),
        ("transaction_hash", "TEXT DEFAULT NULL"),
        ("commitment_hash", "TEXT DEFAULT NULL"),
    ):
        _add_column(conn, "post_votes", col, decl)

    # Project uses qoin_transactions for karma point ledger
    for col, decl in (
        ("blockchain_tx_hash", "TEXT DEFAULT NULL"),
        ("commitment_reveal", "TEXT DEFAULT NULL"),
        ("nullifier_hash", "TEXT DEFAULT NULL"),
    ):
        _add_column(conn, "qoin_transactions", col, decl)

    # Project uses election_cycles (not elections)
    for col, decl in (
        ("election_contract_address", "TEXT DEFAULT NULL"),
        ("tally_hash", "TEXT DEFAULT NULL"),
        ("blockchain_proposal_id", "INTEGER DEFAULT NULL"),
    ):
        _add_column(conn, "election_cycles", col, decl)

    conn.commit()
