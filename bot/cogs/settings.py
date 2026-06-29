"""Admin commands: /settings"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import settings as settings_q
from bot.ui import embeds
from bot.ui.views import ShopPanelView
from bot.utils.helpers import RuntimeSettings
from bot.utils.permissions import staff_only


class SettingsCog(commands.Cog):
    """Configure staff role, ticket categories/channels, currency, and auto-archive."""

    settings_group = app_commands.Group(
        name="settings", description="Configure NOCTRA.", guild_only=True
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @settings_group.command(name="shop_panel", description="Post the Browse Store button panel in this channel.")
    @app_commands.describe(
        title="Panel title",
        description="Panel body text",
        image_url="Full-width banner image shown under the text (PNG/JPG/WebP)",
        thumbnail_url="Small logo/thumbnail image shown top-right (PNG/JPG/WebP)",
        button_label="Text shown on the button",
    )
    @staff_only()
    async def shop_panel(
        self,
        interaction: discord.Interaction,
        title: str = "NOCTRA STORE",
        description: str = "Click below to browse the catalogue and place an order -- no commands needed.",
        image_url: str | None = None,
        thumbnail_url: str | None = None,
        button_label: str = "Browse Store",
    ) -> None:
        embed = embeds.base_embed(title, description, image_url=image_url, thumbnail_url=thumbnail_url)
        await interaction.channel.send(embed=embed, view=ShopPanelView(button_label=button_label))
        await interaction.response.send_message(embed=embeds.success_embed("Shop panel posted."), ephemeral=True)

    @settings_group.command(
        name="order_log_channel",
        description="Set the channel where new orders are posted with staff controls (Mark Paid/Completed/Cancel/Refund).",
    )
    @app_commands.describe(channel="Channel for order notifications and staff controls")
    @staff_only()
    async def order_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await settings_q.set_setting(self.bot.db, "order_log_channel_id", str(channel.id))
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Order log channel set to {channel.mention}."), ephemeral=True
        )

    @settings_group.command(
        name="reviews_channel",
        description="Set the public channel where approved customer reviews are posted (for store reputation).",
    )
    @app_commands.describe(channel="Public channel for showcasing approved reviews")
    @staff_only()
    async def reviews_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await settings_q.set_setting(self.bot.db, "reviews_channel_id", str(channel.id))
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Reviews channel set to {channel.mention}."), ephemeral=True
        )

    @settings_group.command(
        name="brand_logo",
        description="Set the NOCTRA logo/branding image shown on review cards and other showcase embeds.",
    )
    @app_commands.describe(image_url="Logo image URL (PNG/JPG/WebP), e.g. your Cloudinary-hosted NOCTRA logo")
    @staff_only()
    async def brand_logo(self, interaction: discord.Interaction, image_url: str) -> None:
        await settings_q.set_setting(self.bot.db, "brand_logo_url", image_url)
        await interaction.response.send_message(
            embed=embeds.success_embed("Brand logo set.", ).set_thumbnail(url=image_url), ephemeral=True
        )

    @settings_group.command(name="view", description="View current settings.")
    @staff_only()
    async def view(self, interaction: discord.Interaction) -> None:
        runtime = RuntimeSettings(self.bot.db)
        values = {
            "staff_role_id": await runtime.staff_role_id(),
            "order_log_channel_id": await runtime.order_log_channel_id(),
            "reviews_channel_id": await runtime.reviews_channel_id(),
            "brand_logo_url": await runtime.brand_logo_url(),
            "ticket_category_id": await runtime.ticket_category_id(),
            "ticket_archive_category_id": await runtime.ticket_archive_category_id(),
            "ticket_log_channel_id": await runtime.ticket_log_channel_id(),
            "ticket_auto_archive_hours": await runtime.ticket_auto_archive_hours(),
            "default_currency": await runtime.default_currency(),
        }
        await interaction.response.send_message(embed=embeds.settings_embed(values), ephemeral=True)

    @settings_group.command(name="staff_role", description="Set the staff role for admin commands and tickets.")
    @app_commands.describe(role="Role that should be treated as staff")
    @staff_only()
    async def staff_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await settings_q.set_setting(self.bot.db, "staff_role_id", str(role.id))
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Staff role set to {role.mention}."), ephemeral=True
        )

    @settings_group.command(name="ticket_category", description="Set the category new ticket channels are created in.")
    @app_commands.describe(category="Category channel for new tickets")
    @staff_only()
    async def ticket_category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        await settings_q.set_setting(self.bot.db, "ticket_category_id", str(category.id))
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Ticket category set to **{category.name}**."), ephemeral=True
        )

    @settings_group.command(name="archive_category", description="Set the category auto-archived tickets are moved to.")
    @app_commands.describe(category="Category channel for archived tickets")
    @staff_only()
    async def archive_category(self, interaction: discord.Interaction, category: discord.CategoryChannel) -> None:
        await settings_q.set_setting(self.bot.db, "ticket_archive_category_id", str(category.id))
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Archive category set to **{category.name}**."), ephemeral=True
        )

    @settings_group.command(name="log_channel", description="Set the channel ticket transcripts are posted to.")
    @app_commands.describe(channel="Channel for ticket transcripts and logs")
    @staff_only()
    async def log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        await settings_q.set_setting(self.bot.db, "ticket_log_channel_id", str(channel.id))
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Log channel set to {channel.mention}."), ephemeral=True
        )

    @settings_group.command(name="auto_archive_hours", description="Hours of inactivity before a ticket is auto-archived.")
    @app_commands.describe(hours="Number of hours")
    @staff_only()
    async def auto_archive_hours(
        self, interaction: discord.Interaction, hours: app_commands.Range[int, 1, 720]
    ) -> None:
        await settings_q.set_setting(self.bot.db, "ticket_auto_archive_hours", str(hours))
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Tickets will auto-archive after {hours} hours of inactivity."),
            ephemeral=True,
        )

    @settings_group.command(name="currency", description="Set the default currency label for new products.")
    @app_commands.describe(currency_label="e.g. USD, IDR, Robux")
    @staff_only()
    async def currency(self, interaction: discord.Interaction, currency_label: str) -> None:
        await settings_q.set_setting(self.bot.db, "default_currency", currency_label)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Default currency set to **{currency_label}**."), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
