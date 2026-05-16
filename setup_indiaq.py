#!/usr/bin/env python3
"""Restore indiaq.db from the backup and apply the 0.राम| prefix to every id.

The Flask prototype expects `indiaq.db` to exist with prefixed location ids
(e.g. ``0.राम|IND/CS.DL``). The committed snapshot in this repo is
``indiaq_backup.db`` and stores plain ids. Running this script once is enough
to bring the file system into the state the app expects.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

BACKUP = Path("indiaq_backup.db")
TARGET = Path("indiaq.db")
PREFIX = "0.राम|"
TABLES = ("zone", "state", "district", "tehsil", "village")


def main() -> None:
    if not BACKUP.exists():
        raise SystemExit(f"Backup not found: {BACKUP.resolve()}")

    shutil.copyfile(BACKUP, TARGET)
    print(f"Copied {BACKUP} -> {TARGET}")

    conn = sqlite3.connect(TARGET)
    conn.text_factory = str
    try:
        for table in TABLES:
            cur = conn.execute(
                f'UPDATE "{table}" SET id = ? || id '
                f"WHERE id IS NOT NULL AND id NOT LIKE ?",
                (PREFIX, f"{PREFIX}%"),
            )
            print(f"  {table}: prefixed {cur.rowcount} rows")
        conn.commit()
    finally:
        conn.close()

    print("indiaq.db is ready.")


if __name__ == "__main__":
    main()
