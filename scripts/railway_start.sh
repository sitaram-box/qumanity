#!/bin/sh
# Railway / Nixpacks — start Gunicorn quickly; no DB work before the process listens.
export PYTHONUNBUFFERED=1

PORT="${PORT:-8080}"
FLASK_ENV="${FLASK_ENV:-production}"

echo "=== Qumanity Railway diagnostic ==="
echo "PORT: ${PORT}"
echo "FLASK_ENV: ${FLASK_ENV}"
echo "USE_MINIMAL_APP: ${USE_MINIMAL_APP:-unset}"
echo "Python: $(command -v python3 2>/dev/null || echo missing)"
python3 --version 2>&1 || true

# Production always serves the full site — clear stale healthcheck debug flags.
if [ "${FLASK_ENV}" = "production" ]; then
  unset USE_MINIMAL_APP
  unset RAILWAY_MINIMAL_APP
  echo "[railway_start] production: USE_MINIMAL_APP cleared (full app only)"
fi

if [ "${USE_MINIMAL_APP}" = "true" ]; then
  echo "[railway_start] minimal_app mode (healthcheck isolation test)"
  exec python3 -m gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 300 minimal_app:app
fi

echo "[railway_start] starting FULL Qumanity app (app:app)"
export PORT
exec python3 -m gunicorn --config gunicorn.conf.py app:app
