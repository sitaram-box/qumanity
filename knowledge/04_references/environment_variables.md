# Environment Variables

## Required Variables

| Variable | Description | Example |
| :--- | :--- | :--- |
| `FLASK_ENV` | Environment mode | `development` or `production` |
| `SECRET_KEY` | Flask session encryption | `your-very-long-random-secret-key` |
| `QOIN_WALLET_ENCRYPTION_KEY` | Wallet data encryption | `another-long-random-key` |
| `DATABASE_URL` | Database connection string | `sqlite:///indiaq.db` |

## Optional Variables (Email)

| Variable | Description | Example |
| :--- | :--- | :--- |
| `MAIL_SERVER` | SMTP server | `smtp.gmail.com` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_USE_TLS` | Use TLS | `true` |
| `MAIL_USERNAME` | Email username | `your-email@gmail.com` |
| `MAIL_PASSWORD` | Email password/app password | `your-app-password` |

## .env.example

```env
# Flask Environment
FLASK_ENV=development
SECRET_KEY=quantum-box-secret-key-2026-change-this-in-production

# Qoin Wallet Encryption
QOIN_WALLET_ENCRYPTION_KEY=quantum-wallet-encryption-key-2026

# Database (SQLite for development)
DATABASE_URL=sqlite:///indiaq.db

# Email Configuration (optional – for password recovery)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
```
