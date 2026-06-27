"""
Staff permission checks.

"Staff" means: Discord Administrator permission, OR holding the role
configured via /settings (falls back to STAFF_ROLE_ID in .env).
"""

from __future__ import annotations

import discord
from discord import app_commands

from bot.utils.helpers import RuntimeSettings


async def is_staff(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        return False
    if interaction.user.guild_permissions.administrator:
        return True

    db = interaction.client.db  # type: ignore[attr-defined]
    runtime = RuntimeSettings(db)
    staff_role_id = await runtime.staff_role_id()
    if staff_role_id is None:
        return False
    return any(role.id == staff_role_id for role in interaction.user.roles)


def staff_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        ok = await is_staff(interaction)
        if not ok:
            raise app_commands.CheckFailure(
                "You need staff permissions to use this command."
            )
        return True

    return app_commands.check(predicate)
