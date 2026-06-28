"""
Admin commands: /category_type

Sits between Category and Product (Category -> Category Type -> Product).
Replaces the old /variant command -- instead of one product carrying
several priced sub-options, products are grouped under a type and each
product is its own fully independent, fully priced item. Dynamic checkout
fields also live here (the nested /category_type field subgroup) so every
product under a type automatically shares the same checkout fields.
"""

from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import categories as categories_q
from bot.database.queries import category_types as category_types_q
from bot.database.queries import fields as fields_q
from bot.ui import embeds
from bot.utils.autocomplete import category_autocomplete, category_type_autocomplete
from bot.utils.permissions import staff_only
from bot.utils.validators import is_valid_emoji

FieldType = Literal[
    "username", "userid", "login", "email", "password", "serverid", "gameid", "custom"
]
Validation = Literal["none", "numeric", "alpha", "alphanumeric", "email"]


class CategoryTypeCog(commands.Cog):
    """Category Type management, plus dynamic checkout field configuration."""

    category_type_group = app_commands.Group(
        name="category_type", description="Manage category types (sit between Category and Product).", guild_only=True
    )
    field_group = app_commands.Group(
        name="field",
        description="Manage a category type's dynamic checkout input fields.",
        parent=category_type_group,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -- Category Type CRUD ---------------------------------------------------

    @category_type_group.command(name="create", description="Create a new category type under a category.")
    @app_commands.describe(
        category="Parent category this type belongs to",
        name="Category type name",
        description="Optional description",
        emoji="Optional emoji shown next to this type in /shop",
    )
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def create(
        self,
        interaction: discord.Interaction,
        category: int,
        name: str,
        description: str | None = None,
        emoji: str | None = None,
    ) -> None:
        if not await categories_q.get_category(self.bot.db, category):
            await interaction.response.send_message(embed=embeds.error_embed("Category not found."), ephemeral=True)
            return
        if emoji and not is_valid_emoji(emoji):
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    "That doesn't look like a valid emoji. Use a regular emoji or a custom emoji from this server."
                ),
                ephemeral=True,
            )
            return
        category_type_id = await category_types_q.create_category_type(
            self.bot.db, category, name, description, emoji
        )
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Category type **{name}** created with ID `{category_type_id}`."),
            ephemeral=True,
        )

    @category_type_group.command(name="edit", description="Edit an existing category type.")
    @app_commands.describe(
        category_type="Category type to edit",
        name="New name",
        description="New description",
        emoji="New emoji (type none to remove it)",
        category="Move to a different parent category",
    )
    @app_commands.autocomplete(category_type=category_type_autocomplete, category=category_autocomplete)
    @staff_only()
    async def edit(
        self,
        interaction: discord.Interaction,
        category_type: int,
        name: str | None = None,
        description: str | None = None,
        emoji: str | None = None,
        category: int | None = None,
    ) -> None:
        existing = await category_types_q.get_category_type(self.bot.db, category_type)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Category type not found."), ephemeral=True)
            return
        if emoji and emoji != "none" and not is_valid_emoji(emoji):
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    "That doesn't look like a valid emoji. Use a regular emoji or a custom emoji from this server."
                ),
                ephemeral=True,
            )
            return
        await category_types_q.update_category_type(
            self.bot.db, category_type, name=name, description=description, emoji=emoji, category_id=category
        )
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Category type `#{category_type}` updated."), ephemeral=True
        )

    @category_type_group.command(name="delete", description="Delete a category type and all its products.")
    @app_commands.describe(category_type="Category type to delete")
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def delete(self, interaction: discord.Interaction, category_type: int) -> None:
        existing = await category_types_q.get_category_type(self.bot.db, category_type)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Category type not found."), ephemeral=True)
            return
        await category_types_q.delete_category_type(self.bot.db, category_type)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Category type **{existing['name']}** and its products were deleted."),
            ephemeral=True,
        )

    @category_type_group.command(name="enable", description="Enable a category type so it appears in /shop.")
    @app_commands.describe(category_type="Category type to enable")
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def enable(self, interaction: discord.Interaction, category_type: int) -> None:
        await category_types_q.set_category_type_enabled(self.bot.db, category_type, True)
        await interaction.response.send_message(embed=embeds.success_embed("Category type enabled."), ephemeral=True)

    @category_type_group.command(name="disable", description="Disable a category type, hiding it from /shop.")
    @app_commands.describe(category_type="Category type to disable")
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def disable(self, interaction: discord.Interaction, category_type: int) -> None:
        await category_types_q.set_category_type_enabled(self.bot.db, category_type, False)
        await interaction.response.send_message(embed=embeds.success_embed("Category type disabled."), ephemeral=True)

    @category_type_group.command(name="position", description="Set the sort position of a category type.")
    @app_commands.describe(category_type="Category type to reposition", position="New position (lower = earlier)")
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def position(self, interaction: discord.Interaction, category_type: int, position: int) -> None:
        await category_types_q.set_category_type_position(self.bot.db, category_type, position)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Category type `#{category_type}` moved to position {position}."),
            ephemeral=True,
        )

    @category_type_group.command(name="list", description="List category types, optionally filtered by category.")
    @app_commands.describe(category="Filter by parent category")
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def list_category_types(self, interaction: discord.Interaction, category: int | None = None) -> None:
        rows = await category_types_q.list_category_types(self.bot.db, category_id=category)
        await interaction.response.send_message(embed=embeds.category_type_list_embed(rows), ephemeral=True)

    # -- Dynamic checkout fields (shared by every product under the type) ----

    @field_group.command(name="add", description="Add a dynamic checkout input field to a category type.")
    @app_commands.describe(
        category_type="Category type to add the field to",
        label="Field label shown to the customer",
        field_type="Kind of field",
        required="Whether the customer must fill this in",
        placeholder="Placeholder text shown in the input",
        min_length="Minimum character length",
        max_length="Maximum character length",
        validation="Value validation rule",
    )
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def field_add(
        self,
        interaction: discord.Interaction,
        category_type: int,
        label: str,
        field_type: FieldType,
        required: bool = True,
        placeholder: str | None = None,
        min_length: app_commands.Range[int, 0, 4000] = 0,
        max_length: app_commands.Range[int, 1, 4000] = 100,
        validation: Validation = "none",
    ) -> None:
        if not await category_types_q.get_category_type(self.bot.db, category_type):
            await interaction.response.send_message(embed=embeds.error_embed("Category type not found."), ephemeral=True)
            return
        field_id = await fields_q.create_field(
            self.bot.db, category_type, label, field_type, required, placeholder,
            min_length, max_length, validation,
        )
        await interaction.response.send_message(
            embed=embeds.success_embed(
                f"Field **{label}** added with ID `{field_id}` -- every product under this category type will use it."
            ),
            ephemeral=True,
        )

    @field_group.command(name="edit", description="Edit a dynamic checkout input field.")
    @app_commands.describe(
        category_type="Category type the field belongs to",
        field_id="ID of the field to edit (see /category_type field list)",
        label="New label",
        required="New required state",
        placeholder="New placeholder",
        min_length="New minimum length",
        max_length="New maximum length",
        validation="New validation rule",
    )
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def field_edit(
        self,
        interaction: discord.Interaction,
        category_type: int,
        field_id: int,
        label: str | None = None,
        required: bool | None = None,
        placeholder: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        validation: Validation | None = None,
    ) -> None:
        existing = await fields_q.get_field(self.bot.db, field_id)
        if not existing or existing["category_type_id"] != category_type:
            await interaction.response.send_message(
                embed=embeds.error_embed("Field not found on this category type."), ephemeral=True
            )
            return
        updates = {}
        if label is not None:
            updates["label"] = label
        if required is not None:
            updates["required"] = int(required)
        if placeholder is not None:
            updates["placeholder"] = placeholder
        if min_length is not None:
            updates["min_length"] = min_length
        if max_length is not None:
            updates["max_length"] = max_length
        if validation is not None:
            updates["validation"] = validation
        await fields_q.update_field(self.bot.db, field_id, **updates)
        await interaction.response.send_message(embed=embeds.success_embed("Field updated."), ephemeral=True)

    @field_group.command(name="remove", description="Remove a dynamic checkout input field.")
    @app_commands.describe(category_type="Category type the field belongs to", field_id="ID of the field to remove")
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def field_remove(self, interaction: discord.Interaction, category_type: int, field_id: int) -> None:
        existing = await fields_q.get_field(self.bot.db, field_id)
        if not existing or existing["category_type_id"] != category_type:
            await interaction.response.send_message(
                embed=embeds.error_embed("Field not found on this category type."), ephemeral=True
            )
            return
        await fields_q.delete_field(self.bot.db, field_id)
        await interaction.response.send_message(embed=embeds.success_embed("Field removed."), ephemeral=True)

    @field_group.command(name="list", description="List a category type's dynamic checkout input fields.")
    @app_commands.describe(category_type="Category type to inspect")
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def field_list(self, interaction: discord.Interaction, category_type: int) -> None:
        rows = await fields_q.list_fields(self.bot.db, category_type)
        if not rows:
            await interaction.response.send_message(
                embed=embeds.info_embed("Checkout Fields", "No fields configured for this category type."),
                ephemeral=True,
            )
            return
        lines = [
            f"`#{r['id']}` **{r['label']}** ({r['field_type']}) "
            f"{'required' if r['required'] else 'optional'} -- "
            f"{r['min_length']}-{r['max_length']} chars -- validation: {r['validation']}"
            for r in rows
        ]
        await interaction.response.send_message(
            embed=embeds.info_embed("Checkout Fields", "\n".join(lines)), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CategoryTypeCog(bot))
