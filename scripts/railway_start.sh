#!/bin/sh
# Railway / Nixpacks startup — bind to $PORT and respond to /health quickly.
set -e

PORT="${PORT:-5000}"
echo "Qumanity starting on 0.0.0.0:${PORT}"

python3 - <<'PY'
from db_path import ensure_database_parent, resolve_database_path

path = resolve_database_path()
ensure_database_parent(path)
print(f"Database path: {path}")
PY

exec gunicorn -c gunicorn.conf.py app:app
