#!/usr/bin/env bash
# Quick Razorpay configuration check (reads .env in project root).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "❌ .env not found at $ENV_FILE"
  echo "   Run: cp .env.example .env"
  exit 1
fi

echo "=== Razorpay Configuration Check ==="

key_id="$(grep -E '^RAZORPAY_KEY_ID=' "$ENV_FILE" | tail -1 | cut -d '=' -f2- || true)"
key_secret="$(grep -E '^RAZORPAY_KEY_SECRET=' "$ENV_FILE" | tail -1 | cut -d '=' -f2- || true)"
webhook_secret="$(grep -E '^RAZORPAY_WEBHOOK_SECRET=' "$ENV_FILE" | tail -1 | cut -d '=' -f2- || true)"

if [[ -n "$key_id" ]]; then
  echo "RAZORPAY_KEY_ID: $key_id"
else
  echo "❌ RAZORPAY_KEY_ID is missing"
fi

if [[ -n "$key_secret" ]]; then
  preview="${key_secret:0:10}"
  echo "RAZORPAY_KEY_SECRET: ${preview}..."
else
  echo "❌ RAZORPAY_KEY_SECRET is missing"
fi

if [[ -n "$webhook_secret" ]]; then
  echo "✅ RAZORPAY_WEBHOOK_SECRET is set"
else
  echo "❌ RAZORPAY_WEBHOOK_SECRET is missing"
fi

echo ""
echo "Webhook URL (configure in Razorpay Dashboard):"
echo "  https://your-domain/webhook/donation"
echo "Events: payment.captured, payment.failed, qr_code.credited"
echo ""
echo "Razorpay TEST mode UPI (auto-confirms): success@razorpay"
echo "Set on Railway:"
echo "  make railway-set-vpa"
echo "  # or: ./scripts/setup_railway_env.sh --vpa-only"
