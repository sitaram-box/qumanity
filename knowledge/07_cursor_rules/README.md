# Cursor Rules (Reference)

The authoritative AI guidance rules live in `.cursor/rules/` at the project
root. They are loaded automatically by Cursor and apply during AI-assisted
development. This folder is only a pointer to them — edit the `.mdc` files
directly, not copies here.

## Existing Rule Files

| File | Scope | Purpose |
| :--- | :--- | :--- |
| `.cursor/rules/qbox-core.mdc` | Always applied | Core architecture, domain concepts, persistent project knowledge |
| `.cursor/rules/ui-guidelines.mdc` | Always applied | UI/UX design tokens, colours, typography, components |
| `.cursor/rules/qbox-qoin-economy.mdc` | Always applied | Qoin denominations, karma issuance, weekly settlement, nested wallets |
| `.cursor/rules/qbox-post-escalation.mdc` | Domain | Post escalation schedule and scoring rules |
| `.cursor/rules/qbox-election-voting.mdc` | Domain | Zodiac elections, nomination & voting eligibility |
| `.cursor/rules/qbox-personal-social.mdc` | Domain | Personal account, family tree, social connections |
| `.cursor/rules/qbox-time-zodiac.mdc` | Domain | Zodiac calendar, solar months, time handling |
| `.cursor/rules/production-checklist.mdc` | Process | Production deployment checklist and requirements |

## How Cursor Rules Relate to This Knowledge Base

- `.cursor/rules/*.mdc` — concise, machine-facing rules enforced during code
  generation.
- `knowledge/` — human-readable documentation expanding on those rules with
  tables, examples, and context.

When a rule and this knowledge base disagree, treat the `.mdc` rules as the
source of truth and update the documentation to match.
