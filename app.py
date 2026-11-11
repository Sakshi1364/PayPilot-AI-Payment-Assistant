"""
PayPilot – AI-Powered Payment Assistant
A complete, production-quality hackathon MVP integrating official PayPal Sandbox REST API v2
and Google Gemini API (google-genai SDK).
"""

import os
import json
import base64
from typing import Dict, Any, List
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

# Import internal application modules
import database as db
from paypal_service import PayPalService
from ai_service import PayPilotAI
from config_utils import get_secret, mask_secret

# Load environment variables
load_dotenv()

# --- Page Configuration ---
st.set_page_config(
    page_title="PayPilot – AI Payment Assistant",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database tables and seed baseline if empty
db.init_db()
if len(db.get_all_transactions(limit=1)) == 0:
    db.seed_sample_data()

# --- Custom Fintech CSS Styling ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Primary Container Clean Spacing */
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2.5rem;
        max-width: 1250px;
    }

    /* Gradient Top Header */
    .fintech-header {
        background: linear-gradient(135deg, #0b1528 0%, #003087 50%, #1e1b4b 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 24px 30px;
        margin-bottom: 25px;
        color: white;
        box-shadow: 0 10px 25px -5px rgba(0, 48, 135, 0.25);
    }
    .fintech-header h1 {
        margin: 0;
        font-size: 2.1rem;
        font-weight: 700;
        letter-spacing: -0.5px;
        color: #ffffff;
    }
    .fintech-header p {
        margin: 6px 0 0 0;
        font-size: 0.98rem;
        color: #cbd5e1;
    }

    /* Metric Card Styling */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 18px 22px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08);
    }
    .metric-title {
        font-size: 0.82rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        color: #64748b;
        margin-bottom: 4px;
    }
    .metric-value {
        font-size: 1.85rem;
        font-weight: 700;
        color: #0f172a;
        margin: 0;
    }
    .metric-subtitle {
        font-size: 0.78rem;
        color: #10b981;
        font-weight: 500;
        margin-top: 4px;
    }

    /* Badge Tags */
    .badge-completed {
        background-color: #dcfce7;
        color: #15803d;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.75rem;
        display: inline-block;
    }
    .badge-pending {
        background-color: #fef3c7;
        color: #b45309;
        padding: 4px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.75rem;
        display: inline-block;
    }

    /* AI Card Box */
    .payment-action-card {
        background: linear-gradient(145deg, #f8fafc 0%, #f1f5f9 100%);
        border: 1.5px solid #cbd5e1;
        border-left: 5px solid #0079C1;
        border-radius: 12px;
        padding: 20px;
        margin: 15px 0;
    }

    /* Warning Notice Box */
    .setup-warning-card {
        background: #fffbeb;
        border: 1.5px solid #fde68a;
        border-left: 5px solid #d97706;
        border-radius: 12px;
        padding: 16px 20px;
        margin: 12px 0;
        color: #92400e;
    }

    /* Status indicator pills in sidebar */
    .status-pill {
        display: inline-flex;
        align-items: center;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        margin-bottom: 6px;
    }
    .status-online {
        background: #ecfdf5;
        color: #047857;
        border: 1px solid #a7f3d0;
    }
    .status-offline {
        background: #fef2f2;
        color: #b91c1c;
        border: 1px solid #fecaca;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Session State Management ---
if "paypal_client_id" not in st.session_state:
    st.session_state.paypal_client_id = get_secret("PAYPAL_CLIENT_ID", "")
if "paypal_client_secret" not in st.session_state:
    st.session_state.paypal_client_secret = get_secret("PAYPAL_CLIENT_SECRET", "")
if "paypal_base_url" not in st.session_state:
    st.session_state.paypal_base_url = get_secret("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = get_secret("GEMINI_API_KEY", "")

if "nav_selection" not in st.session_state:
    st.session_state.nav_selection = "📊 Dashboard"

if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "👋 **Welcome to PayPilot!** I am your AI payment assistant powered by Google Gemini and PayPal.\n\n"
                "I can help you understand payments, formulate official PayPal Sandbox orders, and analyze your transaction activity.\n\n"
                "Try saying: *'I want to pay $25 for a subscription'*, *'Explain how PayPal payments work'*, or *'Show me my recent transactions'*."
            ),
        }
    ]

if "pending_payment_draft" not in st.session_state:
    st.session_state.pending_payment_draft = None

if "last_created_order" not in st.session_state:
    st.session_state.last_created_order = None

# Initialize Services
paypal_svc = PayPalService(
    client_id=st.session_state.paypal_client_id,
    client_secret=st.session_state.paypal_client_secret,
    base_url=st.session_state.paypal_base_url,
)

ai_svc = PayPilotAI(api_key=st.session_state.gemini_api_key)

# --- Sidebar Navigation & Connection Status ---
with st.sidebar:
    st.image("assets/logo.svg", width=68)
    st.markdown("### **PayPilot AI**")
    st.caption("PayPal Sandbox + Google Gemini Assistant")
    st.divider()

    nav_options = [
        "📊 Dashboard",
        "💬 AI Payment Assistant",
        "💳 Direct Payment Terminal",
        "📜 Transaction History",
        "💡 AI Financial Insights",
        "⚙️ Credentials & Setup",
    ]

    # Ensure index is valid
    current_idx = nav_options.index(st.session_state.nav_selection) if st.session_state.nav_selection in nav_options else 0

    nav_choice = st.radio(
        "Navigation",
        nav_options,
        index=current_idx,
        key="sidebar_nav_radio",
    )
    st.session_state.nav_selection = nav_choice

    st.divider()
    st.markdown("#### **System Connectivity**")

    # Live PayPal Connectivity Check
    if paypal_svc.is_configured:
        st.markdown(
            '<div class="status-pill status-online">● PayPal Sandbox: Configured</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-pill status-offline">○ PayPal Sandbox: Not Configured</div>',
            unsafe_allow_html=True,
        )

    # Live Gemini Connectivity Check
    if ai_svc.is_configured:
        st.markdown(
            '<div class="status-pill status-online">● Google Gemini: Connected</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="status-pill status-offline">○ Gemini: Local Fallback Active</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    st.caption("PayPilot MVP v1.0 • PayPal Global Hackathon")


# ==============================================================================
# VIEW 1: DASHBOARD
# ==============================================================================
if nav_choice == "📊 Dashboard":
    st.markdown(
        """
        <div class="fintech-header">
            <h1>PayPilot Financial Dashboard</h1>
            <p>Real-time PayPal Sandbox metrics, AI transaction analysis, and payment operations.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Missing credentials notice if applicable
    if not paypal_svc.is_configured or not ai_svc.is_configured:
        missing_items = []
        if not paypal_svc.is_configured:
            missing_items.append("PayPal Sandbox Credentials")
        if not ai_svc.is_configured:
            missing_items.append("Google Gemini API Key")

        st.markdown(
            f"""
            <div class="setup-warning-card">
                <b>💡 Environment Notice:</b> {', '.join(missing_items)} not detected in <code>.env</code>.<br>
                You can explore all dashboard features, inspect transactions, and run AI insights. 
                When ready, configure credentials in <b>⚙️ Credentials & Setup</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Metric Cards
    metrics = db.get_metrics()
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Total Volume (USD)</div>
                <div class="metric-value">${metrics['total_volume']:,.2f}</div>
                <div class="metric-subtitle">Average: ${metrics['avg_transaction']:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Completed Payments</div>
                <div class="metric-value" style="color: #10b981;">{metrics['completed_count']}</div>
                <div class="metric-subtitle">Success Rate: {metrics['success_rate']}%</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Pending Orders</div>
                <div class="metric-value" style="color: #f59e0b;">{metrics['pending_count']}</div>
                <div class="metric-subtitle">Awaiting Checkout Capture</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c4:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-title">Total Transactions</div>
                <div class="metric-value" style="color: #6366f1;">{metrics['total_count']}</div>
                <div class="metric-subtitle">PayPal Orders v2 Records</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Charts and Category Visualizations
    col_chart1, col_chart2 = st.columns([5, 5])
    categories = db.get_category_breakdown()

    with col_chart1:
        st.subheader("Spending by Category")
        if categories:
            cat_df = pd.DataFrame(categories)
            fig_pie = px.pie(
                cat_df,
                values="total_amount",
                names="category",
                color="category",
                hole=0.45,
                color_discrete_sequence=["#003087", "#0079C1", "#6366F1", "#8B5CF6", "#06B6D4", "#10B981"],
            )
            fig_pie.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                height=280,
                showlegend=True,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No completed transactions to display in category breakdown.")

    with col_chart2:
        st.subheader("Category Distribution ($ Volume)")
        if categories:
            fig_bar = px.bar(
                cat_df,
                x="category",
                y="total_amount",
                text="total_amount",
                color="category",
                color_discrete_sequence=["#0079C1", "#6366F1", "#8B5CF6", "#06B6D4"],
            )
            fig_bar.update_traces(texttemplate="$%{text:.2f}", textposition="outside")
            fig_bar.update_layout(
                margin=dict(t=10, b=10, l=10, r=10),
                height=280,
                xaxis_title="",
                yaxis_title="Total USD ($)",
                showlegend=False,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Complete an order to view distribution metrics.")

    # Recent Activity Feed
    st.divider()
    st.subheader("Recent Payment Activity")
    recent_txs = db.get_all_transactions(limit=6)

    if recent_txs:
        for tx in recent_txs:
            status = tx["status"]
            badge_html = (
                f'<span class="badge-completed">● {status}</span>'
                if status == "COMPLETED"
                else f'<span class="badge-pending">⏳ {status}</span>'
            )

            col_t1, col_t2, col_t3, col_t4 = st.columns([4, 2, 2, 2])
            with col_t1:
                st.markdown(f"**{tx['description'] or 'PayPal Order'}**")
                st.caption(f"Order ID: `{tx['paypal_order_id']}` • Cat: {tx['category']}")
            with col_t2:
                st.markdown(f"**{tx['currency']} ${tx['amount']:.2f}**")
            with col_t3:
                st.markdown(badge_html, unsafe_allow_html=True)
            with col_t4:
                st.caption(f"{tx['created_at'][:16] if tx['created_at'] else ''}")
            st.markdown("<hr style='margin: 4px 0 8px 0; border: none; border-top: 1px solid #f1f5f9;'>", unsafe_allow_html=True)
    else:
        st.info("No transaction activity recorded yet.")


# ==============================================================================
# VIEW 2: AI PAYMENT ASSISTANT
# ==============================================================================
elif nav_choice == "💬 AI Payment Assistant":
    st.markdown(
        """
        <div class="fintech-header">
            <h1>AI Payment Assistant</h1>
            <p>Converse with Gemini to formulate payments, clarify PayPal processes, and initiate orders with strict approval gates.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Prompt Suggestions
    st.markdown("##### 💡 Try asking:")
    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
    suggested_prompt = None

    if s_col1.button("💳 Pay $25 for a subscription", use_container_width=True):
        suggested_prompt = "I want to pay $25 for a subscription."
    if s_col2.button("☁️ $50 for Cloud Hosting", use_container_width=True):
        suggested_prompt = "Help me create a payment for $50 for Cloud Hosting."
    if s_col3.button("📘 How PayPal payments work", use_container_width=True):
        suggested_prompt = "Explain how PayPal payments work."
    if s_col4.button("📊 Summarize payment activity", use_container_width=True):
        suggested_prompt = "Summarize my payment activity."

    st.divider()

    # Display Chat History
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # If an order was just formulated, present an interactive Payment Order Card
    if st.session_state.pending_payment_draft:
        draft = st.session_state.pending_payment_draft
        st.markdown(
            f"""
            <div class="payment-action-card">
                <h4 style="margin: 0 0 10px 0; color: #003087;">📋 Payment Confirmation Required</h4>
                <p><b>Item:</b> {draft['description']} &nbsp;|&nbsp; <b>Amount:</b> {draft['currency']} ${draft['amount']:.2f} &nbsp;|&nbsp; <b>Category:</b> {draft['category']}</p>
                <p style="font-size: 0.88rem; color: #475569; margin: 0;"><b>Assistant Explanation:</b> {draft['explanation']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        b_col1, b_col2, b_col3 = st.columns([3, 2, 5])
        with b_col1:
            if st.button("✅ Approve & Create PayPal Order", type="primary", use_container_width=True):
                # Verify credentials first
                if not paypal_svc.is_configured:
                    st.error(
                        "🔒 **PayPal Sandbox Credentials Missing**: "
                        "PayPilot connects directly to the official PayPal Orders v2 Sandbox API and never fakes or simulates a payment. "
                        "Please configure your PayPal Client ID and Secret in **⚙️ Credentials & Setup** to place this order."
                    )
                else:
                    with st.spinner("Connecting to PayPal Orders v2 Sandbox..."):
                        success, res = paypal_svc.create_order(
                            amount=draft["amount"],
                            currency=draft["currency"],
                            description=draft["description"],
                        )

                    if success:
                        order_id = res["order_id"]
                        approval_url = res.get("approval_url")

                        # Record in SQLite database
                        db.create_order_record(
                            paypal_order_id=order_id,
                            amount=draft["amount"],
                            currency=draft["currency"],
                            description=draft["description"],
                            category=draft["category"],
                            status="PENDING",
                            approval_url=approval_url or "",
                        )

                        st.session_state.last_created_order = {
                            "order_id": order_id,
                            "amount": draft["amount"],
                            "currency": draft["currency"],
                            "description": draft["description"],
                            "approval_url": approval_url,
                        }
                        st.session_state.pending_payment_draft = None

                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    f"🎉 **PayPal Order Successfully Created!**\n\n"
                                    f"- **Order ID**: `{order_id}`\n"
                                    f"- **Amount**: {draft['currency']} ${draft['amount']:.2f}\n"
                                    f"- **Description**: {draft['description']}\n\n"
                                    f"Please click **Proceed to PayPal Sandbox Checkout** below to approve the payment with your Sandbox account, "
                                    f"then return to capture the transaction."
                                ),
                            }
                        )
                        st.rerun()
                    else:
                        st.error(f"Failed to create PayPal order: {res.get('error')}")

        with b_col2:
            if st.button("❌ Cancel Request", use_container_width=True):
                st.session_state.pending_payment_draft = None
                st.info("Payment creation cancelled.")
                st.rerun()

    # If there is a freshly created pending PayPal order awaiting checkout and capture
    if st.session_state.last_created_order:
        last_ord = st.session_state.last_created_order
        st.success(f"⚡ Active Sandbox Order: `{last_ord['order_id']}` ({last_ord['currency']} ${last_ord['amount']:.2f})")

        c_act1, c_act2, c_act3 = st.columns([4, 3, 3])
        with c_act1:
            if last_ord.get("approval_url"):
                st.link_button(
                    "🚀 Proceed to PayPal Sandbox Checkout ↗",
                    last_ord["approval_url"],
                    type="primary",
                    use_container_width=True,
                )
            else:
                st.warning("No direct approval URL returned by PayPal.")

        with c_act2:
            if st.button("🔒 Verify & Capture Payment", type="secondary", use_container_width=True):
                with st.spinner("Checking buyer approval & capturing funds on PayPal..."):
                    cap_ok, cap_res = paypal_svc.capture_order(last_ord["order_id"])

                if cap_ok:
                    tx_id = cap_res.get("transaction_id")
                    if not tx_id:
                        st.error("PayPal response did not include a verified capture transaction ID. Payment was not completed.")
                    else:
                        payer_email = cap_res.get("payer_email", "sandbox-buyer@example.com")
                        payer_name = cap_res.get("payer_name", "Sandbox Buyer")

                        # Update SQLite database to COMPLETED
                        db.complete_order_record(
                            paypal_order_id=last_ord["order_id"],
                            transaction_id=tx_id,
                            payer_email=payer_email,
                            payer_name=payer_name,
                        )

                        st.session_state.last_created_order = None
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": (
                                    f"✅ **Payment Captured Successfully!**\n\n"
                                    f"- **Capture Transaction ID**: `{tx_id}`\n"
                                    f"- **PayPal Order ID**: `{last_ord['order_id']}`\n"
                                    f"- **Payer**: {payer_name} (`{payer_email}`)\n"
                                    f"- **Status**: `COMPLETED`\n\n"
                                    f"The transaction has been permanently saved to your SQLite records and metrics have been updated."
                                ),
                            }
                        )
                        st.balloons()
                        st.rerun()
                else:
                    st.error(f"⚠️ {cap_res.get('error', 'Capture failed.')}")
                    if cap_res.get("code") == "ORDER_NOT_APPROVED":
                        st.info("💡 **Tip**: Click the checkout link above, log in to PayPal Sandbox, and click 'Complete Purchase'. Once PayPal shows approval, return here and click 'Verify & Capture Payment'.")

        with c_act3:
            if st.button("Dismiss / Clear", use_container_width=True):
                st.session_state.last_created_order = None
                st.rerun()

    # Chat Input Box
    user_input = st.chat_input("Ask PayPilot or enter a payment request (e.g., 'Pay $30 for Software License')...")
    if suggested_prompt:
        user_input = suggested_prompt

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})

        with st.spinner("PayPilot is analyzing..."):
            # 1. Parse intent
            intent = ai_svc.parse_payment_intent(user_input)

            # Build database context for conversational answers
            db_metrics = db.get_metrics()
            db_recent = db.get_all_transactions(limit=5)
            db_context = {
                "total_count": db_metrics["total_count"],
                "completed_count": db_metrics["completed_count"],
                "pending_count": db_metrics["pending_count"],
                "total_volume": db_metrics["total_volume"],
                "success_rate": db_metrics["success_rate"],
                "recent_transactions": db_recent,
            }

            if intent.get("is_payment_request") and intent.get("amount") and intent.get("amount") > 0:
                st.session_state.pending_payment_draft = {
                    "amount": intent["amount"],
                    "currency": intent.get("currency", "USD"),
                    "description": intent.get("description", "Payment Request"),
                    "category": intent.get("category", "General"),
                    "explanation": intent.get("explanation", ""),
                }
                reply = (
                    f"I've prepared a payment request for **{intent.get('currency', 'USD')} ${intent['amount']:.2f}** "
                    f"for **{intent.get('description')}** ({intent.get('category')} category).\n\n"
                    f"🔒 **Safety Gate**: In accordance with PayPilot security policies, please review and click **'Approve & Create PayPal Order'** below to generate the official PayPal Sandbox order."
                )
            elif intent.get("needs_clarification"):
                reply = intent.get("clarification_question") or "Could you clarify the exact amount and currency for this payment?"
            else:
                reply = ai_svc.chat_response(
                    user_message=user_input,
                    conversation_history=st.session_state.messages,
                    db_context=db_context,
                )

            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()


