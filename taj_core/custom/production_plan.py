import json

import frappe
from frappe.model.mapper import get_mapped_doc

@frappe.whitelist()
def make_material_request_from_production_plan(source_name, target_doc=None, args=None):
	"""
	تحويل Production Plan إلى Material Request مع جلب البنود من جدول mr_items (Material Request Plan Item)
	"""
	if args is None:
		args = {}

	if isinstance(args, str):
		args = json.loads(args)

	def set_missing_values(source, target):
		target.company = source.company
		if not target.transaction_date:
			target.transaction_date = frappe.utils.nowdate()

	def select_item(d):
		"""تصفية البنود المختارة والتي material_request_type = 'Purchase'"""
		filtered_items = args.get("filtered_children", [])
		child_filter = d.name in filtered_items if filtered_items else True

		# حقل الكمية في الجدول الفرعي
		qty = d.get("ordered_qty") or 0
		
		# ✅ الشرط الجديد: فقط البنود التي material_request_type = 'Purchase'
		is_purchase_item = d.get("material_request_type") == "Purchase"
		
		return (qty == 0 or qty < d.get("quantity")) and child_filter and is_purchase_item

	def update_item(source_doc, target_doc, source_parent):
		"""تحديث القيم بعد النقل من الجدول الفرعي إلى بنود طلب المواد"""
		target_doc.qty = source_doc.quantity
		target_doc.schedule_date = source_doc.schedule_date or frappe.utils.nowdate()
		target_doc.production_plan = source_parent.name
		target_doc.production_plan_item = source_doc.name

	doclist = get_mapped_doc(
		"Production Plan",
		source_name,
		{
			"Production Plan": {
				"doctype": "Material Request",
				"validation": {"docstatus": ["=", 1]},
			},
			"Material Request Plan Item": {  # 👈 اسم الـ DocType للجدول الفرعي
				"doctype": "Material Request Item",
				"field_map": {
					"name": "production_plan_item",
					"parent": "production_plan",
					"item_code": "item_code",
					"item_name": "item_name",
					"uom": "uom",
				},
				"postprocess": update_item,
				"condition": select_item,
			},
		},
		target_doc,
		set_missing_values
	)

	doclist.set_onload("load_after_mapping", False)
	return doclist