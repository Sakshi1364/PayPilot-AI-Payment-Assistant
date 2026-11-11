"""
PayPilot - Database Module
SQLite database management for transaction history, metrics, and insights.
Uses robust connection lifecycle handling for Windows file locking safety.
"""

import sqlite3
import datetime
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

DB_PATH = "paypilot.db"


@contextmanager
def get_db_cursor(db_path: str = DB_PATH):
    """Context manager yielding a cursor and ensuring commit and connection closure."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH) -> None:
    """Initialize the SQLite database schema."""
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id TEXT,
                paypal_order_id TEXT UNIQUE NOT NULL,
                amount REAL NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                description TEXT,
                category TEXT DEFAULT 'General',
                status TEXT NOT NULL DEFAULT 'PENDING',
                payer_email TEXT,
                payer_name TEXT,
                approval_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_id ON transactions (paypal_order_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON transactions (status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON transactions (created_at)")


def create_order_record(
    paypal_order_id: str,
    amount: float,
    currency: str = "USD",
    description: str = "",
    category: str = "General",
    status: str = "PENDING",
    approval_url: str = "",
    db_path: str = DB_PATH,
) -> int:
    """Insert a newly created PayPal order into the database."""
    now = datetime.datetime.utcnow().isoformat()
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            INSERT INTO transactions (
                paypal_order_id, amount, currency, description, category, status, approval_url, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                paypal_order_id,
                amount,
                currency.upper(),
                description,
                category,
                status,
                approval_url,
                now,
                now,
            ),
        )
        return cursor.lastrowid


def complete_order_record(
    paypal_order_id: str,
    transaction_id: str,
    payer_email: Optional[str] = None,
    payer_name: Optional[str] = None,
    db_path: str = DB_PATH,
) -> bool:
    """Update order record upon successful PayPal capture."""
    now = datetime.datetime.utcnow().isoformat()
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            UPDATE transactions
            SET transaction_id = ?,
                status = 'COMPLETED',
                payer_email = ?,
                payer_name = ?,
                updated_at = ?
            WHERE paypal_order_id = ?
            """,
            (transaction_id, payer_email, payer_name, now, paypal_order_id),
        )
        return cursor.rowcount > 0


def update_order_status(
    paypal_order_id: str,
    status: str,
    db_path: str = DB_PATH,
) -> bool:
    """Update the status of an existing order (e.g. CANCELLED, FAILED)."""
    now = datetime.datetime.utcnow().isoformat()
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            UPDATE transactions
            SET status = ?,
                updated_at = ?
            WHERE paypal_order_id = ?
            """,
            (status, now, paypal_order_id),
        )
        return cursor.rowcount > 0


def get_transaction_by_order_id(
    paypal_order_id: str,
    db_path: str = DB_PATH,
) -> Optional[Dict[str, Any]]:
    """Retrieve a single transaction by its PayPal Order ID."""
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            "SELECT * FROM transactions WHERE paypal_order_id = ?",
            (paypal_order_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_all_transactions(
    status: Optional[str] = None,
    limit: int = 100,
    search: Optional[str] = None,
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    """Fetch transactions with optional filtering by status and text search."""
    with get_db_cursor(db_path) as cursor:
        query = "SELECT * FROM transactions WHERE 1=1"
        params: List[Any] = []

        if status and status.upper() != "ALL":
            query += " AND status = ?"
            params.append(status.upper())

        if search:
            query += " AND (description LIKE ? OR paypal_order_id LIKE ? OR transaction_id LIKE ? OR category LIKE ?)"
            wildcard = f"%{search}%"
            params.extend([wildcard, wildcard, wildcard, wildcard])

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def get_metrics(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Calculate high-level dashboard metrics from transaction data."""
    with get_db_cursor(db_path) as cursor:
        cursor.execute("SELECT COUNT(*) FROM transactions")
        total_count = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'COMPLETED'")
        completed_count = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'PENDING'")
        pending_count = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM transactions WHERE status IN ('FAILED', 'CANCELLED')")
        failed_count = cursor.fetchone()[0] or 0

        cursor.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE status = 'COMPLETED'"
        )
        total_volume = cursor.fetchone()[0] or 0.0

        cursor.execute(
            "SELECT COALESCE(AVG(amount), 0) FROM transactions WHERE status = 'COMPLETED'"
        )
        avg_transaction = cursor.fetchone()[0] or 0.0

        success_rate = (completed_count / total_count * 100.0) if total_count > 0 else 0.0

        return {
            "total_count": total_count,
            "completed_count": completed_count,
            "pending_count": pending_count,
            "failed_count": failed_count,
            "total_volume": round(total_volume, 2),
            "avg_transaction": round(avg_transaction, 2),
            "success_rate": round(success_rate, 1),
        }


def get_category_breakdown(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """Get total completed spending grouped by category."""
    with get_db_cursor(db_path) as cursor:
        cursor.execute(
            """
            SELECT category, COUNT(*) as count, SUM(amount) as total_amount
            FROM transactions
            WHERE status = 'COMPLETED'
            GROUP BY category
            ORDER BY total_amount DESC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def seed_sample_data(db_path: str = DB_PATH) -> None:
    """Seed realistic initial sample data for immediate testing and visualization."""
    sample_records = [
        (
            "5O190127TN364715A",
            "8CD3948271034910A",
            24.99,
            "USD",
            "GitHub Copilot Monthly Subscription",
            "Subscription",
            "COMPLETED",
            "buyer-sandbox@business.example.com",
            "Alex Morgan",
            "2026-10-15 10:30:00",
        ),
        (
            "6P281038UM475826B",
            "9DE4059382145021B",
            89.50,
            "USD",
            "Cloud Infrastructure Hosting (AWS)",
            "Services",
            "COMPLETED",
            "buyer-sandbox@business.example.com",
            "Alex Morgan",
            "2026-10-22 14:15:00",
        ),
        (
            "7Q392149VN586937C",
            "0EF5160493256132C",
            12.00,
            "USD",
            "Domain Renewal (.io domain)",
            "Utilities",
            "COMPLETED",
            "buyer-sandbox@business.example.com",
            "Alex Morgan",
            "2026-11-01 09:00:00",
        ),
        (
            "8R403250WO697048D",
            "1FG6271504367243D",
            45.00,
            "USD",
            "Design Asset Pack - Vector UI Kit",
            "Shopping",
            "COMPLETED",
            "buyer-sandbox@business.example.com",
            "Alex Morgan",
            "2026-11-05 16:45:00",
        ),
        (
            "9S514361XP708159E",
            None,
            150.00,
            "USD",
            "Freelance API Integration Consultation",
            "Services",
            "PENDING",
            None,
            None,
            "2026-11-10 11:20:00",
        ),
    ]

    with get_db_cursor(db_path) as cursor:
        for rec in sample_records:
            cursor.execute(
                """
                INSERT OR IGNORE INTO transactions (
                    paypal_order_id, transaction_id, amount, currency, description,
                    category, status, payer_email, payer_name, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec[0],
                    rec[1],
                    rec[2],
                    rec[3],
                    rec[4],
                    rec[5],
                    rec[6],
                    rec[7],
                    rec[8],
                    rec[9],
                    rec[9],
                ),
            )


def clear_all_transactions(db_path: str = DB_PATH) -> None:
    """Clear all records from transactions table."""
    with get_db_cursor(db_path) as cursor:
        cursor.execute("DELETE FROM transactions")
