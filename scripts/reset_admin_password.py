#!/usr/bin/env python3
"""Reset H_U_ADMIN password to Admin123."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ensure_admin import ensure_admin

if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else None
    if db:
        ensure_admin(db, reset_password=True)
    else:
        ensure_admin(reset_password=True)
