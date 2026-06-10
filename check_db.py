#!/usr/bin/env python3
"""Database connectivity diagnostic for Qumanity.

Mirrors the path-resolution logic in app.py (including .env loading and the
SQLite slash convention) so the path it reports is exactly the one the app will
use. Read-only: it never creates or modifies the database.

Run:
    cd /Users/macmudgal/Desktop/quantum_box
    python3 check_db.py
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from urllib.parse import unquote

BASE_DIR = Path(__file__).resolve().parent


def _load_env() -> None:
    """Load .env exactly like config.py does (no error if dotenv is missing)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("   (python-dotenv not installed; reading OS environment only)")
        return
    env_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=env_path if env_path.is_file() else None)


def resolve_sqlite_path(base_dir: Path) -> Path:
    """Same logic as app._resolve_sqlite_path."""
    default = base_dir / "indiaq.db"
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url or url.startswith("postgres"):
        return default
    if url.startswith("sqlite:"):
        raw = unquote(url[len("sqlite://"):])
        if raw.startswith("//"):
            candidate = Path(raw[1:])
        else:
            candidate = Path(raw.lstrip("/"))
    else:
        candidate = Path(url)
    text = str(candidate).strip()
    if not text or text == ".":
        return default
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate


def main() -> None:
    print("=== Qumanity — Database Diagnostic ===\n")

    print(f"Current directory: {os.getcwd()}")
    print(f"Script directory:  {BASE_DIR}")

    print("\n--- Environment ---")
    _load_env()
    print(f"DATABASE_URL: {os.environ.get('DATABASE_URL', '(not set)')}")

    db_path = resolve_sqlite_path(BASE_DIR)
    print(f"\nResolved DB path the app will use: {db_path}")
    print(f"   Absolute: {db_path.is_absolute()}")

    if db_path.exists():
        size = db_path.stat().st_size
        print(f"   [OK] File exists ({size} bytes)")
        print(f"   Readable: {os.access(db_path, os.R_OK)}")
        print(f"   Writable: {os.access(db_path, os.W_OK)}")
    else:
        print("   [WARN] File does NOT exist at the resolved path.")
        also = BASE_DIR / "indiaq.db"
        if also.exists() and also != db_path:
            print(f"   But a database DOES exist at: {also}")
            print("   -> Your DATABASE_URL is pointing somewhere else.")

    parent = db_path.parent
    print(f"\n--- Parent directory: {parent} ---")
    print(f"   Exists:     {parent.exists()}")
    print(f"   Readable:   {os.access(parent, os.R_OK)}")
    print(f"   Writable:   {os.access(parent, os.W_OK)}")
    print(f"   Executable: {os.access(parent, os.X_OK)}")

    print("\n--- WAL / SHM sidecar files ---")
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        print(f"   {sidecar.name}: {'present' if sidecar.exists() else 'absent'}")

    print("\n--- SQLite connection test (read-only) ---")
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        version = cur.execute("SELECT sqlite_version();").fetchone()[0]
        print(f"   [OK] Connected. SQLite version: {version}")
        tables = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t[0] for t in tables]
        print(f"   Tables found: {len(names)}")
        for key in ("users", "state", "district", "tehsil", "village"):
            print(f"      {key:<10} {'present' if key in names else 'MISSING'}")
        conn.close()
    except Exception as exc:  # noqa: BLE001 - diagnostic wants the raw message
        print(f"   [FAIL] {type(exc).__name__}: {exc}")
        print("   Tip: if DATABASE_URL uses three slashes (sqlite:///indiaq.db)")
        print("        it is now treated as RELATIVE to the project root.")
        print("        For an absolute path use four slashes:")
        print("        sqlite:////Users/macmudgal/Desktop/quantum_box/indiaq.db")

    print("\n=== Diagnostic complete ===")


if __name__ == "__main__":
    main()
