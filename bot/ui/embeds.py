"""
Embed builders buat NOCTRA.

Semua embed lewat `base_embed()` biar branding (footer, warna default)
tetep konsisten. Fungsi-fungsi di sini nerima row/value biasa (bukan objek
ORM) biar module ini gak nempel ke database layer.
"""

from __future__ import annotations

from datetime import datetime

import discord

from bot.core.emojis import EMOJI_ERROR, EMOJI_INFO, EMOJI_SUCCESS
from bot.core.theme import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_MUTED,
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    COLOR_WARNING,
    FOOTER_TEXT,
    MARK_BULLET,
    MARK_DASH,
    STATUS_COLORS,
    rating_bar,
)
from bot.utils.helpers import calculate_final_price, discount_label, format_price


def base_embed(
    title: str,
    description: str | None = None,
    color: int = COLOR_PRIMARY,
    thumbnail_url: str | None = None,
    image_url: str | None = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER_TEXT)
    embed.timestamp = datetime.utcnow()
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    if image_url:
        embed.set_image(url=image_url)
    return embed


def error_embed(message: str) -> discord.Embed:
    return base_embed(f"{EMOJI_ERROR} Yah, Gagal", message, color=COLOR_DANGER)


def success_embed(message: str) -> discord.Embed:
    return base_embed(f"{EMOJI_SUCCESS} Berhasil", message, color=COLOR_SUCCESS)


def info_embed(title: str, message: str, image_url: str | None = None) -> discord.Embed:
    return base_embed(f"{EMOJI_INFO} {title}", message, color=COLOR_ACCENT, image_url=image_url)


# -- Katalog -----------------------------------------------------------------

def category_list_embed(categories: list) -> discord.Embed:
    embed = base_embed("NOCTRA -- Kategori", color=COLOR_PRIMARY)
    if not categories:
        embed.description = "Belum ada kategori yang dibuat nih."
        return embed
    lines = []
    for cat in categories:
        state = "aktif" if cat["enabled"] else "nonaktif"
        emoji_prefix = f"{cat['emoji']} " if cat["emoji"] else ""
        lines.append(
            f"{MARK_BULLET} {emoji_prefix}**#{cat['id']} -- {cat['name']}** "
            f"{MARK_DASH} posisi {cat['position']} {MARK_DASH} {state}"
        )
        if cat["description"]:
            lines.append(f"    {cat['description']}")
    embed.description = "\n".join(lines)
    return embed


def category_type_list_embed(category_types: list) -> discord.Embed:
    embed = base_embed("NOCTRA -- Tipe Kategori", color=COLOR_PRIMARY)
    if not category_types:
        embed.description = "Belum ada tipe kategori yang dibuat nih."
        return embed
    lines = []
    for ct in category_types:
        state = "aktif" if ct["enabled"] else "nonaktif"
        emoji_prefix = f"{ct['emoji']} " if ct["emoji"] else ""
        lines.append(
            f"{MARK_BULLET} {emoji_prefix}**#{ct['id']} -- {ct['name']}** "
            f"{MARK_DASH} kategori #{ct['category_id']} {MARK_DASH} posisi {ct['position']} {MARK_DASH} {state}"
        )
        if ct["description"]:
            lines.append(f"    {ct['description']}")
    embed.description = "\n".join(lines)
    return embed


def product_summary_line(product, rating_summary: dict | None = None) -> str:
    final = calculate_final_price(
        product["base_price"], product["discount_type"], product["discount_value"]
    )
    price_text = format_price(final, product["currency_label"])
    dlabel = discount_label(product["discount_type"], product["discount_value"])
    if dlabel:
        price_text += f" ({dlabel}, awalnya {format_price(product['base_price'], product['currency_label'])})"
    rating_text = ""
    if rating_summary and rating_summary["total"]:
        rating_text = f" {MARK_DASH} {rating_summary['average']:.1f}/5 ({rating_summary['total']} ulasan)"
    visibility = "" if product["visible"] else " [disembunyikan]"
    emoji_prefix = f"{product['emoji']} " if product["emoji"] else ""
    return f"{MARK_BULLET} {emoji_prefix}**{product['name']}**{visibility} {MARK_DASH} {price_text}{rating_text}"


