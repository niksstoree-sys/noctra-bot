"""
View builder buat command /announcement -- alur sendiri (beda dari
/panel): draft dibangun tanpa nge-post apapun ke channel tujuan dulu,
sambil nunjukin preview approx (embed) di panel kontrolnya sendiri. Begitu
tombol Kirim diklik sekali, pesan beneran keposting -- abis itu tiap
perubahan draft langsung live ke pesan yang udah terkirim itu, sama kayak
/panel. Klik Kirim lagi abis itu = revisi, bukan ngirim dobel.
"""

from __future__ import annotations

import discord

from bot.ui import embeds
from bot.ui.draft_builder_base import BaseDraftBuilderView
from bot.utils.message_draft import render_draft_layout, render_draft_preview_embed


class AnnouncementBuilderView(BaseDraftBuilderView):
    def __init__(self, target_channel_id: int) -> None:
        super().__init__(timeout=1800)
        self.target_channel_id = target_channel_id
        self.sent_message_id: int | None = None

    async def _after_edit(self, panel_message: discord.Message | None, client) -> None:
        # Begitu udah pernah dikirim, tiap edit lanjutan langsung live ke
        # pesan yang beneran keposting -- sama kayak PanelBuilderView.
        if self.sent_message_id is not None:
            channel = client.get_channel(self.target_channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    sent_message = await channel.fetch_message(self.sent_message_id)
                    await sent_message.edit(view=render_draft_layout(self.draft))
                except (discord.NotFound, discord.HTTPException):
                    pass

        # Sebelum (atau sesudah) dikirim, panel kontrolnya sendiri selalu
        # nunjukin preview approx (embed) -- ini yang jawab "belum ada
        # preview" waktu draft belum pernah diposting ke channel asli.
        if panel_message is None:
            return
        try:
            await panel_message.edit(embed=render_draft_preview_embed(self.draft), view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Kirim", style=discord.ButtonStyle.success, row=4)
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.defer(ephemeral=True)
        channel = interaction.client.get_channel(self.target_channel_id)  # type: ignore[attr-defined]
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(embed=embeds.error_embed("Channel tujuan gak ketemu."), ephemeral=True)
            return

        layout = render_draft_layout(self.draft)

        if self.sent_message_id is None:
            try:
                sent = await channel.send(view=layout)
            except discord.HTTPException as exc:
                await interaction.followup.send(embed=embeds.error_embed(f"Gagal ngirim pengumuman: {exc}"), ephemeral=True)
                return
            self.sent_message_id = sent.id
            await interaction.followup.send(
                embed=embeds.success_embed(
                    f"Pengumuman udah dikirim ke {channel.mention}. Perubahan berikutnya bakal langsung "
                    "live ke pesan itu."
                ),
                ephemeral=True,
            )
            return

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
