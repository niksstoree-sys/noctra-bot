"""Query helpers for the store leaderboard."""

from __future__ import annotations

from bot.database.core import Database


async def get_top_spenders(db: Database, limit: int = 10) -> list[dict]:
    rows = await db.fetchall(
        """
        SELECT
            user_id,
            SUM(total_price)   AS total_spent,
            COUNT(*)           AS total_orders,
            currency_label
        FROM orders
        WHERE status = 'completed' AND payment_status = 'paid'
        GROUP BY user_id
        ORDER BY total_spent DESC
        LIMIT ?
        """,
        (limit,),
    )
    return [dict(r) for r in rows]


async def get_leaderboard_message_id(db: Database) -> int | None:
    from bot.database.queries.settings import get_setting
    value = await get_setting(db, "leaderboard_message_id")
    return int(value) if value else None


async def set_leaderboard_message_id(db: Database, message_id: int) -> None:
    from bot.database.queries.settings import set_setting
    await set_setting(db, "leaderboard_message_id", str(message_id))
