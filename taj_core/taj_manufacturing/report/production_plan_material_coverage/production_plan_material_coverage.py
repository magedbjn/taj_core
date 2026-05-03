import copy

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.manufacturing.doctype.production_plan.production_plan import (
    get_bin_details as erpnext_get_bin_details,
    get_items_for_material_requests,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})

    if not filters.get("production_plan"):
        frappe.throw(_("Production Plan is required"))

    production_plan = frappe.get_doc("Production Plan", filters.production_plan)

    columns = get_columns()
    data = get_data(production_plan, filters)

    return columns, data


def get_columns():
    return [
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 140,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Warehouse"),
            "fieldname": "warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 160,
        },
        {
            "label": _("Main BOM Item"),
            "fieldname": "main_bom_item",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "label": _("Stock UOM"),
            "fieldname": "stock_uom",
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "label": _("Qty As Per BOM"),
            "fieldname": "required_bom_qty",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "label": _("Actual Qty"),
            "fieldname": "actual_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Indented Qty"),
            "fieldname": "indented_qty",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Ordered Qty"),
            "fieldname": "ordered_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Planned Qty"),
            "fieldname": "planned_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Reserved Qty"),
            "fieldname": "reserved_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Reserved for Production"),
            "fieldname": "reserved_qty_for_production",
            "fieldtype": "Float",
            "width": 155,
        },
        {
            "label": _("Projected Qty"),
            "fieldname": "projected_qty",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Shortage Qty"),
            "fieldname": "shortage_qty",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Purchase UOM"),
            "fieldname": "uom",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Conversion Factor"),
            "fieldname": "conversion_factor",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Plan to Request Qty"),
            "fieldname": "plan_to_request_qty",
            "fieldtype": "Float",
            "width": 140,
        },
        {
            "label": _("Open MR Qty"),
            "fieldname": "open_mr_qty",
            "fieldtype": "Float",
            "width": 120,
        },
        {
            "label": _("Open Material Requests"),
            "fieldname": "open_material_requests",
            "fieldtype": "Data",
            "width": 300,
        },
        {
            "label": _("MR Production Plans"),
            "fieldname": "open_mr_production_plans",
            "fieldtype": "Data",
            "width": 220,
        },
        {
            "label": _("MR Visibility"),
            "fieldname": "mr_visibility",
            "fieldtype": "Data",
            "width": 170,
        },
        {
            "label": _("Hidden Reason"),
            "fieldname": "hidden_reason",
            "fieldtype": "Data",
            "width": 390,
        },
        {
            "label": _("Decision"),
            "fieldname": "decision",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Reason"),
            "fieldname": "reason",
            "fieldtype": "Data",
            "width": 390,
        },
        {
            "label": _("Effective Bin Warehouse"),
            "fieldname": "effective_bin_warehouse",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 170,
        },
        {
            "label": _("Bin Details"),
            "fieldname": "bin_details",
            "fieldtype": "Data",
            "width": 460,
        },
        {
            "label": _("Is Hidden From MR"),
            "fieldname": "is_hidden_from_mr",
            "fieldtype": "Check",
            "hidden": 1,
        },
        {
            "label": _("MR Visibility Code"),
            "fieldname": "mr_visibility_code",
            "fieldtype": "Data",
            "hidden": 1,
        },
        {
            "label": _("Decision Code"),
            "fieldname": "decision_code",
            "fieldtype": "Data",
            "hidden": 1,
        },
    ]


