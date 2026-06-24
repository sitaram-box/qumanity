"""
Production WSGI entry for Railway / Docker / Gunicorn.

/health and /healthz respond instantly without importing app.py.
All other routes lazy-load the full Flask application.

Usage:
    gunicorn -c gunicorn.conf.py wsgi:application

Emergency fallback (loads app.py at worker boot — slower healthcheck):
    USE_SIMPLE_WSGI=true → gunicorn app:app
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import traceback
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("qumanity.wsgi")

_HEALTH_PATHS = frozenset({"/health", "/healthz"})
_WSGI_DEBUG_PATH = "/wsgi-debug"

_flask_app: Any = None
_load_lock = threading.Lock()
_load_error: str | None = None


def get_app() -> Any:
    """Lazy-load the Flask application from app.py."""
    global _flask_app, _load_error
    if _flask_app is not None:
        return _flask_app
    with _load_lock:
        if _flask_app is not None:
            return _flask_app
        logger.info("WSGI: loading full Qumanity app (app.py)…")
        try:
            from app import app as flask_app

            _flask_app = flask_app
            _load_error = None
            logger.info("WSGI: full Qumanity app loaded successfully")
        except Exception as exc:
            _load_error = f"{type(exc).__name__}: {exc}"
            logger.exception("WSGI: failed to load app.py")
            traceback.print_exc()
            raise
    return _flask_app


def preload_full_app() -> None:
    """Background preload after worker is listening (optional)."""
    try:
        get_app()
    except Exception as exc:
        logger.warning("WSGI preload warning: %s", exc)


def _wsgi_debug_body() -> bytes:
    payload = {
        "wsgi": "ok",
        "app_loaded": _flask_app is not None,
        "load_error": _load_error,
    }
    return json.dumps(payload).encode("utf-8")


def application(environ, start_response):
    """Gunicorn WSGI entry — fast health, lazy full Flask app."""
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

    if path == _WSGI_DEBUG_PATH:
        body = _wsgi_debug_body()
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    try:
        flask_app = get_app()
        return flask_app(environ, start_response)
    except Exception as exc:
        logger.exception("WSGI application error for %s", path)
        traceback.print_exc(file=sys.stderr)
        msg = f"Internal Server Error\n\n{_load_error or exc}\n"
        body = msg.encode("utf-8", errors="replace")[:4000]
        start_response(
            "500 Internal Server Error",
            [
                ("Content-Type", "text/plain; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]


# Alias for configs that expect `app`
app = application
