"""Admin commands: /order. User commands: /orders."""

from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import orders as orders_q
from bot.database.queries import payments as payments_q
from bot.database.queries import products as products_q
from bot.database.queries import variants as variants_q
from bot.ui import embeds
from bot.utils.autocomplete import any_order_autocomplete
from bot.utils.permissions import staff_only

OrderStatus = Literal["pending", "processing", "completed", "cancelled", "refunded"]
PaymentStatus = Literal["pending", "paid", "expired", "cancelled"]


class OrderCog(commands.Cog):
    """Admin order management (/order) and customer order history (/orders)."""

    order_group = app_commands.Group(name="order", description="Manage customer orders.", guild_only=True)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _full_embed(self, order_id: int) -> discord.Embed:
        db = self.bot.db
        order = await orders_q.get_order(db, order_id)
        product = await products_q.get_product(db, order["product_id"])
        variant = await variants_q.get_variant(db, order["variant_id"]) if order["variant_id"] else None
        payment = await payments_q.get_payment_method(db, order["payment_method_id"]) if order["payment_method_id"] else None
        field_values = await orders_q.get_field_values(db, order_id)
        return embeds.order_summary_embed(order, product, variant, payment, field_values)

    @order_group.command(name="view", description="View full details of an order.")
    @app_commands.describe(order="Order to view")
    @app_commands.autocomplete(order=any_order_autocomplete)
    @staff_only()
    async def view(self, interaction: discord.Interaction, order: int) -> None:
        existing = await orders_q.get_order(self.bot.db, order)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Order not found."), ephemeral=True)
            return
        await interaction.response.send_message(embed=await self._full_embed(order), ephemeral=True)

    @order_group.command(name="list", description="List recent orders, optionally filtered by status.")
    @app_commands.describe(status="Filter by order status")
    @staff_only()
    async def list_orders(self, interaction: discord.Interaction, status: OrderStatus | None = None) -> None:
        rows = await orders_q.list_orders(self.bot.db, status=status, limit=25)
        if not rows:
            await interaction.response.send_message(
                embed=embeds.info_embed("Orders", "No orders found."), ephemeral=True
            )
            return
        lines = [
            f"`#{r['id']}` -- {r['status'].title()} / {r['payment_status'].title()} -- "
            f"{r['total_price']:,.2f} {r['currency_label']} -- <@{r['user_id']}>"
            for r in rows
        ]
        await interaction.response.send_message(
            embed=embeds.info_embed("Orders", "\n".join(lines)), ephemeral=True
        )

    @order_group.command(name="status", description="Manually set an order's status.")
    @app_commands.describe(order="Order to update", status="New status")
    @app_commands.autocomplete(order=any_order_autocomplete)
    @staff_only()
    async def set_status(self, interaction: discord.Interaction, order: int, status: OrderStatus) -> None:
        existing = await orders_q.get_order(self.bot.db, order)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Order not found."), ephemeral=True)
            return
        if status in ("cancelled", "refunded") and existing["stock_reserved"]:
            await products_q.adjust_stock(self.bot.db, existing["product_id"], 1)
            await orders_q.clear_stock_reserved(self.bot.db, order)
        await orders_q.set_order_status(self.bot.db, order, status)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Order `#{order}` status set to **{status}**."), ephemeral=True
        )

    @order_group.command(name="payment_status", description="Manually set an order's payment status.")
    @app_commands.describe(order="Order to update", payment_status="New payment status")
    @app_commands.autocomplete(order=any_order_autocomplete)
    @staff_only()
    async def set_payment_status(
        self, interaction: discord.Interaction, order: int, payment_status: PaymentStatus
    ) -> None:
        existing = await orders_q.get_order(self.bot.db, order)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Order not found."), ephemeral=True)
            return
        await orders_q.set_payment_status(self.bot.db, order, payment_status)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Order `#{order}` payment status set to **{payment_status}**."),
            ephemeral=True,
        )

    @app_commands.command(name="orders", description="View your order history.")
    @app_commands.guild_only()
    async def orders(self, interaction: discord.Interaction) -> None:
        rows = await orders_q.list_orders_for_user(self.bot.db, interaction.user.id, limit=25)
        if not rows:
            await interaction.response.send_message(
                embed=embeds.info_embed("Your Orders", "You haven't placed any orders yet."), ephemeral=True
            )
            return
        lines = [
            f"`#{r['id']}` -- {r['status'].title()} / {r['payment_status'].title()} -- "
            f"{r['total_price']:,.2f} {r['currency_label']}"
            for r in rows
        ]
        await interaction.response.send_message(
            embed=embeds.info_embed("Your Orders", "\n".join(lines)), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OrderCog(bot))
