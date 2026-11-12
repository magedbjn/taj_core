"""TAJ Nutrition Facts 10x7 context resolution and arithmetic - Frappe v16.

No writes. Values in the approved Finished Product Nutrition Facts document are
per 100 g. Context may refer to the source Item, its Variant, or an explicitly
linked independent Item. Item.weight_per_unit is only a proposed package mass:
QC must confirm it equals net edible mass before external use.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

NUTRIENTS = (
    ("total_fat_g", "Total Fat", "g", "65"),
    ("saturated_fat_g", "Saturated Fat", "g", "20"),
    ("trans_fat_g", "Trans Fat", "g", None),
    ("sodium_mg", "Sodium", "mg", "2400"),
    ("cholesterol_mg", "Cholesterol", "mg", "300"),
    ("carbohydrates_g", "Total Carbohydrates", "g", "300"),
    ("dietary_fiber_g", "Dietary Fiber", "g", "25"),
    ("total_sugars_g", "Total Sugars", "g", None),
    ("added_sugars_g", "Added Sugars", "g", None),
    ("protein_g", "Protein", "g", "50"),
)
KEYS = ("calories_kcal",) + tuple(r[0] for r in NUTRIENTS)
UNIT_TO_G = {
    "g": "1", "gm": "1", "gram": "1", "grams": "1", "\u062c\u0645": "1", "\u063a\u0631\u0627\u0645": "1",
    "kg": "1000", "kgs": "1000", "kilogram": "1000", "kilograms": "1000", "\u0643\u064a\u0644\u0648\u062c\u0631\u0627\u0645": "1000",
    "mg": "0.001", "milligram": "0.001", "milligrams": "0.001",
}
AR = str.maketrans("0123456789", "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")


def num(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid or missing numeric value") from None
    if not result.is_finite():
        raise ValueError("Non-finite numeric value")
    return result


def ar(value):
    return str(value).translate(AR)


def quantity(value):
    """HALF_UP, retain small positive nonzero values to max nine decimals."""
    d = num(value)
    digits = 2
    while d > 0 and digits < 9 and d.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP) == 0:
        digits += 1
    q = d.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return ar(format(q.normalize(), "f"))


def whole(value):
    """Round displayed nutrition amounts HALF_UP to integer; 0.5 becomes 1."""
    # TAJ_NUTRITION_WHOLE_DISPLAY_V1
    return num(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def mass_in_grams(value, uom):
    d = num(value)
    if d <= 0:
        raise ValueError("Weight must be positive")
    factor = UNIT_TO_G.get(str(uom or "").strip().lower())
    if factor is None:
        raise ValueError("Weight UOM must be a mass unit")
    grams = d * Decimal(factor)
    if grams > Decimal("1000000"):
        raise ValueError("Package mass exceeds supported testing limits")
    return grams


def status_error(message, code=""):
    return {"ok": False, "error": message, "item_code": code, "rows": [], "mode": "blocked", "calories": "", "weight_display": "", "basis_label": ""}


def check_plausibility(values):
    # This is objective mass consistency, NOT a regulatory nutrition review.
    g = {k: values[k] for k in ("protein_g", "total_fat_g", "carbohydrates_g", "saturated_fat_g", "trans_fat_g", "total_sugars_g", "added_sugars_g", "dietary_fiber_g")}
    if any(values[k] > 100 for k in g):
        return "Nutrient grams exceed 100 g per 100 g of food"
    if g["protein_g"] + g["total_fat_g"] + g["carbohydrates_g"] > Decimal("100.5"):
        return "Protein + fat + carbohydrates exceed 100 g"
    if g["saturated_fat_g"] + g["trans_fat_g"] > g["total_fat_g"] + Decimal("0.5"):
        return "Fat subtypes exceed total fat"
    if g["total_sugars_g"] > g["carbohydrates_g"] + Decimal("0.5"):
        return "Sugars exceed carbohydrates"
    if g["added_sugars_g"] > g["total_sugars_g"] + Decimal("0.5"):
        return "Added sugars exceed total sugars"
    if g["dietary_fiber_g"] > g["carbohydrates_g"] + Decimal("0.5"):
        return "Dietary fiber exceeds total carbohydrates"
    if values["cholesterol_mg"] > 100000 or values["sodium_mg"] > 100000:
        return "Milligrams exceed the mass of 100 g"
    return ""


def build_label(profile, item, *, group_ok=True, permission_ok=True, today=None, demo=False):
    """Pure function; *item* and *profile* are dicts or Frappe Documents."""
    def get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return obj.get(key, default)

    code = get(item, "name", "") or ""
    if not permission_ok:
        return status_error("Item is not permitted for this user", code)
    if int(get(profile, "docstatus", 0) or 0) != 1:
        return status_error("An approved Nutrition Facts record is required", code)
    if not get(item, "name"):
        return status_error("Item not found", code)
    if int(get(item, "disabled", 0) or 0):
        return status_error("Disabled Item cannot be printed", code)
    if int(get(item, "is_sales_item", 0) or 0) != 1:
        return status_error("Item is not a Sales Item", code)
    if not group_ok:
        return status_error("Item is outside Finished Goods", code)
    expiry = get(item, "end_of_life")
    if expiry:
        try:
            exp_date = expiry if isinstance(expiry, date) else date.fromisoformat(str(expiry)[:10])
            if exp_date < (today or date.today()):
                return status_error("Item End of Life has passed", code)
        except (ValueError, TypeError):
            return status_error("Invalid Item End of Life date", code)

    parent = get(profile, "item_code", "")
    additional = {get(r, "item_code") for r in (get(profile, "additional_items") or [])}
    # Coverage is explicit: main Item, its direct Variants, or independent children.
    covered = code == parent or (get(item, "variant_of") == parent) or (code in additional)
    if not covered:
        return status_error("Item is not covered by this approved Nutrition Facts record", code)

    values = {}
    for field in KEYS:
        raw = get(profile, field)
        if raw is None or raw == "":
            return status_error("Missing nutritional value: " + field, code)
        try:
            val = num(raw)
        except ValueError:
            return status_error("Invalid nutritional value: " + field, code)
        if val < 0:
            return status_error("Negative nutritional value: " + field, code)
        values[field] = val

    problem = check_plausibility(values)
    if problem:
        return status_error("Invalid per-100-g nutrition source: " + problem, code)

    # Template is nutritional reference ONLY. A 0/empty weight means unverified,
    # and transparently falls back to per 100 g rather than implying a package.
    template = bool(int(get(item, "has_variants", 0) or 0))
    raw_weight = get(item, "weight_per_unit")
    mode = "per_100g"
    grams = None
    if not template and raw_weight not in (None, "", 0, "0", "0.0"):
        try:
            grams = mass_in_grams(raw_weight, get(item, "weight_uom"))
        except ValueError as exc:
            return status_error(str(exc), code)
        mode = "per_pack"

    # TAJ_NUTRITION_LESS_THAN_LITERAL_V1: explicit amount rules are fixed print declarations.
    rules = {get(r, "nutrient") for r in (get(profile, "amount_rules") or []) if int(get(r, "less_than_one", 0) or 0)}
    special_fields = {field for field, title, _, _ in NUTRIENTS if title in rules}

    factor = (grams / Decimal(100)) if grams is not None else Decimal(1)
    scaled = {field: (value if field in special_fields else value * factor) for field, value in values.items()}
    if any(not v.is_finite() for v in scaled.values()):
        return status_error("Non-finite calculated quantity", code)

    rows = []
    for field, title, unit, daily in NUTRIENTS:
        special = title in rules
        pct = ""
        if special:
            # Literal Less Than 1: never scale, round, or calculate a percentage.
            amount = "Less than " + ar("1") + " " + unit
        else:
            shown = whole(scaled[field])
            amount = ar(format(shown, "f")) + " " + unit
            if daily:
                # Percentage uses the displayed rounded amount, not hidden decimals.
                share = (shown * Decimal("100") / Decimal(daily)).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
                pct = ar(format(share, "f")) + "\u066a"
        rows.append({"field": field, "label": title, "amount": amount, "percent": pct, "raw": "" if special else format(scaled[field], "f")})

    return {
        "ok": True, "error": "", "item_code": code,
        "item_name": get(item, "item_name_arabic") or get(item, "item_name") or code,
        "item_name_ar": (get(item, "item_name_arabic") or "").strip(),
        "mode": mode, "template": template,
        "basis_label": "Per package" if mode == "per_pack" else "Per 100 g",
        "weight_display": quantity(grams) if grams is not None else "",
        "factor": str(factor),
        "calories": ar(format(whole(scaled["calories_kcal"]), "f")),
        "rows": rows,
        "demo": bool(demo),
        "weight_unverified": mode == "per_pack",
        "source": get(profile, "name", ""),
        "allergens": [r for r in (get(profile, "amount_rules") or [])],
    }


def get_label_context(profile, requested_code=None):
    """Resolve a permitted standard Item; never edit any records."""
    import frappe
    from frappe.utils import getdate, nowdate

    code = str(requested_code or profile.get("item_code") or "").strip()
    if not code:
        return frappe._dict(status_error("No Item selected"))
    if not frappe.has_permission("Item", "read"):
        return frappe._dict(status_error("Item read permission is required", code))
    rows = frappe.get_list("Item", filters={"name": code},
        fields=["name", "item_name", "item_name_arabic", "has_variants", "variant_of", "disabled",
                "is_sales_item", "item_group", "weight_per_unit", "weight_uom", "end_of_life"],
        limit_page_length=1)
    if not rows:
        return frappe._dict(status_error("Item is unavailable or restricted", code))
    item = rows[0]
    root = frappe.db.get_value("Item Group", "Finished Goods", ["lft", "rgt"], as_dict=True)
    node = frappe.db.get_value("Item Group", item.item_group, ["lft", "rgt"], as_dict=True)
    group_ok = bool(root and node and root.lft <= node.lft and node.rgt <= root.rgt)
    data = build_label(profile, item, group_ok=group_ok,
        permission_ok=True, today=getdate(nowdate()),
        demo=bool(getattr(getattr(profile, "flags", None), "taj_nutrition_demo", False)))
    return frappe._dict(data)


def find_approved_profile_for_item(item_code):
    """Resolve one approved, permission-visible source for Item/template/additional Item.

    No record is written and conflicting approved profiles fail closed.
    """
    import frappe

    item_code = str(item_code or '').strip()
    if not item_code or len(item_code) > 140:
        frappe.throw('Select a valid Item.')
    if not frappe.has_permission('Item', 'read') or not frappe.has_permission('Finished Product Nutrition Facts', 'read'):
        frappe.throw('You do not have permission to read the Item and approved Nutrition Facts.', frappe.PermissionError)
    item_rows = frappe.get_list('Item', filters={'name': item_code},
        fields=['name', 'variant_of'], limit_page_length=1)
    if not item_rows:
        frappe.throw('Item not found or not permitted.')
    codes = [item_code]
    if item_rows[0].variant_of:
        codes.append(item_rows[0].variant_of)
    direct = frappe.get_list('Finished Product Nutrition Facts',
        filters={'docstatus': 1, 'item_code': ['in', codes]},
        fields=['name', 'item_code'], limit_page_length=50)

    # Additional Items is a child table. Parent access is always checked again
    # through frappe.get_list, never inferred from the child-table lookup.
    child_parents = frappe.get_all('Finished Product Label Item',
        filters={'item_code': item_code, 'parenttype': 'Finished Product Nutrition Facts',
                 'parentfield': 'additional_items'},
        pluck='parent', limit_page_length=50)
    permitted_additional = []
    if child_parents:
        permitted_additional = frappe.get_list('Finished Product Nutrition Facts',
            filters={'docstatus': 1, 'name': ['in', child_parents]},
            fields=['name', 'item_code'], limit_page_length=50)
    found = {d.name: d for d in direct + permitted_additional}
    if len(found) != 1:
        frappe.throw('Exactly one approved Nutrition Facts source must cover this Item.')
    return next(iter(found.values()))


def get_public_print_context(doc, requested_item_code=None):
    """Jinja hook: auto-select Item or template per-100-g basis; no writes."""
    return get_label_context(doc, requested_item_code)


# Only this method is whitelisted; it returns print identifiers after permission checks.
def get_approved_nutrition_print_target(item_code):
    import frappe
    source = find_approved_profile_for_item(item_code)
    # Ensure the item is explicitly covered, enabled, saleable, and group-valid.
    profile = frappe.get_doc('Finished Product Nutrition Facts', source.name)
    label = get_label_context(profile, item_code)
    if not label.ok:
        frappe.throw(frappe._(label.error))
    if not label.item_name_ar:
        frappe.throw("لا يمكن طباعة الملصق العربي: يرجى تعبئة اسم الصنف بالعربية (Item Name (Arabic)) في بطاقة الصنف.")
    return {'doctype': 'Finished Product Nutrition Facts', 'name': source.name,
            'format': 'Nutrition Facts 10x7', 'item_code': item_code}


try:
    import frappe
    get_approved_nutrition_print_target = frappe.whitelist()(get_approved_nutrition_print_target)
except ImportError:
    pass
