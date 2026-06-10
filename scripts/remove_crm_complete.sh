#!/usr/bin/env bash
# Remove all NocoBase / CRM components from quantum_box.
# Run from anywhere:  bash scripts/remove_crm_complete.sh
set -euo pipefail

ROOT="/Users/macmudgal/Desktop/quantum_box"
cd "$ROOT"

echo "============================================================"
echo " Removing All CRM / NocoBase Components"
echo "============================================================"

# ── 1. Stop Docker containers & volumes ─────────────────────────────────────
echo ""
echo "[1/6] Stopping CRM Docker stack..."
docker compose -f docker-compose.nocobase.yml down -v 2>/dev/null || true
docker compose -f docker-compose.crm.yml down -v 2>/dev/null || true
docker rm -f qumanity_postgres qumanity_nocobase 2>/dev/null || true
docker volume rm quantum_box_postgres_data quantum_box_nocobase_data 2>/dev/null || true
docker volume rm quantum_box_postgres_data nocobase_storage 2>/dev/null || true

# ── 2. Remove Docker / nginx CRM files ──────────────────────────────────────
echo "[2/6] Removing Docker compose & nginx CRM files..."
rm -f docker-compose.nocobase.yml
rm -f docker-compose.nocobase.yml.backup
rm -f docker-compose.crm.yml
rm -f nginx.crm.conf

# ── 3. Remove Python CRM integration files ──────────────────────────────────
echo "[3/6] Removing Python CRM files..."
rm -f crm_integration.py
rm -f crm_routes.py
rm -f jwt_auth.py
rm -f migrate_to_postgres.py
rm -f complete_migration.py
rm -f verify_integration.py
rm -f indiaq_backup.db 2>/dev/null || true

# ── 4. Remove CRM directory ─────────────────────────────────────────────────
echo "[4/6] Removing crm/ directory..."
rm -rf crm/

# ── 5. Remove CRM shell scripts & SQL ───────────────────────────────────────
echo "[5/6] Removing CRM scripts..."
rm -f scripts/fix_crm_db.sh
rm -f scripts/diagnose_crm.sh
rm -f scripts/restart_nocobase.sh
rm -f scripts/setup_nocobase_admin.sh
rm -f scripts/check_nocobase_roles.sh
rm -f scripts/diagnose_nocobase.sh
rm -f scripts/reset_nocobase.sh
rm -f scripts/fix_nocobase_admin.sh
rm -f scripts/fix_qrmanity_admin.sh
rm -f scripts/setup_postgres_mac.sh
rm -f scripts/sql/nocobase_grant_admin.sql

# ── 6. Uninstall CRM-only Python packages ───────────────────────────────────
echo "[6/6] Uninstalling CRM Python packages (if venv active)..."
if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip uninstall -y psycopg2-binary psycopg2 PyJWT requests 2>/dev/null || true
fi

echo ""
echo "============================================================"
echo " CRM file removal complete"
echo "============================================================"
echo ""
echo "Already applied in repo (verify with git diff):"
echo "  • app.py        — CRM blueprint registration removed"
echo "  • config.py     — JWT_SECRET / CRM_API_URL / REDIS_URL removed"
echo "  • requirements.txt — psycopg2-binary, PyJWT, requests removed"
echo "  • .env.example  — CRM / Postgres migration section removed"
echo ""
echo "Manual .env check:"
echo "  DATABASE_URL=sqlite:///indiaq.db"
echo "  (Remove JWT_SECRET, CRM_API_URL, QUMANITY_WEBHOOK_SECRET, DB_* if present)"
echo ""
echo "Verify:"
echo "  cd $ROOT"
echo "  source .venv/bin/activate"
echo "  pip install -r requirements.txt"
echo "  python3 app.py"
echo "  open http://127.0.0.1:5001"
echo ""
echo "Optional — simplify main docker-compose.yml (SQLite-only, no Postgres service):"
echo "  Edit docker-compose.yml to remove the db: service and depends_on: db"
echo ""
