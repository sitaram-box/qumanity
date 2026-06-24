#!/bin/sh
# Railway / Nixpacks startup — bind to $PORT; /health must respond before heavy init.
export PYTHONUNBUFFERED=1

if [ -f scripts/diagnose.sh ]; then
  sh scripts/diagnose.sh
fi

PORT="${PORT:-5000}"
echo "[railway_start] starting on 0.0.0.0:${PORT}"

if [ "${USE_MINIMAL_APP}" = "true" ] || [ "${RAILWAY_MINIMAL_APP}" = "true" ]; then
  echo "[railway_start] minimal_app mode (healthcheck isolation test)"
  exec python3 -m gunicorn -c gunicorn.conf.py minimal_app:app
fi

python3 -c "
from db_path import ensure_database_parent, resolve_database_path
path = resolve_database_path()
try:
    ensure_database_parent(path)
    print(f'[railway_start] database path: {path}')
except OSError as exc:
    print(f'[railway_start] database parent warning: {exc}')
" || echo "[railway_start] database path check skipped"

exec python3 -m gunicorn -c gunicorn.conf.py app:app