# ==============================================================================
# VIEW 3: DIRECT PAYMENT TERMINAL
# ==============================================================================
elif nav_choice == "💳 Direct Payment Terminal":
    st.markdown(
        """
        <div class="fintech-header">
            <h1>Direct Payment Terminal</h1>
            <p>Manual payment creation form for rapid PayPal Sandbox testing and deterministic workflows.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_form, col_info = st.columns([6, 5])

    with col_form:
        st.subheader("Create PayPal Sandbox Order")

        with st.form("manual_payment_form"):
            f_col1, f_col2 = st.columns([3, 2])
            with f_col1:
                f_amount = st.number_input("Amount", min_value=0.50, max_value=10000.0, value=25.00, step=1.00)
            with f_col2:
                f_currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "CAD", "AUD"])

            f_desc = st.text_input("Payment Description", value="API Subscription - PayPilot Pro")
            f_category = st.selectbox(
                "Category",
                ["Subscription", "Services", "Shopping", "Food & Dining", "Travel", "Utilities", "General"],
                index=0,
            )

            submit_btn = st.form_submit_button("Generate PayPal Order v2", type="primary", use_container_width=True)

        if submit_btn:
            if not paypal_svc.is_configured:
                st.error(
                    "🔒 **PayPal Sandbox Credentials Missing**: "
                    "PayPilot connects directly to the official PayPal Orders v2 Sandbox API and never fakes or simulates a payment. "
                    "Please configure your PayPal Client ID and Secret in **⚙️ Credentials & Setup**."
                )
            else:
                with st.spinner("Communicating with PayPal Sandbox..."):
                    ok, res = paypal_svc.create_order(
                        amount=f_amount,
                        currency=f_currency,
                        description=f_desc,
                    )

                if ok:
                    order_id = res["order_id"]
                    approval_url = res.get("approval_url")

                    # Store in database
                    db.create_order_record(
                        paypal_order_id=order_id,
                        amount=f_amount,
                        currency=f_currency,
                        description=f_desc,
                        category=f_category,
                        status="PENDING",
                        approval_url=approval_url or "",
                    )

                    st.session_state.last_created_order = {
                        "order_id": order_id,
                        "amount": f_amount,
                        "currency": f_currency,
                        "description": f_desc,
                        "approval_url": approval_url,
                    }
                    st.success(f"Order `{order_id}` successfully initialized with PayPal!")
                    st.rerun()
                else:
                    st.error(f"Error: {res.get('error')}")

    with col_info:
        st.subheader("PayPal Sandbox Instructions")
        st.markdown(
            """
            **How Sandbox Testing Works**:
            1. **Create Order**: Fill the form on the left and submit. PayPilot will invoke the PayPal REST Orders v2 API.
            2. **Buyer Approval**: Click the generated checkout link to open PayPal's Sandbox login.
            3. **Login with Sandbox Credentials**: Use your PayPal developer Sandbox Personal account (found in developer.paypal.com).
            4. **Capture Payment**: Return here and click **Verify & Capture** to finalize the order.
            
            ⚠️ **Real Verification**: PayPilot never marks an order as completed until the PayPal API confirms capture status `COMPLETED`.
            """
        )

    # Active Order Section
    if st.session_state.last_created_order:
        st.divider()
        st.subheader("Active Order Checkout & Capture")
        active = st.session_state.last_created_order

        st.info(
            f"**Pending Order**: `{active['order_id']}` | **Amount**: {active['currency']} ${active['amount']:.2f} | **Desc**: {active['description']}"
        )

        c1, c2 = st.columns(2)
        with c1:
            if active.get("approval_url"):
                st.link_button(
                    "Open PayPal Checkout ↗",
                    active["approval_url"],
                    type="primary",
                    use_container_width=True,
                )
        with c2:
            if st.button("Verify & Capture Order", type="secondary", use_container_width=True):
                with st.spinner("Capturing PayPal Order..."):
                    cap_ok, cap_res = paypal_svc.capture_order(active["order_id"])

                if cap_ok:
                    tx_id = cap_res.get("transaction_id")
                    if not tx_id:
                        st.error("PayPal response did not include a verified capture transaction ID.")
                    else:
                        db.complete_order_record(
                            paypal_order_id=active["order_id"],
                            transaction_id=tx_id,
                            payer_email=cap_res.get("payer_email"),
                            payer_name=cap_res.get("payer_name"),
                        )
                        st.session_state.last_created_order = None
                        st.success(f"✅ Order captured successfully! Transaction ID: `{tx_id}`")
                        st.balloons()
                        st.rerun()
                else:
                    st.error(cap_res.get("error"))


# ==============================================================================
# VIEW 4: TRANSACTION HISTORY
# ==============================================================================
elif nav_choice == "📜 Transaction History":
    st.markdown(
        """
        <div class="fintech-header">
            <h1>Transaction History</h1>
            <p>Complete audit log of all PayPal orders, capture IDs, payer information, and status states stored in SQLite.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Filter Controls
    f_col1, f_col2, f_col3 = st.columns([3, 4, 3])
    with f_col1:
        status_filter = st.selectbox("Status Filter", ["ALL", "COMPLETED", "PENDING", "FAILED", "CANCELLED"])
    with f_col2:
        search_query = st.text_input("Search Description, Order ID or Capture ID", "")
    with f_col3:
        st.write("")
        st.write("")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("Reload Data 🔄", use_container_width=True):
                st.rerun()
        with col_btn2:
            if st.button("Seed Demo Baseline", use_container_width=True):
                db.seed_sample_data()
                st.success("Sample transactions seeded.")
                st.rerun()

    txs = db.get_all_transactions(
        status=None if status_filter == "ALL" else status_filter,
        search=search_query if search_query.strip() else None,
        limit=100,
    )

    if txs:
        df = pd.DataFrame(txs)
        total_shown = len(df)
        completed_vol = df[df["status"] == "COMPLETED"]["amount"].sum()
        st.caption(f"Showing **{total_shown}** record(s) • Total Completed Volume: **${completed_vol:,.2f}**")

        display_df = df[
            [
                "id",
                "paypal_order_id",
                "transaction_id",
                "amount",
                "currency",
                "description",
                "category",
                "status",
                "payer_email",
                "created_at",
            ]
        ].copy()

        st.dataframe(
            display_df,
            column_config={
                "id": "ID",
                "paypal_order_id": st.column_config.TextColumn("PayPal Order ID"),
                "transaction_id": st.column_config.TextColumn("Capture ID"),
                "amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
                "status": st.column_config.TextColumn("Status"),
                "payer_email": st.column_config.TextColumn("Payer Email"),
                "created_at": st.column_config.TextColumn("Timestamp"),
            },
            use_container_width=True,
            hide_index=True,
        )

        # CSV Export
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Export Transactions to CSV",
            data=csv_data,
            file_name="paypilot_transactions.csv",
            mime="text/csv",
        )

        # Inspection & Live Capture Utility for pending records
        st.divider()
        st.subheader("Inspect & Action Specific Record")
        selected_order = st.selectbox("Select Order ID to inspect or capture:", df["paypal_order_id"].tolist())

        if selected_order:
            rec = next((item for item in txs if item["paypal_order_id"] == selected_order), None)
            if rec:
                col_det1, col_det2 = st.columns([5, 5])
                with col_det1:
                    st.json(rec)
                with col_det2:
                    if rec["status"] == "PENDING":
                        st.warning("This order is currently PENDING capture.")
                        if st.button(f"Attempt PayPal Capture for {selected_order}", type="primary"):
                            if not paypal_svc.is_configured:
                                st.error("Cannot capture: PayPal Sandbox credentials are not configured.")
                            else:
                                with st.spinner("Checking with PayPal API..."):
                                    ok, cap_res = paypal_svc.capture_order(selected_order)
                                if ok:
                                    tx_id = cap_res.get("transaction_id")
                                    if not tx_id:
                                        st.error("PayPal response did not include a verified capture transaction ID.")
                                    else:
                                        db.complete_order_record(
                                            paypal_order_id=selected_order,
                                            transaction_id=tx_id,
                                            payer_email=cap_res.get("payer_email"),
                                            payer_name=cap_res.get("payer_name"),
                                        )
                                        st.success("Captured successfully!")
                                        st.rerun()
                                else:
                                    st.error(cap_res.get("error"))
                    else:
                        st.success(f"Status is {rec['status']}. No further action needed.")
    else:
        st.info("No transactions match the selected criteria.")


