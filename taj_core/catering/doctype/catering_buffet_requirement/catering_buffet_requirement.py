# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

import math
import frappe
from frappe.utils import flt
from frappe.model.document import Document


class CateringBuffetRequirement(Document):
	pass


def get_capacity_key(item_code=None, item_name=None, item_name_arabic=None):
    if item_code:
        return f"ITEM::{item_code.strip()}"

    if item_name or item_name_arabic:
        return f"NEW::{(item_name or '').strip().lower()}::{(item_name_arabic or '').strip()}"

    return ""


def get_capacity_map():
    capacity_map = {}

    try:
        capacity_doc = frappe.get_single("Catering Capacity")
    except Exception:
        return capacity_map

    for row in capacity_doc.items:
        key = get_capacity_key(
            item_code=row.item,
            item_name=row.item_name,
            item_name_arabic=row.item_name_arabic
        )

        if not key:
            continue

        if key not in capacity_map:
            capacity_map[key] = {
                "workstation": row.workstation or "",
                "capacity_person_qty": flt(row.capacity_person_qty),
                "capacity_qty": flt(row.capacity_qty),
                "capacity_uom": row.capacity_uom or "",
            }

    return capacity_map


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


def get_parent_display_names(row):
    item_code, item_name, item_name_arabic = get_display_names(row)
    return item_name, item_name_arabic


def get_effective_requirement_items(menu_doc):
    rows = list(menu_doc.items or [])

    effective_rows = []
    parent_has_children = set()
    row_by_key = {}
    last_parent_by_context = {}
    active_section = ""

    prepared_rows = []

    for row in rows:
        if row.row_type == "Section":
            active_section = row.section or ""
            continue

        row_key = row.row_id or row.name
        row_by_key[row_key] = row

        parent_menu_item = ""
        parent_menu_item_arabic = ""
        parent_row_id = ""

        if row.row_type in ("Item", "New Item"):
            context_key = (row.service_period, row.meal_type)
            last_parent_by_context[context_key] = row

        elif row.row_type == "Sub Item":
            parent_row = None

            if row.parent_row_id:
                parent_row = row_by_key.get(row.parent_row_id)

            if not parent_row:
                context_key = (row.service_period, row.meal_type)
                parent_row = last_parent_by_context.get(context_key)

            if parent_row:
                parent_key = parent_row.row_id or parent_row.name
                parent_has_children.add(parent_key)
                parent_row_id = parent_key
                parent_menu_item, parent_menu_item_arabic = get_parent_display_names(parent_row)

        prepared_rows.append({
            "row": row,
            "row_key": row_key,
            "section": active_section,
            "parent_row_id": parent_row_id or row.parent_row_id or "",
            "parent_menu_item": parent_menu_item,
            "parent_menu_item_arabic": parent_menu_item_arabic,
        })

    for data in prepared_rows:
        row = data["row"]

        if row.row_type in ("Item", "New Item"):
            if data["row_key"] not in parent_has_children:
                effective_rows.append(data)

        elif row.row_type == "Sub Item":
            effective_rows.append(data)

    return effective_rows


@frappe.whitelist()
def get_buffet_requirements():
    center_filters = {}

    center_meta = frappe.get_meta("Catering Center")
    if center_meta.has_field("disabled"):
        center_filters["disabled"] = 0

    centers = frappe.get_all(
        "Catering Center",
        filters=center_filters,
        fields=[
            "name",
            "center_name",
            "catering_menu",
            "person_qty"
        ],
        order_by="center_name asc, name asc"
    )

    capacity_map = get_capacity_map()

    result = []
    total_person_qty = 0

    for center in centers:
        if not center.catering_menu:
            continue

        menu_doc = frappe.get_doc("Catering Menu", center.catering_menu)
        menu_person_qty = flt(menu_doc.get("quantity") or menu_doc.get("qty") or 0)

        if menu_person_qty <= 0:
            continue

        center_doc = frappe.get_doc("Catering Center", center.name)

        for buffet in center_doc.buffet:
            person_qty = flt(buffet.get("person_qty") or buffet.get("qty") or 0)
            is_closed = 1 if (buffet.get("is_closed") or buffet.get("close")) else 0

            if person_qty <= 0:
                continue

            if is_closed:
                person_ratio = 0
            else:
                person_ratio = person_qty / menu_person_qty
                total_person_qty += person_qty

            effective_items = get_effective_requirement_items(menu_doc)

            for data in effective_items:
                item_row = data["row"]

                if item_row.row_type not in ("Item", "New Item", "Sub Item"):
                    continue

                base_item_qty = flt(item_row.qty)

                if base_item_qty <= 0:
                    continue

                required_item_qty = base_item_qty * person_ratio

                item_code, item_name, item_name_arabic = get_display_names(item_row)

                capacity_key = ""

                if item_row.row_type in ("Item", "Sub Item"):
                    capacity_key = get_capacity_key(item_code=item_code)
                elif item_row.row_type == "New Item":
                    capacity_key = get_capacity_key(
                        item_name=item_name,
                        item_name_arabic=item_name_arabic
                    )

                capacity = capacity_map.get(capacity_key, {})

                workstation = capacity.get("workstation") or ""
                capacity_person_qty = flt(capacity.get("capacity_person_qty"))
                capacity_qty = flt(capacity.get("capacity_qty"))
                capacity_uom = capacity.get("capacity_uom") or ""

                cooking_runs = 0
                required_capacity_qty = 0
                extra_person_qty = 0

                if not is_closed and capacity_person_qty > 0 and capacity_qty > 0:
                    cooking_runs = int(math.ceil(person_qty / capacity_person_qty))
                    required_capacity_qty = cooking_runs * capacity_qty
                    extra_person_qty = (cooking_runs * capacity_person_qty) - person_qty

                result.append({
                    "catering_center": center.name,
                    "center_name": center.center_name,
                    "catering_menu": center.catering_menu,

                    "buffet": buffet.buffet,
                    "buffet_company": buffet.buffet_company,
                    "person_qty": person_qty,
                    "menu_person_qty": menu_person_qty,
                    "person_ratio": person_ratio,

                    "service_period": item_row.service_period,
                    "service_period": item_row.service_period,
                    "meal_type": item_row.meal_type,
                    "section": data["section"],
                    "row_type": item_row.row_type,

                    "source_row_id": item_row.row_id or item_row.name,
                    "parent_row_id": data["parent_row_id"],
                    "parent_menu_item": data["parent_menu_item"],
                    "parent_menu_item_arabic": data["parent_menu_item_arabic"],

                    "item_code": item_code,
                    "item_name": item_name,
                    "item_name_arabic": item_name_arabic,
                    "base_item_qty": base_item_qty,
                    "required_item_qty": required_item_qty,
                    "uom": item_row.uom,

                    "close": is_closed,
                    "is_closed": is_closed,

                    "workstation": workstation,
                    "capacity_person_qty": capacity_person_qty,
                    "cooking_runs": cooking_runs,
                    "capacity_qty": capacity_qty,
                    "capacity_uom": capacity_uom,
                    "required_capacity_qty": required_capacity_qty,
                    "extra_person_qty": extra_person_qty,
                })

    return {
        "items": result,
        "total_person_qty": total_person_qty
    }