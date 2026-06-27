"""
Shared order status-transition logic: customer DM notifications, stock
restock on cancel/refund, and kicking off the button-only review prompt on
completion.

Used by BOTH the `/order` admin commands and the order-log channel's
OrderActionButton, so the customer gets the exact same notification no
matter which path staff use to update an order.
"""

from __future__ import annotations

import discord

from bot.core.logger import logger
from bot.database.queries import orders as orders_q
from bot.database.queries import products as products_q
from bot.database.queries import reviews as reviews_q
from bot.ui import embeds
from bot.utils.helpers import RuntimeSettings


async def _notify_customer(
    bot, user_id: int, embed: discord.Embed, view: discord.ui.View | None = None
) -> bool:
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        if view is not None:
            await user.send(embed=embed, view=view)
        else:
            await user.send(embed=embed)
        return True
    except discord.HTTPException:
        logger.warning("Could not DM user %s -- they may have DMs disabled.", user_id)
        return False


async def send_message_to_customer(bot, user_id: int, embed: discord.Embed) -> bool:
    """Public wrapper for staff -> customer DMs (used by /order message)."""
    return await _notify_customer(bot, user_id, embed)


async def forward_to_staff(
    bot, order_id: int, user: discord.abc.User, content: str, attachment_urls: list[str]
) -> bool:
    """Relay a customer's DM (e.g. a payment proof screenshot) into the
    order-log channel, tagged with the order ID and customer, so staff can
    tell exactly who paid for what without the customer ever opening a
    ticket channel. Returns False if no order-log channel is configured."""
    db = bot.db
    runtime = RuntimeSettings(db)
    log_channel_id = await runtime.order_log_channel_id()
    if not log_channel_id:
        return False
    channel = bot.get_channel(log_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return False

    embed = embeds.info_embed(
        f"Message from customer -- Order #{order_id}",
        content if content else "*(no text -- see attachment)*",
    )
    embed.add_field(name="Customer", value=f"<@{user.id}> ({user})", inline=False)
    if attachment_urls:
        embed.set_image(url=attachment_urls[0])
        if len(attachment_urls) > 1:
            embed.add_field(
                name="More attachments", value="\n".join(attachment_urls[1:]), inline=False
            )

    try:
        await channel.send(embed=embed)
        return True
    except discord.HTTPException:
        logger.exception("Failed to forward customer message for order #%s.", order_id)
        return False


async def mark_paid(bot, order_id: int) -> tuple[bool, str]:
    db = bot.db
    order = await orders_q.get_order(db, order_id)
    if not order:
        return False, "Order not found."

    await orders_q.set_payment_status(db, order_id, "paid")
    if order["status"] == "pending":
        await orders_q.set_order_status(db, order_id, "processing")

    await _notify_customer(
        bot,
        order["user_id"],
        embeds.success_embed(
            f"Your order #{order_id} has been marked as **paid** and is now being processed."
        ),
    )
    return True, f"Order #{order_id} marked as paid."


async def mark_completed(bot, order_id: int) -> tuple[bool, str]:
    db = bot.db
    order = await orders_q.get_order(db, order_id)
    if not order:
        return False, "Order not found."

    await orders_q.set_order_status(db, order_id, "completed")

    product = await products_q.get_product(db, order["product_id"])
    product_name = product["name"] if product else "your purchase"

    await _notify_customer(
        bot,
        order["user_id"],
        embeds.success_embed(
            f"Your order #{order_id} for **{product_name}** is complete! Thank you for your purchase."
        ),
    )

    existing_review = await reviews_q.get_review_by_order(db, order_id)
    if not existing_review:
        # Deferred import: bot.ui.views imports this module at the top level
        # (for OrderActionButton), so importing it back here at module scope
        # would be circular. By the time this function actually runs, views
        # is already fully loaded, so this lazy import is safe and cheap.
        from bot.ui.views import ReviewStartButton

        review_view = discord.ui.View(timeout=None)
        review_view.add_item(ReviewStartButton(order_id))
        review_embed = embeds.info_embed(
            "How was your purchase?",
            f"Let others know what you thought of **{product_name}**. "
            "Click below to leave a rating -- no commands needed.",
        )
        await _notify_customer(bot, order["user_id"], review_embed, review_view)

    return True, f"Order #{order_id} marked as completed."


async def cancel_order(bot, order_id: int, reason: str | None) -> tuple[bool, str]:
    db = bot.db
    order = await orders_q.get_order(db, order_id)
    if not order:
        return False, "Order not found."

    await orders_q.set_order_status(db, order_id, "cancelled")
    await orders_q.set_payment_status(db, order_id, "cancelled")
    if order["stock_reserved"]:
        await products_q.adjust_stock(db, order["product_id"], 1)
        await orders_q.clear_stock_reserved(db, order_id)

    text = f"Your order #{order_id} has been **cancelled**."
    if reason:
        text += f"\nReason: {reason}"
    await _notify_customer(bot, order["user_id"], embeds.error_embed(text))
    return True, f"Order #{order_id} cancelled."


async def refund_order(bot, order_id: int, reason: str | None) -> tuple[bool, str]:
    db = bot.db
    order = await orders_q.get_order(db, order_id)
    if not order:
        return False, "Order not found."

    await orders_q.set_order_status(db, order_id, "refunded")
    if order["stock_reserved"]:
        await products_q.adjust_stock(db, order["product_id"], 1)
        await orders_q.clear_stock_reserved(db, order_id)

    text = f"Your order #{order_id} has been **refunded**."
    if reason:
        text += f"\nReason: {reason}"
    await _notify_customer(bot, order["user_id"], embeds.error_embed(text))
    return True, f"Order #{order_id} refunded."
