"""Admin commands: /category"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import categories as categories_q
from bot.ui import embeds
from bot.utils.autocomplete import category_autocomplete
from bot.utils.permissions import staff_only


class CategoryCog(commands.Cog):
    """Create/edit/delete categories, toggle visibility, and set ordering."""

    category_group = app_commands.Group(
        name="category", description="Manage store categories.", guild_only=True
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @category_group.command(name="create", description="Create a new category.")
    @app_commands.describe(name="Category name", description="Optional description")
    @staff_only()
    async def create(
        self, interaction: discord.Interaction, name: str, description: str | None = None
    ) -> None:
        category_id = await categories_q.create_category(self.bot.db, name, description)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Category **{name}** created with ID `{category_id}`."),
            ephemeral=True,
        )

    @category_group.command(name="edit", description="Edit an existing category.")
    @app_commands.describe(category="Category to edit", name="New name", description="New description")
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def edit(
        self,
        interaction: discord.Interaction,
        category: int,
        name: str | None = None,
        description: str | None = None,
    ) -> None:
        existing = await categories_q.get_category(self.bot.db, category)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Category not found."), ephemeral=True)
            return
        await categories_q.update_category(self.bot.db, category, name=name, description=description)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Category `#{category}` updated."), ephemeral=True
        )

    @category_group.command(name="delete", description="Delete a category and all its products.")
    @app_commands.describe(category="Category to delete")
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def delete(self, interaction: discord.Interaction, category: int) -> None:
        existing = await categories_q.get_category(self.bot.db, category)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Category not found."), ephemeral=True)
            return
        await categories_q.delete_category(self.bot.db, category)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Category **{existing['name']}** and its products were deleted."),
            ephemeral=True,
        )

    @category_group.command(name="enable", description="Enable a category so it appears in /shop.")
    @app_commands.describe(category="Category to enable")
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def enable(self, interaction: discord.Interaction, category: int) -> None:
        await categories_q.set_category_enabled(self.bot.db, category, True)
        await interaction.response.send_message(embed=embeds.success_embed("Category enabled."), ephemeral=True)

    @category_group.command(name="disable", description="Disable a category, hiding it from /shop.")
    @app_commands.describe(category="Category to disable")
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def disable(self, interaction: discord.Interaction, category: int) -> None:
        await categories_q.set_category_enabled(self.bot.db, category, False)
        await interaction.response.send_message(embed=embeds.success_embed("Category disabled."), ephemeral=True)

    @category_group.command(name="position", description="Set the sort position of a category.")
    @app_commands.describe(category="Category to reposition", position="New position (lower = earlier)")
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def position(self, interaction: discord.Interaction, category: int, position: int) -> None:
        await categories_q.set_category_position(self.bot.db, category, position)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Category `#{category}` moved to position {position}."), ephemeral=True
        )

    @category_group.command(name="list", description="List all categories.")
    @staff_only()
    async def list_categories(self, interaction: discord.Interaction) -> None:
        rows = await categories_q.list_categories(self.bot.db)
        await interaction.response.send_message(embed=embeds.category_list_embed(rows), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CategoryCog(bot))
