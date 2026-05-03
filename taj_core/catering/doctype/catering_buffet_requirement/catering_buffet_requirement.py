import math

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt


class CateringBuffetRequirement(Document):
    pass


MEAL_ORDER = {
    "Breakfast": 1,
    "Lunch": 2,
    "Dinner": 3,
    "Disposable": 4,
}


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
            item_code=row.get("item_code"),
            item_name=row.get("item_name"),
            item_name_arabic=row.get("item_name_arabic"),
        )

        if not key:
            continue

        if key not in capacity_map:
            capacity_map[key] = {
                "workstation": row.get("workstation") or "",
                "workstation_load_qty": flt(row.get("workstation_load_qty")),
                "capacity_qty": flt(row.get("capacity_qty")),
                "capacity_uom": row.get("capacity_uom") or "",
            }

    return capacity_map


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


def get_parent_display_names(row):
    _item_code, item_name, item_name_arabic = get_item_display_names(row)
    return item_name, item_name_arabic


def get_menu_service_meals(menu_doc):
    pairs = {}
    period_sort_map = {}

    service_periods = list({
        row.service_period
        for row in menu_doc.items
        if row.get("service_period")
    })

    if service_periods:
        period_docs = frappe.get_all(
            "Catering Service Period",
            filters={"name": ["in", service_periods]},
            fields=["name", "sort_order"],
        )

        for period in period_docs:
            period_sort_map[period.name] = cint(period.sort_order)

    for row in menu_doc.items:
        service_period = row.get("service_period")
        meal_type = row.get("meal_type")

        if not service_period or not meal_type:
            continue

        key = (service_period, meal_type)

        if key not in pairs:
            pairs[key] = {
                "service_period": service_period,
                "meal_type": meal_type,
                "period_sort": period_sort_map.get(service_period, 9999),
                "meal_sort": MEAL_ORDER.get(meal_type, 9999),
            }

    return sorted(
        pairs.values(),
        key=lambda d: (
            d.get("period_sort") or 9999,
            d.get("service_period") or "",
            d.get("meal_sort") or 9999,
            d.get("meal_type") or "",
        ),
    )


def get_effective_requirement_items(menu_doc):
    rows = list(menu_doc.items or [])

    prepared_rows = []
    parent_has_children = set()
    row_by_key = {}
    last_parent_by_context = {}
    active_section_by_context = {}

    for row in rows:
        context_key = (row.get("service_period"), row.get("meal_type"))

        if row.row_type == "Section":
            active_section_by_context[context_key] = row.section or ""
            continue

        row_key = row.row_id or row.name
        row_by_key[row_key] = row

        parent_row_id = ""
        parent_menu_item = ""
        parent_menu_item_arabic = ""

        if row.row_type in ("Item", "New Item"):
            last_parent_by_context[context_key] = row

        elif row.row_type == "Sub Item":
            parent_row = None

            if row.parent_row_id:
                parent_row = row_by_key.get(row.parent_row_id)

            if not parent_row:
                parent_row = last_parent_by_context.get(context_key)

            if parent_row:
                parent_key = parent_row.row_id or parent_row.name
                parent_has_children.add(parent_key)

                parent_row_id = parent_key
                parent_menu_item, parent_menu_item_arabic = get_parent_display_names(parent_row)

        prepared_rows.append({
            "row": row,
            "row_key": row_key,
            "section": active_section_by_context.get(context_key, ""),
            "parent_row_id": parent_row_id or row.parent_row_id or "",
            "parent_menu_item": parent_menu_item,
            "parent_menu_item_arabic": parent_menu_item_arabic,
        })

    effective_rows = []

    for data in prepared_rows:
        row = data["row"]

        if row.row_type in ("Item", "New Item"):
            if data["row_key"] not in parent_has_children:
                effective_rows.append(data)

        elif row.row_type == "Sub Item":
            effective_rows.append(data)

    return effective_rows


@frappe.whitelist()
def get_buffet_plan():
    center_filters = {}

    if frappe.get_meta("Catering Center").has_field("disabled"):
        center_filters["disabled"] = 0

    centers = frappe.get_all(
        "Catering Center",
        filters=center_filters,
        fields=[
            "name",
            "center_name",
            "catering_menu",
            "person_qty",
        ],
        order_by="center_name asc, name asc",
    )

    result = []

    for center in centers:
        if not center.catering_menu:
            continue

        menu_doc = frappe.get_doc("Catering Menu", center.catering_menu)
        service_meals = get_menu_service_meals(menu_doc)

        if not service_meals:
            continue

        center_doc = frappe.get_doc("Catering Center", center.name)

        for buffet in center_doc.buffet:
            buffet_name = buffet.get("buffet") or ""
            buffet_company = buffet.get("buffet_company") or ""
            person_qty = flt(buffet.get("person_qty") or 0)
            is_closed = 1 if buffet.get("is_closed") else 0

            if is_closed:
                continue

            if not buffet_name and not buffet_company:
                continue

            for sm in service_meals:
                result.append({
                    "service_period": sm.get("service_period"),
                    "meal_type": sm.get("meal_type"),

                    "catering_center": center.name,
                    "center_name": center.center_name,
                    "catering_menu": center.catering_menu,

                    "buffet": buffet_name,
                    "buffet_company": buffet_company,
                    "person_qty": person_qty,
                    "is_closed": is_closed,
                })

    return result


