"""Minimal Flask app for Railway healthcheck isolation tests.

Set USE_MINIMAL_APP=true (or RAILWAY_MINIMAL_APP=true) on Railway to serve
this instead of the full app.py stack.
"""

from flask import Flask

app = Flask(__name__)


@app.route("/health")
@app.route("/healthz")
def health():
    return "OK", 200


@app.route("/")
def index():
    return "Qumanity is running", 200


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
