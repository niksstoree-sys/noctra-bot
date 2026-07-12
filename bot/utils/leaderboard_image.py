"""
NOCTRA leaderboard image generator -- Pillow only, no emoji (they require
a full emoji font that isn't available on Railway), medals are drawn as
coloured circles with a rank number inside.

Canvas: 1200 x dynamic height so Discord renders it at a reasonable size
without the user having to zoom in.
"""

from __future__ import annotations

import math
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

# ── Palette ─────────────────────────────────────────────────────────────────
BG_TOP       = (8,  5, 20)
BG_BOT       = (18, 10, 40)
CARD_BG      = (24, 15, 50)
CARD_BG_TOP3 = (30, 18, 62)
ACCENT       = (124, 92, 255)
GOLD         = (255, 195, 55)
SILVER       = (185, 195, 210)
BRONZE       = (200, 120, 45)
WHITE        = (255, 255, 255)
OFF_WHITE    = (220, 215, 240)
MUTED        = (140, 128, 178)
BAR_BG       = (40, 26, 72)
MEDAL_CLR    = [GOLD, SILVER, BRONZE]

# ── Layout ──────────────────────────────────────────────────────────────────
IMG_W        = 1200
HEADER_H     = 130
ROW_H        = 100
ROW_GAP      = 10
PAD          = 48
BOTTOM       = 44
RADIUS       = 16          # card corner radius
BAR_H        = 12
BAR_W        = 420         # max bar width
AVATAR_D     = 64          # avatar diameter
BADGE_D      = 52          # medal badge diameter

