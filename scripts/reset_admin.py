#!/usr/bin/env python3
"""
Complete admin reset — delete all admins and create HU-014918240.

  python scripts/reset_admin.py
  railway run python scripts/reset_admin.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import admin_login_repair


def main() -> int:
    status = admin_login_repair.run_reset()
    print(admin_login_repair.format_reset_log(status))
    return 0 if status.get("ok") and status.get("login_verified") else 1


if __name__ == "__main__":
    sys.exit(main())
