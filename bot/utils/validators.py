"""Validation logic for admin-configured dynamic product input fields."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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
