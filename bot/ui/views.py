"""
Interactive Views for NOCTRA: shop browsing (category/product selects),
the purchase wizard (variant select -> dynamic fields -> payment select ->
order confirmation), persistent ticket control buttons, and the button-only
review flow (rating buttons -> optional text modal -- no slash command
needed).

Persistent views (survive bot restarts because they use static custom_id
values and are re-registered in `setup_hook`): ShopPanelView,
TicketControlView, TicketReopenView, OpenTicketPanelView, ReviewPromptView.
"""

from __future__ import annotations

import discord

from bot.core.theme import COLOR_ACCENT
from bot.database.queries import (
    categories as categories_q,
    fields as fields_q,
    orders as orders_q,
    payments as payments_q,
    products as products_q,
    reviews as reviews_q,
    tickets as tickets_q,
    variants as variants_q,
)
from bot.ui import embeds
from bot.ui.modals import ReasonModal, ReviewTextModal, collect_dynamic_fields
from bot.utils import ticket_actions
from bot.utils.helpers import calculate_final_price
from bot.utils.permissions import is_staff
from bot.utils.validators import FieldValidationError, validate_field_value

MAX_SELECT_OPTIONS = 25


# ============================================================================
# SHOP BROWSING
# ============================================================================

class CategorySelect(discord.ui.Select):
    def __init__(self, categories: list):
        options = [
            discord.SelectOption(
                label=cat["name"][:100],
                value=str(cat["id"]),
                description=(cat["description"] or "")[:100] or None,
            )
            for cat in categories[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="Browse a category...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        category_id = int(self.values[0])
        category = await categories_q.get_category(db, category_id)
        products = await products_q.list_products(db, category_id=category_id, visible_only=True)
        embed = embeds.product_list_embed(category, products)
        view = ProductBrowseView(category, products)
        await interaction.response.edit_message(embed=embed, view=view)


class CategoryBrowseView(discord.ui.View):
    def __init__(self, categories: list):
        super().__init__(timeout=300)
        self.add_item(CategorySelect(categories))


class ProductSelect(discord.ui.Select):
    def __init__(self, products: list):
        options = [
            discord.SelectOption(label=p["name"][:100], value=str(p["id"]))
            for p in products[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="View a product...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        product_id = int(self.values[0])
        product = await products_q.get_product(db, product_id)
        variants = await variants_q.list_variants(db, product_id)
        fields = await fields_q.list_fields(db, product_id)
        rating_summary = await reviews_q.get_rating_summary(db, product_id)
        embed = embeds.product_detail_embed(product, variants, fields, rating_summary)
        view = ProductDetailView(product)
        await interaction.response.edit_message(embed=embed, view=view)


class BackToCategoriesButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        categories = await categories_q.list_categories(db, enabled_only=True)
        embed = embeds.base_embed(
            "NOCTRA STORE", "Select a category below to browse available products.", color=COLOR_ACCENT
        )
        view = CategoryBrowseView(categories)
        await interaction.response.edit_message(embed=embed, view=view)


class ProductBrowseView(discord.ui.View):
    def __init__(self, category, products: list):
        super().__init__(timeout=300)
        if products:
            self.add_item(ProductSelect(products))
        self.add_item(BackToCategoriesButton())


class BuyButton(discord.ui.Button):
    def __init__(self, product) -> None:
        super().__init__(label="Buy Now", style=discord.ButtonStyle.success)
        self.product = product

    async def callback(self, interaction: discord.Interaction) -> None:
        await start_purchase(interaction, self.product["id"])


class ProductDetailView(discord.ui.View):
    def __init__(self, product) -> None:
        super().__init__(timeout=300)
        self.add_item(BuyButton(product))
        self.add_item(BackToCategoriesButton())


class ShopPanelView(discord.ui.View):
    """Persistent panel posted once via /settings shop_panel. Customers click
    this instead of ever running /shop -- fully button-driven browsing."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Browse Store", style=discord.ButtonStyle.success, custom_id="noctra:shop:browse")
    async def browse(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        categories = await categories_q.list_categories(db, enabled_only=True)
        embed = embeds.base_embed(
            "NOCTRA STORE", "Select a category below to browse available products.", color=COLOR_ACCENT
        )
        if not categories:
            embed.description = "The store has no categories available right now. Check back soon."
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.send_message(
            embed=embed, view=CategoryBrowseView(categories), ephemeral=True
        )


# ============================================================================
# PURCHASE WIZARD
# ============================================================================

async def start_purchase(interaction: discord.Interaction, product_id: int) -> None:
    db = interaction.client.db  # type: ignore[attr-defined]
    product = await products_q.get_product(db, product_id)
    if not product or not product["visible"]:
        await interaction.response.send_message(
            embed=embeds.error_embed("This product is not available."), ephemeral=True
        )
        return
    if product["stock_type"] == "manual" and product["stock_quantity"] <= 0:
        await interaction.response.send_message(
            embed=embeds.error_embed("This product is currently out of stock."), ephemeral=True
        )
        return

    variants = await variants_q.list_variants(db, product_id, available_only=True)
    if variants:
        embed = embeds.info_embed(
            "Select a Variant", f"Choose a variant for **{product['name']}** to continue."
        )
        await interaction.response.send_message(
            embed=embed, view=VariantSelectView(product, variants), ephemeral=True
        )
    else:
        await proceed_to_fields(interaction, product, None)


class VariantSelect(discord.ui.Select):
    def __init__(self, product, variants: list):
        self.product = product
        self.variant_map = {str(v["id"]): v for v in variants}
        options = []
        for v in variants[:MAX_SELECT_OPTIONS]:
            final = calculate_final_price(v["price"], v["discount_type"], v["discount_value"])
            options.append(
                discord.SelectOption(
                    label=v["title"][:100],
                    value=str(v["id"]),
                    description=f"{final:,.2f} {product['currency_label']}",
                )
            )
        super().__init__(placeholder="Choose a variant...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        variant = self.variant_map[self.values[0]]
        await proceed_to_fields(interaction, self.product, variant)


class VariantSelectView(discord.ui.View):
    def __init__(self, product, variants: list) -> None:
        super().__init__(timeout=180)
        self.add_item(VariantSelect(product, variants))


async def proceed_to_fields(interaction: discord.Interaction, product, variant) -> None:
    db = interaction.client.db  # type: ignore[attr-defined]
    fields = await fields_q.list_fields(db, product["id"])

    if not fields:
        await proceed_to_payment(interaction, product, variant, [])
        return

    async def on_fields_complete(inter: discord.Interaction, values_by_id: dict) -> None:
        field_rows = {f["id"]: f for f in fields}
        cleaned, errors = [], []
        for field_id, raw_value in values_by_id.items():
            f = field_rows[field_id]
            try:
                value = validate_field_value(
                    raw_value,
                    required=bool(f["required"]),
                    min_length=f["min_length"],
                    max_length=f["max_length"],
                    validation=f["validation"],
                    label=f["label"],
                )
                cleaned.append({"label": f["label"], "field_type": f["field_type"], "value": value})
            except FieldValidationError as exc:
                errors.append(str(exc))

        if errors:
            await inter.response.send_message(
                embed=embeds.error_embed("\n".join(errors)), ephemeral=True
            )
            return
        await proceed_to_payment(inter, product, variant, cleaned)

    await collect_dynamic_fields(interaction, fields, on_fields_complete)


async def proceed_to_payment(
    interaction: discord.Interaction, product, variant, field_values: list
) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    db = interaction.client.db  # type: ignore[attr-defined]
    methods = await payments_q.list_payment_methods(db, enabled_only=True)

    if not methods:
        await interaction.followup.send(
            embed=embeds.error_embed(
                "No payment methods are currently configured. Please contact staff."
            ),
            ephemeral=True,
        )
        return

    if len(methods) == 1:
        await finalize_order(interaction, product, variant, field_values, methods[0])
        return

    embed = embeds.info_embed("Select a Payment Method", "Choose how you would like to pay.")
    view = PaymentSelectView(product, variant, field_values, methods)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class PaymentSelect(discord.ui.Select):
    def __init__(self, product, variant, field_values: list, methods: list):
        self.product = product
        self.variant = variant
        self.field_values = field_values
        self.method_map = {str(m["id"]): m for m in methods}
        options = [
            discord.SelectOption(label=m["name"][:100], value=str(m["id"]))
            for m in methods[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="Choose a payment method...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        method = self.method_map[self.values[0]]
        await finalize_order(interaction, self.product, self.variant, self.field_values, method)


class PaymentSelectView(discord.ui.View):
    def __init__(self, product, variant, field_values: list, methods: list) -> None:
        super().__init__(timeout=180)
        self.add_item(PaymentSelect(product, variant, field_values, methods))


async def finalize_order(
    interaction: discord.Interaction, product, variant, field_values: list, payment
) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    db = interaction.client.db  # type: ignore[attr-defined]
    base = variant if variant else product
    unit_price = calculate_final_price(base["price" if variant else "base_price"], base["discount_type"], base["discount_value"])

    stock_reserved = False
    if product["stock_type"] == "manual":
        fresh = await products_q.get_product(db, product["id"])
        if fresh["stock_quantity"] <= 0:
            await interaction.followup.send(
                embed=embeds.error_embed("This product just went out of stock."), ephemeral=True
            )
            return
        await products_q.adjust_stock(db, product["id"], -1)
        stock_reserved = True

    order_id = await orders_q.create_order(
        db,
        interaction.user.id,
        product["id"],
        variant["id"] if variant else None,
        payment["id"],
        unit_price,
        product["currency_label"],
        stock_reserved,
        payment["timeout_minutes"],
    )

    for fv in field_values:
        await orders_q.add_field_value(db, order_id, fv["label"], fv["field_type"], fv["value"])

    channel = await ticket_actions.create_ticket_channel(
        interaction.client, interaction.guild, interaction.user, "order", order_id
    )
    await orders_q.set_ticket_channel(db, order_id, channel.id)

    order_row = await orders_q.get_order(db, order_id)
    saved_fields = await orders_q.get_field_values(db, order_id)
    order_embed = embeds.order_summary_embed(order_row, product, variant, payment, saved_fields)

    view = TicketControlView()
    content = f"{interaction.user.mention}"
    if payment["instructions"]:
        instructions_embed = embeds.info_embed(f"Payment -- {payment['name']}", payment["instructions"])
        await channel.send(content=content, embeds=[order_embed, instructions_embed], view=view)
    else:
        await channel.send(content=content, embed=order_embed, view=view)

    await interaction.followup.send(
        embed=embeds.success_embed(f"Order #{order_id} created. Continue in {channel.mention}."),
        ephemeral=True,
    )


# ============================================================================
# TICKET CONTROLS (persistent)
# ============================================================================

class TicketReopenView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Reopen Ticket", style=discord.ButtonStyle.primary, custom_id="noctra:ticket:reopen")
    async def reopen(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message(
                embed=embeds.error_embed("Only staff can reopen a ticket."), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        await ticket_actions.reopen_ticket(interaction.client, interaction.channel, str(interaction.user))
        await interaction.followup.send(embed=embeds.success_embed("Ticket reopened."), ephemeral=True)


ticket_actions._ReopenViewRef.set(TicketReopenView())


class TicketControlView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    async def _get_order(self, interaction: discord.Interaction):
        db = interaction.client.db  # type: ignore[attr-defined]
        return await orders_q.get_order_by_channel(db, interaction.channel.id)

    @discord.ui.button(label="Mark Paid", style=discord.ButtonStyle.success, custom_id="noctra:ticket:mark_paid")
    async def mark_paid(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message(embed=embeds.error_embed("Staff only."), ephemeral=True)
            return
        order = await self._get_order(interaction)
        if not order:
            await interaction.response.send_message(embed=embeds.error_embed("No order linked to this channel."), ephemeral=True)
            return
        db = interaction.client.db  # type: ignore[attr-defined]
        await orders_q.set_payment_status(db, order["id"], "paid")
        if order["status"] == "pending":
            await orders_q.set_order_status(db, order["id"], "processing")
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Order #{order['id']} marked as **paid**."), ephemeral=False
        )

    @discord.ui.button(label="Mark Completed", style=discord.ButtonStyle.primary, custom_id="noctra:ticket:mark_completed")
    async def mark_completed(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message(embed=embeds.error_embed("Staff only."), ephemeral=True)
            return
        order = await self._get_order(interaction)
        if not order:
            await interaction.response.send_message(embed=embeds.error_embed("No order linked to this channel."), ephemeral=True)
            return
        db = interaction.client.db  # type: ignore[attr-defined]
        await orders_q.set_order_status(db, order["id"], "completed")
        await interaction.response.send_message(
            embed=embeds.success_embed(f"Order #{order['id']} marked as **completed**."),
            ephemeral=False,
        )
        existing_review = await reviews_q.get_review_by_order(db, order["id"])
        if not existing_review:
            product = await products_q.get_product(db, order["product_id"])
            product_name = product["name"] if product else "your purchase"
            embed = embeds.info_embed(
                "How was your purchase?",
                f"<@{order['user_id']}> -- let others know what you thought of **{product_name}**. "
                "Click below to leave a rating, no commands needed.",
            )
            await interaction.channel.send(embed=embed, view=ReviewPromptView())

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="noctra:ticket:cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message(embed=embeds.error_embed("Staff only."), ephemeral=True)
            return
        order = await self._get_order(interaction)
        if not order:
            await interaction.response.send_message(embed=embeds.error_embed("No order linked to this channel."), ephemeral=True)
            return

        async def on_reason(inter: discord.Interaction, reason: str) -> None:
            db = inter.client.db  # type: ignore[attr-defined]
            await orders_q.set_order_status(db, order["id"], "cancelled")
            await orders_q.set_payment_status(db, order["id"], "cancelled")
            if order["stock_reserved"]:
                await products_q.adjust_stock(db, order["product_id"], 1)
                await orders_q.clear_stock_reserved(db, order["id"])
            text = f"Order #{order['id']} has been **cancelled**."
            if reason:
                text += f"\nReason: {reason}"
            await inter.response.send_message(embed=embeds.error_embed(text), ephemeral=False)

        await interaction.response.send_modal(ReasonModal("Cancel Order", on_reason))

    @discord.ui.button(label="Refund", style=discord.ButtonStyle.danger, custom_id="noctra:ticket:refund")
    async def refund(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message(embed=embeds.error_embed("Staff only."), ephemeral=True)
            return
        order = await self._get_order(interaction)
        if not order:
            await interaction.response.send_message(embed=embeds.error_embed("No order linked to this channel."), ephemeral=True)
            return

        async def on_reason(inter: discord.Interaction, reason: str) -> None:
            db = inter.client.db  # type: ignore[attr-defined]
            await orders_q.set_order_status(db, order["id"], "refunded")
            if order["stock_reserved"]:
                await products_q.adjust_stock(db, order["product_id"], 1)
                await orders_q.clear_stock_reserved(db, order["id"])
            text = f"Order #{order['id']} has been **refunded**."
            if reason:
                text += f"\nReason: {reason}"
            await inter.response.send_message(embed=embeds.error_embed(text), ephemeral=False)

        await interaction.response.send_modal(ReasonModal("Refund Order", on_reason))

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.secondary, custom_id="noctra:ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await tickets_q.get_ticket_by_channel(interaction.client.db, interaction.channel.id)  # type: ignore[attr-defined]
        if not ticket:
            await interaction.response.send_message(embed=embeds.error_embed("This is not a ticket channel."), ephemeral=True)
            return
        if not (await is_staff(interaction) or interaction.user.id == ticket["user_id"]):
            await interaction.response.send_message(
                embed=embeds.error_embed("Only staff or the ticket owner can close this ticket."), ephemeral=True
            )
            return

        async def on_reason(inter: discord.Interaction, reason: str) -> None:
            await inter.response.defer(ephemeral=True)
            await ticket_actions.close_ticket(inter.client, inter.channel, str(inter.user), reason or None)
            await inter.followup.send(embed=embeds.success_embed("Ticket closed."), ephemeral=True)

        await interaction.response.send_modal(ReasonModal("Close Ticket", on_reason))


# ============================================================================
# SUPPORT TICKET PANEL (persistent)
# ============================================================================

class OpenTicketPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="noctra:ticket:open_support")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = await ticket_actions.create_ticket_channel(
            interaction.client, interaction.guild, interaction.user, "support"
        )
        await channel.send(
            content=interaction.user.mention,
            embed=embeds.ticket_welcome_embed(),
            view=TicketControlView(),
        )
        await interaction.followup.send(
            embed=embeds.success_embed(f"Your ticket has been created: {channel.mention}"), ephemeral=True
        )


# ============================================================================
# REVIEW FLOW (button-only -- no /review submit needed)
# ============================================================================

class RatingButton(discord.ui.Button):
    def __init__(self, order_id: int, rating_value: int) -> None:
        super().__init__(label=str(rating_value), style=discord.ButtonStyle.secondary)
        self.order_id = order_id
        self.rating_value = rating_value

    async def callback(self, interaction: discord.Interaction) -> None:
        rating = self.rating_value
        order_id = self.order_id
        anonymous = self.view.anonymous  # type: ignore[union-attr]

        async def on_text(inter: discord.Interaction, text: str) -> None:
            db = inter.client.db  # type: ignore[attr-defined]
            order = await orders_q.get_order(db, order_id)
            if not order or order["user_id"] != inter.user.id:
                await inter.response.send_message(
                    embed=embeds.error_embed("This review prompt isn't for you."), ephemeral=True
                )
                return
            if order["status"] != "completed" or order["payment_status"] != "paid":
                await inter.response.send_message(
                    embed=embeds.error_embed("This order is no longer eligible for a review."), ephemeral=True
                )
                return
            if await reviews_q.get_review_by_order(db, order_id):
                await inter.response.send_message(
                    embed=embeds.error_embed("You've already reviewed this order."), ephemeral=True
                )
                return
            await reviews_q.create_review(
                db, order_id, order["product_id"], inter.user.id, rating, text or None, anonymous
            )
            await inter.response.send_message(
                embed=embeds.success_embed(
                    "Thanks! Your review has been submitted and is awaiting staff approval."
                ),
                ephemeral=True,
            )

        await interaction.response.send_modal(ReviewTextModal(f"Rate {rating}/5 -- Write a Review", on_text))


class AnonymousToggleButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Anonymous: Off", style=discord.ButtonStyle.secondary, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        view: RatingPromptView = self.view  # type: ignore[assignment]
        view.anonymous = not view.anonymous
        self.label = f"Anonymous: {'On' if view.anonymous else 'Off'}"
        await interaction.response.edit_message(view=view)


class RatingPromptView(discord.ui.View):
    def __init__(self, order_id: int) -> None:
        super().__init__(timeout=300)
        self.order_id = order_id
        self.anonymous = False
        for value in range(1, 6):
            self.add_item(RatingButton(order_id, value))
        self.add_item(AnonymousToggleButton())


class ReviewPromptView(discord.ui.View):
    """Persistent 'Leave a Review' button -- posted automatically in the
    ticket channel when staff clicks Mark Completed. The customer never has
    to type a command: tap a star rating, optionally write a few words in
    the modal that opens, done."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Leave a Review", style=discord.ButtonStyle.success, custom_id="noctra:review:start")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        order = await orders_q.get_order_by_channel(db, interaction.channel.id)
        if not order:
            await interaction.response.send_message(
                embed=embeds.error_embed("No order linked to this channel."), ephemeral=True
            )
            return
        if order["user_id"] != interaction.user.id:
            await interaction.response.send_message(
                embed=embeds.error_embed("Only the customer who placed this order can leave a review."),
                ephemeral=True,
            )
            return
        if order["status"] != "completed" or order["payment_status"] != "paid":
            await interaction.response.send_message(
                embed=embeds.error_embed("This order isn't eligible for a review yet."), ephemeral=True
            )
            return
        if await reviews_q.get_review_by_order(db, order["id"]):
            await interaction.response.send_message(
                embed=embeds.error_embed("You've already reviewed this order. Use `/review edit` to change it."),
                ephemeral=True,
            )
            return
        embed = embeds.info_embed(
            "Rate Your Purchase", "Choose a rating from 1 to 5, then write an optional review."
        )
        await interaction.response.send_message(embed=embed, view=RatingPromptView(order["id"]), ephemeral=True)
