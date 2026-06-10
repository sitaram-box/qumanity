# Qumanity CRM (NocoBase)

Customer Service CRM for Qumanity, built on [NocoBase](https://www.nocobase.com/) (Node.js + PostgreSQL). Runs as a **separate service** alongside the Flask app with shared JWT auth and PostgreSQL.

> **npm peer dependency errors?** See [`qumanity-crm/INSTALL.md`](qumanity-crm/INSTALL.md) — use `.npmrc` + `--legacy-peer-deps`, Yarn, or Docker.

## Architecture

```
Citizen (Flask) ──POST order──► CRM /api/orders
Citizen creates ticket ───────► CRM /api/tickets
Agent closes ticket ──webhook──► Flask /api/webhooks/ticket-closed
Flask login ──JWT──► CRM dashboards (/crm)
```

| Component | Port | Purpose |
|-----------|------|---------|
| Flask (Qumanity) | 5000 | Main app, issues JWT |
| NocoBase CRM | 3000 | Tickets, vendors, orders, ratings |
| PostgreSQL | 5432 | Shared DB `qumanity_crm` |
| Redis | 6379 | NocoBase workflows / cache |
| Nginx | 80 | `/` → Flask, `/crm/` → CRM |

## File layout

```
quantum_box/
├── migrate_to_postgres.py      # SQLite → PostgreSQL + CRM tables
├── docker-compose.crm.yml      # Full stack (postgres, redis, nocobase, flask, nginx)
├── nginx.crm.conf              # Reverse proxy
├── jwt_auth.py                 # JWT issue/verify (Flask)
├── crm_integration.py          # CRM HTTP client + local tables
├── crm_routes.py               # Flask API routes (registered in app.py)
└── crm/qumanity-crm/
    ├── Dockerfile
    ├── package.json
    ├── .env.example
    ├── plugins/
    │   ├── shared/auth.ts
    │   ├── tickets/index.ts
    │   ├── vendors/index.ts
    │   ├── orders/index.ts
    │   └── ratings/index.ts
    └── client/pages/
        ├── AgentDashboard.tsx
        ├── ManagerDashboard.tsx
        ├── TicketDetail.tsx
        └── crm-dashboard.css
```

## Prerequisites

- Python 3.14+ with project venv
- Node.js 20+
- PostgreSQL 15+
- Redis 7+ (optional locally; required in Docker stack)
- NocoBase CLI: `npm install -g nocobase@latest`

## Step 1 — Environment

From project root:

```bash
cp .env.example .env
```

Set these (same values in Flask **and** CRM):

```env
JWT_SECRET=your_super_secret_jwt_key_here
QUMANITY_WEBHOOK_SECRET=your_webhook_secret_here
CRM_API_URL=http://localhost:3000/api

# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_DATABASE=qumanity_crm
DB_USER=postgres
DB_PASSWORD=your_password
DATABASE_URL=postgresql://qumanity:qumanity123@localhost:5432/qumanity_crm
```

## Step 2 — Create PostgreSQL database

```bash
createdb qumanity_crm
# or via psql:
# CREATE DATABASE qumanity_crm;
# CREATE USER qumanity WITH PASSWORD 'qumanity123';
# GRANT ALL PRIVILEGES ON DATABASE qumanity_crm TO qumanity;
```

## Step 3 — Migrate SQLite → PostgreSQL

```bash
cd /Users/macmudgal/Desktop/quantum_box
pip install psycopg2-binary python-dotenv PyJWT requests
python3 migrate_to_postgres.py
```

This copies Qumanity tables from `indiaq.db` and creates CRM tables (`tickets`, `vendors`, `orders`, etc.).

## Step 4 — Scaffold NocoBase (first time only)

```bash
mkdir -p crm && cd crm
nocobase create --name qumanity-crm
cd qumanity-crm
```

Copy the provided `plugins/` and `client/` folders into the generated app (overwrite if prompted).

Install dependencies:

```bash
npm install
npm install @nocobase/plugin-workflow @nocobase/plugin-workflow-webhook @nocobase/plugin-charts
npm install jsonwebtoken bcrypt axios
cp .env.example .env
# Edit .env — match JWT_SECRET and DB_* with Flask
```

### Register plugins in NocoBase

After `nocobase install`, link local plugins:

```bash
# From crm/qumanity-crm — symlink or copy plugins into packages/plugins/
mkdir -p packages/plugins
cp -R plugins/tickets packages/plugins/@qumanity-plugin-tickets
cp -R plugins/vendors packages/plugins/@qumanity-plugin-vendors
cp -R plugins/orders  packages/plugins/@qumanity-plugin-orders
cp -R plugins/ratings packages/plugins/@qumanity-plugin-ratings
```

Enable plugins in NocoBase Admin → Plugin Manager, then define collections matching PostgreSQL tables (`tickets`, `ticket_comments`, `vendors`, `products`, `orders`, `ratings`).

### Register CRM UI pages

In NocoBase Admin → UI Editor, add routes:

| Path | Component |
|------|-----------|
| `/agent` | `AgentDashboard` |
| `/manager` | `ManagerDashboard` |
| `/tickets/:id` | `TicketDetail` |

Import React pages from `client/pages/` and include `crm-dashboard.css`.

## Step 5 — Flask integration

Already wired in `app.py`:

```python
from crm_routes import register_crm_routes
register_crm_routes(app, get_db, login_required, g)
```

New Flask endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/auth/crm-token` | JWT for CRM UI |
| POST | `/api/webhooks/ticket-closed` | CRM → Flask ticket closure |
| POST | `/api/orders/create` | Create order + sync to CRM |
| POST | `/api/vendors/register` | Vendor sync to CRM |
| POST | `/api/ratings/submit` | Rating sync to CRM |
| GET | `/api/crm/ticket-updates` | Citizen ticket notifications |

### Get CRM token after login

```javascript
const res = await fetch('/api/auth/crm-token', { credentials: 'include' });
const { token } = await res.json();
localStorage.setItem('qumanity_token', token);
```

Open CRM at `http://localhost:3000` (or `http://localhost/crm/` via Nginx).

## Step 6 — Docker (production-like stack)

```bash
cd /Users/macmudgal/Desktop/quantum_box
docker compose -f docker-compose.crm.yml up -d --build
docker compose -f docker-compose.crm.yml ps
docker compose -f docker-compose.crm.yml logs -f
```

Access:

- Qumanity: http://localhost:5000 or http://localhost/
- CRM: http://localhost:3000 or http://localhost/crm/
- PostgreSQL: `localhost:5432`

Run migration **before** first Docker start (or exec into flask container):

```bash
python3 migrate_to_postgres.py
```

## CRM roles

Assign roles in PostgreSQL `crm_staff` table (or NocoBase collection):

| Role | Scope | Permissions |
|------|-------|-------------|
| **agent** | Tehsil | Own tickets, reply, close |
| **manager** | Tehsil/district | Assign tickets, reports, vendor verify |
| **leader** | District/state | Extensible oversight |
| **admin** | Global | Full access |

JWT `role` is derived from Qumanity `account_type` / `is_admin` in `jwt_auth.py`. Override by inserting into `crm_staff`.

## API reference (CRM)

### Tickets

- `GET /api/tickets` — list (role-filtered)
- `GET /api/tickets/:id` — detail + comments
- `POST /api/tickets` — create
- `POST /api/tickets/:id/comments` — reply
- `POST /api/tickets/:id/assign` — manager assigns agent
- `POST /api/tickets/:id/close` — close + webhook to Flask
- `GET /api/agents/stats` — agent metrics
- `GET /api/manager/team-performance` — manager dashboard
- `GET /api/manager/tickets?unassigned=1` — unassigned queue
- `GET /api/manager/export-report` — CSV download

### Vendors

- `GET /api/vendors`
- `GET /api/vendors/:id`
- `POST /api/vendors/sync`
- `POST /api/vendors/verify`
- `GET /api/vendors/pending`

### Orders

- `GET /api/orders`
- `POST /api/orders`
- `POST /api/orders/:id/assign-delivery`
- `POST /api/orders/:id/status`

### Ratings

- `POST /api/ratings`
- `GET /api/ratings`

All endpoints require `Authorization: Bearer <JWT>` except webhook-sync paths that accept `X-Webhook-Secret`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| CRM 401 Unauthorized | Ensure `JWT_SECRET` matches in Flask and CRM `.env` |
| Webhook fails | Check `QUMANITY_WEBHOOK_SECRET` on both sides |
| Empty ticket list | Confirm user JWT `role` and `tehsil_id`; check `crm_staff` |
| Migration errors | Run against empty DB or drop conflicting tables; check `SQLITE_PATH` |
| NocoBase collections empty | Create collections in Admin UI mapped to PostgreSQL tables |

## Development without Docker

Terminal 1 — PostgreSQL + Redis (or Docker only those services):

```bash
docker compose -f docker-compose.crm.yml up postgres redis -d
python3 migrate_to_postgres.py
python3 app.py
```

Terminal 2 — CRM:

```bash
cd crm/qumanity-crm
nocobase install
nocobase dev
```

## Security checklist

- [ ] Strong `JWT_SECRET` and `QUMANITY_WEBHOOK_SECRET` in production
- [ ] HTTPS via Nginx with `SESSION_COOKIE_SECURE=true`
- [ ] Restrict CRM `/crm/` to staff roles at Nginx or NocoBase ACL
- [ ] Do not commit `.env` files
