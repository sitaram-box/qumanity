#!/usr/bin/env bash
# Restart NocoBase after PostgreSQL is healthy.
#
#   bash scripts/restart_nocobase.sh

set -euo pipefail
cd /Users/macmudgal/Desktop/quantum_box

docker compose -f docker-compose.nocobase.yml up -d postgres
echo "Waiting for PostgreSQL..."
docker compose -f docker-compose.nocobase.yml up -d --wait postgres 2>/dev/null || sleep 8

docker compose -f docker-compose.nocobase.yml up -d nocobase
docker compose -f docker-compose.nocobase.yml restart nocobase

echo "NocoBase restarted. Logs:"
echo "  docker compose -f docker-compose.nocobase.yml logs -f nocobase"