# ── Fonts ────────────────────────────────────────────────────────────────────
_BOLD    = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_REG     = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _f(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _tw(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    return int(draw.textlength(text, font=font))


def _gradient(w: int, h: int) -> Image.Image:
    img  = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r = int(BG_TOP[0] * (1 - t) + BG_BOT[0] * t)
        g = int(BG_TOP[1] * (1 - t) + BG_BOT[1] * t)
        b = int(BG_TOP[2] * (1 - t) + BG_BOT[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _glow_overlay(w: int, h: int) -> Image.Image:
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)
    spots = [
        (int(w * 0.85), int(h * 0.08), 320, 30),
        (int(w * 0.12), int(h * 0.72), 260, 22),
        (int(w * 0.50), int(h * 0.45), 200, 12),
    ]
    for cx, cy, cr, alpha in spots:
        for r in range(cr, 0, -5):
            a = int(alpha * (r / cr) ** 2.2)
            d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*ACCENT, a))
    return layer


def _draw_medal(img: Image.Image, cx: int, cy: int, rank: int) -> None:
    """Draw a coloured circle badge with the rank number inside."""
    draw   = ImageDraw.Draw(img)
    r      = BADGE_D // 2
    colour = MEDAL_CLR[rank] if rank < 3 else MUTED
    # shadow
    draw.ellipse([cx-r+2, cy-r+2, cx+r+2, cy+r+2], fill=(0, 0, 0, 80) if False else (10, 5, 25))
    # fill
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=colour)
    # inner highlight ring
    inner_c = tuple(min(255, int(c * 1.35)) for c in colour)
    draw.ellipse([cx-r+3, cy-r+3, cx+r-3, cy+r-3],
                 outline=inner_c, width=2)
    # rank text
    f   = _f(_BOLD, 20 if rank < 9 else 16)
    txt = str(rank + 1)
    tw  = _tw(draw, txt, f)
    draw.text((cx - tw // 2, cy - 13), txt,
              font=f, fill=(20, 10, 40) if rank < 3 else WHITE)


def _circle_avatar(img: Image.Image, avatar: Image.Image | None,
                   initials: str, x: int, y: int, d: int) -> None:
    """Paste a circular avatar; fall back to initials bubble."""
    draw = ImageDraw.Draw(img)
    r    = d // 2

    if avatar:
        try:
            av   = avatar.copy().convert("RGBA").resize((d, d), Image.LANCZOS)
            mask = Image.new("L", (d, d), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, d-1, d-1], fill=255)
            buf  = Image.new("RGBA", (d, d))
            buf.paste(av, (0, 0))
            img.paste(buf, (x, y), mask)
            # ring
            draw.ellipse([x-2, y-2, x+d+1, y+d+1], outline=ACCENT, width=2)
            return
        except Exception:
            pass

    # Initials fallback
    draw.ellipse([x, y, x+d, y+d], fill=(55, 35, 100))
    draw.ellipse([x-2, y-2, x+d+1, y+d+1], outline=ACCENT, width=2)
    ini  = (initials[:2] if len(initials) >= 2 else initials).upper()
    f    = _f(_BOLD, 22)
    fw   = _tw(draw, ini, f)
    draw.text((x + (d - fw) // 2, y + (d - 26) // 2),
              ini, font=f, fill=WHITE)


def _fmt(amount: float, currency: str) -> str:
    c = currency.upper()
    if amount >= 1_000_000:
        s = f"{amount/1_000_000:.1f}jt"
    elif amount >= 1_000:
        s = f"{amount/1_000:.1f}k"
    else:
        s = f"{amount:,.0f}"
    return f"{c} {s}"


def generate_leaderboard_image(
    entries: list[dict],
    *,
    title:            str          = "NOCTRA STORE",
    subtitle:         str          = "Top Spenders",
    brand_logo_bytes: bytes | None = None,
    timestamp:        str          = "",
) -> BytesIO:
    n    = max(1, len(entries))
    h    = HEADER_H + n * (ROW_H + ROW_GAP) - ROW_GAP + BOTTOM
    img  = _gradient(IMG_W, h)

    # glow
    glow = _glow_overlay(IMG_W, h)
    img  = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # ── Brand logo ────────────────────────────────────────────────────────
    logo_bottom = 0
    if brand_logo_bytes:
        try:
            logo = Image.open(BytesIO(brand_logo_bytes)).convert("RGBA")
            logo.thumbnail((72, 72), Image.LANCZOS)
            lw, lh = logo.size
            lx     = (IMG_W - lw) // 2
            ly     = 12
            img.paste(logo, (lx, ly), logo)
            logo_bottom = ly + lh + 6
        except Exception:
            pass

    # ── Header text ───────────────────────────────────────────────────────
    f_title = _f(_BOLD, 48)
    f_sub   = _f(_REG,  20)
    f_ts    = _f(_REG,  14)

    ty  = max(logo_bottom, 14)
    tw  = _tw(draw, title, f_title)
    tx  = (IMG_W - tw) // 2
    # shadow
    draw.text((tx + 3, ty + 3), title, font=f_title, fill=(20, 8, 50))
    # main (two-tone: accent on left half, lighter on right)
    draw.text((tx, ty), title, font=f_title, fill=ACCENT)

    sy   = ty + 56
    sw   = _tw(draw, subtitle, f_sub)
    draw.text(((IMG_W - sw) // 2, sy), subtitle, font=f_sub, fill=OFF_WHITE)

    if timestamp:
        tw2  = _tw(draw, timestamp, f_ts)
        draw.text(((IMG_W - tw2) // 2, sy + 28), timestamp, font=f_ts, fill=MUTED)

    # divider
    div_y = HEADER_H - 8
    draw.line([(PAD, div_y), (IMG_W - PAD, div_y)], fill=(75, 31, 168), width=1)

    # ── Row fonts ─────────────────────────────────────────────────────────
    f_name   = _f(_BOLD, 20)
    f_orders = _f(_REG,  15)
    f_spend  = _f(_BOLD, 18)

    max_spent = max((e["total_spent"] for e in entries), default=1) or 1

    for i, entry in enumerate(entries):
        rank    = entry.get("rank", i)
        name    = entry.get("display_name", "Unknown")[:24]
        spent   = entry.get("total_spent", 0)
        orders  = entry.get("total_orders", 0)
        cur     = entry.get("currency_label", "IDR")
        avatar  = entry.get("avatar")

        ry0 = HEADER_H + i * (ROW_H + ROW_GAP)
        ry1 = ry0 + ROW_H
        rx0 = PAD
        rx1 = IMG_W - PAD

        # card bg -- top 3 get a slightly brighter card
        cf = CARD_BG_TOP3 if rank < 3 else CARD_BG
        if rank < 3:
            # coloured top border strip
            draw.rounded_rectangle([rx0, ry0, rx1, ry0 + 3],
                                   radius=2, fill=MEDAL_CLR[rank])
        draw.rounded_rectangle([rx0, ry0, rx1, ry1],
                               radius=RADIUS, fill=cf,
                               outline=(60, 40, 110), width=1)

        # ── Medal badge ──────────────────────────────────────────────────
        badge_cx = rx0 + 40
        badge_cy = ry0 + ROW_H // 2
        _draw_medal(img, badge_cx, badge_cy, rank)
        draw = ImageDraw.Draw(img)   # re-acquire after paste ops in medal

        # ── Avatar ───────────────────────────────────────────────────────
        av_x = badge_cx + BADGE_D // 2 + 14
        av_y = ry0 + (ROW_H - AVATAR_D) // 2
        _circle_avatar(img, avatar, name, av_x, av_y, AVATAR_D)
        draw = ImageDraw.Draw(img)

        # ── Name + order count ────────────────────────────────────────────
        text_x = av_x + AVATAR_D + 18
        draw.text((text_x, ry0 + 24), name, font=f_name, fill=WHITE)
        ord_txt = f"{orders} order{'s' if orders != 1 else ''}"
        draw.text((text_x, ry0 + 52), ord_txt, font=f_orders, fill=MUTED)

        # ── Spend label + progress bar (right side) ───────────────────────
        bar_x1  = rx1 - 28
        bar_x0  = bar_x1 - BAR_W
        spend_s = _fmt(spent, cur)
        col     = MEDAL_CLR[rank] if rank < 3 else ACCENT
        sw2     = _tw(draw, spend_s, f_spend)
        spend_x = bar_x0 + (BAR_W - sw2) // 2
        draw.text((spend_x, ry0 + 20), spend_s, font=f_spend, fill=col)

        bar_y   = ry0 + 55
        ratio   = math.sqrt(spent / max_spent)
        fill_w  = max(6, int(BAR_W * ratio))
        # track
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + BAR_W, bar_y + BAR_H],
                               radius=BAR_H // 2, fill=BAR_BG)
        # fill -- gradient: medal colour -> accent
        bar_col = tuple(
            int(col[c] * 0.75 + ACCENT[c] * 0.25) for c in range(3)
        )
        draw.rounded_rectangle([bar_x0, bar_y, bar_x0 + fill_w, bar_y + BAR_H],
                               radius=BAR_H // 2, fill=bar_col)

    # ── Footer ────────────────────────────────────────────────────────────
    f_wm  = _f(_REG, 14)
    wm    = "NOCTRA STORE  \u2022  noctra"
    ww    = _tw(draw, wm, f_wm)
    draw.text(((IMG_W - ww) // 2, h - 28), wm, font=f_wm, fill=MUTED)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf
