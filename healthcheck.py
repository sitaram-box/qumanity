"""Standalone health probe for local testing — not used in production deploy.

Production uses wsgi.py (instant /health) + lazy-loaded app.py.
Run: python3 healthcheck.py  OR  gunicorn healthcheck:app
"""

from flask import Flask

app = Flask(__name__)


@app.route("/health")
@app.route("/healthz")
def health():
    return "OK", 200


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
