#!/usr/bin/env python3
"""Auto-run admin migration when imported (optional app startup hook)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

script_path = ROOT / "scripts" / "migrate_admin_fix.py"
spec = importlib.util.spec_from_file_location("migrate_admin_fix", script_path)
if spec and spec.loader:
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.run_migration_with_status(reset_password=True, force=False)
    print("Auto-migration:", result.get("message") or ("ok" if result.get("ok") else "failed"))
else:
    print("Auto-migration: could not load migrate_admin_fix.py")
