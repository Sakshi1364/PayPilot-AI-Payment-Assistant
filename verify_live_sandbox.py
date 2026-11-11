"""
PayPilot - Live PayPal Sandbox Payment Verification Script
Run this script ONLY when valid PayPal Sandbox credentials are configured.
This script performs real live API calls to PayPal Sandbox (no mocks).
"""

import os
import sys
import webbrowser
from dotenv import load_dotenv
from paypal_service import PayPalService
import database as db

# Load credentials from .env
load_dotenv()


def main():
    print("=" * 65)
    print("   PayPilot - Live PayPal Sandbox End-to-End Verification")
    print("=" * 65)

    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    base_url = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com").strip()

    if not client_id or not client_secret:
        print("\n❌ Blocker: PayPal Sandbox credentials not detected in .env.")
        print("Please configure PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET before running this verification.")
        print("Tip: See README.md or app.py '⚙️ Credentials & Setup' for instructions.")
        sys.exit(1)

    print(f"\n[1/4] Authenticating with PayPal Sandbox ({base_url})...")
    paypal = PayPalService(client_id=client_id, client_secret=client_secret, base_url=base_url)
    auth_ok, token_or_err = paypal.get_access_token()

    if not auth_ok:
        print(f"❌ OAuth Authentication Failed: {token_or_err}")
        sys.exit(1)

    print(f"✅ Authentication Successful! Bearer Token obtained (expires in ~9 hours).")

    print("\n[2/4] Creating a real PayPal Orders v2 Sandbox Transaction ($1.00 USD)...")
    create_ok, order_data = paypal.create_order(
        amount=1.00,
        currency="USD",
        description="PayPilot Live Sandbox Verification Test",
    )

    if not create_ok:
        print(f"❌ Order Creation Failed: {order_data.get('error')}")
        sys.exit(1)

    order_id = order_data["order_id"]
    approval_url = order_data.get("approval_url")

    print(f"✅ Order Successfully Created on PayPal Sandbox!")
    print(f"   - PayPal Order ID: {order_id}")
    print(f"   - Status: {order_data.get('status')}")
    print(f"   - Checkout Approval URL: {approval_url}")

    # Record order in local SQLite
    db.init_db()
    db.create_order_record(
        paypal_order_id=order_id,
        amount=1.00,
        currency="USD",
        description="Live Sandbox Verification",
        category="Services",
        status="PENDING",
        approval_url=approval_url or "",
    )

    print("\n[3/4] Awaiting Buyer Approval in PayPal Sandbox Window...")
    print("Opening browser for checkout...")
    if approval_url:
        try:
            webbrowser.open(approval_url)
        except Exception:
            pass
    print(f"If browser did not open automatically, visit:")
    print(f"👉 {approval_url}")
    print("\nInstructions:")
    print("1. Log in using your PayPal developer Sandbox Personal buyer account.")
    print("2. Click 'Complete Purchase' / 'Continue' to approve the payment.")
    print("3. Once approved on PayPal, return to this terminal.")

    input("\nPress [ENTER] after you have approved the payment in PayPal Checkout...")

    print("\n[4/4] Invoking PayPal Orders v2 Capture API...")
    cap_ok, cap_res = paypal.capture_order(order_id)

    if cap_ok:
        tx_id = cap_res.get("transaction_id")
        payer_email = cap_res.get("payer_email")
        print("\n" + "=" * 65)
        print("🎉 SUCCESS: PAYMENT CAPTURED AND VERIFIED BY PAYPAL API!")
        print("=" * 65)
        print(f"   - Capture ID     : {tx_id}")
        print(f"   - Order ID       : {order_id}")
        print(f"   - Final Status   : COMPLETED")
        print(f"   - Payer Email    : {payer_email}")

        # Update database record
        db.complete_order_record(
            paypal_order_id=order_id,
            transaction_id=tx_id,
            payer_email=payer_email,
            payer_name=cap_res.get("payer_name"),
        )
        print(f"✅ Record saved to SQLite database (paypilot.db).")
    else:
        print("\n⚠️ CAPTURE NOT COMPLETED:")
        print(f"Reason: {cap_res.get('error')}")
        print("Note: If the error is ORDER_NOT_APPROVED, the buyer did not finalize approval in the browser.")


if __name__ == "__main__":
    main()
