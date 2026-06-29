"""
Posts an approved review into the public reviews channel
(`/settings reviews_channel`) for store reputation / social proof -- this is
a public showcase visible to anyone in the server, not a staff moderation
queue. Staff still decide what gets shown at all via the existing
`/review admin approve|reject|hide|delete` commands; this module only
handles getting an already-approved review onto the showcase channel.
"""

from __future__ import annotations

import discord

from bot.core.logger import logger
from bot.database.queries import products as products_q
from bot.database.queries import reviews as reviews_q
from bot.ui import embeds
from bot.utils.helpers import RuntimeSettings


async def post_review_publicly(bot, review_id: int) -> bool:
    """Returns True if the review was posted, False if no reviews channel
    is configured (or the post otherwise couldn't happen) -- callers use
    this to decide whether to mention it in their confirmation message."""
    db = bot.db
    runtime = RuntimeSettings(db)
    channel_id = await runtime.reviews_channel_id()
    if not channel_id:
        return False

    channel = bot.get_channel(channel_id)
    if not isinstance(channel, discord.TextChannel):
        return False

    review = await reviews_q.get_review(db, review_id)
    if not review or review["status"] != "approved":
        return False

    product = await products_q.get_product(db, review["product_id"])
    if not product:
        return False

    author_display = "Anonymous" if review["anonymous"] else f"<@{review['user_id']}>"
    author_avatar_url = None
    if not review["anonymous"]:
        try:
            user = bot.get_user(review["user_id"]) or await bot.fetch_user(review["user_id"])
            author_avatar_url = user.display_avatar.url
        except discord.HTTPException:
            author_avatar_url = None

    brand_logo_url = await runtime.brand_logo_url()
    embed = embeds.review_card_embed(
        review, product, author_display, author_avatar_url=author_avatar_url,
        brand_logo_url=brand_logo_url, verified=True,
    )

    try:
        await channel.send(embed=embed)
        return True
    except discord.HTTPException:
        logger.exception("Failed to post review #%s to the reviews channel.", review_id)
        return False
