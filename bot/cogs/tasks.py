"""
Background loops:
  * Expire orders whose payment deadline has passed.
  * Auto-archive tickets that have been inactive past the configured window.
  * Clear stale awaiting-photo review flags (customer never sent a photo
    and didn't tap Skip -- cleaned up after PHOTO_WINDOW_MINUTES).
"""

from __future__ import annotations

import discord
from discord.ext import commands, tasks

from bot.core.logger import logger
from bot.database.queries import orders as orders_q
from bot.database.queries import products as products_q
from bot.database.queries import reviews as reviews_q
from bot.database.queries import tickets as tickets_q
from bot.ui import embeds
from bot.utils import ticket_actions
from bot.utils.helpers import RuntimeSettings


class TasksCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.expire_payments.start()
        self.auto_archive_tickets.start()
        self.clear_stale_photo_windows.start()

    def cog_unload(self) -> None:
        self.expire_payments.cancel()
        self.auto_archive_tickets.cancel()
        self.clear_stale_photo_windows.cancel()

    @tasks.loop(minutes=2)
    async def expire_payments(self) -> None:
        try:
            db = self.bot.db
            expired = await orders_q.list_expired_pending_payments(db)
            for order in expired:
                await orders_q.set_payment_status(db, order["id"], "expired")
                if order["stock_reserved"]:
                    await products_q.adjust_stock(db, order["product_id"], 1)
                    await orders_q.clear_stock_reserved(db, order["id"])
                try:
                    user = self.bot.get_user(order["user_id"]) or await self.bot.fetch_user(order["user_id"])
                    await user.send(
                        embed=embeds.error_embed(
                            f"Your order #{order['id']} payment window has expired. "
                            "Place a new order from the store if you'd still like this item."
                        )
                    )
                except discord.HTTPException:
                    pass
        except Exception:  # noqa: BLE001
            logger.exception("Error in expire_payments task.")

    @tasks.loop(minutes=15)
    async def auto_archive_tickets(self) -> None:
        try:
            db = self.bot.db
            runtime = RuntimeSettings(db)
            hours = await runtime.ticket_auto_archive_hours()
            stale = await tickets_q.list_stale_tickets(db, hours)
            for ticket in stale:
                channel = self.bot.get_channel(ticket["channel_id"])
                if isinstance(channel, discord.TextChannel):
                    await ticket_actions.close_ticket(
                        self.bot, channel, "NOCTRA (auto-archive)",
                        "Automatically archived due to inactivity.", auto=True,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Error in auto_archive_tickets task.")

    @tasks.loop(minutes=5)
    async def clear_stale_photo_windows(self) -> None:
        """Drop awaiting_photo flag on reviews whose 10-minute photo window
        has passed -- stops the flag from getting permanently stuck if the
        customer never replied or the bot restarted mid-wait."""
        try:
            db = self.bot.db
            stale = await reviews_q.list_stale_awaiting_photo_reviews(db)
            for review in stale:
                await reviews_q.set_awaiting_photo(db, review["id"], False)
                logger.debug("Cleared stale photo window for review #%s.", review["id"])
        except Exception:  # noqa: BLE001
            logger.exception("Error in clear_stale_photo_windows task.")

    @expire_payments.before_loop
    @auto_archive_tickets.before_loop
    @clear_stale_photo_windows.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TasksCog(bot))
