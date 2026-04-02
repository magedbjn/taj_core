import json
import frappe
from frappe import _


def execute(filters=None):
	filters = filters or {}

	item_codes = _as_list(filters.get("items"))
	item_groups = _as_list(filters.get("item_groups"))

	columns = [
		{
			"fieldname": "item_code",
			"label": _("Item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 180,
		},
		{
			"fieldname": "item_name",
			"label": _("Item Name"),
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"fieldname": "item_group",
			"label": _("Item Group"),
			"fieldtype": "Link",
			"options": "Item Group",
			"width": 180,
		},
		{
			"fieldname": "warehouse",
			"label": _("Warehouse"),
			"fieldtype": "Data",
			"width": 240,
		},
		{
			"fieldname": "stock_uom",
			"label": _("UOM"),
			"fieldtype": "Link",
			"options": "UOM",
			"width": 100,
		},
		{
			"fieldname": "qty",
			"label": _("Qty"),
			"fieldtype": "Float",
			"width": 120,
		},
	]

	conditions = ["i.disabled = 0"]
	params = {}

	if item_codes:
		conditions.append("b.item_code IN %(item_codes)s")
		params["item_codes"] = tuple(item_codes)

	if item_groups:
		conditions.append("i.item_group IN %(item_groups)s")
		params["item_groups"] = tuple(item_groups)

	where_clause = " AND ".join(conditions)

	data = frappe.db.sql(
		f"""
		SELECT
			b.item_code,
			i.item_name,
			i.item_group,
			b.warehouse AS warehouse,
			i.stock_uom,
			IFNULL(b.actual_qty, 0) AS qty
		FROM `tabBin` b
		INNER JOIN `tabItem` i
			ON i.name = b.item_code
		WHERE {where_clause}
		  AND IFNULL(b.actual_qty, 0) <> 0
		ORDER BY b.item_code, b.warehouse
		""",
		params,
		as_dict=True,
	)

	return columns, data



def _as_list(value):
	if not value:
		return []

	if isinstance(value, list):
		return [v for v in value if v]

	if isinstance(value, str):
		try:
			parsed = json.loads(value)
			if isinstance(parsed, list):
				return [v for v in parsed if v]
		except Exception:
			pass

		return [v.strip() for v in value.split(",") if v.strip()]

	return [value]
