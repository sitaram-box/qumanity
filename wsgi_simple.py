"""Emergency WSGI entry — imports app.py immediately (no lazy-load).

Set USE_SIMPLE_WSGI=true on Railway if wsgi:application fails.
Healthcheck will wait for full app import.
"""

from app import app as application

print("[wsgi_simple] app.py loaded", flush=True)
