"""User & admin commands: /review"""

from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.database.queries import orders as orders_q
from bot.database.queries import products as products_q
from bot.database.queries import reviews as reviews_q
from bot.ui import embeds
from bot.utils import review_actions
from bot.utils.autocomplete import product_autocomplete
from bot.utils.permissions import staff_only

Rating = Literal[1, 2, 3, 4, 5]


async def _unreviewed_order_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    rows = await orders_q.list_completed_unreviewed(db, interaction.user.id)
    choices = []
    for r in rows[:25]:
        product = await products_q.get_product(db, r["product_id"])
        name = product["name"] if product else "Unknown product"
        choices.append(app_commands.Choice(name=f"#{r['id']} -- {name}", value=r["id"]))
    return choices


async def _my_reviewed_order_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    rows = await reviews_q.list_reviews_for_user(db, interaction.user.id)
    choices = []
    for r in rows[:25]:
        product = await products_q.get_product(db, r["product_id"])
        name = product["name"] if product else "Unknown product"
        choices.append(app_commands.Choice(name=f"#{r['order_id']} -- {name}", value=r["order_id"]))
    return choices


async def _pending_review_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[int]]:
    db = interaction.client.db  # type: ignore[attr-defined]
    rows = await reviews_q.list_pending_reviews(db, limit=25)
    choices = []
    for r in rows:
        product = await products_q.get_product(db, r["product_id"])
        name = product["name"] if product else "Unknown product"
        choices.append(app_commands.Choice(name=f"#{r['id']} -- {name} ({r['rating']}/5)", value=r["id"]))
    return choices


