"""General-purpose helpers shared across cogs: price calculation, currency
formatting, and a runtime-settings resolver that merges DB-stored settings
over the `.env` defaults.
"""

from __future__ import annotations

from bot.core.config import config
from bot.database.core import Database
from bot.database.queries import settings as settings_q


def calculate_final_price(
    base_price: float, discount_type: str | None, discount_value: float
) -> float:
    """Apply a discount to a base price. Returns a non-negative float."""
    if not discount_type or discount_value <= 0:
        return round(max(0.0, base_price), 2)
    if discount_type == "percent":
        final = base_price - (base_price * (discount_value / 100))
    elif discount_type == "flat":
        final = base_price - discount_value
    else:
        final = base_price
    return round(max(0.0, final), 2)


def format_price(amount: float, currency_label: str) -> str:
    return f"{amount:,.2f} {currency_label}"


def discount_label(discount_type: str | None, discount_value: float) -> str | None:
    if not discount_type or discount_value <= 0:
        return None
    if discount_type == "percent":
        return f"-{discount_value:g}%"
    if discount_type == "flat":
        return f"-{discount_value:g}"
    return None


class RuntimeSettings:
    """Resolves effective settings: DB override -> .env default."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def _get(self, key: str, env_default):
        value = await settings_q.get_setting(self.db, key)
        if value is None:
            return env_default
        return value

    async def staff_role_id(self) -> int | None:
        value = await self._get("staff_role_id", config.staff_role_id)
        return int(value) if value else None

    async def order_log_channel_id(self) -> int | None:
        value = await self._get("order_log_channel_id", None)
        return int(value) if value else None

    async def reviews_channel_id(self) -> int | None:
        """Public channel where approved reviews are posted automatically
        for everyone to see -- store reputation / social proof, not a staff
        moderation queue."""
        value = await self._get("reviews_channel_id", None)
        return int(value) if value else None

    async def brand_logo_url(self) -> str | None:
        return await self._get("brand_logo_url", None)

    async def leaderboard_channel_id(self) -> int | None:
        value = await self._get("leaderboard_channel_id", None)
        return int(value) if value else None

    async def leaderboard_excluded_user_ids(self) -> list[int]:
        """User IDs manually hidden from the Top Spenders leaderboard via
        /settings leaderboard_exclude -- e.g. staff/tester accounts used to
        test checkout, whose spend shouldn't count toward the public
        leaderboard. Stored as a comma-separated string of IDs."""
        value = await self._get("leaderboard_excluded_users", "")
        if not value:
            return []
        ids: list[int] = []
        for piece in str(value).split(","):
            piece = piece.strip()
            if piece.isdigit():
                ids.append(int(piece))
        return ids

    async def purchase_feed_channel_id(self) -> int | None:
        """Public channel where a card is posted every time an order is
        marked completed -- "X just bought Y" -- configured via
        /settings purchase_feed_channel."""
        value = await self._get("purchase_feed_channel_id", None)
        return int(value) if value else None

    async def ticket_category_id(self) -> int | None:
        value = await self._get("ticket_category_id", config.ticket_category_id)
        return int(value) if value else None

    async def ticket_archive_category_id(self) -> int | None:
        value = await self._get(
            "ticket_archive_category_id", config.ticket_archive_category_id
        )
        return int(value) if value else None

    async def ticket_log_channel_id(self) -> int | None:
        value = await self._get("ticket_log_channel_id", config.ticket_log_channel_id)
        return int(value) if value else None

    async def ticket_auto_archive_hours(self) -> int:
        value = await self._get(
            "ticket_auto_archive_hours", config.ticket_auto_archive_hours
        )
        return int(value)

    async def default_currency(self) -> str:
        value = await self._get("default_currency", config.default_currency)
        return str(value)