# ==============================================================================
# VIEW 5: AI FINANCIAL INSIGHTS
# ==============================================================================
elif nav_choice == "💡 AI Financial Insights":
    st.markdown(
        """
        <div class="fintech-header">
            <h1>AI Financial Insights</h1>
            <p>Gemini-powered financial intelligence synthesizing spending velocity, categories, and patterns from your SQLite store.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    transactions = db.get_all_transactions(limit=50)
    metrics = db.get_metrics()
    categories = db.get_category_breakdown()

    col_btn, _ = st.columns([3, 7])
    with col_btn:
        generate_btn = st.button("⚡ Generate Fresh AI Insights", type="primary", use_container_width=True)

    if generate_btn or "cached_insights" not in st.session_state:
        with st.spinner("Google Gemini is analyzing transaction patterns..."):
            insights = ai_svc.generate_financial_insights(transactions, metrics, categories)
            st.session_state.cached_insights = insights

    insights = st.session_state.get("cached_insights", {})

    st.markdown(
        f"""
        <div style="background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); border-radius: 12px; padding: 22px; border: 1px solid #cbd5e1; margin-bottom: 20px;">
            <h3 style="color: #003087; margin-top: 0;">💡 {insights.get('headline', 'Financial Intelligence Overview')}</h3>
            <p style="font-size: 1.05rem; color: #334155; line-height: 1.5; margin: 0;">{insights.get('summary', '')}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_ins1, col_ins2 = st.columns(2)

    with col_ins1:
        st.subheader("🔍 Key Financial Observations")
        for obs in insights.get("insights", []):
            st.markdown(f"- {obs}")

    with col_ins2:
        st.subheader("📈 AI Recommendations")
        for rec in insights.get("recommendations", []):
            st.markdown(f"✅ **{rec}**")

    st.divider()

    st.subheader("Visual Spending Diagnostics")
    if categories:
        cat_df = pd.DataFrame(categories)
        fig = px.treemap(
            cat_df,
            path=["category"],
            values="total_amount",
            color="total_amount",
            color_continuous_scale="Blues",
            title="Category Volume Treemap",
        )
        fig.update_layout(margin=dict(t=30, b=10, l=10, r=10), height=300)
        st.plotly_chart(fig, use_container_width=True)


# ==============================================================================
# VIEW 6: CREDENTIALS & SETUP
# ==============================================================================
elif nav_choice == "⚙️ Credentials & Setup":
    st.markdown(
        """
        <div class="fintech-header">
            <h1>Credentials & Sandbox Setup</h1>
            <p>Manage your PayPal Sandbox REST API credentials and Google Gemini API key securely.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Real-Time Service Health & Connectivity Diagnostics
    st.subheader("Real-Time Connection Diagnostics")
    col_diag1, col_diag2 = st.columns(2)

    with col_diag1:
        st.markdown("#### **PayPal Sandbox API**")
        if paypal_svc.is_configured:
            st.success("Configuration Detected (Client ID & Secret set)")
            if st.button("🧪 Test PayPal Sandbox Connection", use_container_width=True):
                with st.spinner("Testing OAuth 2.0 handshake with api-m.sandbox.paypal.com..."):
                    t_ok, t_msg = paypal_svc.test_connection()
                if t_ok:
                    st.success("✅ OAuth 2.0 Handshake Successful! Access Token verified.")
                else:
                    st.error(f"❌ Connection Failed: {t_msg}")
        else:
            st.warning("⚠️ Credentials Not Configured. Please enter Client ID & Secret below.")

    with col_diag2:
        st.markdown("#### **Google Gemini API**")
        if ai_svc.is_configured:
            st.success("Configuration Detected (Gemini API Key set)")
            if st.button("🧪 Test Gemini AI Connection", use_container_width=True):
                with st.spinner("Pinging Gemini 2.5 Flash..."):
                    test_reply = ai_svc.chat_response("Respond with 'PayPilot Gemini online'", [])
                st.info(f"🤖 Gemini Response: {test_reply[:150]}")
        else:
            st.warning("⚠️ Gemini Key Not Configured. PayPilot is operating in Deterministic NLP Fallback Mode.")

    st.divider()

    st.subheader("Update Environment Configuration")
    st.markdown(
        "Enter your credentials below. Submitting will update your live active session and write to `.env`."
    )

    with st.form("credentials_form"):
        p_client_id = st.text_input(
            "PayPal Client ID (Sandbox)",
            value=st.session_state.paypal_client_id,
            type="default",
            help="From developer.paypal.com -> Apps & Credentials",
        )
        p_client_secret = st.text_input(
            "PayPal Client Secret (Sandbox)",
            value=st.session_state.paypal_client_secret,
            type="password",
            help="Secret key paired with your Sandbox Client ID",
        )
        p_base_url = st.text_input(
            "PayPal Base URL",
            value=st.session_state.paypal_base_url,
            help="Default: https://api-m.sandbox.paypal.com",
        )
        g_api_key = st.text_input(
            "Google Gemini API Key",
            value=st.session_state.gemini_api_key,
            type="password",
            help="Get your key at aistudio.google.com",
        )

        save_keys = st.form_submit_button("Save Credentials & Connect", type="primary")

    if save_keys:
        st.session_state.paypal_client_id = p_client_id.strip()
        st.session_state.paypal_client_secret = p_client_secret.strip()
        st.session_state.paypal_base_url = p_base_url.strip()
        st.session_state.gemini_api_key = g_api_key.strip()

        try:
            with open(".env", "w") as env_f:
                env_f.write(f"PAYPAL_CLIENT_ID={st.session_state.paypal_client_id}\n")
                env_f.write(f"PAYPAL_CLIENT_SECRET={st.session_state.paypal_client_secret}\n")
                env_f.write(f"PAYPAL_BASE_URL={st.session_state.paypal_base_url}\n")
                env_f.write(f"GEMINI_API_KEY={st.session_state.gemini_api_key}\n")
            st.success("Credentials saved to `.env` and active session!")
        except Exception as e:
            st.warning(f"Saved to session memory (could not write .env: {e})")

        st.rerun()

    st.divider()
    st.subheader("📖 Quick Setup Guide for Judges & Reviewers")

    exp1 = st.expander("1. How to get PayPal Sandbox Credentials (2 minutes)", expanded=True)
    with exp1:
        st.markdown(
            """
            1. Go to [PayPal Developer Portal](https://developer.paypal.com).
            2. Log in and navigate to **Dashboard > Apps & Credentials**.
            3. Ensure you are on the **Sandbox** toggle.
            4. Click **Create App**, give it a name (e.g. `PayPilot-Hackathon`), and select Merchant.
            5. Copy the **Client ID** and **Secret** into the fields above.
            6. To test payments, use one of your Sandbox Personal buyer accounts listed under **Testing Tools > Sandbox Accounts**.
            """
        )

    exp2 = st.expander("2. How to get Google Gemini API Key (1 minute)", expanded=True)
    with exp2:
        st.markdown(
            """
            1. Visit [Google AI Studio](https://aistudio.google.com).
            2. Click **Get API key**.
            3. Create a free API key and paste it into the field above.
            """
        )

    exp3 = st.expander("3. Test Database Management")
    with exp3:
        col_db1, col_db2 = st.columns(2)
        with col_db1:
            if st.button("Reset Database to Demo Baseline", use_container_width=True):
                db.clear_all_transactions()
                db.seed_sample_data()
                st.success("Database restored to demo baseline.")
                st.rerun()
        with col_db2:
            if st.button("Wipe All Transactions (Empty State)", use_container_width=True):
                db.clear_all_transactions()
                st.warning("All records wiped. Database is now empty.")
                st.rerun()
