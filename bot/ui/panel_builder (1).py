"""
View builder buat command /panel -- edit pesan Components V2 custom di
channel yang sama, live lewat panel kontrol ephemeral.
"""

from __future__ import annotations

import discord

from bot.ui import embeds
from bot.ui.draft_builder_base import BaseDraftBuilderView
from bot.utils.message_draft import render_draft_layout


class PanelBuilderView(BaseDraftBuilderView):
    """Semua tombol edit draft (Title/Description/dst) diwarisin dari
    BaseDraftBuilderView -- di sini cuma nambahin tombol Update, yang
    nge-apply draft ke pesan target (`target_message_id`) di channel yang
    sama tempat /panel dijalanin."""

    def __init__(self, target_channel_id: int, target_message_id: int) -> None:
        super().__init__(timeout=1800)
        self.target_channel_id = target_channel_id
        self.target_message_id = target_message_id

    @discord.ui.button(label="Update", style=discord.ButtonStyle.success, row=4)
    async def update_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        channel = interaction.client.get_channel(self.target_channel_id)  # type: ignore[attr-defined]
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(embed=embeds.error_embed("Channel target gak ketemu."), ephemeral=True)
            return
        try:
            target_message = await channel.fetch_message(self.target_message_id)
        except discord.NotFound:
            await interaction.followup.send(
                embed=embeds.error_embed("Pesan target udah kehapus -- jalanin `/panel` lagi buat mulai baru."),
                ephemeral=True,
            )
            return

        layout = render_draft_layout(self.draft)
        try:
            await target_message.edit(view=layout)
        except discord.HTTPException as exc:
            await interaction.followup.send(embed=embeds.error_embed(f"Gagal update pesan: {exc}"), ephemeral=True)
            return

        await interaction.followup.send(
            embed=embeds.success_embed(f"Berhasil update pesan di {channel.mention}."), ephemeral=True
        )
