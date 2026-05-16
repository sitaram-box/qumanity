#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


DB_PATH = Path("indiaq.db")
BACKUP_PATH = Path("indiaq_backup.db")
PREFIX = "0.राम|"

# Parent -> child order is implied by this list.
TABLE_ORDER = ["global", "zone", "state", "district", "tehsil", "village"]

# Hardcoded FK relationships requested by the prompt.
FK_COLUMNS: dict[str, list[str]] = {
    "zone": [],
    "state": ["zone_id"],
    "district": ["state_id"],
    "tehsil": ["district_id"],
    "village": ["tehsil_id"],
    "global": [],
}


def quote_ident(name: str) -> str:
    """Safely quote SQLite identifiers."""
    return '"' + name.replace('"', '""') + '"'


def create_backup(source_db: Path, backup_db: Path) -> None:
    if not source_db.exists():
        raise FileNotFoundError(f"Database not found: {source_db.resolve()}")

    # Overwrite old backup so the latest run always has a predictable filename.
    if backup_db.exists():
        backup_db.unlink()

    src_conn = sqlite3.connect(str(source_db))
    try:
        dst_conn = sqlite3.connect(str(backup_db))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def get_existing_target_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = ? AND name IN (?, ?, ?, ?, ?, ?)
        """,
        ("table", "global", "zone", "state", "district", "tehsil", "village"),
    )
    existing = {row[0] for row in cur.fetchall()}
    return [table for table in TABLE_ORDER if table in existing]


def get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({quote_ident(table)})")
    # PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
    return {row[1] for row in cur.fetchall()}


def apply_prefix_updates(conn: sqlite3.Connection, tables: list[str]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}

    # Disable FK checks temporarily to avoid transient violations
    # while parent and child keys are being rewritten.
    conn.execute("PRAGMA foreign_keys = OFF")

    for table in tables:
        cols = get_table_columns(conn, table)
        table_summary: dict[str, int] = {"id": 0}

        if "id" in cols:
            sql = (
                f"UPDATE {quote_ident(table)} "
                f"SET {quote_ident('id')} = ? || {quote_ident('id')} "
                f"WHERE {quote_ident('id')} IS NOT NULL "
                f"AND {quote_ident('id')} NOT LIKE ?"
            )
            cur = conn.execute(sql, (PREFIX, f"{PREFIX}%"))
            table_summary["id"] = cur.rowcount if cur.rowcount is not None else 0

        for fk_col in FK_COLUMNS.get(table, []):
            if fk_col not in cols:
                continue
            sql = (
                f"UPDATE {quote_ident(table)} "
                f"SET {quote_ident(fk_col)} = ? || {quote_ident(fk_col)} "
                f"WHERE {quote_ident(fk_col)} IS NOT NULL "
                f"AND {quote_ident(fk_col)} NOT LIKE ?"
            )
            cur = conn.execute(sql, (PREFIX, f"{PREFIX}%"))
            table_summary[fk_col] = cur.rowcount if cur.rowcount is not None else 0

        conn.commit()
        summary[table] = table_summary

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    return summary


def print_summary(summary: dict[str, dict[str, int]]) -> None:
    print("Update summary:")
    for table in TABLE_ORDER:
        if table not in summary:
            continue
        parts = [f"id={summary[table].get('id', 0)}"]
        for fk_col in FK_COLUMNS.get(table, []):
            if fk_col in summary[table]:
                parts.append(f"{fk_col}={summary[table][fk_col]}")
        print(f"  {table}: " + ", ".join(parts))


def main() -> None:
    try:
        create_backup(DB_PATH, BACKUP_PATH)
        print(f"Backup created: {BACKUP_PATH.resolve()}")

        conn = sqlite3.connect(str(DB_PATH))
        try:
            # Ensure sqlite3 returns Python str for TEXT with Unicode intact.
            conn.text_factory = str

            tables = get_existing_target_tables(conn)
            if not tables:
                print("No target tables found (global/zone/state/district/tehsil/village).")
                return

            summary = apply_prefix_updates(conn, tables)
            print_summary(summary)
        finally:
            conn.close()
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
