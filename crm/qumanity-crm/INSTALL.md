# NocoBase CRM — Installation (peer dependency fixes)

NocoBase plugins sometimes declare `@nocobase/client@0.x` peer deps while the
framework ships `1.x`. This project ships config to bypass that safely.

## Option A — npm + `.npmrc` (recommended local install)

```bash
cd /Users/macmudgal/Desktop/quantum_box/crm/qumanity-crm

# Clean slate
rm -rf node_modules package-lock.json
npm cache clean --force

# .npmrc already sets legacy-peer-deps=true
npm install

# Environment
cp .env.example .env
# Edit .env: DB_USER, JWT_SECRET (match Flask), QUMANITY_WEBHOOK_SECRET

# Initialize NocoBase (skip re-running npm inside nocobase)
npx nocobase install --skip-install-deps

# Start dev server
npx nocobase dev
```

If install still fails, force the flag explicitly:

```bash
npm install --legacy-peer-deps
npm install @nocobase/plugin-workflow @nocobase/plugin-workflow-webhook @nocobase/plugin-charts jsonwebtoken bcrypt axios --legacy-peer-deps
```

Or use the npm script:

```bash
npm run setup:clean
```

## Option B — Yarn

```bash
cd /Users/macmudgal/Desktop/quantum_box/crm/qumanity-crm
rm -rf node_modules package-lock.json yarn.lock

npm install -g yarn   # if needed
yarn install
yarn nocobase install --skip-install-deps
yarn dev
```

`.yarnrc.yml` discards peer dependency warnings.

## Option C — Docker (no local npm)

Self-contained stack with PostgreSQL (`postgres` / `postgres` user) + NocoBase.

```bash
cd /Users/macmudgal/Desktop/quantum_box

# Stop Homebrew PostgreSQL if port 5432 is in use
# brew services stop postgresql@15

export JWT_SECRET=your_super_secret_jwt_key_change_this
docker compose -f docker-compose.nocobase.yml up -d
docker compose -f docker-compose.nocobase.yml logs -f nocobase
```

**If you see `role "postgres" does not exist`:**

```bash
# Recommended — wipe broken volume and recreate with correct POSTGRES_USER
bash scripts/fix_crm_db.sh --reset

# Or repair without wiping (creates postgres role if another superuser exists)
bash scripts/fix_crm_db.sh

# Restart NocoBase only
bash scripts/restart_nocobase.sh
```

Open http://localhost:3000

### NocoBase blank screen (QRMANITY has no role)

```bash
cd /Users/macmudgal/Desktop/quantum_box
chmod +x scripts/diagnose_nocobase.sh scripts/fix_nocobase_admin.sh scripts/reset_nocobase.sh

# Diagnose (look for *** NO ROLE ASSIGNED ***)
bash scripts/diagnose_nocobase.sh QRMANITY

# Fix — assigns root via "rolesUsers"."userId" / "roleId" (camelCase)
bash scripts/fix_nocobase_admin.sh QRMANITY

# Last resort — wipe and recreate (first signup = root)
bash scripts/reset_nocobase.sh
```

Clear browser cache or use Incognito, then login again at http://localhost:3000

## Verify

```bash
cd /Users/macmudgal/Desktop/quantum_box

curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/
psql -d qumanity_crm -c "\dt" | head -20
python3 verify_integration.py
```

## Skip CRM temporarily

Qumanity works without CRM on SQLite:

```bash
cd /Users/macmudgal/Desktop/quantum_box
python3 app.py
```

## What we changed

| File | Purpose |
|------|---------|
| `.npmrc` | `legacy-peer-deps=true` permanently |
| `package.json` | Pinned `@nocobase/*` to `1.9.63`, npm `overrides` |
| `.yarnrc.yml` | Yarn peer dep noise suppression |
| `docker-compose.nocobase.yml` | Docker-only CRM, no npm |
| `Dockerfile` | `npm install --legacy-peer-deps` |
