from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


GRAM_UOMS = frozenset({"g", "gm", "gram", "grams"})


def _clean_number(value, decimals=3):
    try:
        number = Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        number = Decimal("0")

    quantum = Decimal("1") if decimals <= 0 else Decimal("1." + ("0" * decimals))
    number = number.quantize(quantum, rounding=ROUND_HALF_UP)
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_mass_for_print(value, uom):
    """Return a print-only (value, UOM) pair without changing stored data."""
    text_uom = "" if uom is None else str(uom)
    normalized_uom = text_uom.strip().lower()

    try:
        numeric_value = float(value or 0)
    except (TypeError, ValueError):
        numeric_value = 0.0

    if normalized_uom in GRAM_UOMS and numeric_value > 1000:
        return _clean_number(numeric_value / 1000, decimals=3), "kg"

    return _clean_number(numeric_value, decimals=3), text_uom
