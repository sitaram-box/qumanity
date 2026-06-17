"""
Centralised configuration for Qumanity.

All environment-driven settings live here so the rest of the codebase reads a
single source of truth instead of scattered ``os.environ.get`` calls.

Importing this module loads a local ``.env`` file (if present and if
``python-dotenv`` is installed) so values are available before the rest of the
app reads ``os.environ``.

Usage
-----
    import config
    app.config["SECRET_KEY"] = config.SECRET_KEY

Nothing here imports ``app`` — keep it dependency-free so it can be imported
from anywhere (routes, scripts, tests) without circular imports.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("qumanity.config")

BASE_DIR = Path(__file__).resolve().parent


def load_env() -> None:
    """Load variables from a local .env file if python-dotenv is available.

    Safe to call multiple times. A missing .env file or a missing
    ``python-dotenv`` dependency is not an error — environment variables set by
    the host (Render, Railway, Fly.io, Docker) still take effect.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = BASE_DIR / ".env"
    load_dotenv(dotenv_path=env_path if env_path.is_file() else None)


# Load .env as early as possible (at import time).
load_env()


def _get_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ── Environment ──────────────────────────────────────────────────────────────
FLASK_ENV: str = os.environ.get("FLASK_ENV", "development").strip().lower()
IS_PRODUCTION: bool = FLASK_ENV == "production"
DEBUG: bool = _get_bool("FLASK_DEBUG", default=not IS_PRODUCTION)

# ── Secrets ──────────────────────────────────────────────────────────────────
_DEFAULT_DEV_SECRET = "dev"
SECRET_KEY: str = (
    os.environ.get("SECRET_KEY")
    or os.environ.get("QUANTUM_BOX_SECRET")
    or _DEFAULT_DEV_SECRET
)

# Encryption key for wallet contents (Qoin denominations at rest).
QOIN_WALLET_ENCRYPTION_KEY: str = os.environ.get(
    "QOIN_WALLET_ENCRYPTION_KEY", ""
).strip()

# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL: str | None = os.environ.get("DATABASE_URL")

# ── Public site URL (referral links, QR codes, Open Graph) ───────────────────
PUBLIC_BASE_URL: str = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")

# ── Razorpay (online donations) ──────────────────────────────────────────────
RAZORPAY_KEY_ID: str = os.environ.get("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET: str = os.environ.get("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_WEBHOOK_SECRET: str = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "").strip()
# Display on registration QR screen (merchant UPI VPA from Razorpay dashboard).
DONATION_UPI_VPA: str = os.environ.get("DONATION_UPI_VPA", "").strip()

MAIL_SERVER: str = os.environ.get("MAIL_SERVER", "").strip()
MAIL_PORT: int = int(os.environ.get("MAIL_PORT", "587") or "587")
MAIL_USE_TLS: bool = _get_bool("MAIL_USE_TLS", default=True)
MAIL_USERNAME: str = os.environ.get("MAIL_USERNAME", "").strip()
MAIL_PASSWORD: str = os.environ.get("MAIL_PASSWORD", "").strip()
MAIL_DEFAULT_SENDER: str = os.environ.get(
    "MAIL_DEFAULT_SENDER", MAIL_USERNAME
).strip()

# ── Session / cookies ────────────────────────────────────────────────────────
SESSION_COOKIE_SECURE: bool = _get_bool(
    "SESSION_COOKIE_SECURE", default=IS_PRODUCTION
)
SESSION_COOKIE_HTTPONLY: bool = True
SESSION_COOKIE_SAMESITE: str = os.environ.get(
    "SESSION_COOKIE_SAMESITE", "Lax"
).strip()

# ── Server ───────────────────────────────────────────────────────────────────
HOST: str = os.environ.get("HOST", "0.0.0.0")
PORT: int = int(os.environ.get("PORT", "5000") or "5000")


def validate() -> list[str]:
    """Return a list of human-readable warnings about the current config.

    Does not raise — call it during startup and log the result so misconfigured
    production deploys are obvious without crashing local development.
    """
    warnings: list[str] = []
    if IS_PRODUCTION and SECRET_KEY == _DEFAULT_DEV_SECRET:
        warnings.append(
            "SECRET_KEY is using the insecure default 'dev' in production. "
            "Set a strong SECRET_KEY environment variable."
        )
    if IS_PRODUCTION and not QOIN_WALLET_ENCRYPTION_KEY:
        warnings.append(
            "QOIN_WALLET_ENCRYPTION_KEY is not set in production. "
            "Wallet contents may not be encrypted at rest."
        )
    if IS_PRODUCTION and (DATABASE_URL or "").startswith("sqlite"):
        warnings.append(
            "DATABASE_URL points at SQLite in production. Consider PostgreSQL "
            "for concurrent writes and durability."
        )
    return warnings


def log_warnings() -> None:
    for warning in validate():
        logger.warning("[config] %s", warning)


def as_flask_config() -> dict[str, object]:
    """Mapping suitable for ``app.config.update(...)``."""
    return {
        "SECRET_KEY": SECRET_KEY,
        "DEBUG": DEBUG,
        "SESSION_COOKIE_SECURE": SESSION_COOKIE_SECURE,
        "SESSION_COOKIE_HTTPONLY": SESSION_COOKIE_HTTPONLY,
        "SESSION_COOKIE_SAMESITE": SESSION_COOKIE_SAMESITE,
    }
