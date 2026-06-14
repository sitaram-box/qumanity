#!/bin/bash
set -e

# Run database migrations (SQLite path from DATABASE_PATH / Railway volume)
python init_db.py
python add_global_geography.py

# Railway sets PORT; Docker/local default 5000
exec gunicorn app:app --bind "0.0.0.0:${PORT:-5000}" --workers 1 --timeout 120 --access-logfile - --error-logfile -
