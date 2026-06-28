"""
Interactive Views for NOCTRA: shop browsing (Category -> Category Type ->
Product selects), the purchase wizard (dynamic fields -> payment select ->
order confirmation), persistent ticket control buttons (general support
only), and the button-only review flow (rating buttons -> optional text
modal).

There is no "variant" concept -- each product under a category type is its
own fully independent, fully priced item. Dynamic checkout fields live on
the category type and are automatically shared by every product under it.

The purchase wizard and review flow are DM-based: after the initial "Buy Now"
click in a guild channel, every remaining step (dynamic field modals,
payment select, order confirmation, payment instructions, and later the
review prompt) happens in the customer's DMs. This makes the whole store
guild-agnostic by design -- the same catalogue/orders/reviews work no matter
which server the bot is posted in, since nothing customer-facing depends on
a per-guild ticket channel. Staff manage orders either via `/order` commands
or the optional order-log channel (`/settings order_log_channel`).

Persistent views/items (survive bot restarts):
  - Static custom_id, registered via `add_view` in setup_hook: ShopPanelView,
    TicketControlView, TicketReopenView, OpenTicketPanelView.
  - Dynamic custom_id (order/rating id encoded in the id itself), registered
    via `add_dynamic_items` in setup_hook: OrderActionButton, ReviewStartButton.
"""

from __future__ import annotations

import discord

from bot.core.logger import logger
from bot.core.theme import COLOR_ACCENT
from bot.database.queries import (
    categories as categories_q,
    category_types as category_types_q,
    fields as fields_q,
    orders as orders_q,
    payments as payments_q,
    products as products_q,
    reviews as reviews_q,
    tickets as tickets_q,
)
from bot.ui import embeds
from bot.ui.modals import ReasonModal, ReviewTextModal, collect_dynamic_fields
from bot.utils import order_actions, ticket_actions
from bot.utils.helpers import RuntimeSettings, calculate_final_price
from bot.utils.permissions import is_staff
from bot.utils.validators import FieldValidationError, validate_field_value

MAX_SELECT_OPTIONS = 25


# ============================================================================
# SHOP BROWSING (Category -> Category Type -> Product)
# ============================================================================

