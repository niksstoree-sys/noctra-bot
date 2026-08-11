"""
Base class buat panel kontrol builder pesan Components V2 -- dipake bareng
sama PanelBuilderView (/panel) dan AnnouncementBuilderView (/announcement).

Semua tombol yang cuma NGUBAH DRAFT (Title, Description, Add Line,
Thumbnail, Banner, Color, Undo, Reset, Add Link, sisip separator, Add
Button, Manage Buttons) ada di sini -- dua-duanya sama persis butuhnya.
Yang beda cuma tombol aksi akhir (Update vs Kirim), itu didefinisiin
masing-masing di subclass-nya sendiri karena alurnya emang beda.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

from bot.ui import embeds
from bot.utils.message_draft import ButtonSpec, MessageDraft, SeparatorBlock, TextBlock

MAX_UNDO_HISTORY = 20
MAX_BUTTONS = 5


class _SingleFieldModal(discord.ui.Modal):
    """Modal satu TextInput -- dipake bareng buat Title/Description/Add
    Line/Thumbnail/Banner/Color biar gak nulis 6 class modal yang isinya
    sama persis."""

    def __init__(
        self,
        title: str,
        label: str,
        *,
        style: discord.TextStyle = discord.TextStyle.short,
        max_length: int = 256,
        default: str | None = None,
        placeholder: str | None = None,
        required: bool = True,
        on_submit_callback: Callable[[discord.Interaction, str], Awaitable[None]],
    ) -> None:
        super().__init__(title=title[:45])
        self.value_input = discord.ui.TextInput(
            label=label[:45],
            style=style,
            max_length=max_length,
            default=default,
            placeholder=placeholder,
            required=required,
        )
        self.add_item(self.value_input)
        self._on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_callback(interaction, str(self.value_input.value or "").strip())


class _TwoFieldModal(discord.ui.Modal):
    """Modal dua TextInput -- dipake buat Add Link (teks + URL) dan Add
    Button (label + URL)."""

    def __init__(
        self,
        title: str,
        label1: str,
        label2: str,
        *,
        max1: int = 100,
        max2: int = 500,
        on_submit_callback: Callable[[discord.Interaction, str, str], Awaitable[None]],
    ) -> None:
        super().__init__(title=title[:45])
        self.field1 = discord.ui.TextInput(label=label1[:45], max_length=max1)
        self.field2 = discord.ui.TextInput(label=label2[:45], max_length=max2, placeholder="https://...")
        self.add_item(self.field1)
        self.add_item(self.field2)
        self._on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_callback(
            interaction, str(self.field1.value).strip(), str(self.field2.value).strip()
        )


class ManageButtonsView(discord.ui.View):
    """Sub-view buat hapus salah satu tombol yang udah ditambahin -- pake
    Select (bukan Modal, soalnya Modal gak bisa punya Select menu)."""

    def __init__(self, builder: "BaseDraftBuilderView") -> None:
        super().__init__(timeout=300)
        self.builder = builder
        options = [
            discord.SelectOption(label=b.label[:100], description=b.url[:100], value=str(i))
            for i, b in enumerate(builder.draft.buttons)
        ]
        select = discord.ui.Select(placeholder="Pilih tombol buat dihapus...", options=options)
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        select = self.children[0]
        idx = int(select.values[0])  # type: ignore[attr-defined]
        self.builder._snapshot()
        removed = self.builder.draft.buttons.pop(idx)
        await interaction.response.edit_message(
            embed=embeds.success_embed(f"Tombol **{removed.label}** dihapus dari draft."), view=None
        )


class BaseDraftBuilderView(discord.ui.View):
    def __init__(self, *, timeout: float | None = 1800) -> None:
        super().__init__(timeout=timeout)
        self.draft = MessageDraft()
        self.undo_stack: list[MessageDraft] = []
        self._build_separator_select()

    # -- Helper -----------------------------------------------------------

    def _snapshot(self) -> None:
        self.undo_stack.append(self.draft.copy())
        if len(self.undo_stack) > MAX_UNDO_HISTORY:
            self.undo_stack.pop(0)

    def _build_separator_select(self) -> None:
        for item in list(self.children):
            if isinstance(item, discord.ui.Select):
                self.remove_item(item)
        options = []
        line_no = 0
        for blk in self.draft.blocks:
            if isinstance(blk, TextBlock):
                line_no += 1
                options.append(discord.SelectOption(label=f"Sebelum baris ke-{line_no}", value=str(line_no - 1)))
        options.append(discord.SelectOption(label="Di paling akhir", value="end"))
        select = discord.ui.Select(placeholder="Sisipin garis pemisah...", options=options[:25], row=3)
        select.callback = self._on_separator_select
        self.add_item(select)

    async def _refresh_panel(self, panel_message: discord.Message | None) -> None:
        """Push perubahan (biasanya cuma opsi Select yang baru) balik ke
        pesan panel kontrolnya sendiri -- dipanggil dari dalem modal
        on_submit, di mana `interaction.response` udah kepake buat toast
        konfirmasi, jadi gak bisa dobel dipake buat edit_message."""
        if panel_message is None:
            return
        try:
            await panel_message.edit(view=self)
        except discord.HTTPException:
            pass

    async def _on_separator_select(self, interaction: discord.Interaction) -> None:
        select = [c for c in self.children if isinstance(c, discord.ui.Select)][0]
        value = select.values[0]  # type: ignore[attr-defined]
        self._snapshot()
        if value == "end":
            self.draft.blocks.append(SeparatorBlock())
        else:
            idx_text = int(value)
            count = -1
            insert_at = len(self.draft.blocks)
            for i, blk in enumerate(self.draft.blocks):
                if isinstance(blk, TextBlock):
                    count += 1
                    if count == idx_text:
                        insert_at = i
                        break
            self.draft.blocks.insert(insert_at, SeparatorBlock())
        self._build_separator_select()
        await interaction.response.edit_message(view=self)

    # -- Title / Description / Add Line ------------------------------------

    @discord.ui.button(label="Title", style=discord.ButtonStyle.secondary, row=0)
    async def title_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        panel_message = interaction.message

        async def on_submit(inter: discord.Interaction, value: str) -> None:
            self._snapshot()
            self.draft.title = value or None
            await inter.response.send_message(
                embed=embeds.success_embed("Judul diatur." if value else "Judul dihapus."), ephemeral=True
            )
            await self._refresh_panel(panel_message)

        modal = _SingleFieldModal(
            "Atur Judul", "Judul (kosongin buat hapus)", default=self.draft.title,
            required=False, on_submit_callback=on_submit,
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Description", style=discord.ButtonStyle.secondary, row=0)
    async def description_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        panel_message = interaction.message

        async def on_submit(inter: discord.Interaction, value: str) -> None:
            self._snapshot()
            self.draft.description = value or None
            await inter.response.send_message(
                embed=embeds.success_embed("Deskripsi diatur." if value else "Deskripsi dihapus."), ephemeral=True
            )
            await self._refresh_panel(panel_message)

        modal = _SingleFieldModal(
            "Atur Deskripsi", "Deskripsi (kosongin buat hapus)", style=discord.TextStyle.paragraph,
            max_length=2000, default=self.draft.description, required=False, on_submit_callback=on_submit,
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Line", style=discord.ButtonStyle.secondary, row=0)
    async def add_line_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        panel_message = interaction.message

        async def on_submit(inter: discord.Interaction, value: str) -> None:
            if not value:
                await inter.response.send_message(embed=embeds.error_embed("Isinya gak boleh kosong."), ephemeral=True)
                return
            self._snapshot()
            self.draft.blocks.append(TextBlock(value))
            self._build_separator_select()
            await inter.response.send_message(embed=embeds.success_embed("Baris baru ditambahin."), ephemeral=True)
            await self._refresh_panel(panel_message)

        modal = _SingleFieldModal(
            "Tambah Baris", "Teks", style=discord.TextStyle.paragraph, max_length=1000,
            on_submit_callback=on_submit,
        )
        await interaction.response.send_modal(modal)

    # -- Thumbnail / Banner -------------------------------------------------

    @discord.ui.button(label="Thumbnail", style=discord.ButtonStyle.secondary, row=0)
    async def thumbnail_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        panel_message = interaction.message

        async def on_submit(inter: discord.Interaction, value: str) -> None:
            self._snapshot()
            self.draft.thumbnail_url = value or None
            await inter.response.send_message(
                embed=embeds.success_embed("Thumbnail diatur." if value else "Thumbnail dihapus."), ephemeral=True
            )
            await self._refresh_panel(panel_message)

        modal = _SingleFieldModal(
            "Atur Thumbnail", "URL gambar (kosongin buat hapus)", default=self.draft.thumbnail_url,
            required=False, placeholder="https://...", on_submit_callback=on_submit,
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Banner", style=discord.ButtonStyle.secondary, row=1)
    async def banner_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        panel_message = interaction.message

        async def on_submit(inter: discord.Interaction, value: str) -> None:
            self._snapshot()
            self.draft.banner_url = value or None
            await inter.response.send_message(
                embed=embeds.success_embed("Banner diatur." if value else "Banner dihapus."), ephemeral=True
            )
            await self._refresh_panel(panel_message)

        modal = _SingleFieldModal(
            "Atur Banner", "URL gambar banner (kosongin buat hapus)", default=self.draft.banner_url,
            required=False, placeholder="https://...", on_submit_callback=on_submit,
        )
        await interaction.response.send_modal(modal)

    # -- Color / Undo / Reset / Add Link -------------------------------------

    @discord.ui.button(label="Color", style=discord.ButtonStyle.secondary, row=2)
    async def color_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        panel_message = interaction.message

        async def on_submit(inter: discord.Interaction, value: str) -> None:
            hex_value = value.strip().lstrip("#")
            try:
                color_int = int(hex_value, 16)
                if not (0 <= color_int <= 0xFFFFFF):
                    raise ValueError
            except ValueError:
                await inter.response.send_message(
                    embed=embeds.error_embed("Format warna gak valid. Pake kode hex, misal 7C5CFF."), ephemeral=True
                )
                return
            self._snapshot()
            self.draft.color = color_int
            await inter.response.send_message(
                embed=embeds.success_embed(f"Warna diatur ke #{hex_value.upper()}."), ephemeral=True
            )
            await self._refresh_panel(panel_message)

        modal = _SingleFieldModal(
            "Atur Warna", "Kode warna hex (tanpa #)", max_length=6, placeholder="7C5CFF",
            default=f"{self.draft.color:06X}", on_submit_callback=on_submit,
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Undo", style=discord.ButtonStyle.secondary, row=2)
    async def undo_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.undo_stack:
            await interaction.response.send_message(embed=embeds.error_embed("Gak ada history buat di-undo."), ephemeral=True)
            return
        self.draft = self.undo_stack.pop()
        self._build_separator_select()
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(embed=embeds.success_embed("Draft di-undo ke versi sebelumnya."), ephemeral=True)

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.danger, row=2)
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self._snapshot()
        self.draft = MessageDraft()
        self._build_separator_select()
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            embed=embeds.success_embed("Draft direset. Kepencet gak sengaja? Tinggal klik Undo."), ephemeral=True
        )

    @discord.ui.button(label="Add Link", style=discord.ButtonStyle.secondary, row=2)
    async def add_link_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        panel_message = interaction.message

        async def on_submit(inter: discord.Interaction, text: str, url: str) -> None:
            if not url.startswith(("http://", "https://")):
                await inter.response.send_message(
                    embed=embeds.error_embed("URL harus mulai dari http:// atau https://"), ephemeral=True
                )
                return
            self._snapshot()
            self.draft.blocks.append(TextBlock(f"[{text or url}]({url})"))
            self._build_separator_select()
            await inter.response.send_message(embed=embeds.success_embed("Link ditambahin sebagai baris teks."), ephemeral=True)
            await self._refresh_panel(panel_message)

        modal = _TwoFieldModal("Tambah Link", "Teks yang ditampilin", "URL", on_submit_callback=on_submit)
        await interaction.response.send_modal(modal)

    # -- Add Button / Manage Buttons ----------------------------------------

    @discord.ui.button(label="Add Button", style=discord.ButtonStyle.secondary, row=4)
    async def add_button_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if len(self.draft.buttons) >= MAX_BUTTONS:
            await interaction.response.send_message(
                embed=embeds.error_embed(f"Maksimal {MAX_BUTTONS} tombol per pesan."), ephemeral=True
            )
            return
        panel_message = interaction.message

        async def on_submit(inter: discord.Interaction, label: str, url: str) -> None:
            if not url.startswith(("http://", "https://")):
                await inter.response.send_message(
                    embed=embeds.error_embed("URL harus mulai dari http:// atau https://"), ephemeral=True
                )
                return
            self._snapshot()
            self.draft.buttons.append(ButtonSpec(label or "Klik di sini", url))
            await inter.response.send_message(embed=embeds.success_embed(f"Tombol **{label}** ditambahin."), ephemeral=True)
            await self._refresh_panel(panel_message)

        modal = _TwoFieldModal("Tambah Tombol", "Label tombol", "URL", max1=80, on_submit_callback=on_submit)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Manage Buttons", style=discord.ButtonStyle.secondary, row=4)
    async def manage_buttons_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.draft.buttons:
            await interaction.response.send_message(
                embed=embeds.info_embed("Kelola Tombol", "Belum ada tombol yang ditambahin."), ephemeral=True
            )
            return
        view = ManageButtonsView(self)
        await interaction.response.send_message(
            embed=embeds.info_embed("Kelola Tombol", "Pilih tombol yang mau dihapus."), view=view, ephemeral=True
        )
