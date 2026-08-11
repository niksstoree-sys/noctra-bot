"""
Model data buat draft pesan Components V2 yang dibangun interaktif lewat
/panel (panel builder) atau /announcement (announcement builder). Dua
command itu punya alur & UI kontrol sendiri-sendiri (lihat
bot.ui.panel_builder dan bot.ui.announcement_builder), tapi struktur data
draft-nya dan cara nge-render-nya jadi Components V2 sama persis, jadi
disatuin di sini biar gak duplikat.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import discord

from bot.core.theme import COLOR_PRIMARY

PLACEHOLDER_TEXT = "*(Belum ada konten -- pake tombol di bawah buat mulai nambahin.)*"


@dataclass
class TextBlock:
    content: str


@dataclass
class SeparatorBlock:
    pass


Block = TextBlock | SeparatorBlock


@dataclass
class ButtonSpec:
    label: str
    url: str


@dataclass
class MessageDraft:
    """State kerja satu pesan yang lagi dibangun. Semuanya optional/kosong
    di awal -- draft kosong dirender sebagai placeholder biar Container-nya
    gak pernah beneran kosong (Discord nolak Container tanpa isi)."""

    title: str | None = None
    description: str | None = None
    blocks: list[Block] = field(default_factory=list)  # hasil "Add Line" + "Insert separator"
    thumbnail_url: str | None = None
    banner_url: str | None = None
    color: int = COLOR_PRIMARY
    buttons: list[ButtonSpec] = field(default_factory=list)

    def copy(self) -> "MessageDraft":
        """Deep-enough copy buat snapshot undo history -- list/dataclass di
        dalemnya di-copy juga, bukan di-share reference-nya."""
        return MessageDraft(
            title=self.title,
            description=self.description,
            blocks=[
                TextBlock(b.content) if isinstance(b, TextBlock) else SeparatorBlock()
                for b in self.blocks
            ],
            thumbnail_url=self.thumbnail_url,
            banner_url=self.banner_url,
            color=self.color,
            buttons=[ButtonSpec(b.label, b.url) for b in self.buttons],
        )

    def line_count(self) -> int:
        return sum(1 for b in self.blocks if isinstance(b, TextBlock))


def _group_blocks(blocks: list[Block]) -> list[list[TextBlock]]:
    """Pecah `blocks` jadi beberapa grup teks, dipisah tiap ketemu
    SeparatorBlock -- dipake buat render maupun buat nentuin titik sisip
    separator baru."""
    groups: list[list[TextBlock]] = [[]]
    for blk in blocks:
        if isinstance(blk, SeparatorBlock):
            groups.append([])
        else:
            groups[-1].append(blk)
    return groups


def render_draft_container(draft: MessageDraft) -> discord.ui.Container:
    head_lines: list[str] = []
    if draft.title:
        head_lines.append(f"## {draft.title}")
    if draft.description:
        head_lines.append(draft.description)

    groups = _group_blocks(draft.blocks)
    children: list = []

    if head_lines:
        head_text = discord.ui.TextDisplay("\n".join(head_lines))
        if draft.thumbnail_url:
            children.append(discord.ui.Section(head_text, accessory=discord.ui.Thumbnail(media=draft.thumbnail_url)))
        else:
            children.append(head_text)
    elif draft.thumbnail_url:
        # Thumbnail doang tanpa title/description -- Section butuh minimal
        # satu TextDisplay, jadi kasih placeholder tak-terlihat (zero-width
        # space) biar strukturnya tetep valid.
        children.append(
            discord.ui.Section(discord.ui.TextDisplay("\u200b"), accessory=discord.ui.Thumbnail(media=draft.thumbnail_url))
        )

    first_group = groups[0]
    if first_group:
        children.append(discord.ui.TextDisplay("\n".join(b.content for b in first_group)))

    for group in groups[1:]:
        children.append(discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small))
        if group:
            children.append(discord.ui.TextDisplay("\n".join(b.content for b in group)))

    if draft.banner_url:
        if children:
            children.append(discord.ui.Separator(visible=False))
        children.append(discord.ui.MediaGallery(discord.MediaGalleryItem(media=draft.banner_url)))

    if not children:
        children.append(discord.ui.TextDisplay(PLACEHOLDER_TEXT))

    return discord.ui.Container(*children, accent_colour=draft.color)


def render_draft_action_row(draft: MessageDraft) -> discord.ui.ActionRow | None:
    """ActionRow berisi tombol link yang ditambahin lewat "Add Button".
    Return None kalau belum ada tombol -- caller yang mutusin mau nempelin
    ke Container atau skip sama sekali."""
    if not draft.buttons:
        return None
    row = discord.ui.ActionRow()
    for b in draft.buttons[:5]:  # ActionRow maksimal 5 komponen
        row.add_item(discord.ui.Button(label=b.label[:80], style=discord.ButtonStyle.link, url=b.url))
    return row


def render_draft_layout(draft: MessageDraft) -> discord.ui.LayoutView:
    """Bungkus draft jadi LayoutView siap kirim/edit lewat `view=...`."""

    class _DraftLayout(discord.ui.LayoutView):
        def __init__(self) -> None:
            super().__init__(timeout=None)
            container = render_draft_container(draft)
            action_row = render_draft_action_row(draft)
            if action_row is not None:
                container.add_item(action_row)
            self.add_item(container)

    return _DraftLayout()
