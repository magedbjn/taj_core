"""Pure calculation rules for finished-food 100 g and whole-pack printing.

Daily-value references should be verified by QC against the current applicable
Saudi/GCC regulation before any customer-facing label is approved.
Configured baseline follows GSO 2233:2021 numerical references, pending
QC review of GSO 2233:2025 and the applicable product category.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Per-day reference values. Units match the stored field units.
DAILY_VALUES = {
    "total_fat_g": Decimal("70"),
    "saturated_fat_g": Decimal("20"),
    "cholesterol_mg": Decimal("300"),
    "sodium_mg": Decimal("2400"),  # 6 g salt equivalent / 2.5
    "carbohydrates_g": Decimal("260"),
    "dietary_fiber_g": Decimal("28"),
    "protein_g": Decimal("50"),
    # Screenshot intentionally leaves total/added sugar % blank.
}

NUTRIENTS = (
    "calories_kcal", "protein_g", "total_fat_g", "saturated_fat_g", "trans_fat_g",
    "cholesterol_mg", "carbohydrates_g", "total_sugars_g", "added_sugars_g",
    "dietary_fiber_g", "sodium_mg",
)

_DIGIT_MAP = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')


def to_arabic_digits(value):
    return str(value).translate(_DIGIT_MAP)


def decimal_value(value):
    try:
        d = Decimal(str(0 if value is None else value))
    except (InvalidOperation, TypeError):
        raise ValueError("Invalid numeric value") from None
    if not d.is_finite() or d < 0:
        raise ValueError("Nutritional values must be finite and non-negative")
    return d


def weight_to_grams(value, uom):
    v = decimal_value(value)
    if v <= 0:
        raise ValueError("Weight Per Unit must be greater than zero")
    u = (uom or '').strip().lower()
    units = {
        'g': 1, 'gm': 1, 'gram': 1, 'grams': 1, 'جم': 1, 'غرام': 1,
        'kg': 1000, 'kgs': 1000, 'kilogram': 1000, 'كيلوجرام': 1000,
        'mg': Decimal('0.001'), 'milligram': Decimal('0.001'),
    }
    if u not in units:
        raise ValueError("Weight UOM must be a recognized mass unit (g/Kg/mg)")
    return v * Decimal(str(units[u]))


def format_quantity(value, places=2):
    """Arabic numerals without trailing zeroes, e.g. 1.00 -> ١.

    Preserve meaningful tiny quantities rather than silently reporting 0.
    Precision for stored values is governed by ERPNext Float field precision.
    """
    d = decimal_value(value)
    if d == 0:
        return to_arabic_digits('0')
    if places == 0:
        quantized = d.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    else:
        decimals = max(int(places), 0)
        while decimals < 9 and d < Decimal(1).scaleb(-decimals) / 2:
            decimals += 1
        quantized = d.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    if quantized == 0 and d > 0:
        quantized = d
    return to_arabic_digits(format(quantized.normalize(), 'f'))


def percent_dv(fieldname, value):
    if fieldname not in DAILY_VALUES:
        return None
    return to_arabic_digits(int((decimal_value(value) * 100 / DAILY_VALUES[fieldname]).quantize(Decimal('1'),rounding=ROUND_HALF_UP))) + '٪'


def calculate(values, grams, mode='per_100g'):
    if mode not in ('per_100g', 'per_pack'):
        raise ValueError('Unknown nutrition label print mode')
    factor = Decimal('1') if mode == 'per_100g' else weight_to_grams(grams, 'g') / Decimal('100')
    result = {key: decimal_value(values.get(key, 0)) * factor for key in NUTRIENTS}
    return result
