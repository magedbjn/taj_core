import json
import frappe
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, flt

from erpnext.manufacturing.doctype.work_order import work_order as core_work_order

SETTING_FIELD = "taj_keep_rm_qty"


@frappe.whitelist()
def create_pick_list(source_name, target_doc=None, for_qty=None):
    for_qty = for_qty or (json.loads(target_doc).get("for_qty") if target_doc else None)

    wo = frappe.get_doc("Work Order", source_name)
    max_finished_goods_qty = flt(wo.qty) or 1
    for_qty = flt(for_qty or max_finished_goods_qty)

    item_codes = [d.item_code for d in (wo.required_items or []) if d.item_code]

    bom_items = set()
    if item_codes:
        bom_items = set(
            frappe.get_all(
                "BOM",
                filters={
                    "item": ["in", item_codes],
                    "is_default": 1,
                    "docstatus": 1,
                },
                pluck="item",
            )
        )

    def update_item_quantity(source, target, source_parent):
        pending_to_issue = flt(source.required_qty) - flt(source.transferred_qty)
        desired_to_transfer = (flt(source.required_qty) / max_finished_goods_qty) * for_qty

        qty = 0
        if desired_to_transfer <= pending_to_issue:
            qty = desired_to_transfer
        elif pending_to_issue > 0:
            qty = pending_to_issue

        if qty:
            target.qty = qty
            target.stock_qty = qty
            target.uom = frappe.get_value("Item", source.item_code, "stock_uom")
            target.stock_uom = target.uom
            target.conversion_factor = 1
        else:
            target.delete()

    doc = get_mapped_doc(
        "Work Order",
        source_name,
        {
            "Work Order": {"doctype": "Pick List", "validation": {"docstatus": ["=", 1]}},
            "Work Order Item": {
                "doctype": "Pick List Item",
                "postprocess": update_item_quantity,
                "condition": lambda d: abs(flt(d.transferred_qty)) < abs(flt(d.required_qty))
                and d.item_code not in bom_items,
            },
        },
        target_doc,
    )

    doc.purpose = "Material Transfer for Manufacture"
    doc.for_qty = for_qty

    parent_wh = "Raw Materials - Taj"
    if not frappe.db.exists("Warehouse", parent_wh):
        frappe.throw(f"Warehouse not found: {parent_wh}")

    doc.parent_warehouse = parent_wh
    doc.set_item_locations()
    return doc


def is_keep_rm_qty_enabled() -> bool:
    return cint(frappe.db.get_single_value("Manufacturing Settings", SETTING_FIELD) or 0) == 1


def rebuild_manufacture_rm_rows(stock_entry, work_order):
    finished_rows = []
    scrap_rows = []
    rm_templates = {}

    for row in stock_entry.items:
        rowd = row.as_dict()

        if rowd.get("is_finished_item"):
            finished_rows.append(rowd)
            continue

        if rowd.get("is_scrap_item"):
            scrap_rows.append(rowd)
            continue

        if rowd.get("s_warehouse"):
            rm_templates.setdefault((rowd.get("item_code"), rowd.get("s_warehouse")), rowd)
            rm_templates.setdefault((rowd.get("item_code"), None), rowd)

            if rowd.get("original_item"):
                rm_templates.setdefault((rowd.get("original_item"), rowd.get("s_warehouse")), rowd)
                rm_templates.setdefault((rowd.get("original_item"), None), rowd)

    stock_entry.set("items", [])

    for rowd in finished_rows:
        stock_entry.append("items", rowd)

    for req in work_order.required_items:
        if not cint(getattr(req, "include_item_in_manufacturing", 1)):
            continue

        req_qty = flt(req.required_qty)
        if req_qty <= 0:
            continue

        original_item = getattr(req, "original_item", None) or req.item_code

        template = (
            rm_templates.get((req.item_code, req.source_warehouse))
            or rm_templates.get((req.item_code, None))
            or rm_templates.get((original_item, req.source_warehouse))
            or rm_templates.get((original_item, None))
            or {}
        )

        stock_entry.append(
            "items",
            {
                "item_code": req.item_code,
                "item_name": req.item_name,
                "description": req.description,
                "s_warehouse": req.source_warehouse or template.get("s_warehouse") or stock_entry.from_warehouse,
                "t_warehouse": "",
                "qty": req_qty,
                "transfer_qty": req_qty,
                "uom": req.stock_uom or template.get("uom"),
                "stock_uom": req.stock_uom or template.get("stock_uom"),
                "conversion_factor": template.get("conversion_factor") or 1,
                "basic_rate": template.get("basic_rate") or req.rate or 0,
                "allow_zero_valuation_rate": template.get("allow_zero_valuation_rate") or 1,
                "expense_account": template.get("expense_account"),
                "cost_center": template.get("cost_center"),
                "original_item": original_item,
                "batch_no": template.get("batch_no"),
                "serial_no": template.get("serial_no"),
                "serial_and_batch_bundle": template.get("serial_and_batch_bundle"),
                "use_serial_batch_fields": template.get("use_serial_batch_fields") or 0,
            },
        )

    for rowd in scrap_rows:
        stock_entry.append("items", rowd)


@frappe.whitelist()
def make_stock_entry(work_order_id, purpose, qty=None, target_warehouse=None):
    result = core_work_order.make_stock_entry(
        work_order_id=work_order_id,
        purpose=purpose,
        qty=qty,
        target_warehouse=target_warehouse,
    )

    if purpose != "Manufacture":
        return result

    if not is_keep_rm_qty_enabled():
        return result

    work_order = frappe.get_doc("Work Order", work_order_id)
    stock_entry = frappe.get_doc(result)

    # هذا الوسم هو الذي يميز أن المستند جاء من زر Finish
    stock_entry.taj_from_finish_button = 1

    rebuild_manufacture_rm_rows(stock_entry, work_order)

    stock_entry.from_bom = 1
    stock_entry.bom_no = work_order.bom_no
    stock_entry.use_multi_level_bom = work_order.use_multi_level_bom

    if qty is not None:
        stock_entry.fg_completed_qty = flt(qty)
    elif not stock_entry.fg_completed_qty:
        stock_entry.fg_completed_qty = flt(work_order.qty) - flt(work_order.produced_qty)

    return stock_entry.as_dict()