"""
PayPilot - PayPal Service Module
Official PayPal REST API v2 integration for Sandbox payment processing.
Handles OAuth 2.0 authentication, order creation, approval URL extraction,
real-time status verification, and payment capture.

STRICT GUARANTEE: Never generates synthetic capture IDs. A payment is only marked
COMPLETED when the official PayPal REST API returns a verified capture ID and COMPLETED status.
"""

import time
import uuid
import logging
from typing import Dict, Any, Optional, Tuple
import requests
from requests.auth import HTTPBasicAuth
from config_utils import get_secret

logger = logging.getLogger(__name__)


class PayPalService:
    """Official PayPal REST API v2 integration for Sandbox payment processing."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.client_id = (client_id or get_secret("PAYPAL_CLIENT_ID", "")).strip()
        self.client_secret = (client_secret or get_secret("PAYPAL_CLIENT_SECRET", "")).strip()
        self.base_url = (
            base_url or get_secret("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
        ).strip().rstrip("/")

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def is_configured(self) -> bool:
        """Check if PayPal API credentials are provided."""
        return bool(self.client_id and self.client_secret)

    def get_access_token(self, force_refresh: bool = False) -> Tuple[bool, str]:
        """
        Generate or reuse an OAuth 2.0 access token via PayPal client credentials grant.
        Returns: (success: bool, token_or_error_message: str)
        Never logs client secrets or raw tokens.
        """
        if not self.is_configured:
            return (
                False,
                "PayPal Sandbox credentials are not configured. Please enter your PayPal Client ID and Client Secret in Settings or Streamlit Secrets.",
            )

        # Reuse cached token if still valid (with 60-second buffer)
        if not force_refresh and self._access_token and time.time() < (self._token_expires_at - 60):
            return True, self._access_token

        url = f"{self.base_url}/v1/oauth2/token"
        headers = {
            "Accept": "application/json",
            "Accept-Language": "en_US",
        }
        data = {"grant_type": "client_credentials"}

        try:
            response = requests.post(
                url,
                headers=headers,
                data=data,
                auth=HTTPBasicAuth(self.client_id, self.client_secret),
                timeout=15,
            )

            if response.status_code == 200:
                payload = response.json()
                self._access_token = payload.get("access_token")
                expires_in = payload.get("expires_in", 32400)
                self._token_expires_at = time.time() + float(expires_in)
                return True, self._access_token
            else:
                err_data = response.json() if response.content else {}
                err_desc = (
                    err_data.get("error_description")
                    or err_data.get("message")
                    or f"HTTP {response.status_code}"
                )
                return False, f"PayPal Authentication Failed: {err_desc}"

        except requests.exceptions.RequestException as e:
            logger.error("PayPal OAuth network exception occurred: %s", type(e).__name__)
            return False, f"Network error connecting to PayPal API: {str(e)}"

    def test_connection(self) -> Tuple[bool, str]:
        """Test authentication directly against PayPal Sandbox API."""
        return self.get_access_token(force_refresh=True)

    def create_order(
        self,
        amount: float,
        currency: str = "USD",
        description: str = "PayPilot Order",
        return_url: str = "http://localhost:8501?status=approved",
        cancel_url: str = "http://localhost:8501?status=cancelled",
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Create a new PayPal Order using Orders v2 API with intent=CAPTURE.
        Never fakes or simulates orders; requires verified PayPal API response.
        Returns:
            (success: bool, data_dict_or_error: Dict[str, Any])
        """
        if amount <= 0:
            return False, {"error": "Payment amount must be greater than 0.00"}

        valid_currencies = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CNY", "INR"}
        curr = currency.upper().strip()
        if curr not in valid_currencies:
            curr = "USD"

        # Format amount to 2 decimal places (JPY has 0 decimals in PayPal)
        formatted_amount = f"{amount:.2f}" if curr != "JPY" else f"{int(amount)}"

        # Get access token
        auth_ok, token_or_err = self.get_access_token()
        if not auth_ok:
            return False, {"error": token_or_err, "is_unconfigured": not self.is_configured}

        url = f"{self.base_url}/v2/checkout/orders"
        request_id = str(uuid.uuid4())
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_or_err}",
            "PayPal-Request-Id": request_id,
        }

        order_payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": f"paypilot_{request_id[:8]}",
                    "description": description[:127] if description else "PayPilot Order",
                    "amount": {
                        "currency_code": curr,
                        "value": formatted_amount,
                    },
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED",
                        "brand_name": "PayPilot AI",
                        "locale": "en-US",
                        "landing_page": "LOGIN",
                        "user_action": "PAY_NOW",
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                    }
                }
            },
        }

        try:
            response = requests.post(url, headers=headers, json=order_payload, timeout=20)
            data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                order_id = data.get("id")
                status = data.get("status")

                if not order_id:
                    return False, {"error": "PayPal response did not contain a valid Order ID"}

                # Extract approval checkout link
                approval_url = None
                for link in data.get("links", []):
                    if link.get("rel") in ("approve", "payer-action"):
                        approval_url = link.get("href")
                        break

                # Fallback to direct sandbox checkout link format if rel was not explicit
                if not approval_url and order_id:
                    approval_url = f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}"

                return True, {
                    "order_id": order_id,
                    "status": status,
                    "amount": float(formatted_amount),
                    "currency": curr,
                    "description": description,
                    "approval_url": approval_url,
                    "raw_response": data,
                }
            else:
                err_msg = data.get("message") or data.get("error_description") or response.text
                details = data.get("details", [])
                if details:
                    detail_texts = [d.get("description", d.get("issue", "")) for d in details]
                    err_msg += f" (Details: {'; '.join(detail_texts)})"
                return False, {"error": f"PayPal Order Creation Failed ({response.status_code}): {err_msg}"}

        except requests.exceptions.RequestException as e:
            return False, {"error": f"Network exception during PayPal order creation: {str(e)}"}

    def get_order_details(self, order_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Fetch real-time order status and details directly from PayPal Orders v2 API."""
        if not order_id or not order_id.strip():
            return False, {"error": "Missing order_id"}

        auth_ok, token_or_err = self.get_access_token()
        if not auth_ok:
            return False, {"error": token_or_err, "is_unconfigured": not self.is_configured}

        url = f"{self.base_url}/v2/checkout/orders/{order_id.strip()}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_or_err}",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            data = response.json() if response.content else {}

            if response.status_code == 200:
                return True, {
                    "order_id": data.get("id"),
                    "status": data.get("status"),
                    "intent": data.get("intent"),
                    "payer": data.get("payer", {}),
                    "purchase_units": data.get("purchase_units", []),
                    "create_time": data.get("create_time"),
                    "raw": data,
                }
            else:
                err_msg = data.get("message") or response.text
                return False, {"error": f"Failed to retrieve order ({response.status_code}): {err_msg}"}

        except requests.exceptions.RequestException as e:
            return False, {"error": f"Network exception fetching order details: {str(e)}"}

    def capture_order(self, order_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Capture payment for an approved PayPal Order using Orders v2 API.
        Never marks success unless verified by PayPal API with status='COMPLETED'
        and a verified capture transaction ID.
        """
        if not order_id or not order_id.strip():
            return False, {"error": "Missing order_id"}

        clean_order_id = order_id.strip()

        auth_ok, token_or_err = self.get_access_token()
        if not auth_ok:
            return False, {"error": token_or_err, "is_unconfigured": not self.is_configured}

        url = f"{self.base_url}/v2/checkout/orders/{clean_order_id}/capture"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_or_err}",
        }

        try:
            response = requests.post(url, headers=headers, json={}, timeout=20)
            data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                status = data.get("status")

                if status == "COMPLETED":
                    # Extract verified capture ID
                    capture_id = None
                    captured_amount = None
                    captured_currency = None

                    purchase_units = data.get("purchase_units", [])
                    if purchase_units:
                        payments = purchase_units[0].get("payments", {})
                        captures = payments.get("captures", [])
                        if captures and isinstance(captures, list):
                            cap = captures[0]
                            capture_id = cap.get("id")
                            amt_info = cap.get("amount", {})
                            captured_amount = amt_info.get("value")
                            captured_currency = amt_info.get("currency_code")

                    # STRICT VALIDATION: Never generate synthetic capture IDs
                    if not capture_id:
                        return False, {
                            "error": "PayPal response indicated COMPLETED status but did not return a verified capture transaction ID.",
                            "status": status,
                            "raw_response": data,
                        }

                    # Extract payer details
                    payer = data.get("payer", {})
                    payer_email = payer.get("email_address")
                    payer_name_obj = payer.get("name", {})
                    payer_name = (
                        f"{payer_name_obj.get('given_name', '')} {payer_name_obj.get('surname', '')}".strip()
                        or None
                    )

                    return True, {
                        "order_id": clean_order_id,
                        "transaction_id": capture_id,
                        "status": "COMPLETED",
                        "payer_email": payer_email,
                        "payer_name": payer_name,
                        "amount": captured_amount,
                        "currency": captured_currency,
                        "raw_response": data,
                    }
                else:
                    return False, {
                        "error": f"PayPal returned status '{status}' (expected COMPLETED). Payment was not captured.",
                        "status": status,
                    }

            elif response.status_code == 422:
                details = data.get("details", [])
                issues = [d.get("issue") for d in details if "issue" in d]

                if "ORDER_NOT_APPROVED" in issues:
                    return False, {
                        "error": "The buyer has not yet approved this payment in the PayPal Sandbox window. Please open the Checkout link, log in to your Sandbox buyer account, and approve the payment before capturing.",
                        "code": "ORDER_NOT_APPROVED",
                    }
                elif "ORDER_ALREADY_CAPTURED" in issues:
                    # STRICT RESOLUTION: Retrieve and verify actual order & capture details from PayPal
                    details_ok, details_data = self.get_order_details(clean_order_id)
                    if details_ok and details_data.get("status") == "COMPLETED":
                        purchase_units = details_data.get("purchase_units", [])
                        verified_capture_id = None
                        captured_amount = None
                        captured_currency = None

                        if purchase_units:
                            payments = purchase_units[0].get("payments", {})
                            captures = payments.get("captures", [])
                            if captures and isinstance(captures, list):
                                verified_capture_id = captures[0].get("id")
                                amt_info = captures[0].get("amount", {})
                                captured_amount = amt_info.get("value")
                                captured_currency = amt_info.get("currency_code")

                        if verified_capture_id:
                            payer = details_data.get("payer", {})
                            payer_email = payer.get("email_address")
                            payer_name_obj = payer.get("name", {})
                            payer_name = (
                                f"{payer_name_obj.get('given_name', '')} {payer_name_obj.get('surname', '')}".strip()
                                or None
                            )
                            return True, {
                                "order_id": clean_order_id,
                                "transaction_id": verified_capture_id,
                                "status": "COMPLETED",
                                "payer_email": payer_email,
                                "payer_name": payer_name,
                                "amount": captured_amount,
                                "currency": captured_currency,
                                "note": "Verified existing capture from PayPal Orders v2 records.",
                                "raw_response": details_data.get("raw", data),
                            }

                    return False, {
                        "error": "PayPal reports this order was already captured, but a verified capture ID could not be retrieved from PayPal API.",
                        "code": "ORDER_ALREADY_CAPTURED_UNVERIFIED",
                        "raw": data,
                    }
                else:
                    issue_texts = [d.get("description", d.get("issue", "")) for d in details]
                    return False, {
                        "error": f"PayPal Validation Error (422): {'; '.join(issue_texts)}",
                        "raw": data,
                    }
            else:
                err_msg = data.get("message") or response.text
                return False, {"error": f"PayPal Capture Failed ({response.status_code}): {err_msg}"}

        except requests.exceptions.RequestException as e:
            return False, {"error": f"Network exception during payment capture: {str(e)}"}
