"""Shared autocomplete callbacks for category/product/variant/payment/order options."""

from __future__ import annotations

import discord
from discord import app_commands

from bot.database.queries import categories as categories_q
from bot.database.queries import orders as orders_q
from bot.database.queries import payments as payments_q
from bot.database.queries import products as products_q
from bot.database.queries import variants as variants_q


async def category_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    rows = await categories_q.list_categories(db)
    current_lower = current.lower()
    matches = [r for r in rows if current_lower in r["name"].lower()]
    return [
        app_commands.Choice(name=f"#{r['id']} -- {r['name']}", value=r["id"])
        for r in matches[:25]
    ]


async def product_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    rows = await products_q.search_products(db, current, limit=25)
    return [
        app_commands.Choice(name=f"#{r['id']} -- {r['name']}", value=r["id"]) for r in rows
    ]


async def variant_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    product_id = getattr(interaction.namespace, "product", None)
    if not product_id:
        return []
    rows = await variants_q.list_variants(db, int(product_id))
    current_lower = current.lower()
    matches = [r for r in rows if current_lower in r["title"].lower()]
    return [
        app_commands.Choice(name=f"#{r['id']} -- {r['title']}", value=r["id"])
        for r in matches[:25]
    ]


async def payment_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    rows = await payments_q.list_payment_methods(db)
    current_lower = current.lower()
    matches = [r for r in rows if current_lower in r["name"].lower()]
    return [
        app_commands.Choice(name=f"#{r['id']} -- {r['name']}", value=r["id"])
        for r in matches[:25]
    ]


async def my_order_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    rows = await orders_q.list_orders_for_user(db, interaction.user.id, limit=25)
    return [
        app_commands.Choice(
            name=f"#{r['id']} -- {r['status'].title()} -- {r['total_price']:,.2f} {r['currency_label']}",
            value=r["id"],
        )
        for r in rows
    ]


async def any_order_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    rows = await orders_q.list_orders(db, limit=25)
    return [
        app_commands.Choice(
            name=f"#{r['id']} -- {r['status'].title()} -- {r['total_price']:,.2f} {r['currency_label']}",
            value=r["id"],
        )
        for r in rows
    ]
