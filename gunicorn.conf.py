"""Gunicorn configuration for production (Railway, Docker, Render)."""

import os
import sys
import threading

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
worker_class = "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "300"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
accesslog = "-"
errorlog = "-"
capture_output = True
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
preload_app = False


def when_ready(server):
    try:
        addr = getattr(server, "address", None)
        print(f"[gunicorn] listening on {addr}", flush=True)
    except Exception as exc:
        print(f"[gunicorn] ready ({exc})", flush=True)
    sys.stdout.flush()


def post_worker_init(worker):
    print(f"[gunicorn] worker pid={worker.pid} listening (wsgi lazy-load)", flush=True)
    sys.stdout.flush()

    def _bg_preload() -> None:
        try:
            from wsgi import preload_full_app

            preload_full_app()
        except Exception as exc:
            print(f"[gunicorn] background preload failed: {exc}", flush=True)

    threading.Thread(target=_bg_preload, name="qumanity-preload", daemon=True).start()


def worker_abort(worker):
    print(f"[gunicorn] worker pid={worker.pid} aborted", flush=True)
    sys.stdout.flush()
