import json
import frappe
from frappe.model.mapper import get_mapped_doc
from frappe.utils import flt


@frappe.whitelist()
def create_pick_list(source_name: str, target_doc=None, for_qty: float | None = None):
	# Keep ERPNext behavior: if for_qty is inside target_doc JSON, read it from there.
	if for_qty is None and target_doc:
		for_qty = json.loads(target_doc).get("for_qty")

	wo = frappe.get_doc("Work Order", source_name)

	# Collect item codes from required_items
	item_codes = [d.item_code for d in (wo.required_items or []) if d.item_code]

	# Build a set of items that have a BOM (Default + Submitted).
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

	max_finished_goods_qty = flt(wo.qty) or 1

	def update_item_quantity(source, target, source_parent):
		pending_to_issue = flt(source.required_qty) - flt(source.transferred_qty)
		desired_to_transfer = (flt(source.required_qty) / max_finished_goods_qty) * flt(
			for_qty or max_finished_goods_qty
		)

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
	doc.for_qty = for_qty or max_finished_goods_qty

	# ✅ Force parent_warehouse
	parent_wh = "Raw Materials - Taj"
	if not frappe.db.exists("Warehouse", parent_wh):
		frappe.throw(f"Warehouse not found: {parent_wh}")

	doc.parent_warehouse = parent_wh

	# Populate Item Locations as standard Pick List behavior (now constrained to parent_warehouse)
	doc.set_item_locations()
	return doc