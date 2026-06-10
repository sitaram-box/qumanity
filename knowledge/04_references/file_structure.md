# Project File Structure

```
quantum_box/
├── app.py                 # Main Flask application (11,000+ lines)
├── qoin_core.py           # Qoin economy logic, weekly settlement
├── language_core.py       # Multi-language support
├── translations.py        # Translation dictionaries (12 languages)
├── init_db.py             # Database initialization and migrations
├── scheduler.py           # Weekly settlement job
├── config.py              # Configuration from environment variables
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker container configuration
├── .env.example           # Environment variables template
│
├── templates/
│   ├── base.html          # Base template with navbar and marquee
│   ├── dashboard.html     # User dashboard (all 4 accounts)
│   ├── index.html         # Homepage
│   ├── register.html      # Registration form
│   ├── login.html         # Login page
│   ├── location.html      # Location statistics page
│   ├── about.html         # About Qumanity
│   └── contact.html       # Contact page
│
├── static/
│   ├── style.css          # Global styles
│   ├── dashboard.css      # Dashboard-specific styles
│   ├── dashboard.js       # Dashboard JavaScript
│   ├── marquee.js         # Bottom marquee poem ticker
│   ├── family_tree.js     # D3.js family tree visualization
│   ├── poems.json         # 237 Vinaya Patrika poems
│   └── images/
│       ├── qumanity_logo.svg
│       └── earth_icon.png
│
├── knowledge/             # This documentation folder
│   ├── 01_identity/
│   ├── 02_routing/
│   ├── 03_stage_contracts/
│   ├── 04_references/
│   ├── 05_artifacts/
│   ├── 06_development/
│   └── 07_cursor_rules/
│
└── .cursor/
    └── rules/             # Cursor persistent AI rules
        ├── quantum-box-core.mdc
        ├── qoin-economy.mdc
        └── post-escalation.mdc
```
