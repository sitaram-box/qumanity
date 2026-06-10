# Core Database Tables

## User Management
| Table | Purpose |
| :--- | :--- |
| `users` | User profiles, authentication, karma, wallet, preferences |
| `user_roles` | Role assignments (Volunteer, Agent, Manager, Leader, Mentor) |
| `user_education` | Education history |
| `user_work` | Work history |

## Content & Social
| Table | Purpose |
| :--- | :--- |
| `posts` | User posts, escalation levels, scores |
| `post_votes` | Votes on posts (+1, 0, -1) |
| `messages` | Private inbox messages |
| `connection_requests` | Family/social connection requests |

## Economy
| Table | Purpose |
| :--- | :--- |
| `wallets` | Qoin balances (denominations JSON) |
| `pending_transactions` | Weekly settlement queue |
| `weekly_statements` | Generated transaction history |
| `karma_action_types` | Predefined karma actions with values |
| `karma_transactions` | Record of karma claims |

## Governance
| Table | Purpose |
| :--- | :--- |
| `election_cycles` | Zodiac election periods |
| `election_candidates` | Nominees for council |
| `election_votes` | Votes in elections |
| `leadership_council` | Council members (Mentor, Nayak, Nayika, Manager, Agent) |

## Family
| Table | Purpose |
| :--- | :--- |
| `family_members` | Family tree nodes |
| `family_relationships` | Edges between family nodes |
| `family_removal_requests` | Admin queue for family removal requests |

## Geography & Translations
| Table | Purpose |
| :--- | :--- |
| `state`, `district`, `tehsil`, `village` | Geographic hierarchy |
| `location_translations` | Translated location names |
| `state_languages` | State → default language mapping |
