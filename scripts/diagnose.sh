#!/bin/sh
# Pre-start diagnostics for Railway / Nixpacks deploys.
echo "=== Qumanity Railway diagnostic ==="
echo "PORT=${PORT:-unset}"
echo "PWD=$(pwd)"
echo "FLASK_ENV=${FLASK_ENV:-unset}"
echo "DATABASE_PATH=${DATABASE_PATH:-unset}"
echo "RAILWAY_VOLUME_MOUNT_PATH=${RAILWAY_VOLUME_MOUNT_PATH:-unset}"
echo "USE_MINIMAL_APP=${USE_MINIMAL_APP:-unset}"
echo "Python: $(command -v python3 2>/dev/null || echo missing)"
python3 --version 2>&1 || true
echo "Gunicorn: $(python3 -m gunicorn --version 2>&1 || echo missing)"
echo "Files in project root:"
ls -la 2>&1 | head -25
echo "=== end diagnostic ==="
