"""Query helpers for `orders` and `order_field_values`."""

from __future__ import annotations

from datetime import datetime, timedelta

from bot.database.core import Database

ORDER_STATUSES = ("pending", "processing", "completed", "cancelled", "refunded")
PAYMENT_STATUSES = ("pending", "paid", "expired", "cancelled")


async def create_order(
    db: Database,
    user_id: int,
    product_id: int,
    payment_method_id: int | None,
    unit_price: float,
    currency_label: str,
    stock_reserved: bool,
    timeout_minutes: int | None,
) -> int:
    deadline = None
    if timeout_minutes:
        deadline = (datetime.utcnow() + timedelta(minutes=timeout_minutes)).isoformat(
            sep=" ", timespec="seconds"
        )
    return await db.execute(
        """
        INSERT INTO orders
            (user_id, product_id, payment_method_id, unit_price,
             total_price, currency_label, stock_reserved, payment_deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, product_id, payment_method_id, unit_price,
            unit_price, currency_label, int(stock_reserved), deadline,
        ),
    )


async def add_field_value(
    db: Database, order_id: int, label: str, field_type: str, value: str
) -> None:
    await db.execute(
        "INSERT INTO order_field_values (order_id, label, field_type, value) VALUES (?, ?, ?, ?)",
        (order_id, label, field_type, value),
    )


async def get_field_values(db: Database, order_id: int):
    return await db.fetchall(
        "SELECT * FROM order_field_values WHERE order_id = ? ORDER BY id ASC", (order_id,)
    )


async def set_order_status(db: Database, order_id: int, status: str) -> None:
    await db.execute(
        "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (status, order_id),
    )


async def set_payment_status(db: Database, order_id: int, payment_status: str) -> None:
    await db.execute(
        "UPDATE orders SET payment_status = ?, updated_at = datetime('now') WHERE id = ?",
        (payment_status, order_id),
    )


async def set_ticket_channel(db: Database, order_id: int, channel_id: int) -> None:
    await db.execute(
        "UPDATE orders SET ticket_channel_id = ? WHERE id = ?", (channel_id, order_id)
    )


async def clear_stock_reserved(db: Database, order_id: int) -> None:
    await db.execute("UPDATE orders SET stock_reserved = 0 WHERE id = ?", (order_id,))


async def get_order(db: Database, order_id: int):
    return await db.fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))


async def get_order_by_channel(db: Database, channel_id: int):
    return await db.fetchone("SELECT * FROM orders WHERE ticket_channel_id = ?", (channel_id,))


async def list_orders_for_user(db: Database, user_id: int, limit: int = 25):
    return await db.fetchall(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )


async def list_pending_payment_orders_for_user(db: Database, user_id: int):
    """Orders still awaiting payment confirmation for this user -- used to
    figure out which order a DM (e.g. a payment proof screenshot) belongs to."""
    return await db.fetchall(
        """
        SELECT * FROM orders
        WHERE user_id = ? AND payment_status = 'pending'
          AND status NOT IN ('cancelled', 'refunded')
        ORDER BY created_at DESC
        """,
        (user_id,),
    )


async def list_orders(db: Database, status: str | None = None, limit: int = 50):
    if status:
        return await db.fetchall(
            "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status, limit),
        )
    return await db.fetchall("SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,))


async def list_expired_pending_payments(db: Database):
    return await db.fetchall(
        """
        SELECT * FROM orders
        WHERE payment_status = 'pending'
          AND payment_deadline IS NOT NULL
          AND payment_deadline <= datetime('now')
          AND status NOT IN ('cancelled', 'refunded', 'completed')
        """
    )


async def list_completed_unreviewed(db: Database, user_id: int):
    return await db.fetchall(
        """
        SELECT o.* FROM orders o
        LEFT JOIN reviews r ON r.order_id = o.id
        WHERE o.user_id = ? AND o.status = 'completed' AND o.payment_status = 'paid'
          AND r.id IS NULL
        ORDER BY o.created_at DESC
        """,
        (user_id,),
    )
