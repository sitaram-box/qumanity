#!/usr/bin/env bash
# Complete reset of NocoBase Docker stack (wipes PostgreSQL + NocoBase volumes).
#
#   bash scripts/reset_nocobase.sh
#
# After reset, the FIRST account created at http://localhost:3000 becomes root admin.

set -euo pipefail

ROOT="/Users/macmudgal/Desktop/quantum_box"
COMPOSE_FILE="docker-compose.nocobase.yml"

cd "$ROOT"

echo "============================================================"
echo " Complete NocoBase Reset"
echo "============================================================"
echo ""
echo "WARNING: This removes all NocoBase data and PostgreSQL volume data"
echo "         for the docker-compose.nocobase.yml stack."
echo ""
read -r -p "Continue? [y/N] " confirm
if [[ "${confirm,,}" != "y" ]]; then
  echo "Aborted."
  exit 0
fi

echo ""
echo "Stopping containers and removing volumes..."
docker compose -f "$COMPOSE_FILE" down -v

echo "Removing named volumes (if orphaned)..."
docker volume rm quantum_box_postgres_data quantum_box_nocobase_data 2>/dev/null || true
docker volume rm quantum_box-postgres_data quantum_box-nocobase_data 2>/dev/null || true

echo "Pulling latest NocoBase image..."
docker pull nocobase/nocobase:main

echo "Starting fresh stack..."
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo "============================================================"
echo " Reset complete!"
echo "============================================================"
echo ""
echo "Wait ~30 seconds, then:"
echo "  1. Open http://localhost:3000"
echo "  2. Create the FIRST account — it automatically gets root admin"
echo "     Suggested: username admin / email admin@qumanity.in"
echo ""
echo "Optional — create QRMANITY as second user, then:"
echo "  bash scripts/fix_nocobase_admin.sh QRMANITY"
echo ""
echo "Re-import Qumanity data if needed:"
echo "  python3 complete_migration.py"
