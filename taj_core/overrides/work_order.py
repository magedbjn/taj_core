"""
Purpose
-------
Override ERPNext's Work Order -> "Create Pick List" so that the generated Pick List
automatically EXCLUDES any Work Order Items whose Item has a BOM.

What this does
--------------
- Reads the Work Order's `required_items`.
- Finds which of those items have a BOM (by default: only "Default" + "Submitted" BOMs).
- While mapping Work Order Items -> Pick List Items, it skips items found in that BOM set.
- Then it runs `set_item_locations()` to populate picking locations as usual.
"""

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
	# If you want ANY submitted BOM (not just default), remove "is_default": 1
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
		# Same logic as ERPNext: calculate how much to pick for the requested "for_qty"
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
				# Core rule:
				# - keep original ERPNext condition (required_qty not fully transferred)
				# - AND skip items that have BOM
				"condition": lambda d: abs(flt(d.transferred_qty)) < abs(flt(d.required_qty))
				and d.item_code not in bom_items,
			},
		},
		target_doc,
	)

	doc.purpose = "Material Transfer for Manufacture"
	doc.for_qty = for_qty or max_finished_goods_qty

	# Populate Item Locations (warehouses/bins) as standard Pick List behavior
	doc.set_item_locations()
	return doc