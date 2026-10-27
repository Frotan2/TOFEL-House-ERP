"""Bounded inputs for native counter receipts and cash custody transfers."""
from decimal import Decimal, InvalidOperation
import json

MAX_RECEIPTS = 100
MAX_AMOUNT = Decimal("999999999999.99")
CENT = Decimal("0.01")


def money(value):
    if isinstance(value, bool):
        raise ValueError("Enter a positive cash amount with at most two decimal places")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Enter a valid cash amount") from exc
    if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
        raise ValueError("Enter a positive, finite cash amount within the supported limit")
    if amount != amount.quantize(CENT):
        raise ValueError("Cash amounts may have at most two decimal places")
    return amount.quantize(CENT)


def receipt_names(value):
    if isinstance(value, str):
        if len(value) > 16000:
            raise ValueError("Select at most 100 receipts for one handover")
        try:
            value = json.loads(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("Select the receipts to hand over") from exc
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_RECEIPTS:
        raise ValueError("Select between one and 100 receipts for one handover")
    if any(not isinstance(name, str) or not name or name != name.strip() or len(name) > 140
           or any(ord(char) < 32 for char in name)
           for name in value):
        raise ValueError("Every selected receipt must have a valid reference")
    if len(value) != len(set(value)):
        raise ValueError("A receipt cannot appear twice in one handover")
    return sorted(value)


def bounded_text(value, label, maximum=140):
    if (not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum
            or any(ord(char) < 32 for char in value)):
        raise ValueError(f"A valid {label} is required")
    return value.strip()
