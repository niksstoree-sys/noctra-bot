"""Validation logic for admin-configured dynamic product input fields."""

from __future__ import annotations

import re
import unicodedata

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CUSTOM_EMOJI_RE = re.compile(r"^<a?:\w{2,32}:(\d{15,21})>$")


class FieldValidationError(ValueError):
    pass


def validate_field_value(
    value: str,
    *,
    required: bool,
    min_length: int,
    max_length: int,
    validation: str,
    label: str,
) -> str:
    """Validate a single submitted field value, returning the cleaned value."""
    value = (value or "").strip()

    if not value:
        if required:
            raise FieldValidationError(f"{label} is required.")
        return value

    if len(value) < min_length:
        raise FieldValidationError(f"{label} must be at least {min_length} characters.")
    if len(value) > max_length:
        raise FieldValidationError(f"{label} must be at most {max_length} characters.")

    if validation == "numeric" and not value.isdigit():
        raise FieldValidationError(f"{label} must contain numbers only.")
    elif validation == "alpha" and not value.isalpha():
        raise FieldValidationError(f"{label} must contain letters only.")
    elif validation == "alphanumeric" and not value.isalnum():
        raise FieldValidationError(f"{label} must contain letters and numbers only.")
    elif validation == "email" and not _EMAIL_RE.match(value):
        raise FieldValidationError(f"{label} must be a valid email address.")

    return value


def _char_is_emoji_ish(ch: str) -> bool:
    cp = ord(ch)
    if cp in (0x200D, 0xFE0F):  # zero-width joiner, variation selector
        return True
    if 0x1F3FB <= cp <= 0x1F3FF:  # skin tone modifiers
        return True
    if 0x1F1E6 <= cp <= 0x1F1FF:  # regional indicators (flag emoji)
        return True
    try:
        category = unicodedata.category(ch)
    except (TypeError, ValueError):
        return False
    return category in ("So", "Sk")  # Symbol-other / Symbol-modifier: where real emoji live


def is_valid_emoji(value: str) -> bool:
    """Accepts a real unicode emoji (single or a ZWJ-joined combo like a
    flag or skin-toned gesture) or a custom Discord emoji in
    <:name:id>/<a:name:id> form. Used to validate the optional `emoji`
    parameter on /category create|edit. discord.py's own
    PartialEmoji.from_str() does NOT validate this -- it treats any bare
    string as a "unicode emoji" with no actual character check, so this
    does the real check by Unicode category instead."""
    value = value.strip()
    if not value:
        return False
    if _CUSTOM_EMOJI_RE.match(value):
        return True
    if len(value) > 16:
        return False
    return all(_char_is_emoji_ish(ch) for ch in value)
