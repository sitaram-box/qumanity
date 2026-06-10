# Deployment Guide

## Docker Deployment

### Build Docker image

```bash
docker build -t qumanity .
```

### Run locally

```bash
docker run -p 8080:5000 -v qumanity_data:/data qumanity
```

### Run with environment variables

```bash
docker run -p 8080:5000 \
  -e SECRET_KEY=your-secret-key \
  -e QOIN_WALLET_ENCRYPTION_KEY=your-encryption-key \
  -v qumanity_data:/data \
  qumanity
```

## Deploy to Render

1. Push code to GitHub
2. Login to [render.com](https://render.com)
3. Click "New +" → "Web Service"
4. Connect your GitHub repository
5. Render auto-detects Dockerfile
6. Click "Deploy"

## Deploy to Railway

1. Push code to GitHub
2. Login to [railway.app](https://railway.app)
3. Click "New Project" → "Deploy from GitHub"
4. Select repository
5. Add volume at `/data`
6. Set environment variables
7. Deploy

## Environment Variables (Production)

| Variable | Value |
| :--- | :--- |
| `FLASK_ENV` | `production` |
| `SECRET_KEY` | (generate strong random key) |
| `QOIN_WALLET_ENCRYPTION_KEY` | (generate strong random key) |
| `DATABASE_URL` | `sqlite:////data/indiaq.db` |