class CategorySelect(discord.ui.Select):
    def __init__(self, categories: list):
        options = [
            discord.SelectOption(
                label=cat["name"][:100],
                value=str(cat["id"]),
                description=(cat["description"] or "")[:100] or None,
                emoji=cat["emoji"] or None,
            )
            for cat in categories[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="Browse a category...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        category_id = int(self.values[0])
        category = await categories_q.get_category(db, category_id)
        category_types = await category_types_q.list_category_types(db, category_id=category_id, enabled_only=True)
        embed = embeds.base_embed(
            f"NOCTRA -- {category['emoji'] + ' ' if category['emoji'] else ''}{category['name']}",
            "Select a type below to see its products.",
            color=COLOR_ACCENT,
        )
        if not category_types:
            embed.description = "No product types in this category yet."
        view = CategoryTypeBrowseView(category, category_types)
        await interaction.response.edit_message(embed=embed, view=view)


class CategoryBrowseView(discord.ui.View):
    def __init__(self, categories: list):
        super().__init__(timeout=300)
        self.add_item(CategorySelect(categories))


class CategoryTypeSelect(discord.ui.Select):
    def __init__(self, category_types: list):
        options = [
            discord.SelectOption(
                label=ct["name"][:100],
                value=str(ct["id"]),
                description=(ct["description"] or "")[:100] or None,
                emoji=ct["emoji"] or None,
            )
            for ct in category_types[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="Choose a type...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        category_type_id = int(self.values[0])
        category_type = await category_types_q.get_category_type(db, category_type_id)
        products = await products_q.list_products(db, category_type_id=category_type_id, visible_only=True)
        embed = embeds.product_list_embed(category_type, products)
        view = ProductBrowseView(category_type, products)
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


class CategoryTypeBrowseView(discord.ui.View):
    def __init__(self, category, category_types: list) -> None:
        super().__init__(timeout=300)
        if category_types:
            self.add_item(CategoryTypeSelect(category_types))
        self.add_item(BackToCategoriesButton())


class ProductSelect(discord.ui.Select):
    def __init__(self, products: list):
        options = [
            discord.SelectOption(
                label=p["name"][:100], value=str(p["id"]), emoji=p["emoji"] or None
            )
            for p in products[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="View a product...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        product_id = int(self.values[0])
        product = await products_q.get_product(db, product_id)
        fields = await fields_q.list_fields(db, product["category_type_id"])
        rating_summary = await reviews_q.get_rating_summary(db, product_id)
        embed = embeds.product_detail_embed(product, fields, rating_summary)
        view = ProductDetailView(product)
        await interaction.response.edit_message(embed=embed, view=view)


class BackToCategoryTypesButton(discord.ui.Button):
    def __init__(self, category_id: int) -> None:
        super().__init__(label="Back", style=discord.ButtonStyle.secondary)
        self.category_id = category_id

    async def callback(self, interaction: discord.Interaction) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        category = await categories_q.get_category(db, self.category_id)
        category_types = await category_types_q.list_category_types(db, category_id=self.category_id, enabled_only=True)
        embed = embeds.base_embed(
            f"NOCTRA -- {category['emoji'] + ' ' if category and category['emoji'] else ''}{category['name'] if category else ''}",
            "Select a type below to see its products.",
            color=COLOR_ACCENT,
        )
        view = CategoryTypeBrowseView(category, category_types)
        await interaction.response.edit_message(embed=embed, view=view)


class ProductBrowseView(discord.ui.View):
    def __init__(self, category_type, products: list) -> None:
        super().__init__(timeout=300)
        if products:
            self.add_item(ProductSelect(products))
        self.add_item(BackToCategoryTypesButton(category_type["category_id"] if category_type else 0))


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
        self.add_item(BackToCategoryTypesButton(product["category_type_id"]))


class ShopPanelView(discord.ui.View):
    """Persistent panel posted once via /settings shop_panel. Customers click
    this instead of ever running /shop -- fully button-driven browsing.

    The custom_id stays fixed ("noctra:shop:browse") so this keeps working
    after a bot restart no matter what label staff chose when posting it --
    only the button's `custom_id` matters for re-attaching to the persistent
    template registered in setup_hook, not its visible label."""

    def __init__(self, button_label: str = "Browse Store") -> None:
        super().__init__(timeout=None)
        self.browse.label = button_label[:80]

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
# PURCHASE WIZARD (DM-based)
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

    dm_channel = await interaction.user.create_dm()
    embed = embeds.info_embed(
        "Continue Your Order", f"Click below to continue ordering **{product['name']}**."
    )
    try:
        await dm_channel.send(embed=embed, view=ContinueOrderView(product))
    except discord.Forbidden:
        await interaction.response.send_message(
            embed=embeds.error_embed(
                "I couldn't send you a DM to continue checkout. Please enable "
                '"Allow direct messages from server members" in your Privacy Settings '
                "for this server and try again."
            ),
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        embed=embeds.success_embed("Check your DMs to continue your order."), ephemeral=True
    )


class ContinueOrderButton(discord.ui.Button):
    """Gives the customer something to click in their DM so a Modal can be
    opened for checkout fields, since Discord only allows opening a Modal in
    response to a component interaction, never from a plain bot-sent
    message."""

    def __init__(self, product) -> None:
        super().__init__(label="Continue Order", style=discord.ButtonStyle.success)
        self.product = product

    async def callback(self, interaction: discord.Interaction) -> None:
        await proceed_to_fields(interaction, self.product)


class ContinueOrderView(discord.ui.View):
    def __init__(self, product) -> None:
        super().__init__(timeout=600)
        self.add_item(ContinueOrderButton(product))


async def proceed_to_fields(interaction: discord.Interaction, product) -> None:
    db = interaction.client.db  # type: ignore[attr-defined]
    fields = await fields_q.list_fields(db, product["category_type_id"])

    if not fields:
        await proceed_to_payment(interaction, product, [])
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
        await proceed_to_payment(inter, product, cleaned)

    await collect_dynamic_fields(interaction, fields, on_fields_complete)


async def proceed_to_payment(interaction: discord.Interaction, product, field_values: list) -> None:
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
        await finalize_order(interaction, product, field_values, methods[0])
        return

    embed = embeds.info_embed("Select a Payment Method", "Choose how you would like to pay.")
    view = PaymentSelectView(product, field_values, methods)
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class PaymentSelect(discord.ui.Select):
    def __init__(self, product, field_values: list, methods: list):
        self.product = product
        self.field_values = field_values
        self.method_map = {str(m["id"]): m for m in methods}
        options = [
            discord.SelectOption(label=m["name"][:100], value=str(m["id"]))
            for m in methods[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="Choose a payment method...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        method = self.method_map[self.values[0]]
        await finalize_order(interaction, self.product, self.field_values, method)


class PaymentSelectView(discord.ui.View):
    def __init__(self, product, field_values: list, methods: list) -> None:
        super().__init__(timeout=180)
        self.add_item(PaymentSelect(product, field_values, methods))


async def finalize_order(interaction: discord.Interaction, product, field_values: list, payment) -> None:
    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)

    db = interaction.client.db  # type: ignore[attr-defined]
    unit_price = calculate_final_price(product["base_price"], product["discount_type"], product["discount_value"])

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
        payment["id"],
        unit_price,
        product["currency_label"],
        stock_reserved,
        payment["timeout_minutes"],
    )

    for fv in field_values:
        await orders_q.add_field_value(db, order_id, fv["label"], fv["field_type"], fv["value"])

    order_row = await orders_q.get_order(db, order_id)
    saved_fields = await orders_q.get_field_values(db, order_id)
    order_embed = embeds.order_summary_embed(order_row, product, payment, saved_fields)

    reply_embeds = [order_embed]
    if payment["instructions"] or payment["image_url"]:
        reply_embeds.append(
            embeds.info_embed(
                f"Payment -- {payment['name']}",
                payment["instructions"] or "Scan the QR code below to pay.",
                image_url=payment["image_url"],
            )
        )
    reply_embeds.append(
        embeds.info_embed(
            "Already Paid?",
            "Once you've paid, send your payment proof (a screenshot works great) "
            "right here in this DM -- it gets forwarded to staff automatically, "
            "tagged with this order number, so it's never mixed up with anyone else's.",
        )
    )

    await interaction.followup.send(
        content="Your order has been created! Here are the details:",
        embeds=reply_embeds,
        ephemeral=True,
    )

    # Let staff know via the order-log channel, if one is configured. This
    # works across every server the bot is in, since the channel is a fixed
    # bot-wide object -- it doesn't have to live in the guild the customer
    # bought from.
    runtime = RuntimeSettings(db)
    log_channel_id = await runtime.order_log_channel_id()
    if log_channel_id:
        log_channel = interaction.client.get_channel(log_channel_id)
        if isinstance(log_channel, discord.TextChannel):
            staff_embed = embeds.order_summary_embed(order_row, product, payment, saved_fields)
            staff_embed.add_field(name="Customer", value=f"<@{interaction.user.id}> ({interaction.user})", inline=False)
            staff_view = discord.ui.View(timeout=None)
            for action in ("mark_paid", "mark_completed", "cancel", "refund"):
                staff_view.add_item(OrderActionButton(action, order_id))
            try:
                await log_channel.send(embed=staff_embed, view=staff_view)
            except discord.HTTPException:
                logger.exception("Failed to post order #%s to the order-log channel.", order_id)

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
    """Attached to general support tickets only -- order-specific actions
    (Mark Paid/Completed/Cancel/Refund) now live on OrderActionButton in the
    order-log channel and/or the /order commands, since orders no longer
    create a per-order ticket channel (see module docstring)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

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
# ORDER ACTIONS (persistent, dynamic -- posted in the order-log channel)
# ============================================================================

class OrderActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"noctra:order:(?P<action>mark_paid|mark_completed|cancel|refund):(?P<order_id>[0-9]+)",
):
    """A staff control button whose order ID is encoded directly in its
    custom_id. Unlike a normal persistent View (one fixed custom_id shared by
    every message), this lets every order get its own working Mark Paid /
    Mark Completed / Cancel / Refund buttons in the shared order-log channel,
    and they keep working after a bot restart with no extra bookkeeping --
    discord.py reconstructs the button from the custom_id alone."""

    LABELS = {
        "mark_paid": "Mark Paid",
        "mark_completed": "Mark Completed",
        "cancel": "Cancel",
        "refund": "Refund",
    }
    STYLES = {
        "mark_paid": discord.ButtonStyle.success,
        "mark_completed": discord.ButtonStyle.primary,
        "cancel": discord.ButtonStyle.danger,
        "refund": discord.ButtonStyle.danger,
    }

    def __init__(self, action: str, order_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label=self.LABELS[action],
                style=self.STYLES[action],
                custom_id=f"noctra:order:{action}:{order_id}",
            )
        )
        self.action = action
        self.order_id = order_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):  # noqa: D102
        return cls(match["action"], int(match["order_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await is_staff(interaction):
            await interaction.response.send_message(embed=embeds.error_embed("Staff only."), ephemeral=True)
            return

        if self.action in ("mark_paid", "mark_completed"):
            await interaction.response.defer(ephemeral=True)
            func = order_actions.mark_paid if self.action == "mark_paid" else order_actions.mark_completed
            ok, message = await func(interaction.client, self.order_id)
            await interaction.followup.send(
                embed=embeds.success_embed(message) if ok else embeds.error_embed(message), ephemeral=True
            )
            return

        action, order_id = self.action, self.order_id

        async def on_reason(inter: discord.Interaction, reason: str) -> None:
            await inter.response.defer(ephemeral=True)
            if action == "cancel":
                ok, message = await order_actions.cancel_order(inter.client, order_id, reason or None)
            else:
                ok, message = await order_actions.refund_order(inter.client, order_id, reason or None)
            await inter.followup.send(
                embed=embeds.success_embed(message) if ok else embeds.error_embed(message), ephemeral=True
            )

        title = "Cancel Order" if action == "cancel" else "Refund Order"
        await interaction.response.send_modal(ReasonModal(title, on_reason))


# ============================================================================
# SUPPORT TICKET PANEL (persistent)
# ============================================================================

class OpenTicketPanelView(discord.ui.View):
    def __init__(self, button_label: str = "Open Ticket") -> None:
        super().__init__(timeout=None)
        self.open_ticket.label = button_label[:80]

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


class ReviewStartButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"noctra:review:start:(?P<order_id>[0-9]+)",
):
    """The 'Leave a Review' button -- DMed to the customer automatically when
    staff marks their order completed (see bot.utils.order_actions). The
    order ID is encoded in the custom_id so this keeps working after a bot
    restart with no extra bookkeeping, the same trick as OrderActionButton."""

    def __init__(self, order_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Leave a Review",
                style=discord.ButtonStyle.success,
                custom_id=f"noctra:review:start:{order_id}",
            )
        )
        self.order_id = order_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):  # noqa: D102
        return cls(int(match["order_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        db = interaction.client.db  # type: ignore[attr-defined]
        order = await orders_q.get_order(db, self.order_id)
        if not order:
            await interaction.response.send_message(embed=embeds.error_embed("Order not found."), ephemeral=True)
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
        if await reviews_q.get_review_by_order(db, self.order_id):
            await interaction.response.send_message(
                embed=embeds.error_embed("You've already reviewed this order. Use `/review edit` to change it."),
                ephemeral=True,
            )
            return
        embed = embeds.info_embed(
            "Rate Your Purchase", "Choose a rating from 1 to 5, then write an optional review."
        )
        await interaction.response.send_message(embed=embed, view=RatingPromptView(self.order_id), ephemeral=True)


# ============================================================================
# PAYMENT PROOF DISAMBIGUATION (DM -- used when a customer has more than one
# order awaiting payment at once, see bot.cogs.payment_proof)
# ============================================================================

class PendingOrderSelect(discord.ui.Select):
    def __init__(self, orders: list, content: str, attachment_urls: list[str]) -> None:
        self.orders_map = {str(o["id"]): o for o in orders}
        self.content = content
        self.attachment_urls = attachment_urls
        options = [
            discord.SelectOption(
                label=f"Order #{o['id']}",
                description=f"{o['total_price']:,.2f} {o['currency_label']}",
                value=str(o["id"]),
            )
            for o in orders[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="Select which order this is about...", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        order = self.orders_map[self.values[0]]
        sent = await order_actions.forward_to_staff(
            interaction.client, order["id"], interaction.user, self.content, self.attachment_urls
        )
        if sent:
            await interaction.response.edit_message(
                embed=embeds.success_embed(f"Sent to staff for Order #{order['id']}."), view=None
            )
        else:
            await interaction.response.edit_message(
                embed=embeds.error_embed(
                    "Staff haven't set up an order-log channel yet, so this couldn't be forwarded "
                    "automatically. Please wait for staff to check your order manually."
                ),
                view=None,
            )


class PendingOrderSelectView(discord.ui.View):
    def __init__(self, orders: list, content: str, attachment_urls: list[str]) -> None:
        super().__init__(timeout=300)
        self.add_item(PendingOrderSelect(orders, content, attachment_urls))
