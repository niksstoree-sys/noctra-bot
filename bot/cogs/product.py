"""Admin commands: /product (create/edit/delete/list/visibility) and the
nested /product field subgroup for admin-configurable dynamic checkout
input fields (Username, User ID, Login Data, Email, Password, Server ID,
Game ID, Custom Text).
"""

from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import categories as categories_q
from bot.database.queries import fields as fields_q
from bot.database.queries import products as products_q
from bot.ui import embeds
from bot.utils.autocomplete import category_autocomplete, product_autocomplete
from bot.utils.helpers import RuntimeSettings
from bot.utils.permissions import staff_only

ProductType = Literal["manual", "automatic", "digital", "service"]
StockType = Literal["unlimited", "manual"]
DiscountType = Literal["none", "percent", "flat"]
FieldType = Literal[
    "username", "userid", "login", "email", "password", "serverid", "gameid", "custom"
]
Validation = Literal["none", "numeric", "alpha", "alphanumeric", "email"]


class ProductCog(commands.Cog):
    """Product catalogue management, plus dynamic checkout field configuration."""

    product_group = app_commands.Group(
        name="product", description="Manage store products.", guild_only=True
    )
    field_group = app_commands.Group(
        name="field",
        description="Manage a product's dynamic checkout input fields.",
        parent=product_group,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # -- Product CRUD --------------------------------------------------------

    @product_group.command(name="create", description="Create a new product.")
    @app_commands.describe(
        category="Category this product belongs to",
        name="Product name",
        product_type="Delivery type",
        stock_type="Unlimited or manually tracked stock",
        base_price="Base price (before discount)",
        stock_quantity="Starting stock (only used if stock_type=manual)",
        currency_label="Currency label, e.g. USD, IDR, Robux",
        description="Product description",
        image_url="Banner/thumbnail image URL (PNG/JPG/WebP)",
    )
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def create(
        self,
        interaction: discord.Interaction,
        category: int,
        name: str,
        product_type: ProductType,
        stock_type: StockType,
        base_price: app_commands.Range[float, 0, None],
        stock_quantity: app_commands.Range[int, 0, None] = 0,
        currency_label: str | None = None,
        description: str | None = None,
        image_url: str | None = None,
    ) -> None:
        cat = await categories_q.get_category(self.bot.db, category)
        if not cat:
            await interaction.response.send_message(embed=embeds.error_embed("Category not found."), ephemeral=True)
            return
        currency = currency_label or await RuntimeSettings(self.bot.db).default_currency()
        product_id = await products_q.create_product(
            self.bot.db, category, name, description, product_type, stock_type,
            stock_quantity, base_price, currency, image_url,
        )
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Product **{name}** created with ID `{product_id}`."),
            ephemeral=True,
        )

    @product_group.command(name="edit", description="Edit an existing product.")
    @app_commands.describe(
        product="Product to edit",
        name="New name",
        category="Move to a different category",
        description="New description",
        image_url="New banner/thumbnail URL",
        product_type="New delivery type",
        stock_type="New stock type",
        stock_quantity="New stock quantity (manual stock only)",
        base_price="New base price",
        currency_label="New currency label",
        discount_type="Discount type, or none to remove it",
        discount_value="Discount value (percent number or flat amount)",
    )
    @app_commands.autocomplete(product=product_autocomplete, category=category_autocomplete)
    @staff_only()
    async def edit(
        self,
        interaction: discord.Interaction,
        product: int,
        name: str | None = None,
        category: int | None = None,
        description: str | None = None,
        image_url: str | None = None,
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

        updates = {}
        if name is not None:
            updates["name"] = name
        if category is not None:
            updates["category_id"] = category
        if description is not None:
            updates["description"] = description
        if image_url is not None:
            updates["image_url"] = image_url
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

    @product_group.command(name="delete", description="Delete a product and all its variants/fields.")
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

    @product_group.command(name="list", description="List products, optionally filtered by category.")
    @app_commands.describe(category="Filter by category")
    @app_commands.autocomplete(category=category_autocomplete)
    @staff_only()
    async def list_products(self, interaction: discord.Interaction, category: int | None = None) -> None:
        cat_row = await categories_q.get_category(self.bot.db, category) if category else None
        rows = await products_q.list_products(self.bot.db, category_id=category)
        await interaction.response.send_message(
            embed=embeds.product_list_embed(cat_row, rows), ephemeral=True
        )

    # -- Dynamic checkout fields ---------------------------------------------

    @field_group.command(name="add", description="Add a dynamic checkout input field to a product.")
    @app_commands.describe(
        product="Product to add the field to",
        label="Field label shown to the customer",
        field_type="Kind of field",
        required="Whether the customer must fill this in",
        placeholder="Placeholder text shown in the input",
        min_length="Minimum character length",
        max_length="Maximum character length",
        validation="Value validation rule",
    )
    @app_commands.autocomplete(product=product_autocomplete)
    @staff_only()
    async def field_add(
        self,
        interaction: discord.Interaction,
        product: int,
        label: str,
        field_type: FieldType,
        required: bool = True,
        placeholder: str | None = None,
        min_length: app_commands.Range[int, 0, 4000] = 0,
        max_length: app_commands.Range[int, 1, 4000] = 100,
        validation: Validation = "none",
    ) -> None:
        if not await products_q.get_product(self.bot.db, product):
            await interaction.response.send_message(embed=embeds.error_embed("Product not found."), ephemeral=True)
            return
        field_id = await fields_q.create_field(
            self.bot.db, product, label, field_type, required, placeholder,
            min_length, max_length, validation,
        )
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Field **{label}** added with ID `{field_id}`."), ephemeral=True
        )

    @field_group.command(name="edit", description="Edit a dynamic checkout input field.")
    @app_commands.describe(
        product="Product the field belongs to",
        field_id="ID of the field to edit (see /product field list)",
        label="New label",
        required="New required state",
        placeholder="New placeholder",
        min_length="New minimum length",
        max_length="New maximum length",
        validation="New validation rule",
    )
    @app_commands.autocomplete(product=product_autocomplete)
    @staff_only()
    async def field_edit(
        self,
        interaction: discord.Interaction,
        product: int,
        field_id: int,
        label: str | None = None,
        required: bool | None = None,
        placeholder: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        validation: Validation | None = None,
    ) -> None:
        existing = await fields_q.get_field(self.bot.db, field_id)
        if not existing or existing["product_id"] != product:
            await interaction.response.send_message(
                embed=embeds.error_embed("Field not found on this product."), ephemeral=True
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
    @app_commands.describe(product="Product the field belongs to", field_id="ID of the field to remove")
    @app_commands.autocomplete(product=product_autocomplete)
    @staff_only()
    async def field_remove(self, interaction: discord.Interaction, product: int, field_id: int) -> None:
        existing = await fields_q.get_field(self.bot.db, field_id)
        if not existing or existing["product_id"] != product:
            await interaction.response.send_message(
                embed=embeds.error_embed("Field not found on this product."), ephemeral=True
            )
            return
        await fields_q.delete_field(self.bot.db, field_id)
        await interaction.response.send_message(embed=embeds.success_embed("Field removed."), ephemeral=True)

    @field_group.command(name="list", description="List a product's dynamic checkout input fields.")
    @app_commands.describe(product="Product to inspect")
    @app_commands.autocomplete(product=product_autocomplete)
    @staff_only()
    async def field_list(self, interaction: discord.Interaction, product: int) -> None:
        rows = await fields_q.list_fields(self.bot.db, product)
        if not rows:
            await interaction.response.send_message(
                embed=embeds.info_embed("Checkout Fields", "No fields configured for this product."),
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
    await bot.add_cog(ProductCog(bot))
