# Changelog

All notable changes to Qumanity are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `config.py`: centralised, env-driven configuration (single source of truth),
  loaded via `python-dotenv`. Includes startup config validation/warnings.
- `.env.example` documenting all supported environment variables.
- Toast notification system (`static/toast.js` + styles) to replace `alert()`
  popups; server flash messages are mirrored into toasts.
- Loading spinner utility and form double-submit guard (`data-qb-submitting`).
- Accessibility: skip-to-content link and visible keyboard focus rings.
- Docker `HEALTHCHECK` polling `/`; `curl` added to the image.
- `DEPLOYMENT.md` (Docker / Render / Railway / Fly.io), `CONTRIBUTING.md`,
  and this `CHANGELOG.md`.
- Cursor rules: `ui-guidelines.mdc`, `production-checklist.mdc`.

### Changed
- UI palette consolidated to design tokens: amber primary, **blue secondary
  (`#3B82F6`)**, red danger, green success, yellow warning.
- Typography: base font size 16px; font stack now `Inter, system-ui,
  -apple-system, "DM Sans", sans-serif` for readability.
- `app.py` now sources `SECRET_KEY` and cookie hardening from `config.py`, and
  configures structured logging.
- `.gitignore` expanded (`.env*`, `__pycache__/`, `*.db-wal/-shm`, editor/OS
  files, node artifacts) while keeping `.env.example` tracked.
- Footer cleaned: removed "early prototype · Data for demonstration only".
- Neutral utility buttons moved to `.qb-btn-neutral`; `.qb-btn-secondary` is now
  the blue secondary action.

### Notes
- Splitting `app.py` into Blueprint modules (`routes_auth`, `routes_api`,
  `routes_dashboard`, `routes_admin`) is planned and documented in
  `CONTRIBUTING.md`. It is intentionally being done incrementally rather than as
  a single untested rewrite.

## [0.1.0] — Prototype
- Initial Flask prototype: nested geography, four timelines (Private, Personal,
  Public, Global), Qoin economy with fixed denominations and weekly settlement,
  registration/login, dashboard, multi-language support, village commerce.
