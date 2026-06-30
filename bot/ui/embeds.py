"""
Embed builders for NOCTRA.

Every embed funnels through `base_embed()` so branding (footer, color
defaults) stays consistent. Functions accept plain values/rows rather than
ORM objects to keep this module decoupled from the database layer.
"""

from __future__ import annotations

from datetime import datetime

import discord

from bot.core.theme import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_MUTED,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    FOOTER_TEXT,
    MARK_BULLET,
    MARK_DASH,
    MARK_DIAMOND,
    STATUS_COLORS,
    rating_bar,
)
from bot.utils.helpers import calculate_final_price, discount_label, format_price


def base_embed(
    title: str,
    description: str | None = None,
    color: int = COLOR_PRIMARY,
    thumbnail_url: str | None = None,
    image_url: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER_TEXT)
    embed.timestamp = datetime.utcnow()
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if image_url:
        embed.set_image(url=image_url)
    return embed


def error_embed(message: str) -> discord.Embed:
    return base_embed(f"{MARK_DIAMOND} Error", message, color=COLOR_DANGER)


def success_embed(message: str) -> discord.Embed:
    return base_embed(f"{MARK_DIAMOND} Success", message, color=COLOR_SUCCESS)


def info_embed(title: str, message: str, image_url: str | None = None) -> discord.Embed:
    return base_embed(f"{MARK_DIAMOND} {title}", message, color=COLOR_ACCENT, image_url=image_url)


# -- Catalogue -----------------------------------------------------------------

def category_list_embed(categories: list) -> discord.Embed:
    embed = base_embed("NOCTRA -- Categories", color=COLOR_PRIMARY)
    if not categories:
        embed.description = "No categories have been created yet."
        return embed
    lines = []
    for cat in categories:
        state = "enabled" if cat["enabled"] else "disabled"
        emoji_prefix = f"{cat['emoji']} " if cat["emoji"] else ""
        lines.append(
            f"{MARK_BULLET} {emoji_prefix}**#{cat['id']} -- {cat['name']}** "
            f"{MARK_DASH} pos {cat['position']} {MARK_DASH} {state}"
        )
        if cat["description"]:
            lines.append(f"    {cat['description']}")
    embed.description = "\n".join(lines)
    return embed


def category_type_list_embed(category_types: list) -> discord.Embed:
    embed = base_embed("NOCTRA -- Category Types", color=COLOR_PRIMARY)
    if not category_types:
        embed.description = "No category types have been created yet."
        return embed
    lines = []
    for ct in category_types:
        state = "enabled" if ct["enabled"] else "disabled"
        emoji_prefix = f"{ct['emoji']} " if ct["emoji"] else ""
        lines.append(
            f"{MARK_BULLET} {emoji_prefix}**#{ct['id']} -- {ct['name']}** "
            f"{MARK_DASH} category #{ct['category_id']} {MARK_DASH} pos {ct['position']} {MARK_DASH} {state}"
        )
        if ct["description"]:
            lines.append(f"    {ct['description']}")
    embed.description = "\n".join(lines)
    return embed


def product_summary_line(product, rating_summary: dict | None = None) -> str:
    final = calculate_final_price(
        product["base_price"], product["discount_type"], product["discount_value"]
    )
    price_text = format_price(final, product["currency_label"])
    dlabel = discount_label(product["discount_type"], product["discount_value"])
    if dlabel:
        price_text += f" ({dlabel}, was {format_price(product['base_price'], product['currency_label'])})"
    rating_text = ""
    if rating_summary and rating_summary["total"]:
        rating_text = f" {MARK_DASH} {rating_summary['average']:.1f}/5 ({rating_summary['total']} reviews)"
    visibility = "" if product["visible"] else " [hidden]"
    emoji_prefix = f"{product['emoji']} " if product["emoji"] else ""
    return f"{MARK_BULLET} {emoji_prefix}**{product['name']}**{visibility} {MARK_DASH} {price_text}{rating_text}"


def product_list_embed(category_type, products: list) -> discord.Embed:
    if category_type:
        emoji_prefix = f"{category_type['emoji']} " if category_type["emoji"] else ""
        title = f"NOCTRA -- {emoji_prefix}{category_type['name']}"
    else:
        title = "NOCTRA -- Products"
    embed = base_embed(title, color=COLOR_PRIMARY)
    if not products:
        embed.description = "No products in this category type yet."
        return embed
    embed.description = "\n".join(product_summary_line(p) for p in products)
    return embed


