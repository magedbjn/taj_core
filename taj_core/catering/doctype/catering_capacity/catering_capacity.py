import frappe
from frappe.model.document import Document
from taj_core.catering.utils import get_capacity_key, get_item_display_names


class CateringCapacity(Document):
    pass


def get_effective_menu_items(menu_doc):
    rows = list(menu_doc.items or [])

    effective_rows = []
    parent_has_children = set()
    row_by_key = {}
    last_parent_by_context = {}

    for row in rows:
        row_key = row.row_id or row.name

        if row.row_type in ("Item", "New Item"):
            context_key = (row.service_period, row.meal_type)
            last_parent_by_context[context_key] = row
            row_by_key[row_key] = row

        elif row.row_type == "Sub Item":
            parent_row = None

            if row.parent_row_id:
                parent_row = row_by_key.get(row.parent_row_id)

            if not parent_row:
                context_key = (row.service_period, row.meal_type)
                parent_row = last_parent_by_context.get(context_key)

            if parent_row:
                parent_has_children.add(parent_row.row_id or parent_row.name)

    for row in rows:
        row_key = row.row_id or row.name

        if row.row_type in ("Item", "New Item"):
            if row_key not in parent_has_children:
                effective_rows.append(row)

        elif row.row_type == "Sub Item":
            effective_rows.append(row)

    return effective_rows


@frappe.whitelist()
def get_items_from_active_catering_menus():
    filters = {}

    if frappe.get_meta("Catering Menu").has_field("disabled"):
        filters["disabled"] = 0

    menus = frappe.get_all(
        "Catering Menu",
        filters=filters,
        fields=["name"],
        order_by="modified desc",
    )

    unique_items = {}

    for menu in menus:
        menu_doc = frappe.get_doc("Catering Menu", menu.name)

        for row in get_effective_menu_items(menu_doc):
            if row.row_type not in ("Item", "New Item", "Sub Item"):
                continue

            item_code, item_name, item_name_arabic = get_item_display_names(row)

            key = ""

            if row.row_type in ("Item", "Sub Item"):
                if not item_code:
                    continue

                key = get_capacity_key(item_code=item_code)

            elif row.row_type == "New Item":
                if not item_name or not item_name_arabic:
                    continue

                key = get_capacity_key(
                    item_name=item_name,
                    item_name_arabic=item_name_arabic,
                )

            if not key or key in unique_items:
                continue

            unique_items[key] = {
                "item_code": item_code,
                "item_name": item_name,
                "item_name_arabic": item_name_arabic,
            }

    result = list(unique_items.values())

    result.sort(
        key=lambda d: (
            (d.get("item_name") or "").lower(),
            d.get("item_name_arabic") or "",
        )
    )

    return result