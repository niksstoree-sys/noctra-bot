"""
Shared ticket channel actions.

Centralised here (rather than in a View or Cog) so that the close button,
the /ticket slash commands, and the auto-archive background task can all
reuse the exact same logic without circular imports between bot.ui and
bot.cogs.
"""

from __future__ import annotations

import discord

from bot.core.logger import logger
from bot.database.queries import tickets as tickets_q
from bot.ui import embeds
from bot.utils.helpers import RuntimeSettings
from bot.utils.transcript import build_html_transcript


async def create_ticket_channel(
    bot,
    guild: discord.Guild,
    user: discord.abc.User,
    kind: str,
    order_id: int | None = None,
    name_hint: str | None = None,
) -> discord.TextChannel:
    db = bot.db
    runtime = RuntimeSettings(db)

    category_id = await runtime.ticket_category_id()
    category = guild.get_channel(category_id) if category_id else None
    if not isinstance(category, discord.CategoryChannel):
        category = None

    staff_role_id = await runtime.staff_role_id()

    overwrites: dict = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, attach_files=True
        ),
    }
    member = guild.get_member(user.id) if hasattr(guild, "get_member") else None
    target = member or user
    overwrites[target] = discord.PermissionOverwrite(
        view_channel=True, send_messages=True, attach_files=True, read_message_history=True
    )
    if staff_role_id:
        role = guild.get_role(staff_role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True, read_message_history=True
            )

    base_name = name_hint or f"{kind}-{getattr(user, 'name', 'user')}"
    channel_name = f"{kind}-{order_id}-{base_name}" if order_id else base_name
    channel_name = channel_name.lower().replace(" ", "-")[:90]

    channel = await guild.create_text_channel(
        channel_name,
        category=category,
        overwrites=overwrites,
        reason=f"NOCTRA ticket ({kind}) for {user}",
    )
    await tickets_q.create_ticket(db, user.id, channel.id, kind, order_id)
    logger.info("Created ticket channel #%s (%s) for %s", channel.name, kind, user)
    return channel


async def close_ticket(
    bot,
    channel: discord.TextChannel,
    closed_by_display: str,
    reason: str | None,
    auto: bool = False,
) -> None:
    db = bot.db
    runtime = RuntimeSettings(db)

    ticket = await tickets_q.get_ticket_by_channel(db, channel.id)
    status = "archived" if auto else "closed"
    await tickets_q.set_ticket_status(db, channel.id, status, reason)

    try:
        transcript_file = await build_html_transcript(channel)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to build transcript for #%s", channel.name)
        transcript_file = None

    log_channel_id = await runtime.ticket_log_channel_id()
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if isinstance(log_channel, discord.TextChannel):
            embed = embeds.ticket_closed_embed(reason, closed_by_display)
            embed.add_field(name="Channel", value=channel.mention, inline=True)
            try:
                if transcript_file:
                    transcript_file.fp.seek(0)
                await log_channel.send(
                    embed=embed,
                    file=transcript_file if transcript_file else discord.utils.MISSING,
                )
            except discord.HTTPException:
                logger.exception("Failed to post transcript to log channel.")

    closed_embed = embeds.ticket_closed_embed(reason, closed_by_display)
    if ticket:
        try:
            await channel.send(
                embed=closed_embed,
                view=_ReopenViewRef.get(),
            )
        except discord.HTTPException:
            pass

    # Lock the channel for the ticket owner; staff retains access via overwrite.
    if ticket:
        try:
            owner = channel.guild.get_member(ticket["user_id"])
            if owner:
                await channel.set_permissions(
                    owner, view_channel=True, send_messages=False, read_message_history=True
                )
        except discord.HTTPException:
            logger.exception("Failed to lock channel #%s", channel.name)

    archive_category_id = await runtime.ticket_archive_category_id()
    if auto and archive_category_id:
        archive_category = channel.guild.get_channel(archive_category_id)
        if isinstance(archive_category, discord.CategoryChannel):
            try:
                await channel.edit(category=archive_category)
            except discord.HTTPException:
                pass


async def reopen_ticket(bot, channel: discord.TextChannel, reopened_by_display: str) -> None:
    db = bot.db
    ticket = await tickets_q.get_ticket_by_channel(db, channel.id)
    if not ticket:
        return
    await tickets_q.set_ticket_status(db, channel.id, "open")
    owner = channel.guild.get_member(ticket["user_id"])
    if owner:
        try:
            await channel.set_permissions(
                owner, view_channel=True, send_messages=True, read_message_history=True
            )
        except discord.HTTPException:
            pass
    await channel.send(
        embed=embeds.info_embed("Ticket Reopened", f"Reopened by **{reopened_by_display}**.")
    )


class _ReopenViewRef:
    """Lazy holder to avoid a circular import between this module and bot.ui.views."""

    _view = None

    @classmethod
    def set(cls, view) -> None:
        cls._view = view

    @classmethod
    def get(cls):
        return cls._view
