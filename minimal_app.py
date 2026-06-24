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


@app.route("/debug")
def debug():
    return {"app": "minimal", "hint": "Set ALLOW_MINIMAL_APP=false and redeploy for full site"}


@app.route("/")
def index():
    return "Qumanity is running", 200


@app.errorhandler(404)
def minimal_not_found(_err):
    return (
        "404 — minimal_app is active (only / and /health exist). "
        "On Railway: delete USE_MINIMAL_APP and ALLOW_MINIMAL_APP, then redeploy.",
        404,
    )


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
