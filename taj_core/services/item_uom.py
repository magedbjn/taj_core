import frappe
from frappe import _
from frappe.utils import cstr, flt



def _get_uom_category_from_conversion_table(uom):
    """Resolve the category used by ERPNext UOM Conversion Factor."""
    uom = cstr(uom or "").strip()

    if not uom:
        return None

    # Canonical row is preferred.
    category = frappe.db.get_value(
        "UOM Conversion Factor",
        {
            "from_uom": uom,
            "to_uom": uom,
        },
        "category",
    )

    if category:
        return cstr(category).strip()

    # Custom UOMs may not have a self-conversion row.
    from_category = frappe.db.get_value(
        "UOM Conversion Factor",
        {"from_uom": uom},
        "category",
    )

    to_category = frappe.db.get_value(
        "UOM Conversion Factor",
        {"to_uom": uom},
        "category",
    )

    from_category = cstr(from_category or "").strip()
    to_category = cstr(to_category or "").strip()

    # Reject an ambiguous UOM instead of guessing.
    if (
        from_category
        and to_category
        and from_category != to_category
    ):
        return None

    return from_category or to_category or None


def _get_same_category_global_factor(from_uom, to_uom):
    """
    Convert from_uom to to_uom using UOM Conversion Factor.

    The conversion is accepted only when both UOMs resolve to the same
    category. Direct values are used as stored; reverse values are
    inverted.
    """
    from_uom = cstr(from_uom or "").strip()
    to_uom = cstr(to_uom or "").strip()

    if not from_uom or not to_uom:
        return None

    if from_uom == to_uom:
        return 1.0

    from_category = (
        _get_uom_category_from_conversion_table(from_uom)
    )
    to_category = (
        _get_uom_category_from_conversion_table(to_uom)
    )

    if (
        not from_category
        or not to_category
        or from_category != to_category
    ):
        return None

    direct = frappe.db.get_value(
        "UOM Conversion Factor",
        {
            "from_uom": from_uom,
            "to_uom": to_uom,
        },
        ["category", "value"],
        as_dict=True,
    )

    if direct:
        row_category = cstr(
            direct.get("category") or ""
        ).strip()
        value = flt(direct.get("value"))

        if (
            row_category == from_category
            and value > 0
        ):
            return value

    reverse = frappe.db.get_value(
        "UOM Conversion Factor",
        {
            "from_uom": to_uom,
            "to_uom": from_uom,
        },
        ["category", "value"],
        as_dict=True,
    )

    if reverse:
        row_category = cstr(
            reverse.get("category") or ""
        ).strip()
        value = flt(reverse.get("value"))

        if (
            row_category == from_category
            and value > 0
        ):
            return 1.0 / value

    return None


def get_item_uom_factor_to_stock(
    item_code,
    uom,
    stock_uom=None,
    variant_of=None,
):
    """Return an Item-specific conversion factor from UOM to Stock UOM."""
    item_code = cstr(item_code or "").strip()
    uom = cstr(uom or "").strip()
    stock_uom = cstr(stock_uom or "").strip()
    variant_of = cstr(variant_of or "").strip()

    if not item_code or not uom:
        return None

    if not stock_uom:
        item = frappe.db.get_value(
            "Item",
            item_code,
            ["stock_uom", "variant_of"],
            as_dict=True,
        )

        if not item:
            return None

        stock_uom = cstr(item.get("stock_uom") or "").strip()
        variant_of = variant_of or cstr(item.variant_of or "").strip()

    if not stock_uom:
        return None

    if uom == stock_uom:
        return 1.0

    # Only conversions explicitly configured for this Item are valid.
    # Variants may also inherit conversions from their Item Template.
    for parent in (item_code, variant_of):
        if not parent:
            continue

        factor = frappe.db.get_value(
            "UOM Conversion Detail",
            {
                "parent": parent,
                "parenttype": "Item",
                "uom": uom,
            },
            "conversion_factor",
        )

        if flt(factor) > 0:
            return flt(factor)

    return _get_same_category_global_factor(uom, stock_uom)


def get_item_uom_conversion_factor(
    item_code,
    from_uom,
    to_uom,
    stock_uom=None,
    variant_of=None,
):
    """Convert between two UOMs explicitly configured for the same Item."""
    from_uom = cstr(from_uom or "").strip()
    to_uom = cstr(to_uom or "").strip()

    if not from_uom or not to_uom:
        return None

    if from_uom == to_uom:
        return 1.0

    if not stock_uom:
        item = frappe.db.get_value(
            "Item",
            item_code,
            ["stock_uom", "variant_of"],
            as_dict=True,
        )

        if not item:
            return None

        stock_uom = item.stock_uom
        variant_of = variant_of or item.variant_of

    from_factor = get_item_uom_factor_to_stock(
        item_code,
        from_uom,
        stock_uom,
        variant_of,
    )

    to_factor = get_item_uom_factor_to_stock(
        item_code,
        to_uom,
        stock_uom,
        variant_of,
    )

    if flt(from_factor) > 0 and flt(to_factor) > 0:
        return flt(from_factor) / flt(to_factor)

    return None