def product_list_embed(category_type, products: list) -> discord.Embed:
    if category_type:
        emoji_prefix = f"{category_type['emoji']} " if category_type["emoji"] else ""
        title = f"NOCTRA -- {emoji_prefix}{category_type['name']}"
    else:
        title = "NOCTRA -- Produk"
    embed = base_embed(title, color=COLOR_PRIMARY)
    if not products:
        embed.description = "Belum ada produk di tipe kategori ini."
        return embed
    embed.description = "\n".join(product_summary_line(p) for p in products)
    return embed


def product_detail_embed(product, fields: list, rating_summary: dict) -> discord.Embed:
    final = calculate_final_price(
        product["base_price"], product["discount_type"], product["discount_value"]
    )
    price_text = format_price(final, product["currency_label"])
    dlabel = discount_label(product["discount_type"], product["discount_value"])

    title = f"{product['emoji']} {product['name']}" if product["emoji"] else product["name"]
    embed = base_embed(
        title,
        product["description"] or "Belum ada deskripsi.",
        color=COLOR_PRIMARY,
        thumbnail_url=product["image_url"] or None,
    )

    price_line = f"**{price_text}**"
    if dlabel:
        price_line += f"  {MARK_DASH}  {dlabel} (awalnya {format_price(product['base_price'], product['currency_label'])})"
    embed.add_field(name="Harga", value=price_line, inline=True)

    type_label = product["product_type"].replace("_", " ").title()
    embed.add_field(name="Tipe", value=type_label, inline=True)

    if product["stock_type"] == "unlimited":
        stock_text = "Unlimited"
    else:
        stock_text = f"Sisa {product['stock_quantity']}"
    embed.add_field(name="Stok", value=stock_text, inline=True)

    if fields:
        req = [f["label"] for f in fields if f["required"]]
        opt = [f["label"] for f in fields if not f["required"]]
        field_text = ""
        if req:
            field_text += "Wajib diisi: " + ", ".join(req)
        if opt:
            field_text += ("\n" if field_text else "") + "Opsional: " + ", ".join(opt)
        embed.add_field(name="Data yang Dibutuhin Pas Checkout", value=field_text, inline=False)

    if rating_summary["total"]:
        bar = rating_bar(rating_summary["average"])
        embed.add_field(
            name="Rating",
            value=f"{rating_summary['average']:.1f}/5 {MARK_DASH} {bar} {MARK_DASH} {rating_summary['total']} ulasan",
            inline=False,
        )
    else:
        embed.add_field(name="Rating", value="Belum ada ulasan nih.", inline=False)

    return embed


# -- Order / Ticket -----------------------------------------------------------

def order_summary_embed(
    order_row,
    product_row,
    payment_row,
    field_values: list | None = None,
) -> discord.Embed:
    status = order_row["status"]
    color = STATUS_COLORS.get(status, COLOR_PRIMARY)
    embed = base_embed(f"Order #{order_row['id']}", color=color)

    embed.add_field(name="Produk", value=product_row["name"], inline=True)
    embed.add_field(
        name="Harga",
        value=format_price(order_row["total_price"], order_row["currency_label"]),
        inline=True,
    )
    embed.add_field(name="Status", value=status.title(), inline=True)
    embed.add_field(
        name="Pembayaran", value=order_row["payment_status"].title(), inline=True
    )
    if payment_row:
        embed.add_field(name="Metode Bayar", value=payment_row["name"], inline=True)
    embed.add_field(
        name="Dipesan",
        value=f"<t:{int(datetime.fromisoformat(order_row['created_at']).timestamp())}:R>",
        inline=True,
    )

    if field_values:
        lines = []
        for fv in field_values:
            value = fv["value"]
            if fv["field_type"] == "password" and value:
                value = "*" * min(len(value), 12)
            lines.append(f"{MARK_BULLET} **{fv['label']}:** {value}")
        embed.add_field(name="Data yang Kamu Kirim", value="\n".join(lines), inline=False)

    return embed


