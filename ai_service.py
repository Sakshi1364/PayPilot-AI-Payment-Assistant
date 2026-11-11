"""
PayPilot - AI Service Module
Powered by Google Gemini API using the official `google-genai` SDK.
Handles payment intent parsing, natural language assistant conversations,
and financial transaction insights.
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional
from google import genai
from google.genai import types

from config_utils import get_secret

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are PayPilot AI, an elite fintech payment assistant and financial intelligence advisor built for PayPal integration.
Your role is to:
1. Help users understand and create payments via PayPal Sandbox.
2. Extract and validate payment details (amount, currency, recipient/item, category).
3. Explain how PayPal payments work (Orders v2, Checkout approval, Capture, Buyer Protection).
4. Provide financial insights based strictly on user transaction records from the SQLite database.
5. NEVER execute, create, or capture a payment independently. You only extract the details and present them clearly for explicit user approval.
6. Be concise, professional, accurate, and helpful. Use markdown formatting with bullet points and bold highlights.
"""

INTENT_EXTRACTION_PROMPT = """Analyze the user's input and determine whether it represents a payment intent or financial transaction request.

Return a STRICT valid JSON object with the following schema (no markdown formatting around the JSON, just the JSON string):
{
  "is_payment_request": true or false,
  "amount": float or null (numeric value only, e.g. 25.0),
  "currency": string or null (3-letter uppercase ISO code like USD, EUR, GBP. Default to "USD" if currency symbol is $ or unspecified),
  "description": string or null (short description of the item or purpose),
  "category": string (one of "Subscription", "Services", "Shopping", "Food & Dining", "Travel", "Utilities", "General"),
  "confidence": float (between 0.0 and 1.0),
  "explanation": string (brief, friendly explanation of what you understood),
  "needs_clarification": true or false,
  "clarification_question": string or null (if amount or description is ambiguous)
}

User input:
"""


