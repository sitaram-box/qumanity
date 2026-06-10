#!/usr/bin/env bash
# PostgreSQL setup for Qumanity CRM on macOS (Homebrew).
# Run from project root:  bash scripts/setup_postgres_mac.sh
#
# Does NOT run migration — run python3 migrate_to_postgres.py after this.

set -euo pipefail

MAC_USER="$(whoami)"
PG_VERSION="${PG_VERSION:-15}"
PG_FORMULA="postgresql@${PG_VERSION}"
PG_DATA="/opt/homebrew/var/${PG_FORMULA}"
DB_NAME="${DB_NAME:-qumanity_crm}"

echo "== Qumanity PostgreSQL setup (macOS) =="
echo "User: ${MAC_USER}  Database: ${DB_NAME}"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install from https://brew.sh"
  exit 1
fi

if ! brew list "${PG_FORMULA}" >/dev/null 2>&1; then
  echo "Installing ${PG_FORMULA}…"
  brew install "${PG_FORMULA}"
fi

# Ensure PostgreSQL is running
brew services start "${PG_FORMULA}" || true
sleep 2

# Add psql to PATH for this session
export PATH="/opt/homebrew/opt/${PG_FORMULA}/bin:${PATH}"

# Create database owned by macOS user (Homebrew default superuser)
if psql -lqt | cut -d \| -f 1 | grep -qw "${DB_NAME}"; then
  echo "Database '${DB_NAME}' already exists."
else
  createdb "${DB_NAME}" -O "${MAC_USER}" || createdb "${DB_NAME}"
  echo "Created database '${DB_NAME}'."
fi

# Optional: also create postgres role for Docker parity
if psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='postgres'" | grep -q 1; then
  echo "Role 'postgres' already exists."
else
  createuser -s postgres 2>/dev/null || true
  psql -c "ALTER USER postgres WITH PASSWORD 'postgres';" 2>/dev/null || true
  echo "Created role 'postgres' (password: postgres)."
fi

echo ""
echo "Verify:"
echo "  psql -d ${DB_NAME} -c \"SELECT version();\""
echo ""
echo "Add to .env:"
echo "  DB_HOST=127.0.0.1"
echo "  DB_USER=${MAC_USER}"
echo "  DB_PASSWORD="
echo "  DB_DATABASE=${DB_NAME}"
echo ""
echo "Then run:"
echo "  python3 migrate_to_postgres.py"
