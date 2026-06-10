# Qumanity — Deployment Guide

This guide covers local Docker, Render, Railway, and Fly.io deployments.

> The app is a Flask application served by Gunicorn. Geography and app data live
> in `indiaq.db` (SQLite by default). For production you can migrate to
> PostgreSQL via `DATABASE_URL`.

---

## 0. Prerequisites

- Python 3.12+ (Docker image uses 3.14-slim)
- A built `indiaq.db` (run `python build_indiaq.py` / `python init_db.py` locally)
- Environment variables prepared (see [`.env.example`](.env.example))

Generate secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(48))"   # QOIN_WALLET_ENCRYPTION_KEY
```

---

## 1. Local Docker deployment

```bash
# Build
docker build -t quantum-box .

# Run (persist the database in a named volume)
docker run -d --name quantum-box \
  -p 5000:5000 \
  -e SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e QOIN_WALLET_ENCRYPTION_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e FLASK_ENV=production \
  -v quantum_box_data:/data \
  quantum-box

# Health
docker ps          # STATUS should show "healthy" after ~15s
curl -f http://localhost:5000/
```

Using `docker-compose` (already present):

```bash
docker compose up -d --build
docker compose logs -f
```

The image runs as a non-root user (`quantumuser`) and ships a `HEALTHCHECK`
that polls `/` every 30s.

---

## 2. Render deployment

`render.yaml` is included. Steps:

1. Push the repo to GitHub.
2. In Render: **New → Blueprint**, point at the repo.
3. Set environment variables in the Render dashboard:
   - `SECRET_KEY`, `QOIN_WALLET_ENCRYPTION_KEY`
   - `FLASK_ENV=production`
   - `DATABASE_URL` (Render Postgres add-on, or leave SQLite for prototype)
4. Add a persistent disk mounted at `/data` if staying on SQLite.
5. Deploy. Render runs the Docker `HEALTHCHECK` / start command automatically.

---

## 3. Railway deployment

`railway.json` is included.

1. `railway init` (or import the GitHub repo in the Railway dashboard).
2. Add variables under **Variables**:
   `SECRET_KEY`, `QOIN_WALLET_ENCRYPTION_KEY`, `FLASK_ENV=production`,
   and `DATABASE_URL` if using Railway Postgres.
3. Add a volume mounted at `/data` for SQLite persistence.
4. Deploy: `railway up` (or auto-deploy on push).

---

## 4. Fly.io deployment

```bash
fly launch --no-deploy        # generates fly.toml; keep internal_port = 5000
fly volumes create quantum_data --size 1
fly secrets set \
  SECRET_KEY=... \
  QOIN_WALLET_ENCRYPTION_KEY=... \
  FLASK_ENV=production
fly deploy
```

In `fly.toml`, mount the volume:

```toml
[mounts]
  source = "quantum_data"
  destination = "/data"
```

---

## 5. Database migrations

Migrations run automatically on container start via `docker-entrypoint.sh`
(`python init_db.py`). To run manually:

```bash
python init_db.py
python seed_location_translations.py    # location name translations
```

To migrate to PostgreSQL: set `DATABASE_URL=postgresql://…` and provision the
schema. The SQLite path remains the default until the relational migration is
complete (see `get_db_connection()` in `app.py`).

---

## 6. Post-deployment checklist

See [`.cursor/rules/production-checklist.mdc`](.cursor/rules/production-checklist.mdc). In short:

- [ ] `/` returns 200 (health check green)
- [ ] Registration → auto-login → dashboard works
- [ ] Login / logout works
- [ ] Wallet balance renders; a test transaction settles
- [ ] Post escalation timer behaves
- [ ] Language switching localizes UI + location names
- [ ] No `SECRET_KEY=dev` warning in logs (`config.log_warnings()`)
