#!/usr/bin/env python3
"""
Diagnose and repair admin login (HU-014918240 / P@y#umans123).

  python scripts/fix_admin_login.py
  railway run python scripts/fix_admin_login.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import admin_login_repair


def main() -> int:
    print(admin_login_repair.format_repair_log(
        {"ok": False, "message": "starting…", "login_verified": False}
    ))
    status = admin_login_repair.run_repair(reset_password=True, force=True)
    print(admin_login_repair.format_repair_log(status))
    if status.get("diagnosis"):
        print("\nAdmins in DB:", len(status["diagnosis"].get("admins") or []))
    return 0 if status.get("ok") and status.get("login_verified") else 1


if __name__ == "__main__":
    sys.exit(main())
