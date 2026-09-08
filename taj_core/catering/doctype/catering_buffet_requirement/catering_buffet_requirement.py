import math

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate


class CateringBuffetRequirement(Document):
    def validate(self):
        self.total_person_qty = get_total_center_person_qty(
            [row.as_dict() for row in self.get("buffets") or []]
        )


MEAL_ORDER = {
    "Breakfast": 1,
    "Lunch": 2,
    "Dinner": 3,
}

def get_year_date_range(catering_year=None):
    """
    يرجع بداية ونهاية السنة.
    إذا كان catering_year موجود كـ Fiscal Year يستخدم تواريخه.
    وإلا يستخدم 01-01 إلى 12-31.
    """

    year_text = str(catering_year or getdate().year)

    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        year_text,
        ["year_start_date", "year_end_date"],
        as_dict=True,
    )

    if fiscal_year and fiscal_year.year_start_date and fiscal_year.year_end_date:
        return fiscal_year.year_start_date, fiscal_year.year_end_date

    return f"{year_text}-01-01", f"{year_text}-12-31"

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

@frappe.whitelist()
def get_catering_centers_for_year(catering_year=None):
    """
    يرجع المراكز الموجودة خلال السنة المختارة.
    يستخدم posting_date في Catering Center.
    """

    start_date, end_date = get_year_date_range(catering_year)

    filters = {}

    center_meta = frappe.get_meta("Catering Center")

    if center_meta.has_field("disabled"):
        filters["disabled"] = 0

    if center_meta.has_field("posting_date"):
        filters["posting_date"] = ["between", [start_date, end_date]]

    centers = frappe.get_list(
        "Catering Center",
        filters=filters,
        fields=[
            "name",
            "center_name",
            "catering_menu",
            "person_qty",
            "posting_date",
        ],
        order_by="center_name asc, name asc",
    )

    result = []

    for center in centers:
        result.append({
            "name": center.name,
            "center_name": center.center_name or center.name,
            "catering_menu": center.catering_menu or "",
            "person_qty": flt(center.person_qty or 0),
            "posting_date": center.posting_date,
        })

    return result

def get_effective_requirement_items(menu_doc):
    """
    إذا Item / New Item تحته Sub Item:
        لا يحسب الأب
        يحسب Sub Items

    إذا Item / New Item لا يوجد تحته Sub Item:
        يحسب نفسه
    """

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
def get_buffet_plan(catering_year=None, catering_centers=None):
    """
    يولد Service Plan حسب المراكز المختارة من Dialog.

    إذا المركز فيه Buffet:
        يولد صف لكل Buffet لكل Service Period + Meal Type

    إذا المركز بدون Buffet:
        يولد صف Center كامل لكل Service Period + Meal Type
    """

    if isinstance(catering_centers, str):
        catering_centers = frappe.parse_json(catering_centers)

    catering_centers = catering_centers or []

    center_filters = {}

    center_meta = frappe.get_meta("Catering Center")

    if center_meta.has_field("disabled"):
        center_filters["disabled"] = 0

    if catering_centers:
        center_filters["name"] = ["in", catering_centers]
    else:
        start_date, end_date = get_year_date_range(catering_year)

        if center_meta.has_field("posting_date"):
            center_filters["posting_date"] = ["between", [start_date, end_date]]

    centers = frappe.get_list(
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
        menu_doc.check_permission("read")
        service_meals = get_menu_service_meals(menu_doc)

        if not service_meals:
            continue

        center_doc = frappe.get_doc("Catering Center", center.name)
        center_doc.check_permission("read")
        buffet_rows = list(center_doc.get("buffet") or [])

        if buffet_rows:
            for buffet in buffet_rows:
                buffet_name = buffet.get("buffet") or ""
                buffet_company = buffet.get("buffet_company") or ""
                person_qty = flt(buffet.get("person_qty") or 0)
                is_closed = 1 if buffet.get("is_closed") else 0

                if person_qty <= 0:
                    continue

                for sm in service_meals:
                    result.append({
                        "plan_type": "Buffet",

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

        else:
            center_person_qty = flt(center.person_qty or 0)

            if center_person_qty <= 0:
                continue

            for sm in service_meals:
                result.append({
                    "plan_type": "Center",

                    "service_period": sm.get("service_period"),
                    "meal_type": sm.get("meal_type"),

                    "catering_center": center.name,
                    "center_name": center.center_name,
                    "catering_menu": center.catering_menu,

                    "buffet": "",
                    "buffet_company": "",
                    "person_qty": center_person_qty,
                    "is_closed": 0,
                })

    result = sort_service_plan_rows(result)

    return {
        "rows": result,
        "total_person_qty": get_total_center_person_qty(result),
    }

@frappe.whitelist()
def get_buffet_requirements(buffets=None):
    """
    يحسب الأصناف بناءً على جدول Service Plan / buffets المرسل من الواجهة.
    لا يعتمد مباشرة على Catering Center هنا.
    """

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

        if is_closed:
            continue

        if not service_period or not meal_type or not catering_menu:
            continue

        if person_qty <= 0:
            continue

        if catering_menu not in menu_cache:
            menu_doc = frappe.get_doc("Catering Menu", catering_menu)
            menu_doc.check_permission("read")
            menu_cache[catering_menu] = menu_doc

        menu_doc = menu_cache[catering_menu]
        menu_person_qty = flt(menu_doc.get("qty") or menu_doc.get("quantity") or 0)

        if menu_person_qty <= 0:
            continue

        person_ratio = person_qty / menu_person_qty
        # total_person_qty += person_qty

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

            if workstation_load_qty > 0 and capacity_qty > 0:
                # cooking_runs = int(math.ceil(person_qty / workstation_load_qty))
                required_capacity_qty = math.ceil(required_item_qty / capacity_qty)
                cooking_runs = math.ceil(required_capacity_qty / workstation_load_qty)
                extra_person_qty = (cooking_runs * workstation_load_qty) - person_qty

            result.append({
                "plan_type": buffet.get("plan_type") or "",

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

    result = sort_service_plan_rows(result)

    return {
        "items": result,
        "total_person_qty": get_total_center_person_qty(buffets),
    }

def get_service_period_sort_map():
    period_sort_map = {}

    periods = frappe.get_all(
        "Catering Service Period",
        fields=["name", "sort_order"],
    )

    for period in periods:
        period_sort_map[period.name] = cint(period.sort_order)

    return period_sort_map

def sort_service_plan_rows(rows):
    period_sort_map = get_service_period_sort_map()

    return sorted(
        rows,
        key=lambda d: (
            period_sort_map.get(d.get("service_period"), 9999),
            d.get("service_period") or "",
            MEAL_ORDER.get(d.get("meal_type"), 9999),
            d.get("meal_type") or "",
            d.get("center_name") or "",
            d.get("plan_type") or "",
            d.get("buffet") or "",
            d.get("buffet_company") or "",
        ),
    )

def get_total_center_person_qty(service_plan_rows):
    """
    Total Person Qty يحسب عدد المركز مرة واحدة فقط.
    لا يجمع كل يوم ولا كل وجبة ولا كل بوفيه.
    """

    center_names = set()

    for row in service_plan_rows or []:
        if row.get("is_closed"):
            continue

        if row.get("catering_center"):
            center_names.add(row.get("catering_center"))

    total = 0

    for center_name in center_names:
        total += flt(
            frappe.db.get_value("Catering Center", center_name, "person_qty") or 0
        )

    return total