def product_detail_embed(product, fields: list, rating_summary: dict) -> discord.Embed:
    final = calculate_final_price(
        product["base_price"], product["discount_type"], product["discount_value"]
    )
    price_text = format_price(final, product["currency_label"])
    dlabel = discount_label(product["discount_type"], product["discount_value"])

    title = f"{product['emoji']} {product['name']}" if product["emoji"] else product["name"]
    embed = base_embed(
        title,
        product["description"] or "No description provided.",
        color=COLOR_PRIMARY,
        thumbnail_url=product["image_url"] or None,
    )

    price_line = f"**{price_text}**"
    if dlabel:
        price_line += f"  {MARK_DASH}  {dlabel} (was {format_price(product['base_price'], product['currency_label'])})"
    embed.add_field(name="Price", value=price_line, inline=True)

    type_label = product["product_type"].replace("_", " ").title()
    embed.add_field(name="Type", value=type_label, inline=True)

    if product["stock_type"] == "unlimited":
        stock_text = "Unlimited"
    else:
        stock_text = f"{product['stock_quantity']} in stock"
    embed.add_field(name="Stock", value=stock_text, inline=True)

    if fields:
        req = [f["label"] for f in fields if f["required"]]
        opt = [f["label"] for f in fields if not f["required"]]
        field_text = ""
        if req:
            field_text += "Required: " + ", ".join(req)
        if opt:
            field_text += ("\n" if field_text else "") + "Optional: " + ", ".join(opt)
        embed.add_field(name="Checkout Information Needed", value=field_text, inline=False)

    if rating_summary["total"]:
        bar = rating_bar(rating_summary["average"])
        embed.add_field(
            name="Rating",
            value=f"{rating_summary['average']:.1f}/5 {MARK_DASH} {bar} {MARK_DASH} {rating_summary['total']} reviews",
            inline=False,
        )
    else:
        embed.add_field(name="Rating", value="No reviews yet.", inline=False)

    return embed


# -- Orders / Tickets -----------------------------------------------------------

def order_summary_embed(
    order_row,
    product_row,
    payment_row,
    field_values: list | None = None,
) -> discord.Embed:
    status = order_row["status"]
    color = STATUS_COLORS.get(status, COLOR_PRIMARY)
    embed = base_embed(f"Order #{order_row['id']}", color=color)

    embed.add_field(name="Product", value=product_row["name"], inline=True)
    embed.add_field(
        name="Price",
        value=format_price(order_row["total_price"], order_row["currency_label"]),
        inline=True,
    )
    embed.add_field(name="Status", value=status.title(), inline=True)
    embed.add_field(
        name="Payment", value=order_row["payment_status"].title(), inline=True
    )
    if payment_row:
        embed.add_field(name="Payment Method", value=payment_row["name"], inline=True)
    embed.add_field(
        name="Placed",
        value=f"<t:{int(datetime.fromisoformat(order_row['created_at']).timestamp())}:R>",
        inline=True,
    )

    if field_values:
        lines = []
        for fv in field_values:
            value = fv["value"]
            if fv["field_type"] == "password" and value:
                value = "*" * min(len(value), 12)
            lines.append(f"{MARK_BULLET} **{fv['label']}:** {value}")
        embed.add_field(name="Submitted Information", value="\n".join(lines), inline=False)

    return embed


def order_invoice_embed(
    order_row,
    product_row,
    payment_row,
    brand_logo_url: str | None = None,
) -> discord.Embed:
    """A clean, permanent receipt sent the moment an order is marked
    completed -- distinct from order_summary_embed (which is a working
    checkout-in-progress card that gets cleaned up later). This one is meant
    to stay in the customer's DM as their proof of purchase."""
    invoice_number = f"NOCTRA-{order_row['id']:06d}"
    completed_ts = int(datetime.utcnow().timestamp())

    embed = base_embed(
        f"{MARK_DIAMOND} Invoice {invoice_number}",
        "Thank you for your purchase -- here's your receipt.",
        color=COLOR_SUCCESS,
        thumbnail_url=brand_logo_url,
    )
    embed.add_field(name="Item", value=product_row["name"], inline=False)
    embed.add_field(
        name="Amount Paid",
        value=f"**{format_price(order_row['total_price'], order_row['currency_label'])}**",
        inline=True,
    )
    if payment_row:
        embed.add_field(name="Payment Method", value=payment_row["name"], inline=True)
    embed.add_field(name="Order ID", value=f"#{order_row['id']}", inline=True)
    embed.add_field(name="Completed", value=f"<t:{completed_ts}:f>", inline=True)
    embed.set_footer(text=f"{FOOTER_TEXT}  {MARK_DASH}  Keep this for your records")
    return embed


