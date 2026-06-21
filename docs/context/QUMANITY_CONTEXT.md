# QUMANITY CONTEXT

> **Purpose:** Single-file primer for AI assistants, collaborators, and new contributors.
> For the public narrative, see [White Paper](../white-paper/Qumanity_White_Paper.md).
> For implementation detail, see [Technical Architecture](../technical-architecture/Qumanity_Technical_Architecture.md).

---

## Project Overview

**Qumanity** (Quantum + Humanity) is a public digital governance and economic platform developed by **SITA Foundation** (Sekyor Intelligence Tantra). It restores transparency, accountability, and participatory self-rule from the village to the planet.

Qumanity is **not** a social network, government portal, or speculative cryptocurrency. It is **shared public infrastructure**: village kiosks, dual-key identities (Private ID + Public ID), and an immutable ledger of votes, transactions, and ethical actions.

The platform combines nested geographic governance, a karma-based Qoin economy, zodiac-aligned democratic elections, and collective intelligence grounded in Vedic philosophy (Pañca Mahābhūta: Space, Fire, Earth, Air, Water). Built in India, designed for global humanity.

The prototype is ~50–60% complete with 100+ demo users. Core features (registration, posts, Qoins, family tree, messaging, 12 languages) are operational. Elections UI, marketplace, mobile app, and PLNN are in progress or planned.

---

## Core Architecture

### Three Layers

| Layer | Role | Status |
| :--- | :--- | :--- |
| **Website** | Public transparency, registration, statistics | ✅ Prototype complete |
| **iOS / macOS App** | Governance dashboard, offline-first | ⏳ Phase 4 |
| **PLNN** | Planet-Level Nested Network — distributed sync | ⏳ Phase 3 |

### Four Timelines (Accounts)

| Account | Based On | Features |
| :--- | :--- | :--- |
| Private (Y1) | Birth location | Profile, wallet, messages |
| Personal (Y2) | Family + social | Posts, family tree, connections |
| Public (Y3) | Present location | CVB, elections, marketplace |
| Global (Y4) | Earth → Country | Global stats, CEB |

### Geographic Hierarchy

```
Planet → Continent → Country → Zone → State → District → Tehsil → Village → Citizen
```

Location ID example: `0.राम|IND/CS/DL.5.4.1E`

### Dual-Key Identity

- **Private ID** — based on birth location, never changes
- **Public ID** — based on present location, updates on relocation
- Format: `[Prefix]-[Initials]-[Gender][Age]-[Element][Sign]-[LocationPath]`

### Qoin Economy

- Fixed denominations only: `[2000, 500, 200, 100, 50, 20, 10, 5, 2, 1]`
- Weekly settlement (Sunday 23:59), not real-time
- Greedy algorithm for smallest Qoin count
- Nested wallets at village → tehsil → district → state → nation
- Karma mints new Qoins; commercial/donation/subscription rules apply

### Post Escalation (India)

Personal (7d) → Village (7d) → Tehsil → District → State → Country → Continent → Earth (56 days total). Positive score escalates; score ≤ 0 archives to Private account.

### Zodiac Elections

Monthly, solar months (Aries–Pisces). Element-based voting. Nominees: Yuvak (25–49), matching sun sign, village resident.

### Governance Roles

Mentor, Nayak/Nayika, Manager, Agent, Volunteer

---

## Key Features

- User registration & dual-key identity
- Nested geography (India: Zone → Village)
- Four timeline dashboard
- Post creation, voting (+1/0/−1), escalation
- Qoin wallet with fixed denominations & weekly settlement
- Karma claims with council verification
- Zodiac elections (partial)
- Family tree (D3.js)
- Messaging inbox
- Social connections
- Multi-language (12 Indian languages)
- Admin panel (nominations, karma, donations, elections)
- Solar calendar with birth chart integration
- Varna system (vidya, raksha, artha, seva categories)
- Docker deployment with health checks
- Toast notifications, accessibility (WCAG 2.1 AA)

**Planned:** Marketplace, job portal, justice module, iOS/macOS app, PLNN nodes, blockchain ledger (Polygon), biometric kiosk auth, offline-first sync.

---

## Technical Stack

| Layer | Technology |
| :--- | :--- |
| Backend | Flask (Python 3.12+), Gunicorn |
| Database | SQLite (`indiaq.db`) dev; PostgreSQL via `DATABASE_URL` prod |
| Frontend | HTML, CSS, JS, Bootstrap 5, Chart.js, D3.js |
| Config | `config.py` (env-driven, python-dotenv) |
| Core modules | `qoin_core`, `identity_core`, `karma_core`, `planetary_core`, `varna_core`, `leadership_core`, `blockchain_core`, `language_core`, `donation_core`, `social_core`, `element_core`, `global_core`, `deceased_core`, `referral_core`, `sita_platform_core` |
| Deployment | Docker, Render, Railway, Fly.io |
| Security | Encrypted wallets, non-root container, `HEALTHCHECK`, session hardening |

### Critical Rules

1. Qoins use **only** fixed denominations — never arbitrary values
2. Transactions settle **weekly**, not real-time
3. Respect nested governance — filter by geographic level
4. Never hardcode village IDs — use `current_location_id`
5. Never commit `.env` or `*.db` files
6. API routes return JSON; use `@login_required`
7. Use `window.qbToast()` not `alert()`
8. CSS tokens from `static/style.css` `:root` — no hardcoded hex

---

## Current Status

| Area | Status |
| :--- | :--- |
| Website & registration | ✅ Complete |
| Dashboard (4 timelines) | ✅ Complete |
| Post escalation | ✅ Complete |
| Qoin economy & settlement | ✅ Complete |
| Family tree & messaging | ✅ Complete |
| Multi-language | ✅ Complete |
| Zodiac elections | 🟡 Partial (backend ready, UI incomplete) |
| Council management | 🟡 Partial |
| Marketplace | ⏳ Planned |
| Mobile app | ⏳ Phase 4 |
| PLNN | ⏳ Phase 3 |
| Blockchain | ⏳ Schema stubs in `blockchain_core.py` |

**Version:** 0.1.0 prototype · **Last updated:** June 2026

---

## Documentation Map

| Document | Path | Audience |
| :--- | :--- | :--- |
| White Paper | `docs/white-paper/Qumanity_White_Paper.md` | Public, policymakers, partners |
| Technical Architecture | `docs/technical-architecture/Qumanity_Technical_Architecture.md` | Developers, DevOps, security |
| This file | `docs/context/QUMANITY_CONTEXT.md` | AI priming, quick onboarding |
| Knowledge base | `knowledge/` | Detailed stage contracts & references |
| Deployment | `DEPLOYMENT.md` | Operations |
| Contributing | `CONTRIBUTING.md` | Developers |

---

## Links

- **Website:** [https://qumanity.in](https://qumanity.in)
- **GitHub:** [https://github.com/sitaram-box/QUMANITY](https://github.com/sitaram-box/QUMANITY)
- **Technical Architecture (Google Doc):** [Google Docs link](https://docs.google.com/document/d/1wKAmj_L5sImaW92uVIExT58Dgy5B9yy3jSm0YV0otys/edit?usp=sharing)
- **Organization:** SITA Foundation (Sekyor Intelligence Tantra Foundation)

---

## Contact

- Email: founder@qumanity.in
- Organization: SITA Foundation (Sekyor Intelligence Tantra Foundation)