class ReviewCog(commands.Cog):
    """Customer reviews tied to completed, paid orders -- pending admin approval."""

    review_group = app_commands.Group(name="review", description="Manage product reviews.", guild_only=True)
    admin_group = app_commands.Group(
        name="admin", description="Moderate reviews.", parent=review_group
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _eligible_order(self, order_id: int, user_id: int):
        order = await orders_q.get_order(self.bot.db, order_id)
        if not order or order["user_id"] != user_id:
            return None
        if order["status"] != "completed" or order["payment_status"] != "paid":
            return None
        return order

    @review_group.command(name="submit", description="Submit a review for a completed order.")
    @app_commands.describe(
        order="A completed, paid order of yours that hasn't been reviewed yet",
        rating="Rating from 1 to 5",
        review="Your review text",
        anonymous="Hide your name on the review",
    )
    @app_commands.autocomplete(order=_unreviewed_order_autocomplete)
    async def submit(
        self,
        interaction: discord.Interaction,
        order: int,
        rating: Rating,
        review: str | None = None,
        anonymous: bool = False,
    ) -> None:
        order_row = await self._eligible_order(order, interaction.user.id)
        if not order_row:
            await interaction.response.send_message(
                embed=embeds.error_embed(
                    "That order isn't eligible for a review. It must belong to you, be **paid**, "
                    "and marked **completed** by staff."
                ),
                ephemeral=True,
            )
            return
        existing = await reviews_q.get_review_by_order(self.bot.db, order)
        if existing:
            await interaction.response.send_message(
                embed=embeds.error_embed("You've already reviewed this order. Use `/review edit` instead."),
                ephemeral=True,
            )
            return
        review_id = await reviews_q.create_review(
            self.bot.db, order, order_row["product_id"], interaction.user.id, rating, review, anonymous
        )
        await interaction.response.send_message(
            embed=embeds.success_embed(
                "Thank you! Your review has been submitted and is awaiting staff approval."
            ),
            ephemeral=True,
        )
        await review_actions.notify_staff_new_review(self.bot, review_id)

    @review_group.command(name="edit", description="Edit your existing review.")
    @app_commands.describe(order="Order whose review you want to edit", rating="New rating", review="New review text", anonymous="Hide your name")
    @app_commands.autocomplete(order=_my_reviewed_order_autocomplete)
    async def edit(
        self,
        interaction: discord.Interaction,
        order: int,
        rating: Rating | None = None,
        review: str | None = None,
        anonymous: bool | None = None,
    ) -> None:
        existing = await reviews_q.get_review_by_order(self.bot.db, order)
        if not existing or existing["user_id"] != interaction.user.id:
            await interaction.response.send_message(embed=embeds.error_embed("Review not found."), ephemeral=True)
            return
        updates: dict = {"status": "pending"}
        if rating is not None:
            updates["rating"] = rating
        if review is not None:
            updates["review_text"] = review
        if anonymous is not None:
            updates["anonymous"] = int(anonymous)
        await reviews_q.update_review(self.bot.db, existing["id"], **updates)
        await interaction.response.send_message(
            embed=embeds.success_embed("Review updated and resubmitted for approval."), ephemeral=True
        )
        await review_actions.notify_staff_new_review(self.bot, existing["id"])

    @review_group.command(name="delete", description="Delete your review.")
    @app_commands.describe(order="Order whose review you want to delete")
    @app_commands.autocomplete(order=_my_reviewed_order_autocomplete)
    async def delete(self, interaction: discord.Interaction, order: int) -> None:
        existing = await reviews_q.get_review_by_order(self.bot.db, order)
        if not existing or existing["user_id"] != interaction.user.id:
            await interaction.response.send_message(embed=embeds.error_embed("Review not found."), ephemeral=True)
            return
        await reviews_q.delete_review(self.bot.db, existing["id"])
        await interaction.response.send_message(embed=embeds.success_embed("Review deleted."), ephemeral=True)

    @review_group.command(name="list", description="View approved reviews and rating summary for a product.")
    @app_commands.describe(product="Product to view reviews for")
    @app_commands.autocomplete(product=product_autocomplete)
    async def list_reviews(self, interaction: discord.Interaction, product: int) -> None:
        product_row = await products_q.get_product(self.bot.db, product)
        if not product_row:
            await interaction.response.send_message(embed=embeds.error_embed("Product not found."), ephemeral=True)
            return
        summary = await reviews_q.get_rating_summary(self.bot.db, product)
        recent = await reviews_q.list_reviews_for_product(self.bot.db, product, status="approved", limit=5)

        embed = embeds.rating_distribution_embed(product_row, summary)
        for r in recent:
            author = "Anonymous" if r["anonymous"] else f"<@{r['user_id']}>"
            text = r["review_text"] or "*(no written review)*"
            embed.add_field(
                name=f"{r['rating']}/5 -- {author} -- Verified Purchase",
                value=text[:200],
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -- Admin moderation -----------------------------------------------------

    @admin_group.command(name="approve", description="Approve a pending review, making it publicly visible.")
    @app_commands.describe(review_id="Pending review to approve")
    @app_commands.autocomplete(review_id=_pending_review_autocomplete)
    @staff_only()
    async def approve(self, interaction: discord.Interaction, review_id: int) -> None:
        await reviews_q.set_review_status(self.bot.db, review_id, "approved")
        await interaction.response.send_message(embed=embeds.success_embed("Review approved."), ephemeral=True)

    @admin_group.command(name="reject", description="Reject a pending review.")
    @app_commands.describe(review_id="Pending review to reject")
    @app_commands.autocomplete(review_id=_pending_review_autocomplete)
    @staff_only()
    async def reject(self, interaction: discord.Interaction, review_id: int) -> None:
        await reviews_q.set_review_status(self.bot.db, review_id, "rejected")
        await interaction.response.send_message(embed=embeds.success_embed("Review rejected."), ephemeral=True)

    @admin_group.command(name="hide", description="Hide a previously approved review.")
    @app_commands.describe(review_id="Review to hide")
    @staff_only()
    async def hide(self, interaction: discord.Interaction, review_id: int) -> None:
        await reviews_q.set_review_status(self.bot.db, review_id, "hidden")
        await interaction.response.send_message(embed=embeds.success_embed("Review hidden."), ephemeral=True)

    @admin_group.command(name="delete", description="Permanently delete a review.")
    @app_commands.describe(review_id="Review to delete")
    @staff_only()
    async def admin_delete(self, interaction: discord.Interaction, review_id: int) -> None:
        await reviews_q.delete_review(self.bot.db, review_id)
        await interaction.response.send_message(embed=embeds.success_embed("Review deleted."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReviewCog(bot))