def ticket_welcome_embed(order_summary_text: str | None = None) -> discord.Embed:
    description = (
        "Thank you for opening a ticket. Our staff will assist you shortly.\n\n"
        "Please remain in this channel and provide any additional details staff request."
    )
    if order_summary_text:
        description = order_summary_text + "\n\n" + description
    return base_embed("NOCTRA -- Support Ticket", description, color=COLOR_ACCENT)


def ticket_closed_embed(close_reason: str | None, closed_by: str) -> discord.Embed:
    description = f"This ticket was closed by **{closed_by}**."
    if close_reason:
        description += f"\n\n**Reason:** {close_reason}"
    return base_embed("Ticket Closed", description, color=COLOR_MUTED)


# -- Reviews ---------------------------------------------------------------------

def star_rating(rating: int, scale: int = 5) -> str:
    """A 5-star emoji row, e.g. 4/5 -> 'star star star star outline-star'."""
    rating = max(0, min(scale, rating))
    return "\u2b50" * rating + "\u2606" * (scale - rating)


def review_card_embed(
    review_row,
    product_row,
    author_display: str,
    author_avatar_url: str | None = None,
    brand_logo_url: str | None = None,
    verified: bool = True,
) -> discord.Embed:
    # Always brand purple here -- this is a public branding showcase card,
    # not a status indicator, so it shouldn't shift to green/red based on
    # approved/rejected/hidden the way internal admin embeds do.
    embed = base_embed(
        product_row["name"],
        color=COLOR_PRIMARY,
        image_url=brand_logo_url,
        # The author icon alone is tiny (just a small circle next to the
        # name) -- setting the same avatar as the thumbnail puts a much
        # bigger, clearly visible version of it in the embed's top-right
        # corner, which would otherwise sit empty.
        thumbnail_url=author_avatar_url,
    )
    embed.set_author(name=author_display, icon_url=author_avatar_url or None)
    embed.add_field(
        name="Rating", value=f"{star_rating(review_row['rating'])}  ({review_row['rating']}/5)", inline=False
    )
    if review_row["review_text"]:
        embed.add_field(name="Review", value=review_row["review_text"], inline=False)
    badge = "Verified Purchase" if verified else "Unverified"
    embed.add_field(name="Purchase", value=badge, inline=True)
    embed.add_field(name="Status", value=review_row["status"].title(), inline=True)
    return embed


def rating_distribution_embed(product_row, summary: dict) -> discord.Embed:
    embed = base_embed(f"{product_row['name']} -- Ratings", color=COLOR_PRIMARY)
    if not summary["total"]:
        embed.description = "No approved reviews yet."
        return embed
    embed.description = f"**{summary['average']:.1f}/5** from {summary['total']} reviews"
    lines = []
    for star in (5, 4, 3, 2, 1):
        count = summary["distribution"].get(star, 0)
        ratio = count / summary["total"] if summary["total"] else 0
        bar_len = round(ratio * 12)
        lines.append(f"{star} {MARK_DASH} {'█' * bar_len}{'░' * (12 - bar_len)} ({count})")
    embed.add_field(name="Distribution", value="\n".join(lines), inline=False)
    return embed


# -- Settings / Admin lists ------------------------------------------------------

def settings_embed(values: dict) -> discord.Embed:
    embed = base_embed("NOCTRA -- Settings", color=COLOR_PRIMARY)
    for key, value in values.items():
        label = key.replace("_", " ").title()
        embed.add_field(name=label, value=str(value) if value is not None else "Not set", inline=True)
    return embed


def payment_list_embed(payments: list) -> discord.Embed:
    embed = base_embed("NOCTRA -- Payment Methods", color=COLOR_PRIMARY)
    if not payments:
        embed.description = "No payment methods configured yet."
        return embed
    lines = []
    for p in payments:
        state = "enabled" if p["enabled"] else "disabled"
        has_image = "image set" if p["image_url"] else "no image"
        lines.append(
            f"{MARK_BULLET} **#{p['id']} -- {p['name']}** {MARK_DASH} {state} "
            f"{MARK_DASH} timeout {p['timeout_minutes']}m {MARK_DASH} {has_image}"
        )
    embed.description = "\n".join(lines)
    return embed
