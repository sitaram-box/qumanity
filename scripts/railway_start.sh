#!/bin/sh
# Railway / Nixpacks — wsgi.py answers /health instantly; full app lazy-loads after.
export PYTHONUNBUFFERED=1

PORT="${PORT:-8080}"

echo "=== Qumanity Railway diagnostic ==="
echo "PORT: ${PORT}"
echo "FLASK_ENV: ${FLASK_ENV:-unset}"
echo "USE_MINIMAL_APP: ${USE_MINIMAL_APP:-unset}"
echo "USE_SIMPLE_WSGI: ${USE_SIMPLE_WSGI:-unset}"
echo "Python: $(command -v python3 2>/dev/null || echo missing)"
python3 --version 2>&1 || true
python3 -m gunicorn --version 2>&1 || true

if [ "${USE_MINIMAL_APP}" = "true" ] && [ "${ALLOW_MINIMAL_APP}" = "true" ]; then
  echo "[railway_start] WARNING: minimal_app mode"
  exec python3 -m gunicorn --bind "0.0.0.0:${PORT}" --workers 1 --timeout 300 minimal_app:app
fi

unset USE_MINIMAL_APP
unset RAILWAY_MINIMAL_APP

if [ "${USE_SIMPLE_WSGI}" = "true" ]; then
  echo "[railway_start] USE_SIMPLE_WSGI — loading app:app directly (no lazy wsgi)"
  export PORT
  exec python3 -m gunicorn --config gunicorn.conf.py app:app
fi

echo "[railway_start] starting wsgi:application (instant /health, lazy full app)"
export PORT
exec python3 -m gunicorn --config gunicorn.conf.py wsgi:application
