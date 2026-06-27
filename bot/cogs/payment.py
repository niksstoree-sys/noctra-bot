"""Admin commands: /payment"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import payments as payments_q
from bot.ui import embeds
from bot.utils.autocomplete import payment_autocomplete
from bot.utils.permissions import staff_only


class PaymentCog(commands.Cog):
    """Configure payment methods, instructions, and timeouts."""

    payment_group = app_commands.Group(
        name="payment", description="Manage payment methods.", guild_only=True
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @payment_group.command(name="add", description="Add a new payment method.")
    @app_commands.describe(
        name="Payment method name, e.g. Bank Transfer, PayPal, Maybank",
        instructions="Instructions shown to the customer in their ticket",
        timeout_minutes="Minutes before an unpaid order is auto-expired",
    )
    @staff_only()
    async def add(
        self,
        interaction: discord.Interaction,
        name: str,
        instructions: str | None = None,
        timeout_minutes: app_commands.Range[int, 1, 10080] = 30,
    ) -> None:
        payment_id = await payments_q.create_payment_method(self.bot.db, name, instructions, timeout_minutes)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Payment method **{name}** added with ID `{payment_id}`."),
            ephemeral=True,
        )

    @payment_group.command(name="edit", description="Edit a payment method.")
    @app_commands.describe(
        payment="Payment method to edit",
        name="New name",
        instructions="New instructions",
        timeout_minutes="New payment timeout in minutes",
    )
    @app_commands.autocomplete(payment=payment_autocomplete)
    @staff_only()
    async def edit(
        self,
        interaction: discord.Interaction,
        payment: int,
        name: str | None = None,
        instructions: str | None = None,
        timeout_minutes: int | None = None,
    ) -> None:
        existing = await payments_q.get_payment_method(self.bot.db, payment)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Payment method not found."), ephemeral=True)
            return
        updates = {}
        if name is not None:
            updates["name"] = name
        if instructions is not None:
            updates["instructions"] = instructions
        if timeout_minutes is not None:
            updates["timeout_minutes"] = timeout_minutes
        await payments_q.update_payment_method(self.bot.db, payment, **updates)
        await interaction.response.send_message(embed=embeds.success_embed("Payment method updated."), ephemeral=True)

    @payment_group.command(name="delete", description="Delete a payment method.")
    @app_commands.describe(payment="Payment method to delete")
    @app_commands.autocomplete(payment=payment_autocomplete)
    @staff_only()
    async def delete(self, interaction: discord.Interaction, payment: int) -> None:
        existing = await payments_q.get_payment_method(self.bot.db, payment)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Payment method not found."), ephemeral=True)
            return
        await payments_q.delete_payment_method(self.bot.db, payment)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Payment method **{existing['name']}** deleted."), ephemeral=True
        )

    @payment_group.command(name="enable", description="Enable a payment method.")
    @app_commands.describe(payment="Payment method to enable")
    @app_commands.autocomplete(payment=payment_autocomplete)
    @staff_only()
    async def enable(self, interaction: discord.Interaction, payment: int) -> None:
        await payments_q.set_payment_enabled(self.bot.db, payment, True)
        await interaction.response.send_message(embed=embeds.success_embed("Payment method enabled."), ephemeral=True)

    @payment_group.command(name="disable", description="Disable a payment method.")
    @app_commands.describe(payment="Payment method to disable")
    @app_commands.autocomplete(payment=payment_autocomplete)
    @staff_only()
    async def disable(self, interaction: discord.Interaction, payment: int) -> None:
        await payments_q.set_payment_enabled(self.bot.db, payment, False)
        await interaction.response.send_message(embed=embeds.success_embed("Payment method disabled."), ephemeral=True)

    @payment_group.command(name="list", description="List all payment methods.")
    @staff_only()
    async def list_payments(self, interaction: discord.Interaction) -> None:
        rows = await payments_q.list_payment_methods(self.bot.db)
        await interaction.response.send_message(embed=embeds.payment_list_embed(rows), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PaymentCog(bot))
