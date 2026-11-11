# 💳 PayPilot – AI-Powered Payment Assistant

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Google Gemini API](https://img.shields.io/badge/Google%20Gemini-google--genai-8E75C2?logo=google&logoColor=white)](https://ai.google.dev/)
[![PayPal REST API v2](https://img.shields.io/badge/PayPal-REST%20Orders%20v2-003087?logo=paypal&logoColor=white)](https://developer.paypal.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Built for the **PayPal + AI Global Hackathon**.  
> **PayPilot** bridges conversational artificial intelligence with enterprise financial rails — allowing users to formulate, validate, approve, and capture real PayPal Sandbox payments through natural language.

---

## 📌 Table of Contents
1. [Project Overview](#-project-overview)
2. [Problem Statement & Key Innovation](#-problem-statement--key-innovation)
3. [Architecture & Workflow](#-architecture--workflow)
4. [Key Features](#-key-features)
5. [Technology Stack](#-technology-stack)
6. [Prerequisites & Environment Configuration](#-prerequisites--environment-configuration)
7. [PayPal Sandbox Setup Guide](#-paypal-sandbox-setup-guide)
8. [Google Gemini API Setup Guide](#-google-gemini-api-setup-guide)
9. [Local Installation & Quickstart](#-local-installation--quickstart)
10. [End-to-End Payment Workflow](#-end-to-end-payment-workflow)
11. [Testing & Verification](#-testing--verification)
12. [Security & Compliance](#-security--compliance)
13. [Hackathon Submission Deliverables](#-hackathon-submission-deliverables)
    - [Concise Project Description](#1-concise-project-description)
    - [Key Innovation & Impact](#2-key-innovation--impact)
    - [How PayPal is Used](#3-how-paypal-is-used)
    - [How Gemini AI is Used](#4-how-gemini-ai-is-used)
    - [Demo Video Script (< 3 minutes)](#5-demo-video-script-under-3-minutes)

---

## 🌟 Project Overview

**PayPilot** is an intelligent fintech copilot designed to eliminate friction in consumer and business payments. Instead of navigating confusing checkout forms or struggling with payment jargon, users can state their payment intentions naturally (e.g., *"Pay $25 for my cloud database subscription"*). 

PayPilot extracts the relevant financial parameters, validates them, provides clear explanations, presents an explicit confirmation card, generates an official **PayPal Orders v2** transaction in the Sandbox environment, directs the buyer to PayPal checkout, and verifies capture upon buyer approval.

Crucially, PayPilot enforces strict safety: **it never executes or captures payments independently without human approval**, and **never simulates a fake payment**.

---

## 🎯 Problem Statement & Key Innovation

### The Problem
- **Checkout Friction & Invoicing Confusion**: Users frequently struggle with ambiguous payment links, unknown fee structures, or complex manual invoicing forms.
- **Disconnected Financial Context**: Users rarely receive instant, intelligent feedback on how a new payment fits into their ongoing budget or recurring category spend.
- **AI Safety Concerns**: Naive autonomous agents that attempt to execute transactions without human-in-the-loop validation introduce catastrophic security and financial risks.

### The PayPilot Innovation
1. **Human-in-the-Loop Safe Execution**: PayPilot acts as a mediator: Gemini handles intent parsing, entity extraction, and conversational explanation, but an immutable safety gate requires explicit user approval before triggering the PayPal API.
2. **Official PayPal Orders v2 Deep Integration**: Uses official OAuth 2.0 client credential flows, dynamic approval links, and post-checkout cryptographic capture verification.
3. **Live Transaction-Grounded Financial Insights**: PayPilot synthesizes real SQLite transaction stores into spending velocity charts, recurring subscription tracking, and budget health observations using Gemini.
4. **Resilient Dual-Mode Architecture**: If API keys are not yet configured, PayPilot seamlessly activates offline deterministic NLP parsing so judges can explore the full interface and test baseline data without unexpected crashes.

---

## 🏗️ Architecture & Workflow

```mermaid
flowchart TD
    subgraph Client ["Frontend & Interaction (Streamlit)"]
        UI[User Interface / Chat Input]
        Dashboard[Fintech Metric Dashboard]
        InsightsUI[AI Insights & Charts]
    end

    subgraph AI ["Intelligence Layer (Google Gemini)"]
        Gemini[Google Gemini 2.5 Flash / google-genai SDK]
        NLPFallback[Deterministic NLP Rule Engine]
    end

    subgraph Database ["Local Storage Layer"]
        SQLite[(SQLite: paypilot.db)]
    end

    subgraph PayPal ["Payment Rail (PayPal Sandbox REST API v2)"]
        OAuth[OAuth 2.0 Auth Server]
        OrdersAPI[Orders v2: /v2/checkout/orders]
        CaptureAPI[Capture API: /v2/checkout/orders/{id}/capture]
        BuyerPortal[PayPal Sandbox Checkout Window]
    end

    UI -->|Natural Language Prompt| AI
    Gemini -->|Structured JSON Intent| UI
    NLPFallback -.->|Fallback Parser| UI
    
    UI -->|Human Approval Required| OrdersAPI
    OAuth -.->|Bearer Token| OrdersAPI
    OrdersAPI -->|Approval URL & Order ID| UI
    OrdersAPI -->|Save PENDING Order| SQLite
    
    UI -->|User Opens Checkout| BuyerPortal
    BuyerPortal -->|Buyer Approves Payment| PayPal
    
    UI -->|Verify & Capture Payment| CaptureAPI
    CaptureAPI -->|Capture Verified: COMPLETED| SQLite
    SQLite -->|Real DB Records| Dashboard
    SQLite -->|Financial Aggregates| InsightsUI
    InsightsUI -->|Prompt with DB context| Gemini
```

---

## 🚀 Key Features

### 1. Modern Fintech Dashboard
- Real-time KPI metric cards: **Total Volume**, **Completed Payments**, **Pending Orders**, and **Success Rate**.
- Interactive Plotly visualizations: **Spending by Category Donut Chart** and **Volume Distribution Bar Chart**.
- Live recent activity feed with status badges (`COMPLETED`, `PENDING`).

### 2. Conversational AI Payment Assistant
- Natural language query understanding:
  - *"I want to pay $25 for a subscription."*
  - *"Help me create a payment for $50 for Cloud Hosting."*
  - *"Explain how PayPal payments work."*
  - *"Summarize my payment activity."*
- Structured JSON entity extraction (amount, currency, item/description, category, confidence).
- Interactive **Payment Confirmation Card** with explicit user approval buttons.
- Direct link to official PayPal Sandbox checkout approval URL.
- One-click **Verify & Capture** trigger with real-time PayPal status checking.

### 3. Direct Payment Terminal
- Deterministic form for manual Sandbox order creation (amount, currency, description, category).
- Ideal for fast developer testing and isolated workflow verification.

### 4. Transaction History & Audit Ledger
- Complete SQLite ledger with columns: `id`, `paypal_order_id`, `transaction_id`, `amount`, `currency`, `category`, `status`, `payer_email`, `created_at`.
- Status filtering (`ALL`, `COMPLETED`, `PENDING`, `CANCELLED`).
- Full-text search by description, order ID, or capture ID.
- One-click CSV export for external reporting.
- Single-record JSON inspector and live capture utility for pending orders.

### 5. AI Financial Insights
- Powered by Gemini using actual database records.
- Generates executive summaries, spending velocity metrics, high-velocity category warnings, and actionable budget recommendations.
- Category treemap visualization.

### 6. In-App Credentials & Sandbox Manager
- Live status indicators for PayPal Sandbox and Google Gemini connectivity.
- Direct inline credential configuration saving to `.env` or session memory.
- Instant database seeding or wiping controls for hackathon evaluation.

---

## 💻 Technology Stack

| Component | Technology | Version | Purpose |
|---|---|---|---|
| **Language** | Python | 3.11+ | Core application logic |
| **Frontend** | Streamlit | >= 1.30.0 | High-performance interactive fintech UI |
| **AI Model** | Google Gemini | 2.5 Flash / 2.0 Flash | Intent parsing, conversation, financial analysis |
| **AI SDK** | `google-genai` | >= 3.0.0 | Official Google GenAI Python SDK |
| **Payments** | PayPal REST API | Orders v2 | OAuth 2.0, Order creation, Sandbox checkout, Capture |
| **HTTP Client** | Requests | >= 2.28.0 | REST communication with PayPal endpoints |
| **Database** | SQLite3 | Built-in | Persistent transaction store and audit trail |
| **Charts** | Plotly Express | >= 5.18.0 | Responsive data visualizations and treemaps |
| **Config** | python-dotenv | >= 1.0.0 | Secure environment variable management |

---

## ⚙️ Prerequisites & Environment Configuration

### Prerequisites
- Python 3.11 or higher installed.
- A free [PayPal Developer Account](https://developer.paypal.com/).
- A free [Google AI Studio API Key](https://aistudio.google.com/).

### Environment File Setup
Create a `.env` file in the root directory (copied from `.env.example`):

```bash
cp .env.example .env
```

Populate the `.env` file with your credentials:
```env
PAYPAL_CLIENT_ID=your_sandbox_client_id_here
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret_here
PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com
GEMINI_API_KEY=your_gemini_api_key_here
```

*(Note: You can also leave `.env` empty initially and enter credentials directly inside the app's **⚙️ Credentials & Setup** sidebar menu!)*

---

## 🔑 PayPal Sandbox Setup Guide

1. Log in to the [PayPal Developer Dashboard](https://developer.paypal.com/).
2. Navigate to **Apps & Credentials** on the left menu.
3. Ensure the toggle is switched to **Sandbox** (not Live).
4. Click **Create App**:
   - App Name: `PayPilot-Assistant`
   - App Type: `Merchant`
5. Copy your **Client ID** and click *Show* to copy your **Secret**.
6. Navigate to **Testing Tools > Sandbox Accounts**:
   - Note the pre-generated **Personal** account email and password (e.g., `sb-buyer...@personal.example.com`).
   - You will use these credentials when approving payments in the checkout pop-up!

---

## 🤖 Google Gemini API Setup Guide

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Click **Get API key**.
3. Create a key in a new or existing Google Cloud project.
4. Copy the generated API key into your `.env` as `GEMINI_API_KEY`.

---

## 🏃 Local Installation & Quickstart

### 1. Clone Repository & Open Directory
```bash
git clone https://github.com/your-username/PayPilot.git
cd PayPilot
```

### 2. Create and Activate Virtual Environment (Recommended)
```bash
# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run Application
```bash
streamlit run app.py
```

PayPilot will automatically open in your default browser at `http://localhost:8501`.

---

## 🔄 End-to-End Payment Workflow

1. **User Request**: User sends a natural language prompt via the AI Assistant (e.g., *"Pay $25 for SaaS Subscription"*).
2. **Intent Parsing**: Gemini AI parses the amount (`25.00`), currency (`USD`), item (`SaaS Subscription`), and category (`Subscription`).
3. **Safety Gate & Review**: PayPilot generates a **Payment Confirmation Card**. Nothing has been charged yet.
4. **Order Creation**: The user clicks **Approve & Create PayPal Order**. PayPilot calls `POST /v2/checkout/orders` with `intent: CAPTURE`.
5. **Pending State**: The order is saved to SQLite with status `PENDING`. PayPal returns a Sandbox checkout approval URL.
6. **Buyer Approval**: The user clicks **Proceed to PayPal Sandbox Checkout ↗**, opens the PayPal window, and logs in with their Sandbox Personal account to approve the purchase.
7. **Order Capture**: The user returns to PayPilot and clicks **Verify & Capture Payment**. PayPilot calls `POST /v2/checkout/orders/{id}/capture`.
8. **Verification**: If PayPal confirms capture with status `COMPLETED`, the transaction is recorded with capture ID and payer email in SQLite, confetti triggers, and metrics update in real time!

---

## 🧪 Testing & Verification

PayPilot includes an automated unit test suite covering database operations, AI intent extraction, PayPal validation rules, and error handlers.

Run all tests:
```bash
python -m unittest test_paypilot.py -v
```

### Test Suite Coverage:
- `test_init_db`: Verifies SQLite schema creation and constraints.
- `test_create_and_complete_order`: Tests order creation and status transition to `COMPLETED`.
- `test_update_order_status_cancelled`: Tests order cancellation.
- `test_metrics_calculation`: Tests volume, average transaction, and success rate aggregations.
- `test_status_filtering_and_search`: Tests SQL filtering and multi-column search.
- `test_parse_payment_subscription`: Validates AI extraction of subscription amounts.
- `test_parse_payment_cloud_hosting`: Validates AI extraction of service amounts.
- `test_parse_euro_currency`: Tests multi-currency symbol support (`€`).
- `test_parse_ambiguous_payment`: Tests clarification handling for missing amounts.
- `test_parse_non_payment_query`: Tests non-payment queries.
- `test_chat_response_paypal_workflow`: Verifies accuracy of PayPal payment process explanations.
- `test_unconfigured_state`: Verifies safe failure modes when credentials are absent.
- `test_amount_validation`: Ensures negative/zero amounts are blocked before reaching PayPal.
- `test_oauth_success_and_caching`: Tests token caching and expiration buffer.
- `test_create_order_success`: Verifies order approval link extraction.
- `test_capture_order_success`: Verifies capture ID extraction and payer metadata handling.
- `test_capture_order_not_approved_handling`: Tests graceful handling of 422 `ORDER_NOT_APPROVED`.

---

## 🔒 Security & Compliance

- **Zero Hardcoded Secrets**: All credentials are dynamically loaded from `.env` or session memory.
- **Strict Sandbox Isolation**: All API calls target `https://api-m.sandbox.paypal.com`.
- **PCI-DSS Compliance**: PayPilot never handles, transmits, or stores card numbers, CVVs, or bank credentials. All authentication occurs on PayPal's secure checkout page.
- **Human-in-the-Loop AI Boundary**: The AI assistant cannot execute or capture payments unilaterally. Every financial commitment requires human confirmation.
- **No Simulated Success**: Payments are only marked `COMPLETED` when the PayPal REST API explicitly returns `status == "COMPLETED"` and a capture ID.

---

## 🏆 Hackathon Submission Deliverables

### 1. Concise Project Description
> **PayPilot** is an AI-powered financial copilot that combines Google Gemini's natural language intelligence with PayPal's Orders v2 REST API to formulate, validate, approve, and capture payments safely. Users can initiate payments in plain English, understand transaction mechanics, complete sandbox checkout, and derive deep spending insights from real transaction logs.

### 2. Key Innovation & Impact
- **Conversational to Financial Translation**: Turns informal, conversational human intent into strictly validated, compliant PayPal Orders v2 payloads.
- **Human-Controlled Autonomous Boundary**: Eliminates agentic risk by enforcing explicit user approval gates between AI intent parsing and API order creation.
- **Actionable Financial Copilot**: Closes the loop between making a payment and understanding budget impact by generating real-time Gemini financial insights from local SQLite ledger data.

### 3. How PayPal is Used
- **OAuth 2.0 Authentication**: Generates and caches bearer tokens via `/v1/oauth2/token`.
- **Orders v2 Creation**: Uses `POST /v2/checkout/orders` with `intent: CAPTURE` and `payment_source` experience contexts to initialize orders.
- **Approval Flow**: Directs buyers to PayPal's official sandbox checkout URL (`rel: approve`).
- **Cryptographic Capture**: Finalizes funds via `POST /v2/checkout/orders/{id}/capture` and extracts transaction capture IDs and payer details.
- **Status Verification**: Re-checks and displays live PayPal order states directly in the ledger.

### 4. How Gemini AI is Used
- **Google GenAI SDK (`google-genai`)**: Interacts with `gemini-2.5-flash` for high-speed, structured inference.
- **Structured JSON Intent Extraction**: Analyzes unstructured chat to extract amounts, currency codes, item descriptions, and categories.
- **Fintech Education & Assistance**: Explains PayPal buyer protection, dispute workflows, and transaction fee concepts.
- **Financial Intelligence**: Synthesizes SQLite transaction records into spending summaries, category trends, and budget optimization recommendations.

### 5. Demo Video Script (Under 3 Minutes)

| Time | Visual Scene | Audio Narration |
|---|---|---|
| **0:00 - 0:25** | PayPilot Dashboard, metric cards, logo, and active sidebar. | *"Welcome to PayPilot, the AI-powered payment assistant built for the PayPal and AI Global Hackathon. Managing payments and invoices often feels disjointed. PayPilot bridges conversational intelligence with PayPal's robust payment rails to make payments conversational, safe, and transparent."* |
| **0:25 - 0:55** | Navigate to **AI Payment Assistant**. Type: *"I want to pay $25 for a subscription."* AI responds and renders the **Payment Confirmation Card**. | *"Let's test the AI Assistant. I simply type 'I want to pay $25 for a subscription.' Google Gemini parses the request into a structured JSON payload, extracts the amount, currency, and category, and presents an interactive Confirmation Card. Notice that PayPilot never executes a payment without explicit approval."* |
| **0:55 - 1:40** | Click **Approve & Create PayPal Order**. Order ID appears. Click **Proceed to PayPal Sandbox Checkout**. Log into Sandbox and approve. | *"I click 'Approve & Create PayPal Order'. PayPilot instantly calls the PayPal Orders v2 REST API and generates an official Sandbox order. Clicking 'Proceed to Checkout' opens PayPal's secure Sandbox window. I log in with my sandbox buyer account, review the $25.00 total, and approve the payment."* |
| **1:40 - 2:10** | Return to PayPilot, click **Verify & Capture Payment**. Confetti/balloons appear, capture ID and payer info are displayed. | *"Back in PayPilot, I click 'Verify & Capture'. PayPilot contacts the PayPal Capture API, confirms status COMPLETED, and saves the verified transaction ID into our local SQLite audit store. No simulated payments — only verified PayPal captures!"* |
| **2:10 - 2:40** | Navigate to **AI Financial Insights** and **Transaction History**. Show the category treemap and Gemini analysis. | *"All completed orders populate our Transaction History and trigger real-time updates on our dashboard. In the AI Financial Insights tab, Gemini analyzes our actual transaction history, breaking down category spend and highlighting actionable budget recommendations."* |
| **2:40 - 3:00** | Credentials & Setup tab, test suite terminal running 19 passing tests, final wrap-up. | *"PayPilot includes full credentials management, graceful offline fallbacks, and a 19-test automated test suite. PayPilot makes payments conversational, intelligent, and secure. Thank you!"* |

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
