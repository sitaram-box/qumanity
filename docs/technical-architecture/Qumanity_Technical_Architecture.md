<!--
GOOGLE DOCS IMPORT INSTRUCTIONS:
1. Upload this file: File → Open → Upload
2. Page Setup → 1 inch margins
3. Format → Line spacing → 1.5
4. Format → Font → Times New Roman, 11pt (body), 12pt (headings)
5. Insert → Table of Contents
6. Google Doc name: "Qumanity Technical Architecture Document"
7. Live Google Doc: https://docs.google.com/document/d/1wKAmj_L5sImaW92uVIExT58Dgy5B9yy3jSm0YV0otys/edit?usp=sharing
-->

# Qumanity Technical Architecture Document

**Version 1.0 | June 2026**

**Classification:** Internal / Developer Reference  
**Companion document:** [Qumanity White Paper](../white-paper/Qumanity_White_Paper.md)  
**AI context primer:** [QUMANITY_CONTEXT.md](../context/QUMANITY_CONTEXT.md)

---

## Table of Contents

1. [Document Purpose](#1-document-purpose)
2. [System Overview](#2-system-overview)
3. [Architecture Layers](#3-architecture-layers)
4. [Identity System](#4-identity-system)
5. [Geographic Hierarchy](#5-geographic-hierarchy)
6. [Four Timelines](#6-four-timelines)
7. [Governance Engine](#7-governance-engine)
8. [Qoin Economy](#8-qoin-economy)
9. [Database Schema](#9-database-schema)
10. [API Reference](#10-api-reference)
11. [Core Modules](#11-core-modules)
12. [PLNN — Planet-Level Nested Network](#12-plnn--planet-level-nested-network)
13. [Security Model](#13-security-model)
14. [Deployment](#14-deployment)
15. [UI Design System](#15-ui-design-system)
16. [Feature Implementation Status](#16-feature-implementation-status)
17. [Legal & Compliance Framework](#17-legal--compliance-framework)
18. [Budget Breakdown](#18-budget-breakdown)
19. [Team Roles (Detailed)](#19-team-roles-detailed)
20. [Migration Paths](#20-migration-paths)
21. [Appendices](#21-appendices)

---

## 1. Document Purpose

This document contains **all detailed technical specifications** for the Qumanity platform. It is the engineering companion to the concise [White Paper](../white-paper/Qumanity_White_Paper.md).

**Included here (not in White Paper):**
- Complete database schemas
- Full API endpoint catalogue
- PLNN node architecture
- Security implementation details
- Code module descriptions
- Deployment runbooks
- Legal analysis framework
- Detailed budget breakdown
- Team role specifications
- Migration paths

---

## 2. System Overview

### 2.1 Technology Stack

| Layer | Technology | Version / Notes |
| :--- | :--- | :--- |
| Runtime | Python | 3.12+ (Docker image: 3.14-slim) |
| Web framework | Flask | Served by Gunicorn in production |
| Database (dev) | SQLite | `indiaq.db` |
| Database (prod) | PostgreSQL | Via `DATABASE_URL` |
| Frontend | HTML, CSS, JavaScript | Bootstrap 5, Chart.js, D3.js |
| Config | `config.py` | Env-driven via python-dotenv |
| Container | Docker | Non-root `quantumuser`, HEALTHCHECK |
| Platforms | Render, Railway, Fly.io | See `DEPLOYMENT.md` |
| i18n | `translations.py` | 12 Indian languages |
| Astrology | `ephem` (optional) | Sidereal Lahiri; fallback approximation |
| Blockchain (planned) | Polygon | Schema stubs in `blockchain_core.py` |
| Mobile (planned) | Flutter | iOS / macOS, Phase 4 |

### 2.2 Repository Structure

```
Qumanity/
├── app.py                    # Main Flask app (11,000+ lines)
├── config.py                 # Centralised configuration
├── qoin_core.py              # Qoin economy, settlement
├── identity_core.py          # Dual-key IDs, OTP recovery
├── karma_core.py             # Karma ↔ Varna integration
├── planetary_core.py         # Birth chart, ephemeris (Ākāśa)
├── birth_chart.py            # Astrological calculations
├── varna_core.py             # Vidya/Raksha/Artha/Seva categories
├── leadership_core.py        # Council management
├── blockchain_core.py        # Blockchain schema stubs
├── language_core.py          # Multi-language
├── donation_core.py          # Donation flows
├── social_core.py            # Connections, messaging
├── element_core.py           # Five elements logic
├── global_core.py            # Global account stats
├── deceased_core.py          # Deceased user handling
├── referral_core.py          # Referral system
├── sita_platform_core.py     # SITA platform integration
├── scheduler.py              # Weekly settlement cron
├── init_db.py                # Database initialisation
├── templates/                # Jinja2 HTML templates
├── static/                   # CSS, JS, images, poems.json
├── knowledge/                # Stage contracts & references
├── docs/                     # White paper, architecture, context
├── Dockerfile
├── docker-compose.yml
├── render.yaml
├── railway.json
└── requirements.txt
```

### 2.3 Configuration

All settings flow through `config.py`. Do **not** scatter `os.environ.get` across the codebase.

**Required production variables:**

| Variable | Purpose |
| :--- | :--- |
| `FLASK_ENV` | `production` |
| `SECRET_KEY` | Flask session encryption |
| `QOIN_WALLET_ENCRYPTION_KEY` | Wallet data encryption |
| `DATABASE_URL` | Database connection string |

**Optional:**

| Variable | Purpose |
| :--- | :--- |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS` | SMTP for OTP / recovery |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | Email credentials |

`config.validate()` and `config.log_warnings()` run at startup.

---

## 3. Architecture Layers

### 3.1 Three-Layer Model

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: CITIZEN INTERFACES                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐    │
│  │  Kiosk   │  │  Website │  │  iOS / macOS App     │    │
│  │ (touch)  │  │ (Flask)  │  │  (Flutter, Phase 4)  │    │
│  └────┬─────┘  └────┬─────┘  └──────────┬───────────┘    │
└───────┼─────────────┼─────────────────────┼────────────────┘
        │             │                     │
┌───────▼─────────────▼─────────────────────▼────────────────┐
│  LAYER 2: APPLICATION (app.py + core modules)                │
│  Identity │ Governance │ Economy │ Social │ Calendar │ Admin │
└───────┬──────────────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────┐
│  LAYER 3: PLNN (Planet-Level Nested Network)                 │
│  Village Node → Tehsil Node → District → State → National     │
│  → Planetary Backbone → Optional Blockchain Anchor            │
└───────┬──────────────────────────────────────────────────────┘
        │
┌───────▼──────────────────────────────────────────────────────┐
│  DATA LAYER: SQLite / PostgreSQL + Encrypted Wallets          │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Request Flow

1. Citizen authenticates (session cookie or kiosk biometric)
2. `app.py` route handler resolves user's four timelines
3. Geographic scope filtered by `current_location_id`
4. Business logic delegated to `*_core.py` modules
5. Database read/write via SQLite/PostgreSQL
6. JSON response (API) or Jinja2 render (pages)
7. Pending transactions queued for weekly settlement

---

## 4. Identity System

### 4.1 Dual-Key Model

| ID Type | Field | Basis | Mutable |
| :--- | :--- | :--- | :--- |
| Private ID | `private_id` | Birth location | No |
| Public ID | `public_id` | Present location | Yes (on relocation) |

### 4.2 ID Format

```
[RandomPrefix]-[FirstInitial][LastInitial]-[GenderCode][AgeCode]-[ElementCode][SignCode]-[LocationPath]
```

| Component | Values | Example |
| :--- | :--- | :--- |
| RandomPrefix | 3–4 alphanumeric | `X7K` |
| GenderCode | `M`, `F`, `O` | `M` |
| AgeCode | `B`, `Y`, `V`, `S` | `Y` (Yuvak) |
| ElementCode | `F`, `E`, `A`, `W` | `F` (Fire) |
| SignCode | First letter of sun sign | `L` (Leo) |
| LocationPath | Zone.State.District.Tehsil.Village | `CS.DL.5.4.1E` |

**Admin exception:** `H_U_ADMIN` — does not follow format.

**Example (Rohit Mudgal):**
- Private: `X7K-RM-GM-AY-FL-CS.DL.1.A.12`
- Public: `X7K-RM-GM-AY-FL-CS.DL.5.4.1E`

### 4.3 Multi-Account Support

`user_accounts` table allows multiple public accounts per private ID (one per location the user has lived in).

### 4.4 Recovery

- Birth-location verification via `/recovery`
- OTP via email/phone (`otp_verification` table)
- Password reset without exposing private data

### 4.5 User Types

| Type | Code | Vote | Post | Council |
| :--- | :--- | :---: | :---: | :---: |
| Human User | `H_U` | ✅ | ✅ | ✅ |
| Demo User | `D_U` | ✅ | ✅ | ❌ |
| Admin | `H_U_ADMIN` | ✅ | ✅ | ✅ (Mentor) |

### 4.6 Age Groups (Ashrama)

| Group | Code | Age | Council Nomination |
| :--- | :--- | :--- | :--- |
| Balak | `B` | 0–24 | No (vote if ≥ 13) |
| Yuvak | `Y` | 25–49 | Yes |
| Vridh | `V` | 50–75 | No |
| Sanyas | `S` | 75+ | No |

### 4.7 Access Matrix by Location

| Type | Birth India | Present India | Public Account | Voting |
| :--- | :---: | :---: | :--- | :---: |
| A (Indian abroad) | ✅ | ❌ | Birth only | ❌ |
| B (Foreigner in India) | ❌ | ✅ | Present | ✅ |
| C (Foreigner abroad) | ❌ | ❌ | ❌ | ❌ |
| D (Indian in India) | ✅ | ✅ | Present | ✅ |

---

## 5. Geographic Hierarchy

### 5.1 Levels

| Level | Code | Example |
| :--- | :--- | :--- |
| 0 — Planet | Earth | `0.राम\|` |
| 1 — Continent | Asia | — |
| 2 — Country | India | `IND` |
| 3 — Zone | Central State | `CS` |
| 4 — State | Delhi | `DL` |
| 5 — District | North West Delhi | `5` |
| 6 — Tehsil | Bawana | `4` |
| 7 — Village | Rohini Sector-24 | `1E` |
| 8 — Citizen | Individual | — |

### 5.2 India Zones

| Code | Name |
| :--- | :--- |
| `CS` | Central State (UT & North-East) |
| `NS` | North India State |
| `WS` | West India State |
| `SS` | South India State |
| `ES` | East India State |

### 5.3 Collective Boards

| Level | English | Hindi |
| :--- | :--- | :--- |
| Village | CVB | संयुक्त ग्राम मंडल |
| Tehsil | CTB | संयुक्त तहसील मंडल |
| District | CDB | संयुक्त जिला मंडल |
| State | CSB | संयुक्त राज्य मंडल |
| Country | CCB | संयुक्त देश मंडल |
| Continent | CCOB | संयुक्त महाद्वीप मंडल |
| Earth | CEB | संयुक्त पृथ्वी मंडल |

---

## 6. Four Timelines

| Account | Screen | Based On | Key Features |
| :--- | :--- | :--- | :--- |
| Private (Y1) | Left top | Birth | Profile, wallet, messages, history |
| Personal (Y2) | Left middle | Family + social | PCB, posts, family tree |
| Public (Y3) | Left bottom | Present | CVB, elections, marketplace |
| Global (Y4) | Left alternate | Earth → Country | Stats, CEB |

Zone tab in Global Account appears only for users with India as birth or present location.

---

## 7. Governance Engine

### 7.1 Post Escalation (India)

| Level | Days | Next (if score > 0) | Qoin Reward |
| :--- | :--- | :--- | :--- |
| Personal | 1–7 | Village | ₹1 |
| Village | 8–14 | Tehsil | ₹2 |
| Tehsil | 15–21 | District | ₹10 |
| District | 22–28 | State | ₹20 |
| State | 29–35 | Country | ₹30 |
| Country | 36–42 | Continent | ₹50 |
| Continent | 43–49 | Earth | ₹100 |
| Earth | 50–56 | Archive | ₹200 |

**Rules:**
- Score resets to 0 at each escalation
- Score ≤ 0 → Private Account "Previous Posts"
- One vote per user per post; authors cannot self-vote
- Positive posts stored in Freeze tab at each level

### 7.2 Post Escalation (Global, outside India)

| Level | Days | Next | Reward |
| :--- | :--- | :--- | :--- |
| Personal | 1–35 | Country | ₹1 |
| Country | 36–42 | Continent | ₹50 |
| Continent | 43–49 | Earth | ₹100 |
| Earth | 50–56 | Archive | ₹200 |

### 7.3 Zodiac Elections

**Element-based voting:**

| Zodiac Cycle | Element | Voters |
| :--- | :--- | :--- |
| Taurus, Virgo, Capricorn | Earth | Earth members |
| Gemini, Libra, Aquarius | Air | Air members |
| Cancer, Scorpio, Pisces | Water | Water members |
| Aries, Leo, Sagittarius | Fire | Fire members |

**Nomination requirements:**
- Yuvak (25–49), matching sun sign, Male/Female, village resident

### 7.4 Zodiac Mapping

| Sign | Element | Code | Dates |
| :--- | :--- | :--- | :--- |
| Aries | Fire | `FA` | Mar 21 – Apr 19 |
| Taurus | Earth | `ET` | Apr 20 – May 20 |
| Gemini | Air | `AG` | May 21 – Jun 20 |
| Cancer | Water | `WC` | Jun 21 – Jul 22 |
| Leo | Fire | `FL` | Jul 23 – Aug 22 |
| Virgo | Earth | `EV` | Aug 23 – Sep 22 |
| Libra | Air | `AL` | Sep 23 – Oct 22 |
| Scorpio | Water | `WS` | Oct 23 – Nov 21 |
| Sagittarius | Fire | `FS` | Nov 22 – Dec 21 |
| Capricorn | Earth | `EC` | Dec 22 – Jan 19 |
| Aquarius | Air | `AA` | Jan 20 – Feb 18 |
| Pisces | Water | `WP` | Feb 19 – Mar 20 |

### 7.5 Council Roles

| Role | Responsibility |
| :--- | :--- |
| Mentor | Spiritual/ethical guidance |
| Nayak / Nayika | Elected leader (M/F) |
| Manager | Operations |
| Agent | Kiosk operator |
| Volunteer | Outreach |

### 7.6 Varna System

Four categories scored from verified actions:

| Category | Sanskrit | Domain |
| :--- | :--- | :--- |
| Vidya | विद्या | Education, teaching |
| Raksha | रक्षा | Governance, justice, security |
| Artha | अर्थ | Commerce, economy |
| Seva | सेवा | Service, tree planting, community |

Karma actions map to categories (e.g., `teach_hour` → vidya, `council_day` → raksha).

### 7.7 Permissions Matrix

| Feature | Demo | Human | Admin |
| :--- | :---: | :---: | :---: |
| Dashboard, posts, votes | ✅ | ✅ | ✅ |
| Karma, wallet, family, messages | ✅ | ✅ | ✅ |
| Council nomination | ❌ | ✅ | ✅ |
| Manage nominations | ❌ | ❌ | ✅ |
| Upgrade accounts | ❌ | ❌ | ✅ |
| Admin reports | ❌ | ❌ | ✅ |

---

## 8. Qoin Economy

### 8.1 Denominations

```python
DENOMINATIONS = (2000, 500, 200, 100, 50, 20, 10, 5, 2, 1)
```

**Rule:** No single Qoin holds any other value. ₹7 = ₹5 + ₹2.

### 8.2 Greedy Algorithm

```python
def min_qoins_for_amount(amount):
    qoins = []
    remaining = amount
    for denom in [2000, 500, 200, 100, 50, 20, 10, 5, 2, 1]:
        while remaining >= denom:
            qoins.append(denom)
            remaining -= denom
    return qoins
```

### 8.3 Weekly Settlement

- Transactions recorded in `pending_transactions` during the week
- `scheduler.py` runs `process_weekly_settlement()` Sunday 23:59
- Net rupee amounts converted to Qoins via greedy algorithm
- Qoins transferred from payer to payee
- `weekly_statements` generated for active users

### 8.4 Transaction Types

| Type | Distribution |
| :--- | :--- |
| Commercial | 100% to seller |
| Donation | 50% ethical return + 50% split (20% × 5 levels) |
| Contribution (karma) | Minted from governance container |
| Subscription | 100% to kiosk container |

### 8.5 Karma Actions

| Action | Code | Value | Verification | Followup |
| :--- | :--- | :--- | :---: | :---: |
| Plant a tree | `plant_tree` | ₹10 | ✅ | 180 days |
| Teach 1 hour | `teach_hour` | ₹20 | ✅ | — |
| Help elder | — | ₹15 | ✅ | — |
| Council day | `council_day` | ₹50 | ✅ | — |
| Report issue | `report_issue` | ₹5 | ❌ | — |
| Clean village | — | ₹10 | ✅ | — |

**Tree planting:** 50% upfront (₹5), 50% after 6 months if tree survives.

### 8.6 Karma Claim Workflow

1. User submits claim with proof (photo, GPS, witness)
2. Village Council reviews
3. Approved → Qoins credited
4. Rejected → message with reason

### 8.7 Nested Wallets

| Owner Type | Owner ID Example |
| :--- | :--- |
| `user` | Private ID |
| `village` | Village ID |
| `tehsil` | Tehsil ID |
| `district` | District ID |
| `state` | State ID |
| `nation` | `IND` |
| `kiosk` | Kiosk ID |
| `governance` | `mint` |

---

## 9. Database Schema

### 9.1 User Management

**`users`**

| Column | Type | Notes |
| :--- | :--- | :--- |
| `private_id` | TEXT PK | Birth-based, immutable |
| `public_id` | TEXT | Present-location-based |
| `first_name`, `last_name` | TEXT | |
| `gender` | TEXT | M/F/O |
| `date_of_birth` | DATE | Drives sun sign, age group |
| `sun_sign`, `element` | TEXT | Calculated |
| `current_location_id` | TEXT | Present village |
| `birth_location_id` | TEXT | Birth village |
| `wallet` | TEXT (JSON) | Encrypted Qoin denominations |
| `password_hash` | TEXT | bcrypt |
| `blockchain_user_hash` | TEXT | Phase 3 |
| `identity_commitment` | TEXT | Phase 3 |

**`user_accounts`** — multiple public accounts per user

**`user_roles`** — Volunteer, Agent, Manager, Leader, Mentor

**`user_education`**, **`user_work`** — profile history

**`otp_verification`** — email/phone OTP for recovery

### 9.2 Content & Social

**`posts`**

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | INTEGER PK | |
| `content` | TEXT | |
| `user_private_id` | TEXT FK | |
| `current_level` | TEXT | personal/village/.../earth |
| `status` | TEXT | live/archived/frozen |
| `total_score` | INTEGER | Net votes |
| `level_start_time` | TIMESTAMP | Escalation timer |

**`post_votes`** — `post_id`, `voter_private_id`, `vote_value` (+1/0/−1)

**`messages`** — private inbox

**`connection_requests`** — family/social requests

### 9.3 Economy

**`wallets`** — `owner_type`, `owner_id`, `balance_qoins` (JSON)

**`pending_transactions`** — weekly settlement queue

**`wallet_transactions`** — settled transaction log

**`weekly_statements`** — `user_private_id`, `week_start`, `week_end`, `statement_data` (JSON)

**`karma_action_types`** — predefined actions with rupee values

**`karma_transactions`** — claim records with verification status

### 9.4 Governance

**`election_cycles`** — zodiac period, village, status

**`election_candidates`** — nominees with approval status

**`election_votes`** — voter, candidate, timestamp

**`leadership_council`** — Mentor, Nayak, Nayika, Manager, Agent per location

### 9.5 Family

**`family_members`** — tree nodes

**`family_relationships`** — edges (parent, spouse, sibling)

**`family_removal_requests`** — admin approval queue

### 9.6 Geography

**`state`**, **`district`**, **`tehsil`**, **`village`** — nested hierarchy

**`location_translations`** — i18n location names

**`state_languages`** — state → default language

### 9.7 Varna

**`varna_profiles`** — vidya/raksha/artha/seva scores per user

**`category_history`** — historical score snapshots

### 9.8 Planetary (Ākāśa)

**`birth_charts`** — planetary positions at birth

**`daily_ephemeris`** — sun/moon positions for calendar

### 9.9 Blockchain (Phase 3 Stubs)

**`blockchain_sync`** — `last_processed_block`, `chain_name` (default: polygon), `sync_status`

Additional columns on `users`: `user_registration_tx_hash`, `last_sync_block`

---

## 10. API Reference

### 10.1 Design Principles

- All `/api/*` routes return JSON
- `@login_required` on protected endpoints
- 401: `{"error": "Unauthorized"}`
- Exceptions: `{"error": str(e)}` — never raw tracebacks

### 10.2 Authentication

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/register` | GET, POST | Registration form / submit |
| `/login` | GET, POST | Authentication |
| `/recovery` | GET | Password/ID recovery |
| `/api/recovery/verify` | POST | Birth-location verification |

### 10.3 Geography

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/continents` | GET | List continents |
| `/api/countries` | GET | List countries |
| `/api/states` | GET | List states |
| `/api/states/<country_id>` | GET | States by country |
| `/api/country/<country_id>/states` | GET | States for country |
| `/api/country/<country_id>/languages` | GET | Languages for country |
| `/api/districts` | GET | Districts (filtered) |
| `/api/tehsils` | GET | Tehsils (filtered) |
| `/api/villages` | GET | Villages (filtered) |
| `/api/geo-search` | GET | Search locations |

### 10.4 Posts & Voting

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/posts` | GET | Posts for current level |
| `/api/post/create` | POST | Create post |
| `/api/post/vote` | POST | Vote (+1/0/−1) |

### 10.5 Economy

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/qoin/balance` | GET | Wallet balance |
| `/api/qoin/transfer` | POST | Queue transfer (weekly) |
| `/api/qoin/transactions` | GET | Transaction history |
| `/api/karma/claim` | POST | Submit karma claim |

### 10.6 Elections

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/election/status` | GET | Current election phase |
| `/api/election/nominate` | POST | Submit candidacy |
| `/api/election/vote` | POST | Vote for candidate |
| `/api/admin/nomination/approve` | POST | Admin approve |
| `/api/admin/nomination/reject` | POST | Admin reject |

### 10.7 Family & Social

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/family/tree` | GET | Family tree data |
| `/api/family/add_member` | POST | Add member |
| `/api/connection/request` | POST | Send connection request |
| `/api/connection/accept` | POST | Accept request |

### 10.8 Messaging

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/messages/inbox` | GET | Received messages |
| `/api/messages/send` | POST | Send message |
| `/api/messages/read` | POST | Mark as read |

### 10.9 Calendar

| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/calendar/solar-months` | GET | Solar month data |
| `/api/calendar/events` | GET | Calendar events |
| `/api/calendar/user-birthdays` | GET | Birthday data |

### 10.10 Page Routes (HTML)

| Route | Purpose |
| :--- | :--- |
| `/` | Homepage |
| `/dashboard` | Four-timeline dashboard |
| `/about`, `/about-details` | About pages |
| `/contact` | Contact form |
| `/calendar` | Solar calendar |
| `/settings` | User settings |
| `/location/<level>/<id>` | Geography statistics |
| `/admin/panel` | Admin dashboard |
| `/admin/*` | Admin sub-pages (elections, karma, donations, etc.) |

---

## 11. Core Modules

### 11.1 `app.py`

Main Flask application. Routes, session management, template rendering, API endpoints. Planned incremental split into Blueprints (`routes_auth`, `routes_api`, `routes_dashboard`, `routes_admin`).

### 11.2 `qoin_core.py`

- Fixed denomination logic
- `min_qoins_for_amount()` greedy algorithm
- Wallet CRUD (user + nested geographic wallets)
- `pending_transactions` queue
- `process_weekly_settlement()`
- `weekly_statements` generation
- Karma minting from governance container
- Donation split logic

### 11.3 `identity_core.py`

- Private/Public ID generation
- `user_accounts` multi-location support
- OTP verification (email/phone)
- Birth-location recovery
- Sun sign and element calculation from DOB

### 11.4 `planetary_core.py`

- Birth chart storage (Ākāśa / Space layer)
- Daily ephemeris via `ephem` (sidereal Lahiri)
- Fallback day-of-year approximation
- Integration with solar calendar

### 11.5 `varna_core.py`

- Vidya/Raksha/Artha/Seva scoring
- Category affinity for karma actions
- Bonus multipliers based on dominant category
- Category history tracking

### 11.6 `karma_core.py`

- Stable import path for karma ↔ varna integration
- Re-exports wallet helpers from `qoin_core`

### 11.7 `leadership_core.py`

- Council member management
- Election cycle coordination
- Role assignment (Mentor, Nayak, Nayika, etc.)

### 11.8 `blockchain_core.py`

- Idempotent schema migrations for Phase 3
- `blockchain_sync` table
- Hash columns on `users` table
- Default chain: Polygon

### 11.9 `language_core.py` + `translations.py`

- 12 Indian language support
- State → default language mapping
- Location name translations

### 11.10 `donation_core.py`

- Registration donation flows
- Donation split across nested wallets
- Admin donation reports

### 11.11 `social_core.py`

- Connection requests
- Messaging helpers

### 11.12 `scheduler.py`

- Weekly settlement cron job
- Background task scheduling

### 11.13 `config.py`

- Single source of truth for all env vars
- `validate()` and `log_warnings()` at startup

---

## 12. PLNN — Planet-Level Nested Network

### 12.1 Overview

**PLNN** (Planet-Level Nested Network) is the distributed data infrastructure layer that synchronises governance data across geographic nodes without requiring a single central server.

### 12.2 Node Hierarchy

| Node Type | Scope | Responsibilities |
| :--- | :--- | :--- |
| **Village Node** | Single village | Kiosk sync, local posts, council data, offline cache |
| **Tehsil Node** | Tehsil | Aggregate village data, regional escalation |
| **District Node** | District | District-level boards, karma verification relay |
| **State Node** | State | State boards, language defaults |
| **National Node** | Country | CCB, national statistics, policy config |
| **Planetary Backbone** | Earth | CEB, global sync, blockchain anchor |

### 12.3 Sync Protocol (Planned)

```
Village Node
  │ periodic push (HTTPS / WebSocket)
  ▼
Tehsil Node
  │ aggregate + conflict resolution
  ▼
District Node → State Node → National Node → Planetary Backbone
  │
  ▼
Blockchain Anchor (Polygon) — hash of weekly settlement Merkle root
```

### 12.4 Offline-First Strategy

1. Kiosk maintains local SQLite replica
2. Actions queued when connectivity lost
3. On reconnect, delta sync to parent node
4. Conflict resolution: timestamp + council authority at level
5. Weekly settlement computed at tehsil level minimum

### 12.5 Data Partitioning

| Data Type | Stored At | Synced To |
| :--- | :--- | :--- |
| User profile (private) | Birth village node | User's current village |
| Posts (personal) | Author's village | Escalation path |
| Posts (public level) | Current level node | Parent on escalation |
| Qoin wallets | Owner's node | Parent on cross-level transfer |
| Elections | Village node | Tehsil (results only) |
| Birth charts | Birth village | Read-only replicate to user |

### 12.6 Status

⏳ Phase 3 — schema and sync protocol designed; implementation not yet started. Current prototype uses single-server SQLite/PostgreSQL.

---

## 13. Security Model

### 13.1 Authentication

| Mechanism | Usage |
| :--- | :--- |
| Session cookies | Web login (`SECRET_KEY` signed) |
| bcrypt | Password hashing |
| OTP | Email/phone recovery |
| Biometric (planned) | Kiosk fingerprint/face |
| Birth-location challenge | ID recovery |

### 13.2 Encryption

| Data | Method |
| :--- | :--- |
| Qoin wallets | `QOIN_WALLET_ENCRYPTION_KEY` (Fernet/AES) |
| Sessions | Flask signed cookies |
| Passwords | bcrypt |
| Transit | HTTPS (production requirement) |

### 13.3 Container Security

- Docker runs as non-root `quantumuser`
- `HEALTHCHECK` polls `/` every 30s
- No secrets in image layers — env vars only
- `.env` and `*.db` in `.gitignore`

### 13.4 API Security

- `@login_required` on protected routes
- Admin routes check `H_U_ADMIN` or role
- Rate limiting (planned)
- CSRF protection on form submissions
- `data-qb-submitting` prevents double-submit

### 13.5 Data Privacy

| Principle | Implementation |
| :--- | :--- |
| Data sovereignty | Users own data; no third-party sales |
| Timeline separation | Private data not exposed on Public boards |
| Minimal collection | Only governance-required fields |
| Council verification | Karma claims need local approval |
| Right to deletion | Deceased marking + family removal requests |

### 13.6 Logging

- Python `logging` module (not `print`)
- No passwords or wallet keys in logs
- User-friendly error messages (no tracebacks to client)

### 13.7 Production Checklist

- [ ] `FLASK_ENV=production`
- [ ] Strong `SECRET_KEY` (48+ char random)
- [ ] Strong `QOIN_WALLET_ENCRYPTION_KEY`
- [ ] HTTPS enabled
- [ ] PostgreSQL for production data
- [ ] Persistent volume at `/data`
- [ ] Health check passing
- [ ] `config.validate()` clean

---

## 14. Deployment

### 14.1 Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 init_db.py
python3 app.py
# → http://127.0.0.1:5000
```

### 14.2 Docker

```bash
docker build -t qumanity .
docker run -d --name qumanity \
  -p 5000:5000 \
  -e SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e QOIN_WALLET_ENCRYPTION_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
  -e FLASK_ENV=production \
  -v qumanity_data:/data \
  qumanity
```

Or: `docker compose up -d --build`

### 14.3 Render

1. Push to GitHub
2. New → Blueprint → select repo
3. Set env vars: `SECRET_KEY`, `QOIN_WALLET_ENCRYPTION_KEY`, `FLASK_ENV=production`
4. Add persistent disk at `/data` (if SQLite)
5. Deploy (auto-detects Dockerfile)

### 14.4 Railway

1. Import GitHub repo
2. Add volume at `/data`
3. Set environment variables
4. Deploy via `railway.json` config

### 14.5 Fly.io

See `DEPLOYMENT.md` for `fly.toml` configuration.

### 14.6 Kiosk Deployment

| Spec | Requirement |
| :--- | :--- |
| Hardware | Touchscreen PC/tablet, ≥ 10" display |
| OS | Linux or locked-down browser kiosk mode |
| Connectivity | 4G/5G or village broadband |
| Location | Panchayat office, community centre, market |
| Hours | Daylight; agent-assisted |
| Auth | PIN + biometric (Phase 4) |
| Sync | PLNN village node (Phase 3) |

### 14.7 Database Migration (SQLite → PostgreSQL)

1. Set `DATABASE_URL` to PostgreSQL connection string
2. Run `init_db.py` against new database
3. Export SQLite data via migration script (planned)
4. Verify wallet encryption keys unchanged
5. Run integration tests on staging

---

## 15. UI Design System

### 15.1 CSS Tokens (`static/style.css`)

| Token | Value | Usage |
| :--- | :--- | :--- |
| `--qb-bg` | `#0F172A` | Body background |
| `--qb-surface` | `#1E293B` | Cards, panels |
| `--qb-border` | `#475569` | Borders |
| `--qb-primary` | `#F59E0B` | Primary buttons (black text) |
| `--qb-secondary` | `#3B82F6` | Secondary buttons (white text) |
| `--qb-danger` | `#EF4444` | Danger buttons |
| `--qb-success` | `#10B981` | Success text |
| `--qb-warning` | `#FBBF24` | Warning text |

### 15.2 Brand Colours

| Name | Hex | Usage |
| :--- | :--- | :--- |
| Saffron | `#FF9933` | India accent |
| Green | `#138808` | Success, Earth |
| Gold | `#FFD700` | Spiritual highlights |
| Navy | `#0A1929` | Trust, depth |
| SITA Green | `#2D5016` | Foundation branding |

### 15.3 Components

- Buttons: `.qb-btn` + variant classes
- Neutral/back: `.qb-btn-neutral` (not secondary)
- Notifications: `window.qbToast(message, type)`
- Loading: `.qb-spinner`
- Forms: `data-qb-submitting` double-submit guard
- Accessibility: skip-to-content, `:focus-visible`, `aria-live`

### 15.4 Typography

- Font: `Inter, system-ui, -apple-system, "DM Sans", sans-serif`
- Base: 16px
- Weights: 400 normal, 500 medium, 600 headings, 700 bold
- Contrast: WCAG 2.1 AA (≥ 4.5:1)

---

## 16. Feature Implementation Status

### 16.1 Complete

| Feature | Key Files |
| :--- | :--- |
| Registration & login | `app.py`, `identity_core.py` |
| Location hierarchy | `indiaq.db`, `location.html` |
| 12 languages | `translations.py`, `language_core.py` |
| Posts & voting | `app.py`, `dashboard.js` |
| Post escalation | `app.py`, `qoin_core.py` |
| Qoin wallet | `qoin_core.py` |
| Weekly settlement | `scheduler.py`, `qoin_core.py` |
| Family tree | `family_tree.js` (D3.js) |
| Messaging | `social_core.py` |
| Admin panel | `app.py`, admin templates |
| Poem marquee (237) | `marquee.js`, `poems.json` |
| Toast notifications | `toast.js` |
| Docker | `Dockerfile` |

### 16.2 Partial

| Feature | Remaining |
| :--- | :--- |
| Zodiac elections | Voting UI, winner declaration |
| Council management | Appoint/remove, term tracking |
| Justice module | Formal adjudication workflow |
| Varna dashboard | Public-facing category display |

### 16.3 Planned

| Feature | Phase | Priority |
| :--- | :--- | :--- |
| Marketplace | 3 | High |
| Job portal | 3 | Medium |
| PLNN nodes | 3 | High |
| Blockchain ledger | 3 | Medium |
| iOS/macOS app | 4 | High |
| Biometric auth | 4 | High |
| Offline-first sync | 4 | High |
| AI recommendation | 5 | Medium |
| Voice interface | 5 | Low |

---

## 17. Legal & Compliance Framework

### 17.1 Regulatory Positioning

Qumanity is positioned as **public digital infrastructure**, not a financial institution, social media company, or government body.

| Area | Position |
| :--- | :--- |
| Qoins | Community reward tokens, not legal tender; weekly settlement, not real-time exchange |
| Elections | Community advisory councils, not statutory elections |
| Data | User-sovereign; DPDP Act 2023 compliance target |
| Kiosks | Public access points, not banking correspondents |

### 17.2 India-Specific Compliance

| Regulation | Relevance | Approach |
| :--- | :--- | :--- |
| DPDP Act 2023 | Personal data protection | Consent, purpose limitation, data localisation |
| IT Act 2000 | Electronic records | Signed logs, audit trails |
| Panchayati Raj Act | Local governance alignment | CVB mirrors gram sabha principles |
| RBI guidelines | Not a payment system | Qoins are karma rewards, not e-money |
| Geospatial guidelines | Location data | India geospatial data stored in India |

### 17.3 Intellectual Property

- Code: Open source (GitHub)
- Brand: SITA Foundation trademark (Qumanity, logo)
- Poems: Vinaya Patrika (public domain / attributed)

### 17.4 Liability

- Platform provides infrastructure, not legal advice
- Council decisions are advisory unless adopted by statutory bodies
- Karma verification is community-based, not judicial

### 17.5 Required Legal Work (Pre-Pilot)

- [ ] DPDP compliance audit
- [ ] Terms of service and privacy policy
- [ ] Kiosk placement agreements with panchayats
- [ ] Qoin disclaimer (not legal tender)
- [ ] Data processing agreements for hosting providers

---

## 18. Budget Breakdown

### 18.1 Pilot Phase (50 Villages, 1 District, 12 Months)

| Category | Item | Qty | Unit Cost (INR) | Total (INR) |
| :--- | :--- | ---: | ---: | ---: |
| **Hardware** | Kiosk (touchscreen PC + enclosure) | 50 | ₹40,000–80,000 | ₹20–40 lakh |
| **Hardware** | UPS + solar backup (remote villages) | 20 | ₹15,000 | ₹3 lakh |
| **Connectivity** | 4G annual plan per kiosk | 50 | ₹6,000–12,000 | ₹3–6 lakh |
| **Development** | Phase 3 dashboard + elections UI | — | — | ₹15–25 lakh |
| **Development** | Phase 4 mobile app (Flutter) | — | — | ₹20–40 lakh |
| **Development** | PLNN prototype (3 node types) | — | — | ₹10–20 lakh |
| **Personnel** | Community agents (stipend) | 50 | ₹3,000/mo × 12 | ₹18 lakh |
| **Personnel** | Lead developer (12 months) | 1 | ₹1.5–2.5 lakh/mo | ₹18–30 lakh |
| **Personnel** | Governance designer (6 months) | 1 | ₹1–1.5 lakh/mo | ₹6–9 lakh |
| **Training** | Agent + council training workshops | 5 | ₹1–2 lakh | ₹5–10 lakh |
| **Legal** | DPDP audit, ToS, agreements | — | — | ₹5–10 lakh |
| **Hosting** | Cloud (Render/Railway, 12 months) | — | — | ₹1–3 lakh |
| **Contingency** | 15% | — | — | ₹15–25 lakh |
| | | | **Total** | **₹1.1–2.4 crore** |

### 18.2 National Rollout (Estimate, Phase 6)

| Item | Estimate |
| :--- | :--- |
| 6 lakh villages × kiosk | ₹2,400–4,800 crore (hardware) |
| Annual connectivity | ₹360–720 crore |
| Development & maintenance | ₹100–200 crore/year |
| Training & agents | ₹200–400 crore (initial) |

*National rollout requires government partnership or phased NGO/foundation funding.*

---

## 19. Team Roles (Detailed)

### 19.1 Leadership

| Role | Responsibilities | Skills |
| :--- | :--- | :--- |
| **Founder / Mentor** | Vision, ethics, SITA Foundation governance, external partnerships | Philosophy, governance design, public speaking |
| **Technical Lead** | Architecture, code review, deployment, security | Python, Flask, PostgreSQL, Docker, system design |

### 19.2 Development

| Role | Responsibilities | Skills |
| :--- | :--- | :--- |
| **Backend Developer** | `app.py`, `*_core.py` modules, API, database | Python, SQLite/PostgreSQL, REST |
| **Frontend Developer** | Templates, CSS tokens, dashboard JS, accessibility | HTML/CSS/JS, Bootstrap, WCAG |
| **Mobile Developer** | Flutter iOS/macOS app, offline sync | Dart, Flutter, SQLite |
| **DevOps Engineer** | Docker, CI/CD, monitoring, PLNN node deployment | Docker, Render/Railway, Linux |

### 19.3 Governance

| Role | Responsibilities | Skills |
| :--- | :--- | :--- |
| **Governance Designer** | Election rules, escalation logic, council structures | Political science, Indian panchayati raj |
| **Community Agent** | Kiosk operation, citizen onboarding, local support | Local language, empathy, basic tech |
| **Council Mentor** | Ethical guidance, dispute mediation | Village leadership experience |

### 19.4 Operations

| Role | Responsibilities | Skills |
| :--- | :--- | :--- |
| **Legal Advisor** | DPDP, ToS, kiosk agreements, regulatory positioning | Indian IT/privacy law |
| **Finance Manager** | Budget, donations, Qoin economy auditing | Accounting, NGO finance |
| **Training Coordinator** | Agent workshops, council orientation | Adult education, curriculum design |

---

## 20. Migration Paths

### 20.1 `app.py` Blueprint Split

Current: monolithic `app.py` (11,000+ lines).

Planned modules:
- `routes_auth.py` — register, login, recovery
- `routes_api.py` — all `/api/*` endpoints
- `routes_dashboard.py` — dashboard, calendar, settings
- `routes_admin.py` — admin panel routes
- `routes_geo.py` — location pages and geo API

Migration: incremental extraction, one blueprint at a time, with regression testing.

### 20.2 SQLite → PostgreSQL

1. Add PostgreSQL-compatible DDL (replace `AUTOINCREMENT` → `SERIAL`)
2. Create `scripts/migrate_sqlite_to_pg.py`
3. Test on staging with full seed data
4. Update `DATABASE_URL` in production
5. Verify wallet encryption compatibility

### 20.3 Qoin Core → Karma Core

`karma_core.py` is the stable import path. Gradual migration of wallet helpers from `qoin_core` re-exports to native `karma_core` implementations.

### 20.4 Single Server → PLNN

1. Phase 3a: Read-replica at tehsil level
2. Phase 3b: Village node with offline SQLite
3. Phase 3c: Sync protocol between village ↔ tehsil
4. Phase 3d: Full hierarchy sync
5. Phase 3e: Blockchain anchor for weekly settlement Merkle roots

### 20.5 Web → Mobile

1. Extract API contracts from current `/api/*` routes
2. Build Flutter app against same API
3. Add offline cache layer (local SQLite)
4. Add biometric auth for kiosk mode
5. Shared design tokens (colours, typography)

---

## 21. Appendices

### Appendix A: Environment Variables (Complete)

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
QOIN_WALLET_ENCRYPTION_KEY=your-encryption-key-here
DATABASE_URL=sqlite:///indiaq.db
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
```

### Appendix B: Demo Login Credentials

| User | Private ID | Password |
| :--- | :--- | :--- |
| Admin | `H_U_ADMIN` | `Admin123` |
| Demo (Taurus) | `D_UI_Y_TAURUS_0001` | `Demo123` |

### Appendix C: Seed Scripts

```bash
python3 init_db.py
python3 seed_demo_users.py
python3 seed_taurus_users.py
```

### Appendix D: Cursor AI Rules

| Rule File | Purpose |
| :--- | :--- |
| `.cursor/rules/qbox-core.mdc` | Core architecture |
| `.cursor/rules/qoin-economy.mdc` | Qoin denominations, settlement |
| `.cursor/rules/ui-guidelines.mdc` | Design tokens, accessibility |
| `.cursor/rules/production-checklist.mdc` | Deployment checklist |

### Appendix E: Knowledge Base Index

| Folder | Contents |
| :--- | :--- |
| `knowledge/01_identity/` | User types, age, zodiac, IDs |
| `knowledge/02_routing/` | Geography, timelines, access |
| `knowledge/03_stage_contracts/` | Posts, voting, Qoins, karma |
| `knowledge/04_references/` | Schema, APIs, file structure |
| `knowledge/05_artifacts/` | Features, logo, colours |
| `knowledge/06_development/` | Setup, deploy, Git, troubleshooting |
| `knowledge/07_cursor_rules/` | AI rule references |

---

**© 2026 SITA Foundation. All rights reserved.**

*Document maintained in `docs/technical-architecture/`. Sync with Google Doc as needed.*
