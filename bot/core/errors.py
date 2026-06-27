"""Global error handling for slash commands.

Centralising this avoids duplicated try/except blocks across every cog and
guarantees the user always gets a clean embed response instead of a silent
failure or a raw traceback, while full details still get logged server-side.
"""

from __future__ import annotations

import discord
from discord import app_commands

from bot.core.logger import logger
from bot.ui.embeds import error_embed


def setup_error_handler(bot) -> None:
    tree = bot.tree

    async def on_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CheckFailure):
            message = str(error) or "You don't have permission to use this command."
        elif isinstance(error, app_commands.CommandOnCooldown):
            message = f"This command is on cooldown. Try again in {error.retry_after:.1f}s."
        elif isinstance(error, app_commands.TransformerError):
            message = "One of the values you provided was invalid."
        else:
            logger.exception("Unhandled app command error", exc_info=error)
            message = "Something went wrong while running that command. Staff has been notified."

        embed = error_embed(message)
        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            logger.exception("Failed to deliver error message to user.")

    tree.on_error = on_error
