"""
Konfigurasi custom emoji buat NOCTRA.

Bot cuma bisa pake custom emoji kalau emoji-nya ada di server yang sama
sama bot (atau emoji itu di-set "available everywhere"). Cara pasang emoji
custom lu sendiri di sini:

  1. Upload emoji-nya ke server mana aja yang ada bot-nya (Server Settings
     -> Emoji).
  2. Di channel manapun, ketik emoji-nya pake tanda backslash di depan,
     misal \\:emoji_sukses: terus kirim -- Discord bakal nunjukin bentuk
     mentahnya, contoh <:emoji_sukses:1234567890123456789> (atau
     <a:nama:id> kalau animasi).
  3. Copy persis string itu (termasuk tanda < dan >), terus tempel di
     bawah, ganti emoji default-nya.

Sebelum lu ganti, ini masih pake emoji Unicode biasa dulu biar bot tetep
enak dilihat dari awal.
"""

from __future__ import annotations

EMOJI_SUCCESS = "✅"
EMOJI_ERROR = "❌"
EMOJI_INFO = "ℹ️"

# Tambahin di sini kalau butuh lebih banyak, contoh:
# EMOJI_WARNING = "⚠️"
# EMOJI_LOADING = "⏳"
