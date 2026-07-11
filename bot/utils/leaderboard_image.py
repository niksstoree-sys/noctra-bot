"""
Generates a dark-purple leaderboard image using Pillow, matching the
NOCTRA brand palette.
"""

from __future__ import annotations

import math
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

BG_TOP       = (10, 6, 24)
BG_BOT       = (22, 12, 44)
CARD_BG      = (28, 18, 54)
CARD_BORDER  = (75, 31, 168)
ACCENT       = (124, 92, 255)
GOLD         = (255, 200, 60)
SILVER       = (192, 200, 215)
BRONZE       = (205, 127, 50)
WHITE        = (255, 255, 255)
MUTED        = (150, 135, 190)
BAR_BG       = (45, 30, 80)
BAR_FILL     = (124, 92, 255)
MEDAL_COLORS = [GOLD, SILVER, BRONZE]

IMG_W        = 900
HEADER_H     = 110
ROW_H        = 88
ROW_MARGIN   = 12
SIDE_PAD     = 40
BOTTOM_PAD   = 36
CORNER_R     = 20
BAR_H        = 10
BAR_W_MAX    = 340
AVATAR_SIZE  = 54
AVATAR_MARGIN = 16

_BOLD   = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_MEDIUM = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _gradient_bg(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _rounded_rect(draw, xy, radius, fill, outline=None, outline_width=2):
    draw.rounded_rectangle(xy, radius=radius, fill=fill,
                           outline=outline, width=outline_width)


def _format_currency(amount: float, currency: str) -> str:
    c = currency.upper()
    if amount >= 1_000_000:
        return f"{c} {amount/1_000_000:.1f}jt"
    if amount >= 1_000:
        return f"{c} {amount/1_000:.1f}k"
    return f"{c} {amount:,.0f}"


def generate_leaderboard_image(
    entries: list[dict],
    *,
    title: str = "NOCTRA STORE",
    subtitle: str = "Top Spenders",
    brand_logo_bytes: bytes | None = None,
    timestamp: str = "",
) -> BytesIO:
    n_rows = max(1, len(entries))
    img_h  = HEADER_H + n_rows * (ROW_H + ROW_MARGIN) + BOTTOM_PAD

    img  = _gradient_bg(IMG_W, img_h)

    # Glow overlay
    glow = Image.new("RGBA", (IMG_W, img_h), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    for cx, cy, cr, alpha in [
        (IMG_W * 0.8, img_h * 0.1, 260, 35),
        (IMG_W * 0.1, img_h * 0.7, 200, 25),
    ]:
        for r in range(int(cr), 0, -4):
            a = int(alpha * (r / cr) ** 2)
            gd.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(124, 92, 255, a))
    img  = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Header
    f_title    = _font(_BOLD,   36)
    f_subtitle = _font(_MEDIUM, 18)
    f_ts       = _font(_MEDIUM, 13)

    title_y = 20
    if brand_logo_bytes:
        try:
            logo = Image.open(BytesIO(brand_logo_bytes)).convert("RGBA")
            logo.thumbnail((56, 56))
            lw, lh = logo.size
            img.paste(logo, ((IMG_W - lw) // 2, (HEADER_H // 2 - lh) // 2 - 4), logo)
            title_y = HEADER_H // 2 + 4
        except Exception:
            pass

    tw = draw.textlength(title, font=f_title)
    tx = (IMG_W - tw) // 2
    draw.text((tx + 2, title_y + 2), title, font=f_title, fill=(30, 10, 60))
    draw.text((tx, title_y),         title, font=f_title, fill=ACCENT)

    if not brand_logo_bytes:
        sw = draw.textlength(subtitle, font=f_subtitle)
        draw.text(((IMG_W - sw) // 2, title_y + 46), subtitle, font=f_subtitle, fill=WHITE)

    if timestamp:
        tsw = draw.textlength(timestamp, font=f_ts)
        draw.text(((IMG_W - tsw) // 2, HEADER_H - 22), timestamp, font=f_ts, fill=MUTED)

    draw.line([(SIDE_PAD, HEADER_H - 6), (IMG_W - SIDE_PAD, HEADER_H - 6)],
              fill=CARD_BORDER, width=1)

    # Row fonts
    f_rank   = _font(_BOLD,   22)
    f_name   = _font(_BOLD,   17)
    f_spend  = _font(_BOLD,   15)
    f_orders = _font(_MEDIUM, 13)

    max_spent = max((e["total_spent"] for e in entries), default=1) or 1

    for i, entry in enumerate(entries):
        rank   = entry.get("rank", i)
        name   = entry.get("display_name", "Unknown")[:22]
        spent  = entry.get("total_spent", 0)
        orders = entry.get("total_orders", 0)
        cur    = entry.get("currency_label", "IDR")
        avatar = entry.get("avatar")

        row_y = HEADER_H + i * (ROW_H + ROW_MARGIN)
        rx0, rx1 = SIDE_PAD, IMG_W - SIDE_PAD
        ry0, ry1 = row_y, row_y + ROW_H

        # Card
        if rank < 3:
            bcol = MEDAL_COLORS[rank]
            _rounded_rect(draw, (rx0-1, ry0-1, rx1+1, ry1+1), CORNER_R, fill=bcol)
        _rounded_rect(draw, (rx0, ry0, rx1, ry1), CORNER_R,
                      fill=CARD_BG, outline=CARD_BORDER, outline_width=1)

        cx = rx0 + 14

        # Rank
        badge_col  = MEDAL_COLORS[rank] if rank < 3 else MUTED
        medal_txt  = ["🥇", "🥈", "🥉"][rank] if rank < 3 else f"#{rank + 1}"
        f_badge    = f_rank
        bw = draw.textlength(medal_txt, font=f_badge)
        draw.text((cx, ry0 + (ROW_H - 24) // 2), medal_txt,
                  font=f_badge, fill=badge_col)
        cx += int(bw) + 10

        # Avatar
        av_x = cx
        av_y = ry0 + (ROW_H - AVATAR_SIZE) // 2
        if avatar:
            try:
                av = avatar.copy().convert("RGBA")
                av.thumbnail((AVATAR_SIZE, AVATAR_SIZE))
                mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
                ImageDraw.Draw(mask).ellipse(
                    [0, 0, AVATAR_SIZE-1, AVATAR_SIZE-1], fill=255)
                base = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE))
                base.paste(av, ((AVATAR_SIZE - av.width) // 2,
                                (AVATAR_SIZE - av.height) // 2))
                img.paste(base, (av_x, av_y), mask)
            except Exception:
                draw.ellipse([av_x, av_y, av_x+AVATAR_SIZE, av_y+AVATAR_SIZE],
                             fill=CARD_BORDER)
        else:
            draw.ellipse([av_x, av_y, av_x+AVATAR_SIZE, av_y+AVATAR_SIZE],
                         fill=CARD_BORDER)
            ini = name[0].upper() if name else "?"
            iw  = draw.textlength(ini, font=f_name)
            draw.text((av_x + (AVATAR_SIZE - iw)//2, av_y + (AVATAR_SIZE-18)//2),
                      ini, font=f_name, fill=WHITE)
        cx += AVATAR_SIZE + AVATAR_MARGIN

        # Name + orders
        draw.text((cx, ry0 + 14), name, font=f_name, fill=WHITE)
        draw.text((cx, ry0 + 38), f"{orders} order{'s' if orders != 1 else ''}",
                  font=f_orders, fill=MUTED)

        # Spend + bar (right side)
        spend_txt = _format_currency(spent, cur)
        bar_x1    = rx1 - 24
        bar_x0    = bar_x1 - BAR_W_MAX
        spend_w   = int(draw.textlength(spend_txt, font=f_spend))
        draw.text((bar_x0 + (BAR_W_MAX - spend_w)//2, ry0 + 14),
                  spend_txt, font=f_spend,
                  fill=MEDAL_COLORS[rank] if rank < 3 else ACCENT)

        bar_y    = ry0 + 40
        ratio    = math.sqrt(spent / max_spent)
        fill_w   = max(4, int(BAR_W_MAX * ratio))
        bar_col  = tuple(int(MEDAL_COLORS[rank][c]*0.9 + ACCENT[c]*0.1)
                         for c in range(3)) if rank < 3 else BAR_FILL

        _rounded_rect(draw, (bar_x0, bar_y, bar_x0+BAR_W_MAX, bar_y+BAR_H),
                      BAR_H//2, fill=BAR_BG)
        _rounded_rect(draw, (bar_x0, bar_y, bar_x0+fill_w, bar_y+BAR_H),
                      BAR_H//2, fill=bar_col)

    # Footer
    wm = "NOCTRA STORE  •  noctra"
    wm_font = _font(_MEDIUM, 12)
    ww = draw.textlength(wm, font=wm_font)
    draw.text(((IMG_W - ww)//2, img_h - 22), wm, font=wm_font, fill=MUTED)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf
