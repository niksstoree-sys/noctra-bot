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
from bot.database.queries import payments as payments_q
from bot.database.queries import products as products_q
from bot.database.queries import reviews as reviews_q
from bot.ui import embeds
from bot.utils.helpers import RuntimeSettings


async def _notify_customer(
    bot,
    user_id: int,
    embed: discord.Embed,
    view: discord.ui.View | None = None,
    *,
    order_id: int | None = None,
    track: bool = False,
) -> bool:
    """Sends a DM to the customer. When `track` is True (and `order_id` is
    given), the sent message is recorded in order_dm_messages so it can be
    deleted later -- used for transient working messages (status
    notifications, the review prompt, staff replies) as opposed to the
    final invoice, which is meant to stay permanently."""
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        if view is not None:
            sent = await user.send(embed=embed, view=view)
        else:
            sent = await user.send(embed=embed)
        if track and order_id is not None:
            await orders_q.add_dm_message(bot.db, order_id, sent.channel.id, sent.id)
        return True
    except discord.HTTPException:
        logger.warning("Could not DM user %s -- they may have DMs disabled.", user_id)
        return False


async def send_message_to_customer(
    bot, user_id: int, embed: discord.Embed, order_id: int | None = None
) -> bool:
    """Public wrapper for staff -> customer DMs (used by /order message and
    the order-log Reply button). Tracked for cleanup when `order_id` is
    given, same as the rest of the working checkout messages."""
    return await _notify_customer(bot, user_id, embed, order_id=order_id, track=True)


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

    # Deferred import: bot.ui.views imports this module at the top level
    # (for OrderActionButton/ReplyButton), so importing it back here at
    # module scope would be circular. By the time this function actually
    # runs, views is already fully loaded, so this lazy import is safe.
    from bot.ui.views import ReplyButton

    view = discord.ui.View(timeout=None)
    view.add_item(ReplyButton(order_id))

    try:
        await channel.send(embed=embed, view=view)
        return True
    except discord.HTTPException:
        logger.exception("Failed to forward customer message for order #%s.", order_id)
        return False


async def cleanup_dm_messages(bot, order_id: int) -> None:
    """Deletes the checkout messages (order summary, payment instructions,
    etc.) NOCTRA sent to the customer's DM for this order, so completed
    orders don't pile up in their DM history forever. Uses channel_id +
    message_id directly (get_partial_message) rather than holding onto the
    original message object, since this can run days after the message was
    sent -- long after any short-lived webhook token would matter."""
    db = bot.db
    tracked = await orders_q.list_dm_messages(db, order_id)
    for row in tracked:
        try:
            channel = bot.get_channel(row["channel_id"]) or await bot.fetch_channel(row["channel_id"])
            await channel.get_partial_message(row["message_id"]).delete()
        except discord.HTTPException:
            pass  # already deleted, DM closed, or too old -- safe to ignore
    await orders_q.clear_dm_messages(db, order_id)


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
        order_id=order_id,
        track=True,
    )
    return True, f"Order #{order_id} marked as paid."


async def mark_completed(bot, order_id: int) -> tuple[bool, str]:
    db = bot.db
    order = await orders_q.get_order(db, order_id)
    if not order:
        return False, "Order not found."

    await orders_q.set_order_status(db, order_id, "completed")
    if order["payment_status"] != "paid":
        # Completing an order implies it was paid -- without this, staff
        # clicking "Mark Completed" without first clicking "Mark Paid"
        # leaves payment_status stuck on "pending" forever, which silently
        # blocks the customer's review button (it requires both to be set).
        await orders_q.set_payment_status(db, order_id, "paid")

    # Clear out every transient working message for this order (checkout
    # flow, the "marked paid" notification, any staff replies sent so far)
    # before sending the permanent invoice -- so the invoice is the clean
    # start of what's left in the customer's DM, not buried under clutter.
    await cleanup_dm_messages(bot, order_id)

    product = await products_q.get_product(db, order["product_id"])
    product_name = product["name"] if product else "your purchase"
    payment = (
        await payments_q.get_payment_method(db, order["payment_method_id"])
        if order["payment_method_id"]
        else None
    )

    runtime = RuntimeSettings(db)
    brand_logo_url = await runtime.brand_logo_url()
    invoice_embed = embeds.order_invoice_embed(order, product, payment, brand_logo_url=brand_logo_url)
    # Not tracked -- the invoice is meant to stay as the customer's
    # permanent proof of purchase, unlike everything else in this flow.
    await _notify_customer(bot, order["user_id"], invoice_embed)

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
        # Tracked: once the customer actually submits a review, this prompt
        # (and the button on it) gets cleaned up automatically -- see
        # RatingButton in bot.ui.views.
        await _notify_customer(bot, order["user_id"], review_embed, review_view, order_id=order_id, track=True)

    # Refresh the leaderboard image -- deferred import, fire-and-forget.
    try:
        from bot.utils.leaderboard import refresh_leaderboard
        await refresh_leaderboard(bot)
    except Exception:  # noqa: BLE001
        logger.warning("Leaderboard refresh failed silently after order #%s.", order_id)

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

    # Keep the leaderboard accurate immediately. get_top_spenders already
    # excludes anything that isn't status='completed', but if this order had
    # been marked completed earlier and is only being cancelled now, the
    # posted leaderboard image itself won't drop that spend until something
    # triggers a refresh -- so trigger one right here instead of waiting for
    # the next completed order.
    try:
        from bot.utils.leaderboard import refresh_leaderboard
        await refresh_leaderboard(bot)
    except Exception:  # noqa: BLE001
        logger.warning("Leaderboard refresh failed silently after cancelling order #%s.", order_id)

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

    # Same reasoning as cancel_order -- a refund can happen after an order
    # was already completed and counted, so refresh right away.
    try:
        from bot.utils.leaderboard import refresh_leaderboard
        await refresh_leaderboard(bot)
    except Exception:  # noqa: BLE001
        logger.warning("Leaderboard refresh failed silently after refunding order #%s.", order_id)

    return True, f"Order #{order_id} refunded."
