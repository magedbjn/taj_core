import json
import frappe
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, flt

from erpnext.manufacturing.doctype.work_order import work_order as core_work_order

SETTING_FIELD = "taj_keep_rm_qty"

# -------------------------------------------------------------------------
# Customization Note
# Date: 2026-05-25
# 1. Exclude Work Order required items that have a submitted default BOM.
#    Purpose:
#    Prevent sub-assembly / internally manufactured items from appearing
#    in the Pick List as raw materials.
#
# 2. Force Pick List item location search under parent warehouse:
#    "Raw Materials - Taj"
# -------------------------------------------------------------------------

@frappe.whitelist()
def create_pick_list(source_name, target_doc=None, for_qty=None):
	for_qty = for_qty or json.loads(target_doc).get("for_qty")
	max_finished_goods_qty = frappe.db.get_value("Work Order", source_name, "qty")

	item_codes = frappe.get_all(
		"Work Order Item",
		filters={"parent": source_name},
		pluck="item_code",
	)

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
		desire_to_transfer = flt(source.required_qty) / max_finished_goods_qty * flt(for_qty)

		qty = 0
		if desire_to_transfer <= pending_to_issue:
			qty = desire_to_transfer
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
				"condition": lambda doc: abs(doc.transferred_qty) < abs(doc.required_qty)
				and doc.item_code not in bom_items,
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


# -------------------------------------------------------------------------

# -------------------------------------------------------------------------
# Customization Note
# Date: 2026-05-25
#
# Function: make_stock_entry
#
# This function keeps the standard ERPNext make_stock_entry behavior by
# calling the original core_work_order.make_stock_entry first.
#
# Custom logic is applied only when:
# 1. The Stock Entry purpose is "Manufacture".
# 2. The Manufacturing Settings field "taj_keep_rm_qty" is enabled.
#
# Custom changes when taj_keep_rm_qty is enabled:
# 1. Mark the generated Stock Entry with taj_from_finish_button = 1.
# 2. Rebuild raw material rows and keep their quantities based on
#    Work Order required_items.
# 3. Preserve finished item rows and scrap item rows.
# 4. Re-apply BOM reference fields:
#    - from_bom
#    - bom_no
#    - use_multi_level_bom
# 5. Adjust fg_completed_qty based on the requested manufacture quantity.
#
# If taj_keep_rm_qty is disabled, the standard ERPNext result is returned
# without changing item rows or quantities.
# -------------------------------------------------------------------------
def is_keep_rm_qty_enabled() -> bool:
	# Return False safely if the custom field does not exist.
	if not frappe.get_meta("Manufacturing Settings").has_field(SETTING_FIELD):
		return False

	return cint(frappe.db.get_single_value("Manufacturing Settings", SETTING_FIELD) or 0) == 1

def rebuild_manufacture_rm_rows(stock_entry, work_order):
	# Keep ERPNext standard generated rows unchanged.
	# Only update raw material quantities from Work Order required_items.

	required_qty_map = {}

	for req in work_order.required_items:
		if not cint(getattr(req, "include_item_in_manufacturing", 1)):
			continue

		req_qty = flt(req.required_qty)
		if req_qty <= 0:
			continue

		original_item = getattr(req, "original_item", None) or req.item_code

		required_qty_map[(req.item_code, req.source_warehouse)] = req_qty
		required_qty_map[(req.item_code, None)] = req_qty
		required_qty_map[(original_item, req.source_warehouse)] = req_qty
		required_qty_map[(original_item, None)] = req_qty

	for row in stock_entry.items:
		if row.get("is_finished_item"):
			continue

		if row.get("is_scrap_item"):
			continue

		if not row.get("s_warehouse"):
			continue

		item_code = row.get("item_code")
		original_item = row.get("original_item") or item_code
		source_warehouse = row.get("s_warehouse")

		req_qty = (
			required_qty_map.get((item_code, source_warehouse))
			or required_qty_map.get((item_code, None))
			or required_qty_map.get((original_item, source_warehouse))
			or required_qty_map.get((original_item, None))
		)

		if req_qty is None:
			continue

		row.qty = req_qty
		row.transfer_qty = req_qty
		
@frappe.whitelist()
def make_stock_entry(
	work_order_id: str,
	purpose: str,
	qty: float | None = None,
	target_warehouse: str | None = None,
	source_stock_entry: str | None = None,
):
	result = core_work_order.make_stock_entry(
		work_order_id=work_order_id,
		purpose=purpose,
		qty=qty,
		target_warehouse=target_warehouse,
		source_stock_entry=source_stock_entry,
	)

	if purpose != "Manufacture":
		return result

	if not is_keep_rm_qty_enabled():
		return result

	work_order = frappe.get_doc("Work Order", work_order_id)
	stock_entry = frappe.get_doc(result)

	# This flag identifies that the document was generated from the Finish button.
	stock_entry.taj_from_finish_button = 1

	# Rebuild raw material rows only when taj_keep_rm_qty is enabled.
	rebuild_manufacture_rm_rows(stock_entry, work_order)

	# Re-apply BOM reference fields.
	stock_entry.from_bom = 1
	stock_entry.bom_no = work_order.bom_no
	stock_entry.use_multi_level_bom = work_order.use_multi_level_bom

	# Keep fg_completed_qty aligned with the requested manufacture quantity.
	if qty is not None:
		stock_entry.fg_completed_qty = flt(qty)
	elif not stock_entry.fg_completed_qty:
		stock_entry.fg_completed_qty = flt(work_order.qty) - flt(work_order.produced_qty)

	return stock_entry.as_dict()
# -------------------------------------------------------------------------