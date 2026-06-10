# Development Setup Guide

## Prerequisites

- Python 3.14+
- Git
- SQLite3 (pre-installed on macOS)
- Virtual environment (venv)

## Setup Steps

### 1. Clone or navigate to project

```bash
cd /Users/macmudgal/Desktop/quantum_box
```

### 2. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If `requirements.txt` is missing:

```bash
pip install Flask bcrypt python-dotenv
```

### 4. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` with your own values:

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key-here
QOIN_WALLET_ENCRYPTION_KEY=your-encryption-key-here
DATABASE_URL=sqlite:///indiaq.db
```

### 5. Initialize database

```bash
python3 init_db.py
```

### 6. Seed demo users (optional)

```bash
python3 seed_demo_users.py
python3 seed_taurus_users.py
```

### 7. Run the application

```bash
python3 app.py
```

### 8. Open browser

Go to `http://127.0.0.1:5000`

## Login Credentials (after seeding)

| User | Private ID | Password |
| :--- | :--- | :--- |
| Admin | `H_U_ADMIN` | `Admin123` |
| Demo User (Taurus) | `D_UI_Y_TAURUS_0001` | `Demo123` |
