#!/usr/bin/env bash
# Fix NocoBase ↔ PostgreSQL connection in Docker.
#
# Run from project root:
#   bash scripts/fix_crm_db.sh
#
# Options:
#   bash scripts/fix_crm_db.sh          # try repair without wiping data
#   bash scripts/fix_crm_db.sh --reset  # wipe volumes and recreate (recommended)

set -euo pipefail

ROOT="/Users/macmudgal/Desktop/quantum_box"
COMPOSE_FILE="docker-compose.nocobase.yml"
PG_CONTAINER="qumanity_postgres"
NB_CONTAINER="qumanity_nocobase"
DB_NAME="qumanity_crm"
PG_USER="postgres"
PG_PASS="postgres"

cd "$ROOT"

reset_stack() {
  echo "== Full reset: stopping containers and removing volumes =="
  docker compose -f "$COMPOSE_FILE" down -v
  echo "== Starting fresh stack (POSTGRES_USER=postgres) =="
  docker compose -f "$COMPOSE_FILE" up -d
  echo "== Waiting for PostgreSQL healthcheck =="
  sleep 8
  docker compose -f "$COMPOSE_FILE" ps
  echo ""
  echo "Done. Watch NocoBase: docker compose -f $COMPOSE_FILE logs -f nocobase"
}

ensure_postgres_running() {
  if ! docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    echo "Starting PostgreSQL container..."
    docker compose -f "$COMPOSE_FILE" up -d postgres
    echo "Waiting for PostgreSQL..."
    sleep 8
  fi
}

# Detect which superuser exists inside the container
detect_pg_superuser() {
  for candidate in postgres macmudgal qumanity; do
    if docker exec "$PG_CONTAINER" psql -U "$candidate" -d postgres -c "SELECT 1" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

repair_without_reset() {
  ensure_postgres_running

  echo "Detecting PostgreSQL superuser inside container..."
  SUPERUSER="$(detect_pg_superuser || true)"
  if [[ -z "${SUPERUSER:-}" ]]; then
    echo "ERROR: Cannot connect to PostgreSQL with any known superuser."
    echo "Run with --reset to recreate volumes:"
    echo "  bash scripts/fix_crm_db.sh --reset"
    exit 1
  fi
  echo "Using superuser: $SUPERUSER"

  if [[ "$SUPERUSER" != "$PG_USER" ]]; then
    echo "Creating role '$PG_USER' (NocoBase expects this user)..."
    docker exec "$PG_CONTAINER" psql -U "$SUPERUSER" -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$PG_USER') THEN
    CREATE ROLE $PG_USER WITH LOGIN SUPERUSER PASSWORD '$PG_PASS';
  END IF;
END
\$\$;
ALTER ROLE $PG_USER WITH SUPERUSER PASSWORD '$PG_PASS';
SQL
  fi

  echo "Ensuring database '$DB_NAME' exists..."
  docker exec "$PG_CONTAINER" psql -U "$SUPERUSER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT 'CREATE DATABASE $DB_NAME OWNER $PG_USER'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$DB_NAME')\gexec
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $PG_USER;
SQL

  echo "Verifying connection as $PG_USER..."
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$DB_NAME" -c "SELECT version();"

  echo "Restarting NocoBase..."
  docker compose -f "$COMPOSE_FILE" up -d nocobase
  docker compose -f "$COMPOSE_FILE" restart nocobase

  echo ""
  echo "Fix completed. Check logs:"
  echo "  docker compose -f $COMPOSE_FILE logs -f nocobase"
  echo "Open: http://localhost:3000"
}

if [[ "${1:-}" == "--reset" ]]; then
  reset_stack
else
  repair_without_reset
fi
