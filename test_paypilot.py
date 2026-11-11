"""
Comprehensive Test Suite for PayPilot MVP
Strictly isolated unit tests covering:
- SQLite database transactions, metrics, filtering, search, and lifecycle
- AI Payment Assistant intent extraction and conversational logic (rule-based & mocked Gemini)
- PayPal REST API v2 OAuth, Order creation, Approval link extraction, and Capture parsing
- Validation logic for amounts, currencies, missing credentials, and error responses

NOTE: All PayPal and Gemini external API interactions in this file use mocks.
To run live end-to-end sandbox verification, see `verify_live_sandbox.py`.
"""

import os
import json
import unittest
import tempfile
from unittest.mock import patch, MagicMock
import database as db
from paypal_service import PayPalService
from ai_service import PayPilotAI


class TestPayPilotDatabase(unittest.TestCase):
    """Test SQLite database operations, queries, and aggregations."""

    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.db_path = self.temp_db.name
        db.init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_init_db(self):
        """Verify table creation and initial empty state."""
        txs = db.get_all_transactions(db_path=self.db_path)
        self.assertEqual(len(txs), 0)

    def test_create_and_complete_order(self):
        """Verify order insertion, status transition, and completion capture update."""
        order_id = "ORD_TEST_998877"
        amount = 75.50
        currency = "USD"
        description = "Pro Developer Cloud Plan"

        # 1. Create order
        row_id = db.create_order_record(
            paypal_order_id=order_id,
            amount=amount,
            currency=currency,
            description=description,
            category="Services",
            status="PENDING",
            approval_url="https://www.sandbox.paypal.com/checkoutnow?token=TEST",
            db_path=self.db_path,
        )
        self.assertGreater(row_id, 0)

        # 2. Check pending state
        rec = db.get_transaction_by_order_id(order_id, db_path=self.db_path)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["status"], "PENDING")
        self.assertEqual(rec["amount"], 75.50)
        self.assertEqual(rec["currency"], "USD")
        self.assertEqual(rec["category"], "Services")

        # 3. Update to completed
        ok = db.complete_order_record(
            paypal_order_id=order_id,
            transaction_id="CAP_5544332211",
            payer_email="buyer@example.com",
            payer_name="Jane Doe",
            db_path=self.db_path,
        )
        self.assertTrue(ok)

        # 4. Check completed state
        updated = db.get_transaction_by_order_id(order_id, db_path=self.db_path)
        self.assertEqual(updated["status"], "COMPLETED")
        self.assertEqual(updated["transaction_id"], "CAP_5544332211")
        self.assertEqual(updated["payer_email"], "buyer@example.com")
        self.assertEqual(updated["payer_name"], "Jane Doe")

    def test_update_order_status_cancelled(self):
        """Verify updating order status to CANCELLED."""
        order_id = "ORD_CANCEL_01"
        db.create_order_record(paypal_order_id=order_id, amount=10.0, db_path=self.db_path)
        db.update_order_status(order_id, "CANCELLED", db_path=self.db_path)
        rec = db.get_transaction_by_order_id(order_id, db_path=self.db_path)
        self.assertEqual(rec["status"], "CANCELLED")

    def test_metrics_calculation(self):
        """Verify metrics calculations with seed data."""
        db.seed_sample_data(db_path=self.db_path)
        metrics = db.get_metrics(db_path=self.db_path)

        self.assertGreater(metrics["total_count"], 0)
        self.assertGreater(metrics["completed_count"], 0)
        self.assertGreater(metrics["total_volume"], 0.0)
        self.assertGreaterEqual(metrics["success_rate"], 0.0)
        self.assertLessEqual(metrics["success_rate"], 100.0)

    def test_category_breakdown(self):
        """Verify category breakdown calculations."""
        db.seed_sample_data(db_path=self.db_path)
        cats = db.get_category_breakdown(db_path=self.db_path)
        self.assertGreater(len(cats), 0)
        self.assertTrue(any(c["category"] == "Subscription" for c in cats))

    def test_status_filtering_and_search(self):
        """Verify filtering by status and text searching."""
        db.seed_sample_data(db_path=self.db_path)

        completed = db.get_all_transactions(status="COMPLETED", db_path=self.db_path)
        for t in completed:
            self.assertEqual(t["status"], "COMPLETED")

        pending = db.get_all_transactions(status="PENDING", db_path=self.db_path)
        for t in pending:
            self.assertEqual(t["status"], "PENDING")

        # Search by description
        searched = db.get_all_transactions(search="Hosting", db_path=self.db_path)
        self.assertGreater(len(searched), 0)
        self.assertIn("hosting", searched[0]["description"].lower())

    def test_clear_all_transactions(self):
        """Verify wiping all transactions."""
        db.seed_sample_data(db_path=self.db_path)
        db.clear_all_transactions(db_path=self.db_path)
        txs = db.get_all_transactions(db_path=self.db_path)
        self.assertEqual(len(txs), 0)


