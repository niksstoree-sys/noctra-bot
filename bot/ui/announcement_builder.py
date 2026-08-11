"""
View builder buat command /announcement -- alur sendiri (beda dari
/panel): draft dibangun tanpa nge-post apapun dulu, baru beneran dikirim ke
channel tujuan pas tombol Kirim diklik. Klik Kirim lagi setelahnya
nge-revisi pesan yang udah terkirim (bukan kirim dobel).
"""

from __future__ import annotations

import discord

from bot.ui import embeds
from bot.ui.draft_builder_base import BaseDraftBuilderView
from bot.utils.message_draft import render_draft_layout


class AnnouncementBuilderView(BaseDraftBuilderView):
    """Sama kayak PanelBuilderView soal tombol edit draft (diwarisin dari
    BaseDraftBuilderView), tapi tombol aksinya "Kirim" bukan "Update", dan
    channel tujuannya dipilih pas /announcement dijalanin -- bukan channel
    saat ini kayak /panel."""

    def __init__(self, target_channel_id: int) -> None:
        super().__init__(timeout=1800)
        self.target_channel_id = target_channel_id
        self.sent_message_id: int | None = None

    @discord.ui.button(label="Kirim", style=discord.ButtonStyle.success, row=4)
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        channel = interaction.client.get_channel(self.target_channel_id)  # type: ignore[attr-defined]
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(embed=embeds.error_embed("Channel tujuan gak ketemu."), ephemeral=True)
            return

        layout = render_draft_layout(self.draft)

        if self.sent_message_id is None:
            # Belum pernah dikirim -- posting pesan baru.
            try:
                sent = await channel.send(view=layout)
            except discord.HTTPException as exc:
                await interaction.followup.send(embed=embeds.error_embed(f"Gagal ngirim pengumuman: {exc}"), ephemeral=True)
                return
            self.sent_message_id = sent.id
            await interaction.followup.send(
                embed=embeds.success_embed(f"Pengumuman udah dikirim ke {channel.mention}."), ephemeral=True
            )
            return

        # Udah pernah dikirim sebelumnya -- klik Kirim lagi berarti revisi,
        # bukan ngirim salinan baru.
        try:
            sent_message = await channel.fetch_message(self.sent_message_id)
            await sent_message.edit(view=layout)
        except discord.NotFound:
            try:
                sent = await channel.send(view=layout)
                self.sent_message_id = sent.id
            except discord.HTTPException as exc:
                await interaction.followup.send(embed=embeds.error_embed(f"Gagal ngirim pengumuman: {exc}"), ephemeral=True)
                return
            await interaction.followup.send(
                embed=embeds.success_embed(
                    f"Pengumuman lama udah kehapus, jadi dikirim ulang sebagai pesan baru di {channel.mention}."
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(embed=embeds.error_embed(f"Gagal revisi pengumuman: {exc}"), ephemeral=True)
            return

        await interaction.followup.send(
            embed=embeds.success_embed(f"Pengumuman di {channel.mention} udah direvisi."), ephemeral=True
        )
