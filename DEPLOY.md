# Qumanity — Docker & Cloud Deployment

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- Git repository pushed to GitHub (for Render / Railway)
- Optional: [Fly.io CLI](https://fly.io/docs/hands-on/install-flyctl/)

## Important: Database

Qumanity is **SQLite-native** (geography, Qoin wallets, migrations). The Docker setup uses a **persistent SQLite file** at `/data/indiaq.db`.

- `DATABASE_URL=sqlite:////data/indiaq.db` — **use this for Docker and cloud deploy today**
- `DATABASE_URL=postgresql://...` — scaffold exists in `app.py` (`get_db_connection()`), but the app still requires a full PostgreSQL migration before use

`docker-compose.yml` includes a Postgres service for future testing; the web service defaults to SQLite so the app runs without code changes.

---

## Local Docker Test

```bash
cd /Users/macmudgal/Desktop/quantum_box

# Make entrypoint executable (once)
chmod +x docker-entrypoint.sh

# Build image
docker build -t quantum-box .

# Run (SQLite persisted in a named volume)
docker run -p 8080:5000 \
  -e DATABASE_URL=sqlite:////data/indiaq.db \
  -v quantum_box_data:/data \
  quantum-box
```

Open http://localhost:8080

### Docker Compose (dev with live reload)

```bash
docker compose up --build
```

App: http://localhost:8080  
Postgres (optional/future): `localhost:5432`

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | No | Default: `indiaq.db` in project root. Docker: `sqlite:////data/indiaq.db` |
| `FLASK_ENV` | No | `production` in Docker; `development` for local compose reload |
| `SECRET_KEY` | Yes (prod) | Flask session secret — set in cloud dashboard |
| `QOIN_WALLET_ENCRYPTION_KEY` | Yes (prod) | Qoin wallet encryption — set in cloud dashboard |
| `FLASK_RUN_PORT` | No | Local dev only (default `5001` in `app.py`) |

Generate secrets locally:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Deploy to Render

1. Push code to GitHub
2. Log in at [render.com](https://render.com)
3. **New +** → **Blueprint** (uses `render.yaml`) or **Web Service** → connect repo
4. Render detects `Dockerfile` / `render.yaml`
5. Set env vars: `SECRET_KEY`, `QOIN_WALLET_ENCRYPTION_KEY`
6. Ensure persistent disk is mounted at `/data` (configured in `render.yaml`)
7. Deploy

`render.yaml` sets `DATABASE_URL=sqlite:////data/indiaq.db` and a 1 GB disk at `/data`.

---

## Deploy to Railway

1. Push code to GitHub
2. Log in at [railway.app](https://railway.app)
3. **New Project** → **Deploy from GitHub** → select repository
4. Railway auto-detects `Dockerfile` via `railway.json`
5. Add variables:
   - `DATABASE_URL=sqlite:////data/indiaq.db`
   - `SECRET_KEY`, `QOIN_WALLET_ENCRYPTION_KEY`
6. Add a **Volume** mounted at `/data` (required for SQLite persistence)
7. Deploy

---

## Deploy to Fly.io

```bash
cd /Users/macmudgal/Desktop/quantum_box

flyctl launch
# Accept Dockerfile, set app name, region

flyctl secrets set SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
flyctl secrets set QOIN_WALLET_ENCRYPTION_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
flyctl secrets set DATABASE_URL="sqlite:////data/indiaq.db"

# Persistent volume for SQLite
flyctl volumes create quantum_data --size 1
# Mount volume at /data in fly.toml:
#   [mounts]
#     source = "quantum_data"
#     destination = "/data"

flyctl deploy
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Permission denied` on `/data` | Ensure container runs as `quantumuser` and volume is writable |
| Empty database on restart | Mount persistent volume at `/data`; set `DATABASE_URL=sqlite:////data/indiaq.db` |
| `PostgreSQL DATABASE_URL` error | App does not use Postgres yet — switch to SQLite URL above |
| Port 5000 in use (macOS) | Map host port: `-p 8080:5000` |
| Migrations fail on start | Check `docker logs`; run `python init_db.py` inside container |

---

## Files Added

| File | Purpose |
|------|---------|
| `Dockerfile` | Production image (Python 3.14, gunicorn, non-root user) |
| `.dockerignore` | Exclude venv, DB files, secrets from image |
| `docker-compose.yml` | Local dev stack |
| `docker-entrypoint.sh` | Migrations + gunicorn |
| `render.yaml` | Render Blueprint |
| `railway.json` | Railway Docker config |
| `DEPLOY.md` | This guide |
