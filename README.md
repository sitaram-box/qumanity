# Qumanity

**Quantum + Humanity — For Harmony, Peace & Self-Rule**

A public digital governance and economic platform by [SITA Foundation](https://qumanity.in).

[![GitHub](https://img.shields.io/badge/GitHub-sitaram--box%2FQUMANITY-blue)](https://github.com/sitaram-box/QUMANITY)

---

## What is Qumanity?

Qumanity is shared public infrastructure for transparent, participatory governance — from the village to the planet. It combines nested geographic governance, a karma-based Qoin economy, zodiac-aligned elections, and collective intelligence grounded in Vedic philosophy.

It is **not** a social network, government portal, or speculative cryptocurrency.

---

## Documentation

| Document | Path | Audience |
| :--- | :--- | :--- |
| **White Paper** (8–16 pages) | [`docs/white-paper/Qumanity_White_Paper.md`](docs/white-paper/Qumanity_White_Paper.md) | Public, policymakers, partners |
| **Technical Architecture** | [`docs/technical-architecture/Qumanity_Technical_Architecture.md`](docs/technical-architecture/Qumanity_Technical_Architecture.md) | Developers, DevOps, security |
| **AI Context Primer** | [`docs/context/QUMANITY_CONTEXT.md`](docs/context/QUMANITY_CONTEXT.md) | AI assistants, quick onboarding |
| **Knowledge Base** | [`knowledge/`](knowledge/) | Stage contracts, API refs, schemas |
| **Deployment Guide** | [`DEPLOYMENT.md`](DEPLOYMENT.md) | Operations |
| **Contributing** | [`CONTRIBUTING.md`](CONTRIBUTING.md) | Developers |

### Google Docs

- **White Paper:** Import `docs/white-paper/Qumanity_White_Paper.md` → name "Qumanity White Paper"
- **Technical Architecture:** Import `docs/technical-architecture/Qumanity_Technical_Architecture.md` → name "Qumanity Technical Architecture Document"
- **Live Technical Doc:** [Google Docs](https://docs.google.com/document/d/1wKAmj_L5sImaW92uVIExT58Dgy5B9yy3jSm0YV0otys/edit?usp=sharing)

---

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 init_db.py
python3 app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000)

See [`knowledge/06_development/setup_guide.md`](knowledge/06_development/setup_guide.md) for full instructions.

---

## Project Structure

```
Qumanity/
├── app.py                  # Main Flask application
├── *_core.py               # Domain modules (qoin, identity, karma, etc.)
├── templates/              # HTML templates
├── static/                 # CSS, JS, images
├── knowledge/              # Detailed knowledge base
├── docs/
│   ├── white-paper/        # Concise public white paper
│   ├── technical-architecture/  # Full technical specs
│   ├── context/            # AI priming document
│   └── assets/             # Diagrams and images
├── Dockerfile
└── requirements.txt
```

---

## Core Features

- Nested governance (Village → Earth)
- Four timelines (Private, Personal, Public, Global)
- Dual-key identity (Private ID + Public ID)
- Qoin economy with fixed denominations & weekly settlement
- Post escalation through governance levels
- Zodiac-based council elections
- Family tree, messaging, 12 languages
- Docker deployment

---

## Links

- **Website:** [qumanity.in](https://qumanity.in)
- **GitHub:** [github.com/sitaram-box/QUMANITY](https://github.com/sitaram-box/QUMANITY)
- **Organization:** SITA Foundation (Sekyor Intelligence Tantra)

---

## License & Contact

Open source. See GitHub repository for license details.

**SITA Foundation** — Sekyor Intelligence Tantra Foundation

*Qumanity — For Humanity, Harmony & Peace*

# Qumanity

A Quantum-Informed Governance Protocol for Transparent Civilization.

## Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| **[White Paper](docs/white-paper/Qumanity_White_Paper.md)** | Vision, problem, solution, roadmap (12-14 pages) | General public, investors, policymakers, researchers |
| **[Technical Architecture](docs/technical-architecture/Qumanity_Technical_Architecture.md)** | Complete system specifications, APIs, schemas | Developers, engineers, technical collaborators |
| **[Context](docs/context/QUMANITY_CONTEXT.md)** | AI priming file | AI assistants (Claude, ChatGPT, DeepSeek) |

## Quick Links

- **Live:** https://qumanity.in
- **GitHub:** https://github.com/sitaram-box/qumanity
- **Organization:** SITA Foundation (Sekyor Intelligence Tantra Foundation)

## License

© 2026 SITA Foundation. All rights reserved.
