#!/usr/bin/env bash
# CRM accessibility diagnostic (NocoBase on localhost:3000 / 13000).
#
#   bash scripts/diagnose_crm.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "============================================================"
echo " CRM Diagnostic Tool"
echo "============================================================"

echo ""
echo "Docker status:"
if ! docker info >/dev/null 2>&1; then
  echo "  Docker is not running. Start Docker Desktop:"
  echo "    open /Applications/Docker.app"
  exit 1
fi

echo ""
echo "Container status (qumanity / nocobase):"
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' \
  | grep -E 'qumanity|nocobase|NAMES' || echo "  (no matching containers)"

check_url() {
  local url="$1"
  local label="$2"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "$url" 2>/dev/null || echo "000")"
  if [[ "$code" =~ ^(200|301|302|303|307|308)$ ]]; then
    echo "  OK  $label — HTTP $code ($url)"
    return 0
  fi
  echo "  FAIL $label — HTTP $code ($url)"
  return 1
}

echo ""
echo "HTTP checks:"
ok300=0
ok13000=0
check_url "http://localhost:3000" "port 3000" && ok300=1 || true
check_url "http://localhost:13000" "port 13000" && ok13000=1 || true

echo ""
echo "Recent logs:"
echo "--- qumanity_nocobase ---"
docker logs qumanity_nocobase --tail 10 2>/dev/null || echo "  (container not found)"
echo ""
echo "--- qumanity_postgres ---"
docker logs qumanity_postgres --tail 5 2>/dev/null || echo "  (container not found)"

if docker ps --format '{{.Names}}' | grep -qx qumanity_postgres; then
  echo ""
  echo "PostgreSQL readiness:"
  docker exec qumanity_postgres pg_isready -U postgres -d qumanity_crm 2>/dev/null \
    || echo "  pg_isready failed"
  pg_logs="$(docker logs qumanity_postgres --tail 5 2>&1 || true)"
  if echo "$pg_logs" | grep -q "incompatible with server"; then
    echo ""
    echo "  WARNING: Postgres data volume version mismatch (e.g. PG15 volume with PG16 image)."
    echo "  Fix: use postgres:15 in docker-compose.nocobase.yml, OR wipe volume:"
    echo "       docker compose -f docker-compose.nocobase.yml down -v"
  fi
fi

echo ""
echo "============================================================"
echo " Suggested actions"
echo "============================================================"
if [[ "$ok300" -eq 0 && "$ok13000" -eq 0 ]]; then
  echo "  1. Start CRM:"
  echo "       docker compose -f docker-compose.nocobase.yml up -d"
  echo "  2. Wait ~20s, then follow logs:"
  echo "       docker compose -f docker-compose.nocobase.yml logs -f nocobase"
  echo "  3. If port 5432 is busy, set POSTGRES_HOST_PORT=5433 in .env"
  echo "  4. Full reset (wipes volumes):"
  echo "       docker compose -f docker-compose.nocobase.yml down -v"
  echo "       docker compose -f docker-compose.nocobase.yml up -d"
elif [[ "$ok300" -eq 0 && "$ok13000" -eq 1 ]]; then
  echo "  CRM responds on :13000 but not :3000."
  echo "  Update docker-compose.nocobase.yml ports to \"3000:80\" and restart."
else
  echo "  CRM looks reachable. Open: http://localhost:3000"
fi
echo "============================================================"
