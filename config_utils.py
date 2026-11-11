"""
PayPilot - Configuration and Secret Management
Safely resolves credentials from Streamlit Cloud secrets (`st.secrets`)
or local environment variables (`.env`).
Ensures secrets are never logged or exposed.
"""

import os
from typing import Optional


def get_secret(key: str, default: str = "") -> str:
    """
    Retrieve secret prioritizing Streamlit Cloud secrets (st.secrets)
    with fallback to environment variables.
    Never exposes raw secrets in exceptions or logs.
    """
    # 1. Attempt retrieval from Streamlit Cloud secrets (st.secrets)
    try:
        import streamlit as st

        if hasattr(st, "secrets") and st.secrets is not None:
            # Case 1: Direct flat key, e.g. st.secrets["PAYPAL_CLIENT_ID"]
            if key in st.secrets:
                val = st.secrets[key]
                if val is not None and str(val).strip():
                    return str(val).strip()

            # Case 2: Lowercase flat key
            key_lower = key.lower()
            if key_lower in st.secrets:
                val = st.secrets[key_lower]
                if val is not None and str(val).strip():
                    return str(val).strip()

            # Case 3: Nested TOML table, e.g. [paypal] client_id = "..."
            if "paypal" in key_lower and "paypal" in st.secrets:
                sub_key = key_lower.replace("paypal_", "")
                if sub_key in st.secrets["paypal"]:
                    val = st.secrets["paypal"][sub_key]
                    if val is not None and str(val).strip():
                        return str(val).strip()

            if "gemini" in key_lower and "gemini" in st.secrets:
                sub_key = key_lower.replace("gemini_", "")
                if sub_key in st.secrets["gemini"]:
                    val = st.secrets["gemini"][sub_key]
                    if val is not None and str(val).strip():
                        return str(val).strip()
    except Exception:
        # st.secrets may raise FileNotFoundError when no secrets.toml exists locally
        pass

    # 2. Fallback to OS environment variable
    env_val = os.getenv(key, "")
    if env_val is not None and str(env_val).strip():
        return str(env_val).strip()

    return default


def mask_secret(value: Optional[str]) -> str:
    """Return a safely masked preview of a secret (e.g. 'Abc•••xyz') or empty indicator."""
    if not value or not value.strip():
        return "Not Configured"
    v = value.strip()
    if len(v) <= 8:
        return "••••••••"
    return f"{v[:3]}••••••••{v[-3:]}"