def get_data(production_plan, filters):
    raw_items = get_all_bom_materials(production_plan)
    raw_items = merge_raw_items(raw_items)

    data = []

    for item in raw_items:
        item = frappe._dict(item)

        if filters.get("item_code") and item.item_code != filters.item_code:
            continue

        warehouse = (
            filters.get("warehouse")
            or item.get("warehouse")
            or production_plan.get("for_warehouse")
            or item.get("source_warehouse")
            or item.get("default_warehouse")
        )

        effective_bin, bin_details = get_effective_bin_details(
            item_code=item.item_code,
            company=production_plan.company,
            warehouse=warehouse,
        )

        shortage_qty = calculate_shortage_qty(
            production_plan=production_plan,
            item=item,
            projected_qty=flt(effective_bin.projected_qty),
            force_ignore_projected_qty=filters.get("ignore_projected_qty"),
        )

        conversion_factor = flt(item.get("conversion_factor")) or 1
        plan_to_request_qty = shortage_qty / conversion_factor if conversion_factor else shortage_qty

        open_mr_qty, open_mrs, open_mr_production_plans = get_open_material_requests(
            item_code=item.item_code,
            warehouse=warehouse,
            company=production_plan.company,
        )

        (
            mr_visibility_code,
            is_hidden_from_mr,
            mr_visibility,
            hidden_reason,
        ) = get_mr_visibility(
            required_bom_qty=flt(item.required_bom_qty),
            shortage_qty=shortage_qty,
            projected_qty=flt(effective_bin.projected_qty),
            indented_qty=flt(effective_bin.indented_qty),
            open_mr_qty=open_mr_qty,
            ignore_projected_qty=filters.get("ignore_projected_qty")
            or production_plan.get("ignore_existing_ordered_qty"),
        )

        decision_code, decision, reason = get_decision(
            required_bom_qty=flt(item.required_bom_qty),
            shortage_qty=shortage_qty,
            actual_qty=flt(effective_bin.actual_qty),
            indented_qty=flt(effective_bin.indented_qty),
            projected_qty=flt(effective_bin.projected_qty),
            open_mr_qty=open_mr_qty,
            ignore_projected_qty=filters.get("ignore_projected_qty")
            or production_plan.get("ignore_existing_ordered_qty"),
        )

        row = {
            "item_code": item.item_code,
            "item_name": item.get("item_name"),
            "warehouse": warehouse,
            "main_bom_item": item.get("main_bom_item"),
            "stock_uom": item.get("stock_uom"),
            "required_bom_qty": flt(item.required_bom_qty),
            "actual_qty": flt(effective_bin.actual_qty),
            "indented_qty": flt(effective_bin.indented_qty),
            "ordered_qty": flt(effective_bin.ordered_qty),
            "planned_qty": flt(effective_bin.planned_qty),
            "reserved_qty": flt(effective_bin.reserved_qty),
            "reserved_qty_for_production": flt(effective_bin.reserved_qty_for_production),
            "projected_qty": flt(effective_bin.projected_qty),
            "shortage_qty": shortage_qty,
            "uom": item.get("uom") or item.get("purchase_uom") or item.get("stock_uom"),
            "conversion_factor": conversion_factor,
            "plan_to_request_qty": plan_to_request_qty,
            "open_mr_qty": open_mr_qty,
            "open_material_requests": open_mrs,
            "open_mr_production_plans": open_mr_production_plans,
            "mr_visibility_code": mr_visibility_code,
            "mr_visibility": mr_visibility,
            "hidden_reason": hidden_reason,
            "is_hidden_from_mr": 1 if is_hidden_from_mr else 0,
            "decision_code": decision_code,
            "decision": decision,
            "reason": reason,
            "effective_bin_warehouse": effective_bin.get("warehouse"),
            "bin_details": bin_details,
        }

        if filters.get("show_only_shortage") and shortage_qty <= 0:
            continue

        if filters.get("show_only_hidden_from_mr") and not is_hidden_from_mr:
            continue

        if filters.get("show_only_covered_by_open_mr") and decision_code != "covered_by_open_mr":
            continue

        if filters.get("show_only_covered_by_projected_qty") and decision_code not in (
            "covered_by_open_mr",
            "covered_by_projected_qty",
            "covered_by_stock",
        ):
            continue

        data.append(row)

    return data


def get_all_bom_materials(production_plan):
    """
    ERPNext hides raw materials from mr_items when Projected Qty covers the requirement.
    This report first forces ignore_existing_ordered_qty = 1 only to fetch all BOM materials.
    Then it recalculates the real coverage separately.
    """
    doc = frappe._dict(copy.deepcopy(production_plan.as_dict()))
    doc.ignore_existing_ordered_qty = 1
    doc.mr_items = []

    old_show_qty_in_stock_uom = frappe.flags.get("show_qty_in_stock_uom", None)

    try:
        frappe.flags.show_qty_in_stock_uom = 1
        return get_items_for_material_requests(doc, warehouses=[])
    finally:
        frappe.flags.show_qty_in_stock_uom = old_show_qty_in_stock_uom or 0


