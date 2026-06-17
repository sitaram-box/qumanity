"""Print payment-related environment variables (for Railway/local debugging)."""
from __future__ import annotations

import os
import sys

VARS = [
    "DONATION_UPI_VPA",
    "RAZORPAY_UPI_VPA",
    "UPI_VPA",
    "MERCHANT_UPI_VPA",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET",
]


def main() -> None:
    print("=== Payment environment debug ===")
    print(f"Python: {sys.version.split()[0]}")
    for name in VARS:
        value = os.environ.get(name)
        if value:
            preview = value[:8] + "…" if len(value) > 8 else value
            print(f"{name}: set ({len(value)} chars) preview={preview}")
        else:
            print(f"{name}: NOT SET")
    print("\nAll env keys containing UPI, VPA, RAZORPAY, or DONATION:")
    for key in sorted(os.environ):
        if any(x in key for x in ("UPI", "VPA", "RAZORPAY", "DONATION")):
            val = os.environ[key]
            print(f"  {key}: {len(val)} chars")


if __name__ == "__main__":
    main()