class TestPayPilotAI(unittest.TestCase):
    """Test AI intent extraction and conversational logic."""

    def setUp(self):
        self.ai = PayPilotAI(api_key="")

    def test_parse_payment_subscription(self):
        """Test extraction of subscription payment query."""
        res = self.ai.parse_payment_intent("I want to pay $25 for a subscription.")
        self.assertTrue(res["is_payment_request"])
        self.assertEqual(res["amount"], 25.0)
        self.assertEqual(res["currency"], "USD")
        self.assertEqual(res["category"], "Subscription")

    def test_parse_payment_cloud_hosting(self):
        """Test extraction of cloud hosting payment query."""
        res = self.ai.parse_payment_intent("Help me create a payment for $50 for Cloud Hosting.")
        self.assertTrue(res["is_payment_request"])
        self.assertEqual(res["amount"], 50.0)
        self.assertEqual(res["currency"], "USD")
        self.assertEqual(res["category"], "Services")

    def test_parse_euro_currency(self):
        """Test extraction of EUR currency symbol."""
        res = self.ai.parse_payment_intent("Send €35 for consulting fees")
        self.assertTrue(res["is_payment_request"])
        self.assertEqual(res["amount"], 35.0)
        self.assertEqual(res["currency"], "EUR")

    def test_parse_ambiguous_payment(self):
        """Test clarification request when amount is missing."""
        res = self.ai.parse_payment_intent("I want to pay for my netflix subscription")
        self.assertTrue(res["needs_clarification"])
        self.assertIsNone(res["amount"])

    def test_parse_non_payment_query(self):
        """Test non-payment query parsing."""
        res = self.ai.parse_payment_intent("Explain how PayPal payments work.")
        self.assertFalse(res["is_payment_request"])
        self.assertIsNone(res["amount"])

    def test_chat_response_paypal_workflow(self):
        """Test explanation of PayPal payment workflow."""
        explanation = self.ai.chat_response("Explain how PayPal payments work.", [])
        self.assertIn("PayPal", explanation)
        self.assertIn("Capture", explanation)

    def test_chat_response_recent_transactions(self):
        """Test chat response when asking for recent transactions."""
        mock_ctx = {
            "total_count": 2,
            "completed_count": 2,
            "pending_count": 0,
            "total_volume": 50.0,
            "success_rate": 100.0,
            "recent_transactions": [
                {"description": "SaaS Plan", "amount": 20.0, "currency": "USD", "status": "COMPLETED", "paypal_order_id": "ORD1"},
                {"description": "Domain", "amount": 30.0, "currency": "USD", "status": "COMPLETED", "paypal_order_id": "ORD2"},
            ]
        }
        resp = self.ai.chat_response("Show me my recent transactions", [], db_context=mock_ctx)
        self.assertIn("SaaS Plan", resp)
        self.assertIn("Domain", resp)

    @patch("google.genai.Client")
    def test_gemini_configured_intent_parsing(self, mock_client_cls):
        """Verify that when Gemini API is configured, Gemini responses are parsed and labeled."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "is_payment_request": True,
            "amount": 120.0,
            "currency": "USD",
            "description": "Annual Premium SaaS Membership",
            "category": "Subscription",
            "confidence": 0.98,
            "explanation": "Detected an annual subscription payment of $120.00 USD.",
            "needs_clarification": False,
            "clarification_question": None
        })
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        ai_configured = PayPilotAI(api_key="mock_gemini_key_12345")
        res = ai_configured.parse_payment_intent("Pay $120 for annual premium membership")

        self.assertTrue(res["is_payment_request"])
        self.assertEqual(res["amount"], 120.0)
        self.assertEqual(res["category"], "Subscription")
        self.assertEqual(res.get("source"), "Gemini AI")

    @patch("google.genai.Client")
    def test_gemini_financial_insights_generation(self, mock_client_cls):
        """Verify Gemini financial insights generation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "headline": "Healthy Velocity in Developer Tooling",
            "summary": "Completed 5 orders totaling $171.49 with 100% capture rate.",
            "insights": [
                "Highest spend is in Services ($89.50).",
                "Recurring subscriptions account for 15% of budget."
            ],
            "recommendations": [
                "Audit monthly SaaS subscriptions quarterly."
            ]
        })
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        ai_configured = PayPilotAI(api_key="mock_gemini_key_12345")
        insights = ai_configured.generate_financial_insights(
            transactions=[{"paypal_order_id": "ORD1", "amount": 50.0, "status": "COMPLETED"}],
            metrics={"total_count": 1, "completed_count": 1, "total_volume": 50.0, "success_rate": 100.0},
            category_breakdown=[{"category": "Services", "total_amount": 50.0}]
        )

        self.assertEqual(insights["headline"], "Healthy Velocity in Developer Tooling")
        self.assertGreater(len(insights["insights"]), 0)


