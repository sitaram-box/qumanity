#!/usr/bin/env bash
# Fix NocoBase blank screen — assign root role via camelCase "rolesUsers" table.
#
# Usage:
#   bash scripts/fix_nocobase_admin.sh
#   bash scripts/fix_nocobase_admin.sh QRMANITY
#   ADMIN_EMAIL=qrmanity@qumanity.in bash scripts/fix_nocobase_admin.sh

set -euo pipefail

ROOT="/Users/macmudgal/Desktop/quantum_box"
COMPOSE_FILE="docker-compose.nocobase.yml"
PG_CONTAINER="${PG_CONTAINER:-qumanity_postgres}"
NB_CONTAINER="${NB_CONTAINER:-qumanity_nocobase}"
DB="${DB_NAME:-qumanity_crm}"
PG_USER="${PG_USER:-postgres}"
ADMIN_USER="${1:-${ADMIN_USER:-QRMANITY}}"
ADMIN_EMAIL="${ADMIN_EMAIL:-qrmanity@qumanity.in}"

cd "$ROOT"

psql() {
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DB" -v ON_ERROR_STOP=1 "$@"
}

echo "============================================================"
echo " Fixing NocoBase Admin Access — Blank Screen Issue"
echo " User: $ADMIN_USER"
echo "============================================================"

if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
  echo "PostgreSQL not running. Starting stack..."
  docker compose -f "$COMPOSE_FILE" up -d
  sleep 15
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$NB_CONTAINER"; then
  echo "NocoBase not running. Starting..."
  docker compose -f "$COMPOSE_FILE" up -d nocobase
  sleep 10
fi

echo ""
echo "Step 1: Current users and role status"
psql -c "
SELECT u.id, u.nickname, u.username, u.email,
       CASE WHEN EXISTS (
         SELECT 1 FROM \"rolesUsers\" ru WHERE ru.\"userId\" = u.id
       ) THEN 'HAS ROLE' ELSE 'NO ROLE' END AS role_status
FROM users u
ORDER BY u.id;
"

echo ""
echo "Step 2: Available roles"
psql -c "SELECT id, name, title FROM roles ORDER BY id;"

echo ""
echo "Step 3: Ensure root role exists"
psql -c "
INSERT INTO roles (name, title, description, \"createdAt\", \"updatedAt\")
SELECT 'root', 'Root', 'Super Administrator - Full System Access', NOW(), NOW()
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'root');
"

echo ""
echo "Step 4: Assign root role to $ADMIN_USER"
psql -c "
INSERT INTO \"rolesUsers\" (\"userId\", \"roleId\", \"createdAt\", \"updatedAt\")
SELECT u.id, r.id, NOW(), NOW()
FROM users u
CROSS JOIN roles r
WHERE (
    u.nickname ILIKE '$ADMIN_USER'
    OR u.username ILIKE '$ADMIN_USER'
    OR u.email ILIKE '$ADMIN_EMAIL'
  )
  AND r.name = 'root'
ON CONFLICT (\"userId\", \"roleId\") DO NOTHING;
"

# Remove member-only role when root is assigned (optional cleanup)
psql -c "
DELETE FROM \"rolesUsers\" ru
USING roles r, users u
WHERE ru.\"userId\" = u.id
  AND ru.\"roleId\" = r.id
  AND r.name = 'member'
  AND (u.nickname ILIKE '$ADMIN_USER' OR u.username ILIKE '$ADMIN_USER')
  AND EXISTS (
    SELECT 1 FROM \"rolesUsers\" ru2
    JOIN roles r2 ON r2.id = ru2.\"roleId\"
    WHERE ru2.\"userId\" = u.id AND r2.name = 'root'
  );
" 2>/dev/null || true

echo ""
echo "Step 5: Verification"
psql -c "
SELECT u.id, u.nickname, u.username, u.email,
       COALESCE(r.name, 'NO ROLE') AS role_name,
       COALESCE(r.title, 'None') AS role_title
FROM users u
LEFT JOIN \"rolesUsers\" ru ON ru.\"userId\" = u.id
LEFT JOIN roles r ON r.id = ru.\"roleId\"
WHERE u.nickname ILIKE '$ADMIN_USER'
   OR u.username ILIKE '$ADMIN_USER'
   OR u.email ILIKE '$ADMIN_EMAIL';
"

USER_COUNT="$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DB" -tAc \
  "SELECT COUNT(*) FROM users WHERE nickname ILIKE '$ADMIN_USER' OR username ILIKE '$ADMIN_USER';" | tr -d '[:space:]')"

if [[ "${USER_COUNT:-0}" == "0" ]]; then
  echo ""
  echo "WARN: User '$ADMIN_USER' not found."
  echo "  Create the account at http://localhost:3000 first, then re-run this script."
  echo "  The FIRST account created in a fresh NocoBase install automatically gets root."
fi

ROLE_OK="$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DB" -tAc "
SELECT COUNT(*) FROM users u
JOIN \"rolesUsers\" ru ON ru.\"userId\" = u.id
JOIN roles r ON r.id = ru.\"roleId\"
WHERE r.name = 'root'
  AND (u.nickname ILIKE '$ADMIN_USER' OR u.username ILIKE '$ADMIN_USER');
" | tr -d '[:space:]')"

if [[ "${ROLE_OK:-0}" == "0" && "${USER_COUNT:-0}" != "0" ]]; then
  echo ""
  echo "ERROR: User exists but root role was not assigned. Run: bash scripts/diagnose_nocobase.sh"
  exit 1
fi

echo ""
echo "Step 6: NocoBase upgrade (sync ACL / plugins)"
docker exec "$NB_CONTAINER" sh -c 'yarn nocobase upgrade 2>/dev/null || npx nocobase upgrade 2>/dev/null || true'

echo ""
echo "Step 7: Restart NocoBase"
docker compose -f "$COMPOSE_FILE" restart nocobase

echo ""
echo "============================================================"
echo " Fix completed!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Clear browser cache OR use Incognito for http://localhost:3000"
echo "  2. Logout if already logged in"
echo "  3. Login as: $ADMIN_USER"
echo ""
echo "You should see: Collections, Plugins, Settings, Users & Permissions"
echo ""
echo "Diagnose: bash scripts/diagnose_nocobase.sh"
