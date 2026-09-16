import frappe


def get_capacity_key(item_code=None, item_name=None, item_name_arabic=None):
    if item_code:
        return f"ITEM::{item_code.strip()}"

    if item_name or item_name_arabic:
        return f"NEW::{(item_name or '').strip().lower()}::{(item_name_arabic or '').strip()}"

    return ""


def get_item_display_names(row):
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
                as_dict=True,
            ) or {}

            item_name = item_doc.get("item_name") or row.item_name or item_code
            item_name_arabic = item_doc.get("item_name_arabic") or row.item_name_arabic or ""

    elif row.row_type == "New Item":
        item_name = row.new_item_name or ""
        item_name_arabic = row.new_item_name_arabic or ""

    return item_code, item_name, item_name_arabic