class TestPayPalService(unittest.TestCase):
    """Test PayPal Service client validation, OAuth flow, and API response parsing."""

    def test_unconfigured_state(self):
        """Verify unconfigured client reports clean error message without faking payments."""
        svc = PayPalService(client_id="", client_secret="")
        self.assertFalse(svc.is_configured)
        ok, msg = svc.get_access_token()
        self.assertFalse(ok)
        self.assertIn("not configured", msg.lower())

    def test_create_order_unconfigured_fails_safely(self):
        """Verify creating order without credentials fails cleanly with error explanation."""
        svc = PayPalService(client_id="", client_secret="")
        ok, res = svc.create_order(amount=25.00, currency="USD")
        self.assertFalse(ok)
        self.assertTrue(res.get("is_unconfigured"))
        self.assertIn("not configured", res["error"].lower())

    def test_capture_order_unconfigured_fails_safely(self):
        """Verify capturing order without credentials fails cleanly."""
        svc = PayPalService(client_id="", client_secret="")
        ok, res = svc.capture_order("TEST_ORDER_ID")
        self.assertFalse(ok)
        self.assertTrue(res.get("is_unconfigured"))

    def test_amount_validation(self):
        """Verify negative or zero amount is rejected prior to API call."""
        svc = PayPalService(client_id="mock_id", client_secret="mock_secret")
        ok, res = svc.create_order(amount=-10.00, currency="USD")
        self.assertFalse(ok)
        self.assertIn("greater than", res["error"])

    def test_empty_order_capture_validation(self):
        """Verify capture requires valid order ID."""
        svc = PayPalService(client_id="mock_id", client_secret="mock_secret")
        ok, res = svc.capture_order("")
        self.assertFalse(ok)
        self.assertIn("Missing order_id", res["error"])

    @patch("requests.post")
    def test_oauth_success_and_caching(self, mock_post):
        """Verify OAuth 2.0 token generation and caching mechanism."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "ACCESS_TOKEN_ABC_123",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_resp.content = b'{"access_token": "ACCESS_TOKEN_ABC_123"}'
        mock_post.return_value = mock_resp

        svc = PayPalService(client_id="CLIENT_ID", client_secret="CLIENT_SECRET")
        ok, token = svc.get_access_token()
        self.assertTrue(ok)
        self.assertEqual(token, "ACCESS_TOKEN_ABC_123")

        # Second call should reuse cached token without network request
        mock_post.reset_mock()
        ok2, token2 = svc.get_access_token()
        self.assertTrue(ok2)
        self.assertEqual(token2, "ACCESS_TOKEN_ABC_123")
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_create_order_success(self, mock_post):
        """Verify order creation extracts approval URL and order ID."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        order_resp = MagicMock()
        order_resp.status_code = 201
        order_resp.content = b"{}"
        order_resp.json.return_value = {
            "id": "5O190127TN364715T",
            "status": "CREATED",
            "links": [
                {"href": "https://api-m.sandbox.paypal.com/v2/checkout/orders/5O190127TN364715T", "rel": "self"},
                {"href": "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T", "rel": "approve"},
            ],
        }

        mock_post.side_effect = [token_resp, order_resp]

        svc = PayPalService(client_id="CID", client_secret="CSECRET")
        ok, data = svc.create_order(amount=25.00, currency="USD", description="Subscription")
        self.assertTrue(ok)
        self.assertEqual(data["order_id"], "5O190127TN364715T")
        self.assertEqual(data["status"], "CREATED")
        self.assertEqual(data["approval_url"], "https://www.sandbox.paypal.com/checkoutnow?token=5O190127TN364715T")

    @patch("requests.post")
    def test_create_order_payer_action_link_fallback(self, mock_post):
        """Verify order creation recognizes 'payer-action' rel as approval URL."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        order_resp = MagicMock()
        order_resp.status_code = 201
        order_resp.content = b"{}"
        order_resp.json.return_value = {
            "id": "7P281038UM475826X",
            "status": "CREATED",
            "links": [
                {"href": "https://www.sandbox.paypal.com/checkoutnow?token=7P281038UM475826X", "rel": "payer-action"},
            ],
        }

        mock_post.side_effect = [token_resp, order_resp]

        svc = PayPalService(client_id="CID", client_secret="CSECRET")
        ok, data = svc.create_order(amount=50.00, currency="USD")
        self.assertTrue(ok)
        self.assertEqual(data["approval_url"], "https://www.sandbox.paypal.com/checkoutnow?token=7P281038UM475826X")

    @patch("requests.post")
    def test_capture_order_success(self, mock_post):
        """Verify successful order capture response parsing."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        cap_resp = MagicMock()
        cap_resp.status_code = 201
        cap_resp.content = b"{}"
        cap_resp.json.return_value = {
            "id": "5O190127TN364715T",
            "status": "COMPLETED",
            "payer": {
                "email_address": "buyer-test@example.com",
                "name": {"given_name": "Alex", "surname": "Smith"},
            },
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "2C778234D3554341B",
                                "status": "COMPLETED",
                                "amount": {"currency_code": "USD", "value": "25.00"},
                            }
                        ]
                    }
                }
            ],
        }

        mock_post.side_effect = [token_resp, cap_resp]

        svc = PayPalService(client_id="CID", client_secret="CSECRET")
        ok, res = svc.capture_order("5O190127TN364715T")
        self.assertTrue(ok)
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["transaction_id"], "2C778234D3554341B")
        self.assertEqual(res["payer_email"], "buyer-test@example.com")
        self.assertEqual(res["payer_name"], "Alex Smith")

    @patch("requests.post")
    def test_capture_order_not_approved_handling(self, mock_post):
        """Verify ORDER_NOT_APPROVED 422 error is caught and converted to friendly guidance."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        err_resp = MagicMock()
        err_resp.status_code = 422
        err_resp.content = b"{}"
        err_resp.json.return_value = {
            "name": "UNPROCESSABLE_ENTITY",
            "details": [{"issue": "ORDER_NOT_APPROVED", "description": "Payer has not yet approved the Order"}],
            "message": "The requested action could not be performed",
        }

        mock_post.side_effect = [token_resp, err_resp]

        svc = PayPalService(client_id="CID", client_secret="CSECRET")
        ok, res = svc.capture_order("5O190127TN364715T")
        self.assertFalse(ok)
        self.assertEqual(res["code"], "ORDER_NOT_APPROVED")
        self.assertIn("not yet approved", res["error"])

    @patch("requests.post")
    def test_capture_order_missing_capture_id_fails(self, mock_post):
        """Verify capture fails if PayPal returns COMPLETED but no capture ID is present."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        # Response without captures list
        cap_resp = MagicMock()
        cap_resp.status_code = 201
        cap_resp.content = b"{}"
        cap_resp.json.return_value = {
            "id": "5O190127TN364715T",
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"captures": []}}],
        }

        mock_post.side_effect = [token_resp, cap_resp]

        svc = PayPalService(client_id="CID", client_secret="CSECRET")
        ok, res = svc.capture_order("5O190127TN364715T")
        self.assertFalse(ok)
        self.assertIn("verified capture", res["error"].lower())

    @patch("requests.get")
    @patch("requests.post")
    def test_capture_order_already_captured_verified(self, mock_post, mock_get):
        """Verify ORDER_ALREADY_CAPTURED triggers order details lookup and extracts verified capture ID."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        err_resp = MagicMock()
        err_resp.status_code = 422
        err_resp.content = b"{}"
        err_resp.json.return_value = {
            "name": "UNPROCESSABLE_ENTITY",
            "details": [{"issue": "ORDER_ALREADY_CAPTURED", "description": "Order already captured"}],
            "message": "Order already captured",
        }

        mock_post.side_effect = [token_resp, err_resp]

        details_resp = MagicMock()
        details_resp.status_code = 200
        details_resp.content = b"{}"
        details_resp.json.return_value = {
            "id": "5O190127TN364715T",
            "status": "COMPLETED",
            "payer": {"email_address": "verified-buyer@example.com", "name": {"given_name": "Sarah", "surname": "Connor"}},
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "REAL_CAPTURE_ID_778899",
                                "status": "COMPLETED",
                                "amount": {"value": "25.00", "currency_code": "USD"},
                            }
                        ]
                    }
                }
            ],
        }
        mock_get.return_value = details_resp

        svc = PayPalService(client_id="CID", client_secret="CSECRET")
        ok, res = svc.capture_order("5O190127TN364715T")
        self.assertTrue(ok)
        self.assertEqual(res["status"], "COMPLETED")
        self.assertEqual(res["transaction_id"], "REAL_CAPTURE_ID_778899")
        self.assertEqual(res["payer_email"], "verified-buyer@example.com")

    @patch("requests.get")
    @patch("requests.post")
    def test_capture_order_already_captured_unverified_fails(self, mock_post, mock_get):
        """Verify ORDER_ALREADY_CAPTURED fails safely if order details do not contain a capture ID."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        err_resp = MagicMock()
        err_resp.status_code = 422
        err_resp.content = b"{}"
        err_resp.json.return_value = {
            "name": "UNPROCESSABLE_ENTITY",
            "details": [{"issue": "ORDER_ALREADY_CAPTURED"}],
        }
        mock_post.side_effect = [token_resp, err_resp]

        # Order details endpoint returns error
        details_resp = MagicMock()
        details_resp.status_code = 404
        details_resp.content = b"{}"
        details_resp.json.return_value = {"message": "Order not found"}
        mock_get.return_value = details_resp

        svc = PayPalService(client_id="CID", client_secret="CSECRET")
        ok, res = svc.capture_order("5O190127TN364715T")
        self.assertFalse(ok)
        self.assertEqual(res.get("code"), "ORDER_ALREADY_CAPTURED_UNVERIFIED")

    @patch("requests.post")
    def test_capture_order_status_not_completed_fails(self, mock_post):
        """Verify capture fails if status returned is not COMPLETED (e.g. SAVED or VOIDED)."""
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        cap_resp = MagicMock()
        cap_resp.status_code = 200
        cap_resp.content = b"{}"
        cap_resp.json.return_value = {"id": "ORD1", "status": "VOIDED"}

        mock_post.side_effect = [token_resp, cap_resp]

        svc = PayPalService(client_id="CID", client_secret="CSECRET")
        ok, res = svc.capture_order("ORD1")
        self.assertFalse(ok)
        self.assertIn("VOIDED", res["error"])


class TestConfigUtils(unittest.TestCase):
    """Test configuration and secret retrieval/masking."""

    def test_get_secret_fallback(self):
        from config_utils import get_secret
        val = get_secret("NON_EXISTENT_KEY_XYZ", default="fallback_val")
        self.assertEqual(val, "fallback_val")

    def test_mask_secret(self):
        from config_utils import mask_secret
        self.assertEqual(mask_secret(""), "Not Configured")
        self.assertEqual(mask_secret("short"), "••••••••")
        masked = mask_secret("paypal_client_secret_super_long_12345")
        self.assertTrue(masked.startswith("pay"))
        self.assertTrue(masked.endswith("345"))
        self.assertIn("••••••••", masked)


if __name__ == "__main__":
    unittest.main()
