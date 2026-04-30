# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CateringCapacity(Document):
	pass

def get_display_names(row):
    item_code = ""
    item_name = ""
    item_name_arabic = ""

    if row.row_type in ("Item", "Sub Item"):
        item_code = row.item_code or ""

        if item_code:
            item_doc = frappe.db.get_value(
                "Item",
                item_code,
                ["item_name", "item_name_arabic"],
                as_dict=True
            ) or {}

            item_name = item_doc.get("item_name") or row.item_name or item_code
            item_name_arabic = item_doc.get("item_name_arabic") or row.item_name_arabic or ""

    elif row.row_type == "New Item":
        item_name = row.new_item_name or ""
        item_name_arabic = row.new_item_name_arabic or ""

    return item_code, item_name, item_name_arabic


def get_effective_menu_items(menu_doc):
    rows = list(menu_doc.items or [])

    parent_has_children = set()
    last_parent_by_context = {}

    for row in rows:
        row_key = row.row_id or row.name

        if row.row_type in ("Item", "New Item"):
            context_key = (row.service_period, row.meal_type)
            last_parent_by_context[context_key] = row

        elif row.row_type == "Sub Item":
            if row.parent_row_id:
                parent_has_children.add(row.parent_row_id)
            else:
                context_key = (row.service_period, row.meal_type)
                parent_row = last_parent_by_context.get(context_key)

                if parent_row:
                    parent_has_children.add(parent_row.row_id or parent_row.name)

    effective_items = []

    for row in rows:
        row_key = row.row_id or row.name

        if row.row_type in ("Item", "New Item"):
            if row_key not in parent_has_children:
                effective_items.append(row)

        elif row.row_type == "Sub Item":
            effective_items.append(row)

    return effective_items


@frappe.whitelist()
def get_items_from_active_catering_menus():
    filters = {}

    meta = frappe.get_meta("Catering Menu")
    if meta.has_field("disabled"):
        filters["disabled"] = 0

    menus = frappe.get_all(
        "Catering Menu",
        filters=filters,
        fields=["name"],
        order_by="modified desc"
    )

    unique_items = {}

    for menu in menus:
        menu_doc = frappe.get_doc("Catering Menu", menu.name)
        effective_items = get_effective_menu_items(menu_doc)

        for row in effective_items:
            if row.row_type not in ("Item", "New Item", "Sub Item"):
                continue

            item_code, item_name, item_name_arabic = get_display_names(row)

            if row.row_type in ("Item", "Sub Item"):
                if not item_code:
                    continue

                key = f"ITEM::{item_code}"

                if key not in unique_items:
                    unique_items[key] = {
                        "item": item_code,
                        "item_name": item_name or item_code,
                        "item_name_arabic": item_name_arabic or "",
                    }

            elif row.row_type == "New Item":
                if not item_name or not item_name_arabic:
                    continue

                key = f"NEW::{item_name.strip().lower()}::{item_name_arabic.strip()}"

                if key not in unique_items:
                    unique_items[key] = {
                        "item": "",
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