def merge_raw_items(raw_items):
    merged = {}

    for row in raw_items:
        row = frappe._dict(row)

        conversion_factor = flt(row.get("conversion_factor")) or 1
        required_bom_qty = flt(row.get("required_bom_qty"))

        if not required_bom_qty:
            required_bom_qty = flt(row.get("quantity")) * conversion_factor

        key = (
            row.get("item_code"),
            row.get("warehouse"),
            row.get("stock_uom"),
            row.get("uom"),
            conversion_factor,
            row.get("material_request_type"),
        )

        if key not in merged:
            merged[key] = frappe._dict(row)
            merged[key].required_bom_qty = required_bom_qty
            merged[key].quantity = flt(row.get("quantity"))
            merged[key].safety_stock = flt(row.get("safety_stock"))
            merged[key].min_order_qty = flt(row.get("min_order_qty"))
            merged[key].conversion_factor = conversion_factor
            merged[key].main_bom_items = set()

            if row.get("main_bom_item"):
                merged[key].main_bom_items.add(row.get("main_bom_item"))

        else:
            merged[key].required_bom_qty += required_bom_qty
            merged[key].quantity += flt(row.get("quantity"))
            merged[key].safety_stock = max(
                flt(merged[key].safety_stock),
                flt(row.get("safety_stock")),
            )
            merged[key].min_order_qty = max(
                flt(merged[key].min_order_qty),
                flt(row.get("min_order_qty")),
            )

            if row.get("main_bom_item"):
                merged[key].main_bom_items.add(row.get("main_bom_item"))

    result = []

    for row in merged.values():
        if row.get("main_bom_items"):
            row.main_bom_item = ", ".join(sorted(row.main_bom_items))
        result.append(row)

    return result


def calculate_shortage_qty(
    production_plan,
    item,
    projected_qty,
    force_ignore_projected_qty=False,
):
    required_bom_qty = flt(item.get("required_bom_qty"))
    min_order_qty = flt(item.get("min_order_qty"))
    safety_stock = flt(item.get("safety_stock"))

    ignore_projected_qty = (
        force_ignore_projected_qty
        or production_plan.get("ignore_existing_ordered_qty")
    )

    if ignore_projected_qty or projected_qty < 0:
        shortage_qty = required_bom_qty
    else:
        shortage_qty = max(0, required_bom_qty - projected_qty)

    if (
        production_plan.get("consider_minimum_order_qty")
        and shortage_qty > 0
        and min_order_qty
        and shortage_qty < min_order_qty
    ):
        shortage_qty = min_order_qty

    if production_plan.get("include_safety_stock"):
        shortage_qty += safety_stock

    return flt(shortage_qty)


def get_effective_bin_details(item_code, company, warehouse=None):
    """
    Mirrors ERPNext Production Plan behavior:
    get_bin_details returns possible Bin rows and Production Plan uses the first row.
    This is important because MR visibility must match what Production Plan does.
    """
    fields = [
        "actual_qty",
        "indented_qty",
        "ordered_qty",
        "planned_qty",
        "reserved_qty",
        "reserved_qty_for_production",
        "projected_qty",
    ]

    effective_bin = frappe._dict({field: 0 for field in fields})
    effective_bin.warehouse = warehouse

    row_arg = frappe._dict({"item_code": item_code})

    bin_rows = erpnext_get_bin_details(
        row=row_arg,
        company=company,
        for_warehouse=warehouse,
    )

    details = []

    for idx, row in enumerate(bin_rows or []):
        row = frappe._dict(row)

        if idx == 0:
            effective_bin.warehouse = row.get("warehouse")
            for field in fields:
                effective_bin[field] = flt(row.get(field))

        details.append(
            "{warehouse}: Actual {actual_qty}, Indented {indented_qty}, Ordered {ordered_qty}, Planned {planned_qty}, Reserved {reserved_qty}, Reserved for Production {reserved_qty_for_production}, Projected {projected_qty}".format(
                warehouse=row.get("warehouse"),
                actual_qty=flt(row.get("actual_qty")),
                indented_qty=flt(row.get("indented_qty")),
                ordered_qty=flt(row.get("ordered_qty")),
                planned_qty=flt(row.get("planned_qty")),
                reserved_qty=flt(row.get("reserved_qty")),
                reserved_qty_for_production=flt(row.get("reserved_qty_for_production")),
                projected_qty=flt(row.get("projected_qty")),
            )
        )

    return effective_bin, " | ".join(details)


def get_warehouse_tree(warehouse=None, company=None):
    if warehouse:
        wh = frappe.db.get_value(
            "Warehouse",
            warehouse,
            ["name", "company", "lft", "rgt"],
            as_dict=True,
        )

        if not wh:
            return [warehouse]

        warehouses = frappe.get_all(
            "Warehouse",
            filters={
                "company": wh.company,
                "lft": [">=", wh.lft],
                "rgt": ["<=", wh.rgt],
            },
            pluck="name",
        )

        return warehouses or [warehouse]

    if company:
        return frappe.get_all(
            "Warehouse",
            filters={"company": company},
            pluck="name",
        )

    return []


