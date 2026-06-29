"""
Modal components for NOCTRA.

Modals are used specifically where the set of inputs is only known at
runtime (the admin-configured dynamic checkout fields) or where a single
short freeform text response is needed (close/cancel/refund reasons).
Everything with a fixed, well-typed shape (categories, category types,
products,
payment methods) is handled via slash command options instead, which is the
more idiomatic discord.py pattern for structured CRUD and keeps autocomplete
available on those commands.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

from bot.database.queries.fields import MODAL_BATCH_SIZE

MULTILINE_TYPES = {"login", "custom"}


def _style_for(field_row) -> discord.TextStyle:
    if field_row["field_type"] in MULTILINE_TYPES and (field_row["max_length"] or 0) > 100:
        return discord.TextStyle.paragraph
    return discord.TextStyle.short


class DynamicFieldsModal(discord.ui.Modal):
    """One batch (max 5) of admin-defined checkout fields."""

    def __init__(
        self,
        *,
        title: str,
        fields_batch: list,
        on_submit_callback: Callable[[discord.Interaction, dict], Awaitable[None]],
    ) -> None:
        super().__init__(title=title[:45])
        self.fields_batch = fields_batch
        self._on_submit_callback = on_submit_callback
        self._inputs: dict[int, discord.ui.TextInput] = {}

        for field_row in fields_batch:
            text_input = discord.ui.TextInput(
                label=field_row["label"][:45],
                placeholder=(field_row["placeholder"] or "")[:100] or None,
                required=bool(field_row["required"]),
                min_length=max(0, field_row["min_length"] or 0),
                max_length=min(max(field_row["max_length"] or 100, 1), 4000),
                style=_style_for(field_row),
            )
            self.add_item(text_input)
            self._inputs[field_row["id"]] = text_input

    async def on_submit(self, interaction: discord.Interaction) -> None:
        values = {field_id: ti.value for field_id, ti in self._inputs.items()}
        await self._on_submit_callback(interaction, values)


async def collect_dynamic_fields(
    interaction: discord.Interaction,
    fields: list,
    on_complete: Callable[[discord.Interaction, dict], Awaitable[None]],
) -> None:
    """
    Kick off (possibly chained) modal(s) to collect values for `fields`.

    `on_complete(interaction, {field_id: value})` is awaited once every batch
    has been submitted. Discord modals cap at 5 text inputs, so fields are
    split into batches and chained: each modal submission opens the next one
    as its *initial* response (required by Discord -- you cannot defer and
    then open a modal later).
    """
    batches = [
        fields[i : i + MODAL_BATCH_SIZE] for i in range(0, len(fields), MODAL_BATCH_SIZE)
    ]
    collected: dict[int, str] = {}

    async def handle_batch(batch_index: int, inter: discord.Interaction, values: dict) -> None:
        collected.update(values)
        next_index = batch_index + 1
        if next_index < len(batches):
            modal = DynamicFieldsModal(
                title=f"Checkout Information ({next_index + 1}/{len(batches)})",
                fields_batch=batches[next_index],
                on_submit_callback=lambda i, v: handle_batch(next_index, i, v),
            )
            await inter.response.send_modal(modal)
        else:
            await on_complete(inter, collected)

    first_modal = DynamicFieldsModal(
        title=f"Checkout Information (1/{len(batches)})" if len(batches) > 1 else "Checkout Information",
        fields_batch=batches[0],
        on_submit_callback=lambda i, v: handle_batch(0, i, v),
    )
    await interaction.response.send_modal(first_modal)


class ReviewTextModal(discord.ui.Modal):
    """Final step of the button-only review flow -- the star rating is
    already chosen via buttons before this opens, so this only asks for the
    optional written part."""

    review_text = discord.ui.TextInput(
        label="Write a review (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
        placeholder="Tell others about your experience...",
    )

    def __init__(
        self,
        title: str,
        on_submit_callback: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(title=title[:45])
        self._on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_callback(interaction, str(self.review_text.value or "").strip())


class ReasonModal(discord.ui.Modal):
    """Reusable single-field modal for close/cancel/refund reasons."""

    reason = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=300,
        placeholder="Optional -- explain why",
    )

    def __init__(
        self,
        title: str,
        on_submit_callback: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(title=title[:45])
        self._on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_callback(interaction, str(self.reason.value or "").strip())


class MessageModal(discord.ui.Modal):
    """Reusable single required-field modal -- used for the order-log
    'Reply' button so staff can message a customer by DM without ever
    typing /order message."""

    message = discord.ui.TextInput(
        label="Message to customer",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
        placeholder="Type your reply here...",
    )

    def __init__(
        self,
        title: str,
        on_submit_callback: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(title=title[:45])
        self._on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_callback(interaction, str(self.message.value).strip())
