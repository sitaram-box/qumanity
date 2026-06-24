#!/bin/sh
# Railway / Nixpacks — wsgi.py answers /health instantly; full app lazy-loads after.
export PYTHONUNBUFFERED=1

PORT="${PORT:-8080}"

echo "=== Qumanity Railway diagnostic ==="
echo "PORT: ${PORT}"
echo "FLASK_ENV: ${FLASK_ENV:-unset}"
echo "USE_MINIMAL_APP: ${USE_MINIMAL_APP:-unset}"
echo "ALLOW_MINIMAL_APP: ${ALLOW_MINIMAL_APP:-unset}"
echo "Python: $(command -v python3 2>/dev/null || echo missing)"
python3 --version 2>&1 || true
python3 -m gunicorn --version 2>&1 || true

# minimal_app only when BOTH debug flags are set (never the default).
if [ "${USE_MINIMAL_APP}" = "true" ] && [ "${ALLOW_MINIMAL_APP}" = "true" ]; then
  echo "[railway_start] WARNING: minimal_app mode — use only for healthcheck debugging"
  exec python3 -m gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 300 minimal_app:app
fi

unset USE_MINIMAL_APP
unset RAILWAY_MINIMAL_APP

echo "[railway_start] starting wsgi:application (instant /health, lazy full app)"
export PORT
exec python3 -m gunicorn --config gunicorn.conf.py wsgi:application
