"""The NOCTRA bot client: wires together the database, cogs, persistent
views, and command tree sync.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.config import config
from bot.core.errors import setup_error_handler
from bot.core.logger import logger
from bot.database.core import Database

EXTENSIONS = (
    "bot.cogs.category",
    "bot.cogs.product",
    "bot.cogs.variant",
    "bot.cogs.payment",
    "bot.cogs.settings",
    "bot.cogs.shop",
    "bot.cogs.order",
    "bot.cogs.ticket",
    "bot.cogs.review",
    "bot.cogs.tasks",
)


class NoctraBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True  # needed to reliably manage ticket channel permissions
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.db = Database(config.database_path)

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.db.init_schema()

        for extension in EXTENSIONS:
            try:
                await self.load_extension(extension)
                logger.info("Loaded extension: %s", extension)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to load extension: %s", extension)

        self._register_persistent_views()
        setup_error_handler(self)

        if config.guild_id:
            guild = discord.Object(id=config.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %d commands to guild %s.", len(synced), config.guild_id)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d global commands.", len(synced))

    def _register_persistent_views(self) -> None:
        # Imported lazily to avoid import-order issues with bot.db being used
        # inside view callbacks before the cog package is fully loaded.
        from bot.ui.views import OpenTicketPanelView, TicketControlView, TicketReopenView

        self.add_view(TicketControlView())
        self.add_view(TicketReopenView())
        self.add_view(OpenTicketPanelView())
        logger.info("Persistent views registered.")

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id if self.user else "?")
        logger.info("NOCTRA is online across %d guild(s).", len(self.guilds))

    async def close(self) -> None:
        await self.db.close()
        await super().close()
