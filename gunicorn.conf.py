"""Gunicorn configuration for production (Railway, Docker, Render)."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
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
    print(f"[gunicorn] listening on {server.addresses}", flush=True)


def post_worker_init(worker):
    print(f"[gunicorn] worker pid={worker.pid} ready", flush=True)


def worker_abort(worker):
    print(f"[gunicorn] worker pid={worker.pid} aborted", flush=True)
