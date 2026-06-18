#!/usr/bin/env python3
"""Set Razorpay test UPI VPA and credentials on Railway via Railway CLI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

TEST_VPA = "success@razorpay"
REGISTER_URL = "https://web-production-5649cf.up.railway.app/register"
TEST_URI_URL = "https://web-production-5649cf.up.railway.app/api/test-upi-uri"


def run(cmd: str, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        shell=True,
        text=True,
        capture_output=True,
        check=check,
    )


def railway_available() -> bool:
    return run("railway --version").returncode == 0


def railway_set(name: str, value: str) -> bool:
    for cmd in (
        f'railway variables set "{name}={value}"',
        f'railway variables --set "{name}={value}"',
        f'railway env set {name}={value}',
    ):
        result = run(cmd)
        if result.returncode == 0:
            print(f"  OK {name}")
            return True
    print(f"  Failed {name}: {result.stderr.strip() or result.stdout.strip()}")
    return False


def railway_get(name: str) -> str | None:
    for cmd in (f"railway variables get {name}", f"railway env get {name}"):
        result = run(cmd)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def railway_restart() -> None:
    for cmd in ("railway redeploy -y", "railway restart"):
        result = run(cmd)
        if result.returncode == 0:
            print("Service redeploy/restart triggered.")
            return
    print("Could not auto-redeploy. Redeploy from Railway dashboard or run: railway up")


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Razorpay test vars on Railway")
    parser.add_argument(
        "--vpa-only",
        action="store_true",
        help="Only set DONATION_UPI_VPA / RAZORPAY_UPI_VPA and redeploy",
    )
    args = parser.parse_args()

    print("=== Qumanity Railway — Razorpay test setup ===")

    if not railway_available():
        print("Railway CLI not found. Install: npm install -g @railway/cli")
        sys.exit(1)

    if run("railway whoami").returncode != 0:
        print("Logging in to Railway...")
        os.system("railway login")

    print(f"Setting test UPI VPA: {TEST_VPA}")
    railway_set("DONATION_UPI_VPA", TEST_VPA)
    railway_set("RAZORPAY_UPI_VPA", TEST_VPA)

    if not args.vpa_only:
        for var_name, prompt in (
            ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_ID (rzp_test_...)"),
            ("RAZORPAY_KEY_SECRET", "RAZORPAY_KEY_SECRET"),
            ("RAZORPAY_WEBHOOK_SECRET", "RAZORPAY_WEBHOOK_SECRET"),
        ):
            if not railway_get(var_name):
                value = input(f"{prompt}: ").strip()
                if value:
                    railway_set(var_name, value)

    print("\nRedeploying...")
    railway_restart()

    print("\nSetup complete.")
    print(f"  Test UPI VPA: {TEST_VPA}")
    print(f"  Register:     {REGISTER_URL}")
    print(f"  Verify URI:   {TEST_URI_URL}")


if __name__ == "__main__":
    main()