def order_invoice_embed(
    order_row,
    product_row,
    payment_row,
    bot_avatar_url: str | None = None,
) -> discord.Embed:
    """Struk bersih yang dikirim begitu order ditandain selesai -- beda sama
    order_summary_embed (yang cuma kartu kerja checkout-in-progress dan bakal
    dibersihin belakangan). Ini didesain buat nempel permanen di DM customer
    sebagai bukti pembelian mereka.

    `bot_avatar_url` diambil langsung dari foto profil bot -- jadi kalau
    icon bot lu ganti, struk ini otomatis ikut ganti juga tanpa perlu
    setting manual."""
    invoice_number = f"NOCTRA-{order_row['id']:06d}"
    completed_ts = int(datetime.utcnow().timestamp())

    embed = base_embed(
        f"{EMOJI_SUCCESS} Invoice {invoice_number}",
        "Makasih udah belanja -- ini struk pembelian kamu.",
        color=COLOR_SUCCESS,
        thumbnail_url=bot_avatar_url,
    )
    embed.add_field(name="Barang", value=product_row["name"], inline=False)
    embed.add_field(
        name="Total Bayar",
        value=f"**{format_price(order_row['total_price'], order_row['currency_label'])}**",
        inline=True,
    )
    if payment_row:
        embed.add_field(name="Metode Bayar", value=payment_row["name"], inline=True)
    embed.add_field(name="Order ID", value=f"#{order_row['id']}", inline=True)
    embed.add_field(name="Selesai", value=f"<t:{completed_ts}:f>", inline=True)
    embed.set_footer(text=f"{FOOTER_TEXT}  {MARK_DASH}  Simpan ini buat catatan kamu ya")
    return embed


def purchase_announcement_embed(
    buyer_display: str,
    buyer_avatar_url: str | None,
    product_row,
    category_type_row,
    order_row,
) -> discord.Embed:
    """Kartu publik "Si X baru aja beli Y" yang diposting ke channel
    purchase-feed begitu order ditandain selesai. Gaya visualnya sama kayak
    review_card_embed -- author tag kecil plus thumbnail gede dari avatar
    yang sama, soalnya icon author yang kecil suka gak keliatan."""
    price_text = format_price(order_row["total_price"], order_row["currency_label"])
    type_label = product_row["product_type"].replace("_", " ").title()

    embed = base_embed(
        f"{EMOJI_SUCCESS} Pembelian Baru",
        f"**{buyer_display}** baru aja beli **{product_row['name']}**!",
        color=COLOR_SUCCESS,
        thumbnail_url=buyer_avatar_url,
        image_url=product_row["image_url"] or None,
    )
    embed.set_author(name=buyer_display, icon_url=buyer_avatar_url or None)

    embed.add_field(name="Produk", value=product_row["name"], inline=True)
    if category_type_row:
        cat_emoji = f"{category_type_row['emoji']} " if category_type_row["emoji"] else ""
        embed.add_field(name="Kategori", value=f"{cat_emoji}{category_type_row['name']}", inline=True)
    embed.add_field(name="Tipe", value=type_label, inline=True)
    embed.add_field(name="Harga", value=f"**{price_text}**", inline=True)

    return embed


def ticket_welcome_embed(order_summary_text: str | None = None) -> discord.Embed:
    description = (
        "Makasih udah buka ticket. Staff kita bakal bantuin kamu sebentar lagi.\n\n"
        "Tetep di channel ini ya, dan kasih info tambahan kalau diminta staff."
    )
    if order_summary_text:
        description = order_summary_text + "\n\n" + description
    return base_embed("NOCTRA -- Support Ticket", description, color=COLOR_ACCENT)


def ticket_closed_embed(close_reason: str | None, closed_by: str) -> discord.Embed:
    description = f"Ticket ini ditutup sama **{closed_by}**."
    if close_reason:
        description += f"\n\n**Alasan:** {close_reason}"
    return base_embed("Ticket Ditutup", description, color=COLOR_MUTED)