class PayPilotAI:
    """Google Gemini AI integration for PayPilot payment assistant."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = (api_key or get_secret("GEMINI_API_KEY", "")).strip()
        self.model = model
        self._client: Optional[genai.Client] = None

        if self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                logger.warning("Failed to initialize Google GenAI Client: %s", type(e).__name__)
                self._client = None

    @property
    def is_configured(self) -> bool:
        """Return True if Gemini API key is configured."""
        return bool(self.api_key and self._client is not None)

    def parse_payment_intent(self, user_input: str) -> Dict[str, Any]:
        """
        Parse natural language payment request into structured JSON.
        Uses Gemini API when configured, falls back to deterministic NLP regex parser.
        """
        if not user_input or not user_input.strip():
            return {
                "is_payment_request": False,
                "amount": None,
                "currency": "USD",
                "description": "",
                "category": "General",
                "confidence": 0.0,
                "explanation": "No input provided.",
                "needs_clarification": False,
                "clarification_question": None,
            }

        # Try Gemini API first if configured
        if self.is_configured and self._client:
            try:
                prompt = INTENT_EXTRACTION_PROMPT + f'"{user_input}"'
                # Support Gemini 2.5 Flash with fallback to 2.0 Flash or 1.5 Flash
                response = None
                for candidate_model in [self.model, "gemini-2.0-flash", "gemini-1.5-flash"]:
                    try:
                        response = self._client.models.generate_content(
                            model=candidate_model,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                temperature=0.1,
                            ),
                        )
                        if response and response.text:
                            break
                    except Exception as model_err:
                        logger.warning("Gemini model %s failed: %s", candidate_model, model_err)
                        continue

                if response and response.text:
                    cleaned_text = response.text.strip()
                    # Strip any markdown code fences if returned
                    if cleaned_text.startswith("```json"):
                        cleaned_text = cleaned_text[7:]
                    if cleaned_text.startswith("```"):
                        cleaned_text = cleaned_text[3:]
                    if cleaned_text.endswith("```"):
                        cleaned_text = cleaned_text[:-3]

                    parsed = json.loads(cleaned_text.strip())

                    # Post-validate parsed fields
                    if parsed.get("amount") is not None:
                        try:
                            parsed["amount"] = round(float(parsed["amount"]), 2)
                        except (ValueError, TypeError):
                            parsed["amount"] = None

                    if not parsed.get("currency"):
                        parsed["currency"] = "USD"
                    else:
                        parsed["currency"] = str(parsed["currency"]).upper()

                    parsed["source"] = "Gemini AI"
                    return parsed

            except Exception as e:
                logger.error("Gemini API error during intent parsing: %s. Falling back to local parser.", e)

        # Deterministic regex fallback parser
        return self._fallback_regex_parser(user_input)

    def _fallback_regex_parser(self, user_input: str) -> Dict[str, Any]:
        """Deterministic NLP pattern extractor for offline/demo/unconfigured modes."""
        text = user_input.strip()

        # Keywords indicating payment intent
        payment_triggers = [
            "pay",
            "send",
            "create payment",
            "order",
            "checkout",
            "transfer",
            "buy",
            "purchase",
            "bill",
            "invoice",
            "subscription",
            "$",
            "usd",
            "eur",
            "gbp",
        ]
        is_payment = any(trigger in text.lower() for trigger in payment_triggers)

        # Regex to capture amount and currency
        # Examples: "$25", "$50.00", "25 dollars", "100 USD", "€40", "£15.50"
        amount: Optional[float] = None
        currency = "USD"

        # Check currency symbols
        if "€" in text or "eur" in text.lower():
            currency = "EUR"
        elif "£" in text or "gbp" in text.lower():
            currency = "GBP"
        elif "cad" in text.lower():
            currency = "CAD"
        elif "aud" in text.lower():
            currency = "AUD"

        # Match numbers with optional currency symbol
        amount_patterns = [
            r"[$€£]?\s*(\d+(?:\.\d{1,2})?)\s*(?:usd|dollars|bucks|eur|gbp)?",
            r"(?:for|pay|of)\s+[$€£]?\s*(\d+(?:\.\d{1,2})?)",
        ]

        for pat in amount_patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                try:
                    val = float(match.group(1))
                    if val > 0:
                        amount = val
                        break
                except ValueError:
                    pass

        # Extract description / item
        description = "Payment Order"
        category = "General"

        desc_patterns = [
            r"(?:for|towards|on)\s+([^.,!?\n]+)",
            r"(?:pay|send)\s+[$€£]?\d+(?:\.\d{1,2})?\s+(?:for\s+)?([^.,!?\n]+)",
        ]
        for pat in desc_patterns:
            desc_match = re.search(pat, text, re.IGNORECASE)
            if desc_match:
                extracted_desc = desc_match.group(1).strip()
                # Clean out common filler words
                extracted_desc = re.sub(
                    r"^(a|an|the|some|my)\s+", "", extracted_desc, flags=re.IGNORECASE
                )
                if extracted_desc:
                    description = extracted_desc.capitalize()
                    break

        # Categorize
        desc_lower = description.lower()
        if any(w in desc_lower for w in ["sub", "subscription", "monthly", "saas", "netflix", "spotify"]):
            category = "Subscription"
        elif any(w in desc_lower for w in ["hosting", "cloud", "api", "dev", "consult", "freelance", "service"]):
            category = "Services"
        elif any(w in desc_lower for w in ["book", "shirt", "gear", "item", "product", "gadget", "shop", "buy"]):
            category = "Shopping"
        elif any(w in desc_lower for w in ["food", "dinner", "lunch", "coffee", "meal", "pizza", "restaurant"]):
            category = "Food & Dining"
        elif any(w in desc_lower for w in ["flight", "hotel", "uber", "taxi", "travel"]):
            category = "Travel"
        elif any(w in desc_lower for w in ["bill", "domain", "internet", "electricity", "phone"]):
            category = "Utilities"

        needs_clarification = (amount is None) and is_payment

        explanation = (
            f"Detected payment request for {currency} {amount:.2f} ({description})."
            if amount
            else "I noticed a payment topic, but need to know the exact amount."
        )

        return {
            "is_payment_request": is_payment and (amount is not None),
            "amount": amount,
            "currency": currency,
            "description": description,
            "category": category,
            "confidence": 0.85 if amount else 0.40,
            "explanation": explanation,
            "needs_clarification": needs_clarification,
            "clarification_question": "What amount would you like to pay?" if needs_clarification else None,
            "source": "PayPilot Rule-Based NLP",
        }

    def chat_response(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        db_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate conversational reply with Gemini.
        Equipped with PayPal knowledge base and database transaction context.
        """
        if not user_message or not user_message.strip():
            return "How can I assist you with your PayPal payments today?"

        # Gemini API generation if client is available
        if self.is_configured and self._client:
            try:
                # Build context
                context_str = ""
                if db_context:
                    context_str = (
                        f"\nCURRENT USER FINANCIAL CONTEXT FROM DATABASE:\n"
                        f"- Total Transactions: {db_context.get('total_count', 0)}\n"
                        f"- Completed Payments: {db_context.get('completed_count', 0)}\n"
                        f"- Pending Orders: {db_context.get('pending_count', 0)}\n"
                        f"- Total Volume Spent: ${db_context.get('total_volume', 0.0):.2f}\n"
                        f"- Success Rate: {db_context.get('success_rate', 0.0)}%\n"
                        f"- Recent Records: {json.dumps(db_context.get('recent_transactions', []))}\n"
                    )

                full_prompt = (
                    f"{SYSTEM_PROMPT}\n{context_str}\n"
                    f"Conversation so far:\n"
                )
                for msg in conversation_history[-6:]:
                    full_prompt += f"{msg.get('role', 'user').title()}: {msg.get('content', '')}\n"

                full_prompt += f"User: {user_message}\nPayPilot AI:"

                for candidate_model in [self.model, "gemini-2.0-flash", "gemini-1.5-flash"]:
                    try:
                        res = self._client.models.generate_content(
                            model=candidate_model,
                            contents=full_prompt,
                            config=types.GenerateContentConfig(temperature=0.4),
                        )
                        if res and res.text:
                            return res.text.strip()
                    except Exception as model_err:
                        logger.warning("Gemini model %s failed for chat: %s", candidate_model, model_err)
                        continue

            except Exception as e:
                logger.error("Error generating Gemini chat response: %s", e)

        # Fallback intelligent conversational responses
        msg_lower = user_message.lower()

        if "how paypal payments work" in msg_lower or "how paypal works" in msg_lower:
            return (
                "### 💳 How PayPal Payments Work\n\n"
                "PayPal's REST Orders v2 API follows a secure, 3-step lifecycle:\n\n"
                "1. **Order Creation (`intent: CAPTURE`)**:\n"
                "   The merchant creates an order detailing the amount, currency, and items. PayPal returns a unique Order ID and a buyer approval link.\n\n"
                "2. **Buyer Approval (PayPal Checkout)**:\n"
                "   The user opens the PayPal Checkout window, authenticates with their PayPal account or enters card details, and reviews the total. No money is moved yet.\n\n"
                "3. **Payment Capture**:\n"
                "   Once approved, PayPilot triggers the official `POST /v2/checkout/orders/{id}/capture` call. PayPal verifies funds, processes the transaction, and returns a final `COMPLETED` capture ID.\n\n"
                "🔒 **Security**: Sensitive payment details are handled exclusively on PayPal's secure servers, never touching our application."
            )

        if "recent transaction" in msg_lower or "transaction history" in msg_lower or "show me" in msg_lower:
            if db_context and db_context.get("recent_transactions"):
                recent = db_context["recent_transactions"]
                lines = ["### 📜 Recent Transactions in Database:\n"]
                for t in recent[:5]:
                    lines.append(
                        f"- **{t.get('description', 'Order')}**: {t.get('currency', 'USD')} {t.get('amount', 0.0):.2f} "
                        f"• Status: `{t.get('status', 'PENDING')}` • Order ID: `{t.get('paypal_order_id', 'N/A')}`"
                    )
                return "\n".join(lines)
            else:
                return "You currently have no recorded transactions in your database. You can create a new payment request to test the flow!"

        if "summarize" in msg_lower or "summary" in msg_lower or "activity" in msg_lower:
            if db_context:
                return (
                    f"### 📊 Financial Activity Summary\n\n"
                    f"- **Total Volume**: ${db_context.get('total_volume', 0.0):.2f} USD\n"
                    f"- **Completed Transactions**: {db_context.get('completed_count', 0)}\n"
                    f"- **Pending Orders**: {db_context.get('pending_count', 0)}\n"
                    f"- **Success Rate**: {db_context.get('success_rate', 0.0)}%\n\n"
                    f"All metrics are computed in real time from your local SQLite transaction store."
                )

        return (
            "I'm **PayPilot**, your AI payment assistant. I can help you create and validate PayPal payments, "
            "explain payment workflows, or inspect your transaction history.\n\n"
            "Try asking:\n"
            "- *'I want to pay $25 for a subscription.'*\n"
            "- *'Help me create a payment for $50 for Cloud Hosting.'*\n"
            "- *'Explain how PayPal payments work.'*\n"
            "- *'Summarize my payment activity.'*"
        )

    def generate_financial_insights(
        self,
        transactions: List[Dict[str, Any]],
        metrics: Dict[str, Any],
        category_breakdown: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Generate deep financial insights and categorization using Gemini API
        based strictly on the SQLite database records.
        """
        if not transactions:
            return {
                "headline": "No Transaction History Yet",
                "summary": "Start by initiating a PayPal Sandbox payment to generate financial insights.",
                "insights": [],
                "recommendations": [
                    "Create your first PayPal sandbox test payment using the AI Assistant or Direct Terminal."
                ],
            }

        # Format data for LLM
        tx_summary = []
        for t in transactions[:30]:
            tx_summary.append({
                "order_id": t.get("paypal_order_id"),
                "amount": t.get("amount"),
                "currency": t.get("currency"),
                "category": t.get("category"),
                "status": t.get("status"),
                "description": t.get("description"),
                "date": t.get("created_at"),
            })

        if self.is_configured and self._client:
            prompt = f"""You are PayPilot's Senior Financial Analyst AI.
Analyze the following user transaction data from their PayPal account store:

Metrics:
- Total Transactions: {metrics.get('total_count', 0)}
- Completed Count: {metrics.get('completed_count', 0)}
- Total Volume Completed: ${metrics.get('total_volume', 0.0):.2f}
- Pending Orders: {metrics.get('pending_count', 0)}

Category Breakdown:
{json.dumps(category_breakdown, indent=2)}

Transaction Records:
{json.dumps(tx_summary, indent=2)}

Strictly based on this data (do NOT invent data or mention bank accounts), provide a structured JSON response:
{{
  "headline": "A concise punchy executive headline summarizing the financial behavior",
  "summary": "2-3 sentences overview of spending velocity and completion health",
  "insights": [
    "Key insight 1 regarding spending distribution or recurring expenses",
    "Key insight 2 regarding transaction sizes or trends",
    "Key insight 3 regarding pending or uncompleted orders"
  ],
  "recommendations": [
    "Practical actionable tip 1",
    "Practical actionable tip 2"
  ]
}}
"""
            for candidate_model in [self.model, "gemini-2.0-flash", "gemini-1.5-flash"]:
                try:
                    res = self._client.models.generate_content(
                        model=candidate_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2,
                        ),
                    )
                    if res and res.text:
                        cleaned = res.text.strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned[7:]
                        if cleaned.startswith("```"):
                            cleaned = cleaned[3:]
                        if cleaned.endswith("```"):
                            cleaned = cleaned[:-3]
                        return json.loads(cleaned.strip())
                except Exception as e:
                    logger.warning("Gemini financial insights failed with %s: %s", candidate_model, e)
                    continue

        # Deterministic analytical fallback
        top_cat = category_breakdown[0]["category"] if category_breakdown else "General"
        top_cat_amount = category_breakdown[0]["total_amount"] if category_breakdown else 0.0

        return {
            "headline": f"Financial Overview: {metrics.get('completed_count', 0)} Completed Payments totaling ${metrics.get('total_volume', 0.0):.2f}",
            "summary": f"Your primary spending allocation is in the '{top_cat}' category (${top_cat_amount:.2f}). Overall payment success rate stands at {metrics.get('success_rate', 0.0)}%.",
            "insights": [
                f"Top spending category is '{top_cat}', accounting for the majority of completed volume.",
                f"Average transaction size is ${metrics.get('avg_transaction', 0.0):.2f}.",
                f"You have {metrics.get('pending_count', 0)} pending order(s) awaiting capture or approval.",
            ],
            "recommendations": [
                "Review pending payments in the Transaction History table to either capture or clear abandoned checkouts.",
                "Set recurring payment budgets for high-velocity categories like Services and Subscriptions.",
            ],
        }
