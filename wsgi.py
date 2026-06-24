"""
Production WSGI entry for Railway / Docker / Gunicorn.

Responds to /health and /healthz immediately without importing app.py.
All other routes lazy-load the full Qumanity Flask application on first use.

Usage:
    gunicorn -c gunicorn.conf.py wsgi:application
"""

from __future__ import annotations

import threading
from typing import Any, Callable

_HEALTH_PATHS = frozenset({"/health", "/healthz"})

_full_wsgi: Callable[..., Any] | None = None
_load_lock = threading.Lock()


def _ensure_full_app() -> Callable[..., Any]:
    """Import app.py once and return its WSGI callable."""
    global _full_wsgi
    if _full_wsgi is not None:
        return _full_wsgi
    with _load_lock:
        if _full_wsgi is None:
            print("[wsgi] loading full Qumanity app (app.py)…", flush=True)
            from app import app as flask_app

            _full_wsgi = flask_app.wsgi_app
            print("[wsgi] full Qumanity app ready", flush=True)
    return _full_wsgi


def preload_full_app() -> None:
    """Optional background preload after worker is listening."""
    try:
        _ensure_full_app()
    except Exception as exc:
        print(f"[wsgi] preload warning: {exc}", flush=True)


def application(environ, start_response):
    """Gunicorn WSGI entry — fast health, lazy full app."""
    path = environ.get("PATH_INFO") or ""
    if path in _HEALTH_PATHS:
        body = b"OK"
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/plain"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    return _ensure_full_app()(environ, start_response)


# Alias for configs that expect `app`
app = application
