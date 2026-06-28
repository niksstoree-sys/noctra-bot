"""
Shared review moderation notification logic.

Posts new (or re-submitted-after-edit) pending reviews to the order-log
channel -- the same place order notifications go -- with one-click
Approve/Reject/Hide buttons, so staff don't have to proactively run
`/review admin approve` and guess what's waiting. If no order-log channel
is configured, this quietly does nothing; `/review admin ...` still works
as the manual fallback either way.
"""

from __future__ import annotations

import discord

from bot.core.logger import logger
from bot.database.queries import products as products_q
from bot.database.queries import reviews as reviews_q
from bot.ui import embeds
from bot.utils.helpers import RuntimeSettings


async def notify_staff_new_review(bot, review_id: int) -> None:
    db = bot.db
    review = await reviews_q.get_review(db, review_id)
    if not review:
        return
    product = await products_q.get_product(db, review["product_id"])
    if not product:
        return

    runtime = RuntimeSettings(db)
    log_channel_id = await runtime.order_log_channel_id()
    if not log_channel_id:
        return
    channel = bot.get_channel(log_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    author_display = "Anonymous" if review["anonymous"] else f"<@{review['user_id']}>"
    embed = embeds.review_card_embed(review, product, author_display, verified=True)
    embed.add_field(name="Order", value=f"#{review['order_id']}", inline=True)

    # Deferred import: bot.ui.views imports this module at the top level
    # (for ReviewModerationButton's callback), so importing it back here at
    # module scope would be circular. By the time this function actually
    # runs, views is already fully loaded, so this lazy import is safe.
    from bot.ui.views import ReviewModerationButton

    view = discord.ui.View(timeout=None)
    for action in ("approve", "reject", "hide"):
        view.add_item(ReviewModerationButton(action, review_id))

    try:
        await channel.send(embed=embed, view=view)
    except discord.HTTPException:
        logger.exception("Failed to post review #%s to the order-log channel.", review_id)