# -- Review ---------------------------------------------------------------------

def star_rating(rating: int, scale: int = 5) -> str:
    """Baris bintang emoji buat rating 0-5, misal 4/5 -> 4 bintang penuh + 1 kosong."""
    rating = max(0, min(scale, rating))
    return "\u2b50" * rating + "\u2606" * (scale - rating)


def review_card_embed(
    review_row,
    product_row,
    author_display: str,
    author_avatar_url: str | None = None,
    bot_avatar_url: str | None = None,
    verified: bool = True,
) -> discord.Embed:
    # Slot banner di bawah dipakai gantian: foto review dari customer
    # diutamain kalau ada, baru fallback ke avatar bot -- gak pernah
    # ditumpuk dua-duanya biar tetep rapi.
    banner_url = review_row["image_url"] or bot_avatar_url

    # Selalu ungu brand di sini -- ini kartu showcase publik, bukan
    # indikator status, jadi gak perlu ikutan ganti warna hijau/merah
    # kayak embed admin internal berdasarkan approved/rejected/hidden.
    embed = base_embed(
        product_row["name"],
        color=COLOR_PRIMARY,
        image_url=banner_url,
        # Icon author doang kecil banget (cuma lingkaran mini di samping
        # nama) -- pasang avatar yang sama di thumbnail bikin versi lebih
        # gede & jelas muncul di pojok kanan atas embed, yang kalau enggak
        # bakal kosong aja di situ.
        thumbnail_url=author_avatar_url,
    )
    embed.set_author(name=author_display, icon_url=author_avatar_url or None)
    embed.add_field(
        name="Rating", value=f"{star_rating(review_row['rating'])}  ({review_row['rating']}/5)", inline=False
    )
    if review_row["review_text"]:
        embed.add_field(name="Ulasan", value=review_row["review_text"], inline=False)
    badge = "Pembelian Terverifikasi" if verified else "Belum Terverifikasi"
    embed.add_field(name="Pembelian", value=badge, inline=True)
    embed.add_field(name="Status", value=review_row["status"].title(), inline=True)
    return embed


def rating_distribution_embed(product_row, summary: dict) -> discord.Embed:
    embed = base_embed(f"{product_row['name']} -- Rating", color=COLOR_PRIMARY)
    if not summary["total"]:
        embed.description = "Belum ada ulasan yang di-approve nih."
        return embed
    embed.description = f"**{summary['average']:.1f}/5** dari {summary['total']} ulasan"
    lines = []
    for star in (5, 4, 3, 2, 1):
        count = summary["distribution"].get(star, 0)
        ratio = count / summary["total"] if summary["total"] else 0
        bar_len = round(ratio * 12)
        lines.append(f"{star} {MARK_DASH} {'█' * bar_len}{'░' * (12 - bar_len)} ({count})")
    embed.add_field(name="Distribusi", value="\n".join(lines), inline=False)
    return embed


# -- Settings / List Admin ------------------------------------------------------

def settings_embed(values: dict) -> discord.Embed:
    embed = base_embed("NOCTRA -- Pengaturan", color=COLOR_PRIMARY)
    for key, value in values.items():
        label = key.replace("_", " ").title()
        embed.add_field(name=label, value=str(value) if value is not None else "Belum diatur", inline=True)
    return embed


def payment_list_embed(payments: list) -> discord.Embed:
    embed = base_embed("NOCTRA -- Metode Pembayaran", color=COLOR_PRIMARY)
    if not payments:
        embed.description = "Belum ada metode pembayaran yang diatur nih."
        return embed
    lines = []
    for p in payments:
        state = "aktif" if p["enabled"] else "nonaktif"
        has_image = "ada gambar" if p["image_url"] else "belum ada gambar"
        lines.append(
            f"{MARK_BULLET} **#{p['id']} -- {p['name']}** {MARK_DASH} {state} "
            f"{MARK_DASH} timeout {p['timeout_minutes']}m {MARK_DASH} {has_image}"
        )
    embed.description = "\n".join(lines)
    return embed