@frappe.whitelist()
def get_item_uom_options(item_code):
    """
    Return UOMs allowed for a Taj Core Item.

    Sources:
    1. Stock UOM
    2. Item / Variant Template UOM Conversion Detail
    3. Direct ERPNext UOM Conversion Factor rows in the same category
       as the Stock UOM.

    Conversion factors are always expressed as:
        selected UOM -> Stock UOM
    """
    item_code = cstr(item_code or "").strip()

    if not item_code:
        return {
            "stock_uom": "",
            "uoms": [],
        }

    item = frappe.db.get_value(
        "Item",
        item_code,
        ["stock_uom", "variant_of"],
        as_dict=True,
    )

    if not item:
        return {
            "stock_uom": "",
            "uoms": [],
        }

    stock_uom = cstr(item.get("stock_uom") or "").strip()
    variant_of = cstr(item.get("variant_of") or "").strip()

    allowed = {}

    if stock_uom:
        allowed[stock_uom] = 1.0

    # ---------------------------------------------------------
    # Item-specific UOMs.
    # Variant template first; variant/item itself wins later.
    # ---------------------------------------------------------
    item_sources = []

    if variant_of:
        item_sources.append(variant_of)

    item_sources.append(item_code)

    for parent in item_sources:
        rows = frappe.get_all(
            "UOM Conversion Detail",
            filters={
                "parent": parent,
                "parenttype": "Item",
            },
            fields=[
                "uom",
                "conversion_factor",
            ],
        )

        for row in rows:
            uom = cstr(row.get("uom") or "").strip()
            factor = flt(row.get("conversion_factor"))

            if uom and factor > 0:
                allowed[uom] = factor

    # ---------------------------------------------------------
    # Global UOM conversions, restricted to the Stock UOM's
    # own category and directly connected to Stock UOM.
    # ---------------------------------------------------------
    category = _get_uom_category_from_conversion_table(
        stock_uom
    )

    if category and stock_uom:
        rows = frappe.get_all(
            "UOM Conversion Factor",
            filters={
                "category": category,
            },
            fields=[
                "category",
                "from_uom",
                "to_uom",
                "value",
            ],
        )

        for row in rows:
            from_uom = cstr(
                row.get("from_uom") or ""
            ).strip()

            to_uom = cstr(
                row.get("to_uom") or ""
            ).strip()

            value = flt(row.get("value"))

            if value <= 0:
                continue

            candidate = None
            factor_to_stock = None

            # Example:
            # Litre -> Millilitre = 1000
            # Therefore 1 Millilitre = 0.001 Litre.
            if from_uom == stock_uom and to_uom:
                candidate = to_uom
                factor_to_stock = 1.0 / value

            # Example:
            # Bag (40k) -> Kg = 40
            # Therefore 1 Bag = 40 Kg.
            elif to_uom == stock_uom and from_uom:
                candidate = from_uom
                factor_to_stock = value

            if (
                candidate
                and factor_to_stock
                and factor_to_stock > 0
            ):
                # Explicit Item conversion always wins.
                allowed.setdefault(
                    candidate,
                    factor_to_stock,
                )

    result = []

    # Stock UOM always first.
    if stock_uom:
        result.append({
            "uom": stock_uom,
            "conversion_factor": 1.0,
        })

    # Remaining allowed UOMs alphabetically.
    for uom in sorted(
        key
        for key in allowed
        if key != stock_uom
    ):
        result.append({
            "uom": uom,
            "conversion_factor": flt(allowed[uom]),
        })

    return {
        "stock_uom": stock_uom,
        "uoms": result,
    }

def validate_item_uom(item_code, uom):
    """Validate that UOM is configured for the Item or its Variant template."""
    item_code = cstr(item_code or "").strip()
    uom = cstr(uom or "").strip()

    if not item_code:
        frappe.throw(_("Item is required."))

    if not uom:
        frappe.throw(
            _("UOM is required for Item {0}.").format(item_code)
        )

    item = frappe.db.get_value(
        "Item",
        item_code,
        ["stock_uom", "variant_of"],
        as_dict=True,
    )

    if not item:
        frappe.throw(
            _("Item {0} does not exist.").format(item_code)
        )

    factor = get_item_uom_factor_to_stock(
        item_code=item_code,
        uom=uom,
        stock_uom=item.stock_uom,
        variant_of=item.variant_of,
    )

    if flt(factor) <= 0:
        frappe.throw(
            _(
                "UOM {0} is not valid for Item {1}. "
                "Use the Stock UOM, an Item UOM Conversion, "
                "or a same-category UOM Conversion Factor."
            ).format(uom, item_code)
        )

    return flt(factor)

def validate_item_uom_rows(
    rows,
    item_field="item_code",
    uom_field="uom",
):
    """Validate Item/UOM pairs using one reusable Taj Core policy."""
    for row in rows or []:
        item_code = cstr(
            row.get(item_field) or ""
        ).strip()

        if not item_code:
            continue

        validate_item_uom(
            item_code,
            row.get(uom_field),
        )



@frappe.whitelist()
def item_uom_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters,
):
    """Link query containing only UOMs configured for the selected Item."""
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)

    filters = filters or {}

    item_code = cstr(
        filters.get("item_code") or ""
    ).strip()

    if not item_code:
        return []

    result = get_item_uom_options(item_code)

    query_text = cstr(txt or "").strip().lower()

    uoms = [
        cstr(row.get("uom") or "").strip()
        for row in (result.get("uoms") or [])
        if row.get("uom")
    ]

    if query_text:
        uoms = [
            uom
            for uom in uoms
            if query_text in uom.lower()
        ]

    start = max(int(start or 0), 0)
    page_len = max(int(page_len or 20), 1)

    return [
        [uom]
        for uom in uoms[start:start + page_len]
    ]
