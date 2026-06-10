#!/bin/bash
set -e

# Run database migrations (SQLite; path from DATABASE_URL or default)
python init_db.py

# Start the app
exec gunicorn --bind 0.0.0.0:5000 app:app
