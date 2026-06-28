"""Admin commands: /product (create/edit/delete/list/visibility).

Products now belong to a Category Type (Category -> Category Type ->
Product) instead of a Category directly, and dynamic checkout fields live
on the Category Type -- see bot.cogs.category_type for both.
"""

from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import category_types as category_types_q
from bot.database.queries import products as products_q
from bot.ui import embeds
from bot.utils.autocomplete import category_type_autocomplete, product_autocomplete
from bot.utils.helpers import RuntimeSettings
from bot.utils.permissions import staff_only
from bot.utils.validators import is_valid_emoji

ProductType = Literal["manual", "automatic", "digital", "service"]
StockType = Literal["unlimited", "manual"]
DiscountType = Literal["none", "percent", "flat"]


class ProductCog(commands.Cog):
    """Product catalogue management."""

    product_group = app_commands.Group(
        name="product", description="Manage store products.", guild_only=True
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -- Product CRUD --------------------------------------------------------

    @product_group.command(name="create", description="Create a new product.")
    @app_commands.describe(
        category_type="Category type this product belongs to",
        name="Product name",
        product_type="Delivery type",
        stock_type="Unlimited or manually tracked stock",
        base_price="Base price (before discount)",
        stock_quantity="Starting stock (only used if stock_type=manual)",
        currency_label="Currency label, e.g. USD, IDR, Robux",
        description="Product description",
        image_url="Banner/thumbnail image URL (PNG/JPG/WebP)",
        emoji="Optional emoji shown next to this product in /shop",
    )
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def create(
        self,
        interaction: discord.Interaction,
        category_type: int,
        name: str,
        product_type: ProductType,
        stock_type: StockType,
        base_price: app_commands.Range[float, 0, None],
        stock_quantity: app_commands.Range[int, 0, None] = 0,
        currency_label: str | None = None,
        description: str | None = None,
        image_url: str | None = None,
        emoji: str | None = None,
    ) -> None:
        if not await category_types_q.get_category_type(self.bot.db, category_type):
            await interaction.response.send_message(embed=embeds.error_embed("Category type not found."), ephemeral=True)
            return
        if emoji and not is_valid_emoji(emoji):
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    "That doesn't look like a valid emoji. Use a regular emoji or a custom emoji from this server."
                ),
                ephemeral=True,
            )
            return
        currency = currency_label or await RuntimeSettings(self.bot.db).default_currency()
        product_id = await products_q.create_product(
            self.bot.db, category_type, name, description, product_type, stock_type,
            stock_quantity, base_price, currency, image_url, emoji,
        )
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Product **{name}** created with ID `{product_id}`."),
            ephemeral=True,
        )

    @product_group.command(name="edit", description="Edit an existing product.")
    @app_commands.describe(
        product="Product to edit",
        name="New name",
        category_type="Move to a different category type",
        description="New description",
        image_url="New banner/thumbnail URL",
        emoji="New emoji (type none to remove it)",
        product_type="New delivery type",
        stock_type="New stock type",
        stock_quantity="New stock quantity (manual stock only)",
        base_price="New base price",
        currency_label="New currency label",
        discount_type="Discount type, or none to remove it",
        discount_value="Discount value (percent number or flat amount)",
    )
    @app_commands.autocomplete(product=product_autocomplete, category_type=category_type_autocomplete)
    @staff_only()
    async def edit(
        self,
        interaction: discord.Interaction,
        product: int,
        name: str | None = None,
        category_type: int | None = None,
        description: str | None = None,
        image_url: str | None = None,
        emoji: str | None = None,
        product_type: ProductType | None = None,
        stock_type: StockType | None = None,
        stock_quantity: int | None = None,
        base_price: float | None = None,
        currency_label: str | None = None,
        discount_type: DiscountType | None = None,
        discount_value: float | None = None,
    ) -> None:
        existing = await products_q.get_product(self.bot.db, product)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Product not found."), ephemeral=True)
            return
        if emoji and emoji != "none" and not is_valid_emoji(emoji):
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    "That doesn't look like a valid emoji. Use a regular emoji or a custom emoji from this server."
                ),
                ephemeral=True,
            )
            return

        updates = {}
        if name is not None:
            updates["name"] = name
        if category_type is not None:
            updates["category_type_id"] = category_type
        if description is not None:
            updates["description"] = description
        if image_url is not None:
            updates["image_url"] = image_url
        if emoji is not None:
            updates["emoji"] = None if emoji == "none" else emoji
        if product_type is not None:
            updates["product_type"] = product_type
        if stock_type is not None:
            updates["stock_type"] = stock_type
        if stock_quantity is not None:
            updates["stock_quantity"] = stock_quantity
        if base_price is not None:
            updates["base_price"] = base_price
        if currency_label is not None:
            updates["currency_label"] = currency_label
        if discount_type is not None:
            updates["discount_type"] = None if discount_type == "none" else discount_type
        if discount_value is not None:
            updates["discount_value"] = discount_value

        await products_q.update_product(self.bot.db, product, **updates)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Product `#{product}` updated."), ephemeral=True
        )

    @product_group.command(name="delete", description="Delete a product.")
    @app_commands.describe(product="Product to delete")
    @app_commands.autocomplete(product=product_autocomplete)
    @staff_only()
    async def delete(self, interaction: discord.Interaction, product: int) -> None:
        existing = await products_q.get_product(self.bot.db, product)
        if not existing:
            await interaction.response.send_message(embed=embeds.error_embed("Product not found."), ephemeral=True)
            return
        await products_q.delete_product(self.bot.db, product)
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Product **{existing['name']}** deleted."), ephemeral=True
        )

    @product_group.command(name="visibility", description="Show or hide a product in /shop.")
    @app_commands.describe(product="Product to update", visible="True to show, False to hide")
    @app_commands.autocomplete(product=product_autocomplete)
    @staff_only()
    async def visibility(self, interaction: discord.Interaction, product: int, visible: bool) -> None:
        await products_q.set_product_visible(self.bot.db, product, visible)
        state = "visible" if visible else "hidden"
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Product `#{product}` is now **{state}**."), ephemeral=True
        )

    @product_group.command(name="list", description="List products, optionally filtered by category type.")
    @app_commands.describe(category_type="Filter by category type")
    @app_commands.autocomplete(category_type=category_type_autocomplete)
    @staff_only()
    async def list_products(self, interaction: discord.Interaction, category_type: int | None = None) -> None:
        type_row = await category_types_q.get_category_type(self.bot.db, category_type) if category_type else None
        rows = await products_q.list_products(self.bot.db, category_type_id=category_type)
        await interaction.response.send_message(
            embed=embeds.product_list_embed(type_row, rows), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProductCog(bot))
