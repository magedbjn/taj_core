import json
import frappe
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, flt

from erpnext.manufacturing.doctype.work_order import work_order as core_work_order

SETTING_FIELD = "taj_keep_rm_qty"


@frappe.whitelist()
def create_pick_list(source_name, target_doc=None, for_qty=None):
	# v15-safe: same behavior as standard, with safe fallback
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


@frappe.whitelist()
def make_stock_entry(work_order_id, purpose, qty=None, target_warehouse=None):
	result = core_work_order.make_stock_entry(
		work_order_id=work_order_id,
		purpose=purpose,
		qty=qty,
		target_warehouse=target_warehouse,
	)

	# Keep v15 standard behavior for all other purposes
	if purpose != "Manufacture":
		return result

	enabled = cint(frappe.db.get_single_value("Manufacturing Settings", SETTING_FIELD) or 0)
	if not enabled:
		return result

	work_order = frappe.get_doc("Work Order", work_order_id)
	stock_entry = frappe.get_doc(result)

	_keep_raw_material_qty_same_as_work_order(stock_entry, work_order)

	# Prevent BOM re-generation in the same draft
	stock_entry.from_bom = 0

	return stock_entry.as_dict()


def _keep_raw_material_qty_same_as_work_order(stock_entry, work_order):
	finished_rows = []
	other_rows = []
	issue_templates = {}

	for row in stock_entry.items:
		rowd = row.as_dict()

		if rowd.get("is_finished_item"):
			finished_rows.append(rowd)
			continue

		if rowd.get("s_warehouse"):
			issue_templates.setdefault(rowd.get("item_code"), rowd)
			continue

		other_rows.append(rowd)

	stock_entry.set("items", [])

	for rowd in finished_rows:
		stock_entry.append("items", rowd)

	for req in work_order.required_items:
		req_qty = flt(req.required_qty)
		if req_qty <= 0:
			continue

		template = issue_templates.get(req.item_code, {})

		stock_entry.append(
			"items",
			{
				"item_code": req.item_code,
				"item_name": req.item_name,
				"description": req.description,
				"s_warehouse": req.source_warehouse or template.get("s_warehouse"),
				"qty": req_qty,
				"transfer_qty": req_qty,
				"uom": req.stock_uom or template.get("uom"),
				"stock_uom": req.stock_uom or template.get("stock_uom"),
				"conversion_factor": template.get("conversion_factor") or 1,
				"basic_rate": template.get("basic_rate") or req.rate or 0,
				"allow_zero_valuation_rate": template.get("allow_zero_valuation_rate") or 1,
				"expense_account": template.get("expense_account"),
				"cost_center": template.get("cost_center"),
				"original_item": req.item_code,
			},
		)

	for rowd in other_rows:
		stock_entry.append("items", rowd)