#!/usr/bin/env bash
# Set Razorpay test UPI VPA and related variables on Railway.
# Usage: ./scripts/setup_railway_env.sh
# Quick: ./scripts/setup_railway_env.sh --vpa-only

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TEST_VPA="success@razorpay"
VPA_ONLY=false

if [[ "${1:-}" == "--vpa-only" ]]; then
  VPA_ONLY=true
fi

railway_cmd() {
  if command -v railway >/dev/null 2>&1; then
    return 0
  fi
  echo "Railway CLI not found."
  echo "Install: npm install -g @railway/cli"
  echo "Or:      brew install railway"
  exit 1
}

railway_set() {
  local name="$1"
  local value="$2"
  echo "Setting ${name}..."
  if railway variables set "${name}=${value}" 2>/dev/null; then
    echo "  OK (${name})"
    return 0
  fi
  if railway variables --set "${name}=${value}" 2>/dev/null; then
    echo "  OK (${name})"
    return 0
  fi
  if railway env set "${name}=${value}" 2>/dev/null; then
    echo "  OK (${name}) [legacy env command]"
    return 0
  fi
  echo "  Failed to set ${name}. Try manually:"
  echo "    railway variables set ${name}=${value}"
  return 1
}

railway_get() {
  local name="$1"
  if railway variables get "$name" 2>/dev/null; then
    return 0
  fi
  railway env get "$name" 2>/dev/null || return 1
}

railway_restart() {
  echo "Redeploying Railway service..."
  if railway redeploy -y 2>/dev/null; then
    echo "Redeploy triggered."
    return 0
  fi
  if railway restart 2>/dev/null; then
    echo "Service restarted."
    return 0
  fi
  echo "Could not auto-redeploy. Redeploy from the Railway dashboard or run: railway up"
}

echo "=== Qumanity Railway — Razorpay test setup ==="
railway_cmd

echo "Checking Railway login..."
if ! railway whoami 2>/dev/null; then
  echo "Please log in to Railway..."
  railway login
fi

echo ""
echo "Setting Razorpay test UPI VPA: ${TEST_VPA}"
railway_set "DONATION_UPI_VPA" "$TEST_VPA"
railway_set "RAZORPAY_UPI_VPA" "$TEST_VPA"

if [[ "$VPA_ONLY" == true ]]; then
  railway_restart
  echo ""
  echo "Done. Test registration:"
  echo "  https://web-production-5649cf.up.railway.app/register"
  exit 0
fi

echo ""
echo "Checking other Razorpay variables..."

if ! railway_get RAZORPAY_KEY_ID >/dev/null 2>&1; then
  read -r -p "RAZORPAY_KEY_ID (rzp_test_...): " key_id
  if [[ -n "${key_id:-}" ]]; then
    railway_set "RAZORPAY_KEY_ID" "$key_id"
  fi
fi

if ! railway_get RAZORPAY_KEY_SECRET >/dev/null 2>&1; then
  read -r -s -p "RAZORPAY_KEY_SECRET: " key_secret
  echo ""
  if [[ -n "${key_secret:-}" ]]; then
    railway_set "RAZORPAY_KEY_SECRET" "$key_secret"
  fi
fi

if ! railway_get RAZORPAY_WEBHOOK_SECRET >/dev/null 2>&1; then
  read -r -s -p "RAZORPAY_WEBHOOK_SECRET: " webhook_secret
  echo ""
  if [[ -n "${webhook_secret:-}" ]]; then
    railway_set "RAZORPAY_WEBHOOK_SECRET" "$webhook_secret"
  fi
fi

echo ""
echo "Current payment-related variables:"
railway variables 2>/dev/null | grep -E 'VPA|UPI|RAZORPAY|DONATION' || \
  railway env list 2>/dev/null | grep -E 'VPA|UPI|RAZORPAY|DONATION' || \
  echo "(run 'railway variables' to view all)"

railway_restart

echo ""
echo "Setup complete."
echo "  Test UPI VPA: ${TEST_VPA} (Razorpay test mode — auto-confirms)"
echo "  Registration: https://web-production-5649cf.up.railway.app/register"
echo "  Verify:       https://web-production-5649cf.up.railway.app/api/test-upi-uri"
