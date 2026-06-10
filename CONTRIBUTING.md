# Contributing to Qumanity

Thanks for helping build Qumanity — a decentralised governance and economic
platform for Indian villages.

## Local setup

```bash
git clone <repo-url>
cd quantum_box

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                # then fill in SECRET_KEY etc.

python build_indiaq.py             # build geography DB (first time)
python init_db.py                  # create app tables + migrations
python seed_location_translations.py

python app.py                      # dev server on http://localhost:5000
```

## Project layout

| Path | Purpose |
| --- | --- |
| `app.py` | Flask app, routes, API endpoints (large — see refactor note below) |
| `config.py` | Centralised env/config (single source of truth) |
| `qoin_core.py` | Qoin economy: denominations, wallets, settlement, karma |
| `language_core.py` | Multi-language UI + location-name translations |
| `translations.py` | UI string tables |
| `village_platform.py` | Village commerce / platform features |
| `identity_core.py` | ID generation, account hierarchy |
| `templates/` | Jinja2 templates (`base.html` is the shell) |
| `static/` | CSS, JS, images (`style.css`, `dashboard.css`, `toast.js`) |
| `.cursor/rules/` | Project rules / persistent AI memory (`.mdc`) |

## Coding conventions

- **Python**: `from __future__ import annotations`; type hints on public
  functions; `snake_case` for functions/variables, `UPPER_SNAKE` for constants.
- **SQL**: always parameterised (`?` placeholders) — never string-format user
  input into queries.
- **Config**: read settings from `config.py`, not scattered `os.environ.get`.
- **Logging**: use the `logging` module (`logger = logging.getLogger(...)`),
  not `print`.
- **API endpoints**: return JSON, guard with `@login_required`, and return
  `{"error": "..."}` with an appropriate status on failure.
- **CSS**: use the design tokens in `:root` (see
  `.cursor/rules/ui-guidelines.mdc`) — avoid hardcoded hex values.
- **JS UX**: use `window.qbToast(msg, type)` instead of `alert()`; add
  `data-qb-submitting` to forms to prevent double submission.

## Refactor in progress: splitting `app.py`

`app.py` is ~12k lines / 160+ routes / 420+ functions with heavy shared
module-level state. It is being migrated to Flask **Blueprints** incrementally
(not in one big-bang rewrite, which would break shared helpers/decorators).

Recommended migration order, one PR at a time, each verified by running the app:

1. Extract shared helpers into `extensions.py` / `db.py` (e.g. `get_db`,
   `login_required`, geography helpers) so route modules can import them
   without importing `app`.
2. Create `routes_auth.py` (login, register, logout) as a `Blueprint`.
3. Create `routes_api.py` (the `/api/*` endpoints).
4. Create `routes_dashboard.py` and `routes_admin.py`.
5. In `app.py`, `app.register_blueprint(...)` each module.

Until a module is fully extracted and tested, leave its routes in `app.py`.

## Pull requests

- Keep PRs focused and small.
- Describe what changed and why; note any DB migration.
- Verify locally: registration, login, dashboard, wallet, language switch.
- Do not commit `.env`, `*.db`, or `__pycache__` (see `.gitignore`).

## Reporting issues

Open a GitHub issue with steps to reproduce, expected vs. actual behaviour,
and the relevant log output (with secrets redacted).
