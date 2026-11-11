"""
Comprehensive Test Suite for PayPilot MVP
Covers:
- SQLite database transactions, metrics, filtering, and ordering
- AI Payment Assistant intent extraction and conversational logic
- PayPal REST API v2 OAuth, Order creation, Approval link extraction, and Capture parsing
- Validation logic for amounts, currencies, missing credentials, and error responses
"""

import os
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


class TestPayPalService(unittest.TestCase):
    """Test PayPal Service client validation, OAuth flow, and API response parsing."""

    def test_unconfigured_state(self):
        """Verify unconfigured client reports clean error message."""
        svc = PayPalService(client_id="", client_secret="")
        self.assertFalse(svc.is_configured)
        ok, msg = svc.get_access_token()
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())

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
        # 1. Mock token response
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.content = b"{}"
        token_resp.json.return_value = {"access_token": "VALID_TOKEN", "expires_in": 3600}

        # 2. Mock create order response
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


if __name__ == "__main__":
    unittest.main()
