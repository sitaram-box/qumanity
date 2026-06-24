#!/bin/sh
# Railway / Nixpacks startup — bind to $PORT; /health must respond before heavy init.
export PYTHONUNBUFFERED=1

PORT="${PORT:-5000}"

echo "=== Qumanity Railway diagnostic ==="
echo "PORT: ${PORT}"
echo "PWD: $(pwd)"
echo "FLASK_ENV: ${FLASK_ENV:-unset}"
echo "DATABASE_PATH: ${DATABASE_PATH:-unset}"
echo "RAILWAY_VOLUME_MOUNT_PATH: ${RAILWAY_VOLUME_MOUNT_PATH:-unset}"
echo "USE_MINIMAL_APP: ${USE_MINIMAL_APP:-unset}"
echo "Python: $(command -v python3 2>/dev/null || echo missing)"
python3 --version 2>&1 || true

if [ "${USE_MINIMAL_APP}" = "true" ] || [ "${RAILWAY_MINIMAL_APP}" = "true" ]; then
  echo "[railway_start] minimal_app mode (healthcheck isolation test)"
  exec python3 -m gunicorn --bind "0.0.0.0:${PORT}" minimal_app:app
fi

echo "[railway_start] starting full app on 0.0.0.0:${PORT}"

python3 -c "
from db_path import ensure_database_parent, resolve_database_path
path = resolve_database_path()
try:
    ensure_database_parent(path)
    print(f'[railway_start] database path: {path}')
except OSError as exc:
    print(f'[railway_start] database parent warning: {exc}')
" || echo "[railway_start] database path check skipped"

exec python3 -m gunicorn --bind "0.0.0.0:${PORT}" --config gunicorn.conf.py app:app