def get_open_material_requests(item_code, warehouse=None, company=None):
    warehouses = get_warehouse_tree(warehouse=warehouse, company=company)

    if not warehouses:
        return 0, "", ""

    rows = frappe.db.sql(
        """
        SELECT
            mr.name,
            mr.transaction_date,
            mr.status,
            mr.material_request_type,
            mri.warehouse,
            mri.qty,
            IFNULL(mri.ordered_qty, 0) AS ordered_qty,
            IFNULL(NULLIF(mri.conversion_factor, 0), 1) AS conversion_factor,
            mri.production_plan
        FROM `tabMaterial Request` mr
        INNER JOIN `tabMaterial Request Item` mri
            ON mri.parent = mr.name
        WHERE
            mr.docstatus = 1
            AND mr.status NOT IN ('Stopped', 'Cancelled')
            AND mri.item_code = %(item_code)s
            AND mri.warehouse IN %(warehouses)s
            AND mri.qty > IFNULL(mri.ordered_qty, 0)
        ORDER BY
            mr.transaction_date DESC,
            mr.name DESC
        """,
        {
            "item_code": item_code,
            "warehouses": tuple(warehouses),
        },
        as_dict=True,
    )

    total_pending_stock_qty = 0
    material_requests = []
    production_plans = []

    for row in rows:
        row = frappe._dict(row)

        pending_qty = flt(row.qty) - flt(row.ordered_qty)
        pending_stock_qty = pending_qty * (flt(row.conversion_factor) or 1)

        total_pending_stock_qty += pending_stock_qty

        material_requests.append(
            "{mr} / {warehouse} / {qty}".format(
                mr=row.name,
                warehouse=row.warehouse,
                qty=flt(pending_stock_qty),
            )
        )

        if row.production_plan:
            production_plans.append(row.production_plan)

    return (
        flt(total_pending_stock_qty),
        " | ".join(material_requests),
        " | ".join(sorted(set(production_plans))),
    )


def get_mr_visibility(
    required_bom_qty,
    shortage_qty,
    projected_qty,
    indented_qty,
    open_mr_qty,
    ignore_projected_qty=False,
):
    if ignore_projected_qty:
        return (
            "visible_ignore_projected_qty",
            False,
            _("Visible - Ignore Projected Qty"),
            _("Projected Qty is ignored, so the item will be shown with full BOM quantity."),
        )

    if required_bom_qty <= 0:
        return (
            "no_requirement",
            False,
            _("No Requirement"),
            _("BOM requirement is zero."),
        )

    if shortage_qty > 0:
        return (
            "visible_in_mr_items",
            False,
            _("Visible in MR Items"),
            _("There is a shortage after deducting Projected Qty."),
        )

    if projected_qty >= required_bom_qty:
        if indented_qty > 0 or open_mr_qty > 0:
            return (
                "hidden_from_mr_open_mr",
                True,
                _("Hidden from MR Items"),
                _("Projected Qty covers the requirement because of Indented Qty / open Material Requests."),
            )

        return (
            "hidden_from_mr_projected_qty",
            True,
            _("Hidden from MR Items"),
            _("Projected Qty covers the BOM requirement."),
        )

    return (
        "review",
        False,
        _("Review"),
        _("Please review stock and projected quantity."),
    )


def get_decision(
    required_bom_qty,
    shortage_qty,
    actual_qty,
    indented_qty,
    projected_qty,
    open_mr_qty,
    ignore_projected_qty=False,
):
    if required_bom_qty <= 0:
        return (
            "no_requirement",
            _("No Requirement"),
            _("BOM requirement is zero."),
        )

    if ignore_projected_qty:
        return (
            "ignore_projected_qty",
            _("Request Full BOM Qty"),
            _("Projected Qty is ignored by filter or Production Plan setting."),
        )

    if shortage_qty > 0:
        return (
            "need_material_request",
            _("Need Material Request"),
            _("Projected Qty is less than BOM requirement."),
        )

    if indented_qty > 0 or open_mr_qty > 0:
        return (
            "covered_by_open_mr",
            _("Covered by Open MR"),
            _("Indented Qty / open Material Requests are covering the BOM requirement."),
        )

    if actual_qty >= required_bom_qty:
        return (
            "covered_by_stock",
            _("Covered by Stock"),
            _("Actual Qty is enough to cover the BOM requirement."),
        )

    if projected_qty >= required_bom_qty:
        return (
            "covered_by_projected_qty",
            _("Covered by Projected Qty"),
            _("Projected Qty is enough to cover the BOM requirement."),
        )

    return (
        "review",
        _("Review"),
        _("Please review stock and open transactions."),
    )