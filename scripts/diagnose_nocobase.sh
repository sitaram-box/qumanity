#!/usr/bin/env bash
# Diagnostic script for NocoBase blank screen (missing rolesUsers assignment).
#
#   bash scripts/diagnose_nocobase.sh
#   bash scripts/diagnose_nocobase.sh QRMANITY

set -euo pipefail

ROOT="/Users/macmudgal/Desktop/quantum_box"
PG_CONTAINER="${PG_CONTAINER:-qumanity_postgres}"
NB_CONTAINER="${NB_CONTAINER:-qumanity_nocobase}"
DB="${DB_NAME:-qumanity_crm}"
PG_USER="${PG_USER:-postgres}"
TARGET="${1:-QRMANITY}"

cd "$ROOT"

psql() {
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DB" "$@"
}

echo "============================================================"
echo " NocoBase Blank Screen Diagnostic"
echo " Target user: $TARGET"
echo "============================================================"

echo ""
echo "Container status:"
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'qumanity|NAMES' || echo "  (no qumanity containers running)"

if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
  echo ""
  echo "ERROR: $PG_CONTAINER is not running."
  echo "  docker compose -f docker-compose.nocobase.yml up -d"
  exit 1
fi

echo ""
echo "All users:"
psql -c "SELECT id, nickname, username, email FROM users ORDER BY id;"

echo ""
echo "All roles:"
psql -c "SELECT id, name, title FROM roles ORDER BY id;"

echo ""
echo "Role assignments (rolesUsers — note camelCase columns):"
psql -c "
SELECT ru.\"userId\", u.nickname, ru.\"roleId\", r.name AS role_name
FROM \"rolesUsers\" ru
LEFT JOIN users u ON u.id = ru.\"userId\"
LEFT JOIN roles r ON r.id = ru.\"roleId\"
ORDER BY ru.\"userId\";
" 2>/dev/null || psql -c "SELECT * FROM \"rolesUsers\" LIMIT 20;"

echo ""
echo "$TARGET details:"
psql -c "
SELECT u.id, u.nickname, u.username, u.email,
       COALESCE(r.name, '*** NO ROLE ASSIGNED ***') AS role,
       COALESCE(r.title, '') AS role_title
FROM users u
LEFT JOIN \"rolesUsers\" ru ON ru.\"userId\" = u.id
LEFT JOIN roles r ON r.id = ru.\"roleId\"
WHERE u.nickname ILIKE '$TARGET' OR u.username ILIKE '$TARGET';
"

echo ""
echo "Collections (admin needs roles to see UI):"
psql -c "SELECT COUNT(*) AS collection_count FROM collections;" 2>/dev/null || echo "  (collections table not found)"

if docker ps --format '{{.Names}}' | grep -qx "$NB_CONTAINER"; then
  echo ""
  echo "Recent NocoBase logs (last 15 lines):"
  docker logs "$NB_CONTAINER" --tail 15 2>&1 || true
fi

echo ""
echo "============================================================"
echo " Interpretation"
echo "============================================================"
NO_ROLE="$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DB" -tAc "
SELECT COUNT(*) FROM users u
WHERE (u.nickname ILIKE '$TARGET' OR u.username ILIKE '$TARGET')
  AND NOT EXISTS (SELECT 1 FROM \"rolesUsers\" ru WHERE ru.\"userId\" = u.id);
" | tr -d '[:space:]')"

if [[ "${NO_ROLE:-0}" != "0" ]]; then
  echo "  CAUSE: $TARGET exists but has NO entry in \"rolesUsers\"."
  echo "  FIX:   bash scripts/fix_nocobase_admin.sh $TARGET"
else
  HAS_ROOT="$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DB" -tAc "
SELECT COUNT(*) FROM users u
JOIN \"rolesUsers\" ru ON ru.\"userId\" = u.id
JOIN roles r ON r.id = ru.\"roleId\"
WHERE r.name = 'root' AND (u.nickname ILIKE '$TARGET' OR u.username ILIKE '$TARGET');
" | tr -d '[:space:]')"
  if [[ "${HAS_ROOT:-0}" != "0" ]]; then
    echo "  OK: $TARGET has root role. If UI still blank, clear cache / Incognito login."
  else
    echo "  WARN: $TARGET has a role but not root. Run: bash scripts/fix_nocobase_admin.sh $TARGET"
  fi
fi
echo ""
