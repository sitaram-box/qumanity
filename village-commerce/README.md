# Village Employment & Local Commerce System (VELCS)

Full-stack Next.js application for the **Qumanity** project — digitising the unorganised sector in Indian villages with employment, local commerce, Qoins payments, AI assistance, hyperlocal delivery, and Village Council verification.

## Tech Stack

- **Next.js 15** (App Router) + TypeScript
- **TailwindCSS 4** — spiritual-modern earthy theme (saffron, green, cream)
- **Supabase** — Auth (phone OTP), PostgreSQL, Realtime, Storage
- **OpenAI** — AI assistant & trust summaries (optional fallback without key)
- **PWA** — installable, offline-capable service worker

## Project Structure

```
village-commerce/
├── supabase/
│   ├── schema.sql          # Full PostgreSQL schema + RLS
│   └── seed_categories.sql # Travel, Food, Labour, etc.
├── scripts/
│   └── import-villages.mjs # Import from indiaq.db
├── public/
│   ├── manifest.json
│   └── sw.js
└── src/
    ├── app/
    │   ├── page.tsx              # Landing
    │   ├── marketplace/          # Combined services & products
    │   ├── employment/           # Employment exchange
    │   ├── services/             # Service providers directory
    │   ├── products/             # Product marketplace
    │   ├── assistant/            # AI chat assistant
    │   ├── wallet/               # Qoins dashboard
    │   ├── delivery/             # Delivery agent dashboard
    │   ├── admin/                # Village Council panel
    │   ├── chat/                 # Realtime chat
    │   ├── reviews/              # Ratings & reviews
    │   ├── profile/              # User profile
    │   ├── register/             # Role registration flows
    │   ├── auth/login/           # Phone OTP login
    │   └── api/                  # REST API routes
    ├── components/
    └── lib/                      # wallet, geo, ai, delivery, verification
```

## Quick Start (Local)

### 1. Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Enable **Phone Auth** in Authentication → Providers
3. Run SQL in SQL Editor:
   - `supabase/schema.sql`
   - `supabase/seed_categories.sql`
4. Enable Realtime for `messages`, `delivery_tasks`, `orders`
5. Create storage bucket `product-images` (public read)

### 2. Environment

```bash
cd village-commerce
cp .env.example .env.local
# Fill in Supabase URL, anon key, service role key, OpenAI key
```

### 3. Install & Run

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### 4. Import Villages from indiaq.db

```bash
# Import first 1000 villages for dev (full import: remove --limit)
INDIAQ_DB_PATH=../indiaq.db npm run import-villages -- --limit 1000
```

### 5. Grant Village Council Role

After first login, promote a user in Supabase SQL:

```sql
UPDATE profiles
SET roles = ARRAY['customer','village_council']::user_role[]
WHERE phone = '+919876543210';
```

## Features Implemented

| Feature | Status |
|---------|--------|
| Phone OTP auth + village registration | ✅ |
| Role-based registration (4 flows) | ✅ |
| Verification queue + Council approve/reject | ✅ |
| Expandable categories (admin CRUD) | ✅ |
| Marketplace search (category, distance, rating) | ✅ |
| AI assistant with DB search | ✅ |
| Realtime chat (Supabase Realtime) | ✅ |
| Qoins wallet + escrow + ledger | ✅ |
| Hyperlocal delivery flow | ✅ |
| Ratings & reviews + AI trust summary | ✅ |
| Admin analytics dashboard | ✅ |
| PWA (manifest + service worker) | ✅ |
| Hindi-ready UI labels | ✅ |
| Aadhaar-ready profile fields | ✅ (structure only) |

## API Routes

| Route | Methods | Purpose |
|-------|---------|---------|
| `/api/villages` | GET | Search villages |
| `/api/categories` | GET, POST, PATCH | Category management |
| `/api/profile` | GET, POST | User profile |
| `/api/register` | GET, POST | Verification applications |
| `/api/marketplace` | GET | Search providers/products |
| `/api/orders` | GET, POST | Place orders + escrow |
| `/api/delivery` | GET, POST | Delivery agent tasks |
| `/api/wallet` | GET, POST | Balance & transfers |
| `/api/chat` | GET, POST | Chats & messages |
| `/api/reviews` | GET, POST | Ratings |
| `/api/ai` | POST | AI assistant |
| `/api/admin` | GET, POST | Council verification & analytics |

## Deployment (Vercel + Supabase)

### Vercel

```bash
npm i -g vercel
vercel
```

Set environment variables in Vercel dashboard:
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `OPENAI_API_KEY`
- `NEXT_PUBLIC_APP_URL` (your Vercel URL)

### Supabase Production

1. Run schema + seed on production project
2. Configure phone OTP provider (Twilio/MessageBird)
3. Set Site URL + redirect URLs to your Vercel domain
4. Import villages: run `import-villages.mjs` from CI or locally

### PWA Icons

Add `public/icons/icon-192.png` and `public/icons/icon-512.png` (saffron-themed) for install prompts.

## Database Tables

`villages`, `profiles`, `categories`, `verification_applications`, `employment_seekers`, `service_providers`, `product_sellers`, `products`, `delivery_agents`, `orders`, `order_items`, `delivery_tasks`, `chats`, `messages`, `wallets`, `transactions`, `reviews`, `disputes`, `village_economy_snapshots`, `fraud_flags`

## Integration with Qumanity (Flask)

This app is a standalone Next.js service that shares the **village ID format** from `indiaq.db` (`0.राम|IND/CS/...`). The Flask monolith at repo root can link to VELCS via:

- Village pages → `/marketplace?village_id=...`
- Shared Qoins concept (future sync via API)

## Security Notes

- Row Level Security enabled on sensitive tables
- Escrow handled server-side with service role
- Service role key **never** exposed to client
- Transaction metadata includes `blockchain_ready` flag for future ledger

## License

Part of the Qumanity project.