@frappe.whitelist()
def get_buffet_requirements(buffets=None):
    if isinstance(buffets, str):
        buffets = frappe.parse_json(buffets)

    buffets = buffets or []

    capacity_map = get_capacity_map()
    menu_cache = {}

    result = []
    total_person_qty = 0

    for buffet in buffets:
        service_period = buffet.get("service_period")
        meal_type = buffet.get("meal_type")
        catering_menu = buffet.get("catering_menu")
        catering_center = buffet.get("catering_center")

        person_qty = flt(buffet.get("person_qty") or 0)
        is_closed = 1 if buffet.get("is_closed") else 0

        if not service_period or not meal_type or not catering_menu:
            continue

        if person_qty <= 0:
            continue

        if catering_menu not in menu_cache:
            menu_cache[catering_menu] = frappe.get_doc("Catering Menu", catering_menu)

        menu_doc = menu_cache[catering_menu]
        menu_person_qty = flt(menu_doc.get("qty") or menu_doc.get("quantity") or 0)

        if menu_person_qty <= 0:
            continue

        person_ratio = person_qty / menu_person_qty
        total_person_qty += person_qty

        effective_items = get_effective_requirement_items(menu_doc)

        for data in effective_items:
            item_row = data["row"]

            if item_row.row_type not in ("Item", "New Item", "Sub Item"):
                continue

            if item_row.service_period != service_period:
                continue

            if item_row.meal_type != meal_type:
                continue

            base_item_qty = flt(item_row.qty)

            if base_item_qty <= 0:
                continue

            required_item_qty = base_item_qty * person_ratio

            item_code, item_name, item_name_arabic = get_item_display_names(item_row)

            if item_row.row_type in ("Item", "Sub Item"):
                capacity_key = get_capacity_key(item_code=item_code)
            else:
                capacity_key = get_capacity_key(
                    item_name=item_name,
                    item_name_arabic=item_name_arabic,
                )

            capacity = capacity_map.get(capacity_key, {})

            workstation = capacity.get("workstation") or ""
            workstation_load_qty = flt(capacity.get("workstation_load_qty"))
            capacity_qty = flt(capacity.get("capacity_qty"))
            capacity_uom = capacity.get("capacity_uom") or ""

            cooking_runs = 0
            required_capacity_qty = 0
            extra_person_qty = 0

            if (
                not is_closed
                and workstation_load_qty > 0
                and capacity_qty > 0
            ):
                cooking_runs = int(math.ceil(person_qty / workstation_load_qty))
                required_capacity_qty = cooking_runs * capacity_qty
                extra_person_qty = (cooking_runs * workstation_load_qty) - person_qty

            result.append({
                "catering_center": catering_center,
                "center_name": buffet.get("center_name") or "",
                "catering_menu": catering_menu,

                "buffet": buffet.get("buffet") or "",
                "buffet_company": buffet.get("buffet_company") or "",
                "person_qty": person_qty,
                "menu_person_qty": menu_person_qty,
                "person_ratio": person_ratio,

                "service_period": service_period,
                "meal_type": meal_type,
                "section": data.get("section") or "",
                "row_type": item_row.row_type,

                "source_row_id": item_row.row_id or item_row.name,
                "parent_row_id": data.get("parent_row_id") or "",
                "parent_menu_item": data.get("parent_menu_item") or "",
                "parent_menu_item_arabic": data.get("parent_menu_item_arabic") or "",

                "item_code": item_code,
                "item_name": item_name,
                "item_name_arabic": item_name_arabic,
                "base_item_qty": base_item_qty,
                "required_item_qty": required_item_qty,
                "uom": item_row.uom,

                "is_closed": is_closed,

                "workstation": workstation,
                "workstation_load_qty": workstation_load_qty,
                "cooking_runs": cooking_runs,
                "capacity_qty": capacity_qty,
                "capacity_uom": capacity_uom,
                "required_capacity_qty": required_capacity_qty,
                "extra_person_qty": extra_person_qty,
            })

    return {
        "items": result,
        "total_person_qty": total_person_qty,
    }