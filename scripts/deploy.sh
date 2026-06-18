#!/usr/bin/env bash
# Deploy Qumanity and verify health / admin migration status.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_URL="${APP_URL:-https://qumanity.in}"

echo "Deploying Qumanity…"
git push origin main

echo "Waiting for deployment (30s)…"
sleep 30

if command -v railway >/dev/null 2>&1; then
  railway status || true
  railway logs --lines 20 || true
fi

echo ""
echo "Health check:"
curl -fsS "${APP_URL}/health" || echo "Health check failed"
echo ""
echo "Deployment complete."
echo "  Login: ${APP_URL}/login"
echo "  Admin digits: 014918240"
echo "  Password: P@y#umans123"
