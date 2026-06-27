"""Admin & user commands: /ticket"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import tickets as tickets_q
from bot.ui import embeds
from bot.ui.modals import ReasonModal
from bot.ui.views import OpenTicketPanelView, TicketControlView
from bot.utils import ticket_actions
from bot.utils.permissions import is_staff, staff_only


class TicketCog(commands.Cog):
    """Ticket panel setup plus open/close/reopen commands."""

    ticket_group = app_commands.Group(name="ticket", description="Manage support tickets.", guild_only=True)

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        ticket = await tickets_q.get_ticket_by_channel(self.bot.db, message.channel.id)
        if ticket and ticket["status"] == "open":
            await tickets_q.touch_activity(self.bot.db, message.channel.id)

    @ticket_group.command(name="panel", description="Post the Open Ticket panel in this channel.")
    @staff_only()
    async def panel(self, interaction: discord.Interaction) -> None:
        embed = embeds.base_embed(
            "NOCTRA -- Support",
            "Need help with an order or have a question for staff? "
            "Click below to open a private ticket.",
        )
        await interaction.channel.send(embed=embed, view=OpenTicketPanelView())
        await interaction.response.send_message(embed=embeds.success_embed("Ticket panel posted."), ephemeral=True)

    @ticket_group.command(name="open", description="Open a new support ticket.")
    @app_commands.guild_only()
    async def open_ticket(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = await ticket_actions.create_ticket_channel(
            self.bot, interaction.guild, interaction.user, "support"
        )
        await channel.send(
            content=interaction.user.mention,
            embed=embeds.ticket_welcome_embed(),
            view=TicketControlView(),
        )
        await interaction.followup.send(
            embed=embeds.success_embed(f"Your ticket has been created: {channel.mention}"), ephemeral=True
        )

    @ticket_group.command(name="close", description="Close the current ticket.")
    @app_commands.describe(reason="Reason for closing")
    async def close(self, interaction: discord.Interaction, reason: str | None = None) -> None:
        ticket = await tickets_q.get_ticket_by_channel(self.bot.db, interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(embed=embeds.error_embed("This is not a ticket channel."), ephemeral=True)
            return
        if not (await is_staff(interaction) or interaction.user.id == ticket["user_id"]):
            await interaction.response.send_message(
                embed=embeds.error_embed("Only staff or the ticket owner can close this ticket."), ephemeral=True
            )
            return

        if reason is not None:
            await interaction.response.defer(ephemeral=True)
            await ticket_actions.close_ticket(self.bot, interaction.channel, str(interaction.user), reason)
            await interaction.followup.send(embed=embeds.success_embed("Ticket closed."), ephemeral=True)
            return

        async def on_reason(inter: discord.Interaction, typed_reason: str) -> None:
            await inter.response.defer(ephemeral=True)
            await ticket_actions.close_ticket(self.bot, inter.channel, str(inter.user), typed_reason or None)
            await inter.followup.send(embed=embeds.success_embed("Ticket closed."), ephemeral=True)

        await interaction.response.send_modal(ReasonModal("Close Ticket", on_reason))

    @ticket_group.command(name="reopen", description="Reopen the current ticket.")
    @staff_only()
    async def reopen(self, interaction: discord.Interaction) -> None:
        ticket = await tickets_q.get_ticket_by_channel(self.bot.db, interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(embed=embeds.error_embed("This is not a ticket channel."), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await ticket_actions.reopen_ticket(self.bot, interaction.channel, str(interaction.user))
        await interaction.followup.send(embed=embeds.success_embed("Ticket reopened."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketCog(bot))
