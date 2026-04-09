import json
import calendar
from datetime import date

import frappe
from frappe import _
from frappe.utils import flt, getdate
from erpnext.stock.get_item_details import get_conversion_factor


MONTHS = {
	"Jan": 1,
	"Feb": 2,
	"Mar": 3,
	"Apr": 4,
	"May": 5,
	"Jun": 6,
	"Jul": 7,
	"Aug": 8,
	"Sep": 9,
	"Oct": 10,
	"Nov": 11,
	"Dec": 12,
}

WEIGHT_TO_KG = {
	"kg": 1.0,
	"kilogram": 1.0,
	"kilograms": 1.0,
	"كجم": 1.0,
	"كيلو": 1.0,
	"كيلوجرام": 1.0,

	"g": 0.001,
	"gm": 0.001,
	"gram": 0.001,
	"grams": 0.001,
	"gr": 0.001,
	"جرام": 0.001,
	"غرام": 0.001,

	"ton": 1000.0,
	"tons": 1000.0,
	"tonne": 1000.0,
	"tonnes": 1000.0,
	"طن": 1000.0,
}

VOLUME_EQUAL_WEIGHT_TO_KG = {
	"l": 1.0,
	"ltr": 1.0,
	"liter": 1.0,
	"litre": 1.0,
	"liters": 1.0,
	"litres": 1.0,

	"ml": 0.001,
	"milliliter": 0.001,
	"millilitre": 0.001,
	"milliliters": 0.001,
	"millilitres": 0.001,
}

def execute(filters=None):
	filters = frappe._dict(filters or {})

	validate_filters(filters)
	from_date, to_date = resolve_date_range(filters)

	target_unit = filters.get("unit") or "Kg"
	transaction_scope = filters.get("transaction_scope") or "All"

	original_item_groups = parse_multiselect(filters.get("item_groups"))
	selected_item_groups = expand_item_groups(original_item_groups)

	rows = get_stock_rows(
		from_date=from_date,
		to_date=to_date,
		item_groups=selected_item_groups,
		transaction_scope=transaction_scope
	)

	grouped_data = {}
	has_any_reason = False
	grand_total_qty = 0.0
	grand_total_cost = 0.0
	show_source_in_label = transaction_scope == "All"

	for row in rows:
		group_name = row.item_group or _("No Item Group")

		if group_name not in grouped_data:
			grouped_data[group_name] = {
				"valid_items": [],
				"invalid_items": [],
			}

		converted_qty, reason = convert_row_qty_with_reason(row, target_unit)

		item_label = get_item_label(
			row.item_code,
			row.item_name,
			row.source_kind if show_source_in_label else None
		)

		if reason:
			has_any_reason = True
			grouped_data[group_name]["invalid_items"].append({
				"node_name": item_label,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"reason": reason or _("Unknown reason."),
				"conversion_basis": row.get("_conversion_basis"),
			})
			continue

		total_cost = flt(row.total_cost)
		unit_cost = total_cost / converted_qty if converted_qty else 0

		note = row.get("_conversion_note")
		if note:
			has_any_reason = True

		grouped_data[group_name]["valid_items"].append({
			"node_name": item_label,
			"item_code": row.item_code,
			"item_name": row.item_name,
			"qty": converted_qty,
			"unit_cost": unit_cost,
			"total_cost": total_cost,
			"reason": note,
			"conversion_basis": row.get("_conversion_basis"),
		})

		grand_total_qty += converted_qty
		grand_total_cost += total_cost

	columns = get_columns(target_unit, include_reason=has_any_reason)
	data = build_data(
		grouped_data=grouped_data,
		root_groups=original_item_groups,
		all_selected_groups=selected_item_groups,
		include_reason=has_any_reason
	)

	report_summary = [
		{
			"value": round(grand_total_qty, 3),
			"indicator": "Blue",
			"label": _("Total Quantity ({0})").format(target_unit),
			"datatype": "Float",
		},
		{
			"value": round(grand_total_cost, 2),
			"indicator": "Green",
			"label": _("Total Cost"),
			"datatype": "Currency",
		},
	]

	return columns, data, None, None, report_summary, 1


def get_columns(target_unit, include_reason=False):
	columns = [
		{
			"label": _("Item / Group"),
			"fieldname": "node_name",
			"fieldtype": "Data",
			"width": 420,
		},
		{
			"label": _("Qty ({0})").format(target_unit),
			"fieldname": "qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 160,
		},
		{
			"label": _("Unit Cost / {0}").format(target_unit),
			"fieldname": "unit_cost",
			"fieldtype": "Currency",
			"width": 160,
		},
		{
			"label": _("Total Cost"),
			"fieldname": "total_cost",
			"fieldtype": "Currency",
			"width": 170,
		},
		{
			"label": _("Conversion Basis"),
			"fieldname": "conversion_basis",
			"fieldtype": "Data",
			"width": 250,
		},
		{
			"label": _("Parent Node"),
			"fieldname": "parent_node",
			"fieldtype": "Data",
			"hidden": 1,
		},
	]

	if include_reason:
		columns.append({
			"label": _("Reason"),
			"fieldname": "reason",
			"fieldtype": "Data",
			"width": 380,
		})

	return columns

def validate_filters(filters):
	date_filter_type = filters.get("date_filter_type") or "Monthly"

	if date_filter_type == "Custom":
		if not filters.get("from_date") or not filters.get("to_date"):
			frappe.throw(_("From Date and To Date are required for Custom mode."))

		if getdate(filters.get("from_date")) > getdate(filters.get("to_date")):
			frappe.throw(_("From Date cannot be after To Date."))

	elif date_filter_type == "Monthly":
		if not filters.get("month"):
			frappe.throw(_("Month is required."))
		if not filters.get("month_year"):
			frappe.throw(_("Year is required."))

	elif date_filter_type == "Yearly":
		if not filters.get("year_option"):
			frappe.throw(_("Year option is required."))


def resolve_date_range(filters):
	date_filter_type = filters.get("date_filter_type") or "Monthly"
	today = getdate()

	if date_filter_type == "Custom":
		return getdate(filters.from_date), getdate(filters.to_date)

	if date_filter_type == "Monthly":
		month = MONTHS.get(filters.get("month"))
		year = cint_safe(filters.get("month_year"))

		if not month:
			frappe.throw(_("Invalid month."))

		if not year:
			frappe.throw(_("Year is required."))

		last_day = calendar.monthrange(year, month)[1]
		return date(year, month, 1), date(year, month, last_day)

	year_option = filters.get("year_option") or "This Year"
	year = today.year if year_option == "This Year" else today.year - 1
	return date(year, 1, 1), date(year, 12, 31)


def cint_safe(value):
	try:
		return int(value)
	except Exception:
		return None


def parse_multiselect(value):
	if not value:
		return []

	if isinstance(value, (list, tuple)):
		return [v for v in value if v]

	if isinstance(value, str):
		value = value.strip()
		if not value:
			return []

		try:
			parsed = json.loads(value)
			if isinstance(parsed, list):
				return [v for v in parsed if v]
		except Exception:
			pass

		if "\n" in value:
			return [v.strip() for v in value.split("\n") if v.strip()]

		return [v.strip() for v in value.split(",") if v.strip()]

	return []


def expand_item_groups(item_groups):
	if not item_groups:
		return []

	ranges = frappe.get_all(
		"Item Group",
		filters={"name": ["in", item_groups]},
		fields=["name", "lft", "rgt"],
	)

	all_groups = set()
	for row in ranges:
		descendants = frappe.get_all(
			"Item Group",
			filters={
				"lft": [">=", row.lft],
				"rgt": ["<=", row.rgt],
			},
			pluck="name",
		)
		all_groups.update(descendants)

	return sorted(all_groups)


def get_stock_rows(from_date, to_date, item_groups, transaction_scope="All"):
	conditions = [
		"sle.posting_date >= %(from_date)s",
		"sle.posting_date <= %(to_date)s",
		"ifnull(sle.is_cancelled, 0) = 0",
		"sle.actual_qty > 0",
	]

	params = {
		"from_date": from_date,
		"to_date": to_date,
	}

	if item_groups:
		conditions.append("i.item_group in %(item_groups)s")
		params["item_groups"] = tuple(item_groups)

	if transaction_scope == "Purchased Materials":
		conditions.append("sle.voucher_type = 'Purchase Receipt'")

	elif transaction_scope == "Manufactured Items":
		conditions.append("sle.voucher_type = 'Stock Entry'")
		conditions.append("se.purpose = 'Manufacture'")

	else:
		conditions.append(
			"""(
				sle.voucher_type = 'Purchase Receipt'
				OR (
					sle.voucher_type = 'Stock Entry'
					AND se.purpose = 'Manufacture'
				)
			)"""
		)

	query = f"""
		SELECT
			i.item_group,
			sle.item_code,
			i.item_name,
			i.stock_uom,
			i.weight_per_unit,
			i.weight_uom,
			CASE
				WHEN sle.voucher_type = 'Purchase Receipt' THEN 'Purchased Materials'
				WHEN sle.voucher_type = 'Stock Entry' AND se.purpose = 'Manufacture' THEN 'Manufactured Items'
				ELSE 'Other'
			END AS source_kind,
			MAX(
				CASE
					WHEN sle.voucher_type = 'Stock Entry' AND se.purpose = 'Manufacture' THEN 1
					ELSE 0
				END
			) AS is_manufactured,
			MAX(COALESCE(bom.taj_total_weight, 0)) AS bom_total_weight,
			SUM(sle.actual_qty) AS qty,
			SUM(sle.stock_value_difference) AS total_cost
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` i
			ON i.name = sle.item_code
		LEFT JOIN `tabStock Entry` se
			ON se.name = sle.voucher_no
			AND sle.voucher_type = 'Stock Entry'
		LEFT JOIN `tabStock Entry Detail` sed
			ON sed.name = sle.voucher_detail_no
			AND sle.voucher_type = 'Stock Entry'
		LEFT JOIN `tabBOM` bom
			ON bom.name = COALESCE(sed.bom_no, i.default_bom)
		WHERE {" AND ".join(conditions)}
		GROUP BY
			i.item_group,
			sle.item_code,
			i.item_name,
			i.stock_uom,
			i.weight_per_unit,
			i.weight_uom,
			source_kind
		ORDER BY
			i.item_group ASC,
			sle.item_code ASC
	"""

	return frappe.db.sql(query, params, as_dict=True)


def normalize_uom(uom):
	return (uom or "").strip().lower()


def get_item_label(item_code, item_name, source_kind=None):
	label = f"{item_code} - {item_name or ''}".strip(" -")
	if source_kind:
		label = f"{label} [{source_kind}]"
	return label


def weight_value_to_kg(value, uom):
	uom_key = normalize_uom(uom)
	factor = WEIGHT_TO_KG.get(uom_key)
	if factor is None:
		return None
	return flt(value) * factor


def has_explicit_uom_conversion(item_code, target_uom):
	variant_of = frappe.db.get_value("Item", item_code, "variant_of", cache=True)

	if frappe.db.exists("UOM Conversion Detail", {"parent": item_code, "uom": target_uom}):
		return True

	if variant_of and frappe.db.exists("UOM Conversion Detail", {"parent": variant_of, "uom": target_uom}):
		return True

	return False


def convert_using_standard_factor(item_code, stock_qty, stock_uom, target_uom):
	if stock_uom == target_uom:
		return flt(stock_qty)

	if not has_explicit_uom_conversion(item_code, target_uom):
		return None

	try:
		result = get_conversion_factor(item_code, target_uom) or {}
		factor = flt(result.get("conversion_factor"))
		if factor:
			return flt(stock_qty) / factor
	except Exception:
		return None

	return None

def convert_row_qty_with_reason(row, target_unit):
	stock_uom = (row.stock_uom or "").strip()
	stock_uom_key = normalize_uom(stock_uom)
	row["_conversion_note"] = None
	row["_conversion_basis"] = None

	if not stock_uom:
		return None, _("Missing stock UOM.")

	# 1) إذا كانت stock_uom نفسها وزن
	if stock_uom_key in WEIGHT_TO_KG:
		qty_in_kg = flt(row.qty) * WEIGHT_TO_KG[stock_uom_key]
		row["_conversion_basis"] = _("Stock UOM")
		if target_unit == "Ton":
			return qty_in_kg / 1000.0, None
		return qty_in_kg, None

	# 2) Business rule: Liter = Kg / Milliliter = Gram
	if stock_uom_key in VOLUME_EQUAL_WEIGHT_TO_KG:
		qty_in_kg = flt(row.qty) * VOLUME_EQUAL_WEIGHT_TO_KG[stock_uom_key]

		if stock_uom_key in ("l", "ltr", "liter", "litre", "liters", "litres"):
			row["_conversion_note"] = _("Used business rule: Liter = Kg.")
			row["_conversion_basis"] = _("Business rule: Liter = Kg")
		else:
			row["_conversion_note"] = _("Used business rule: Milliliter = Gram.")
			row["_conversion_basis"] = _("Business rule: Milliliter = Gram")

		if target_unit == "Ton":
			return qty_in_kg / 1000.0, None
		return qty_in_kg, None

	# 3) التحويل القياسي من ERPNext
	standard_qty = convert_using_standard_factor(row.item_code, row.qty, stock_uom, target_uom=target_unit)
	if standard_qty is not None:
		row["_conversion_note"] = _("Used standard UOM conversion.")
		row["_conversion_basis"] = _("Standard UOM Conversion")
		return standard_qty, None

	# 4) BOM.taj_total_weight لأصناف الإنتاج
	if cint_safe(row.is_manufactured) and stock_uom_key not in WEIGHT_TO_KG:
		bom_total_weight = flt(row.bom_total_weight)
		if bom_total_weight:
			qty_in_kg = flt(row.qty) * (bom_total_weight / 1000.0)
			row["_conversion_note"] = _("Used BOM taj_total_weight (grams per unit).")
			row["_conversion_basis"] = _("BOM taj_total_weight")
			if target_unit == "Ton":
				return qty_in_kg / 1000.0, None
			return qty_in_kg, None

	# 5) Item.weight_per_unit + Item.weight_uom
	weight_per_unit = flt(row.weight_per_unit)
	weight_uom = (row.weight_uom or "").strip()

	if weight_per_unit and weight_uom:
		kg_per_unit = weight_value_to_kg(weight_per_unit, weight_uom)
		if kg_per_unit is not None:
			qty_in_kg = flt(row.qty) * kg_per_unit
			row["_conversion_note"] = _("Used Item weight_per_unit and weight_uom.")
			row["_conversion_basis"] = _("Item weight fields")
			if target_unit == "Ton":
				return qty_in_kg / 1000.0, None
			return qty_in_kg, None

	# 6) الأسباب
	reasons = []

	reasons.append(_("No conversion rule found from {0} to {1}.").format(stock_uom, target_unit))

	if cint_safe(row.is_manufactured):
		if not flt(row.bom_total_weight):
			reasons.append(_("BOM taj_total_weight is missing."))

	if not weight_per_unit and not weight_uom:
		reasons.append(_("Item weight fields are missing."))
	elif not weight_per_unit:
		reasons.append(_("weight_per_unit is missing."))
	elif not weight_uom:
		reasons.append(_("weight_uom is missing."))
	elif weight_value_to_kg(weight_per_unit, weight_uom) is None:
		reasons.append(_("weight_uom ({0}) is unsupported.").format(weight_uom))

	if not reasons:
		reasons.append(_("Unknown reason."))

	return None, " ".join(reasons)

def get_display_group_meta(grouped_data, root_groups=None, all_selected_groups=None):
	group_names = set(grouped_data.keys())
	group_names.update(root_groups or [])
	group_names.update(all_selected_groups or [])

	if not group_names:
		return {}

	initial_meta = frappe.get_all(
		"Item Group",
		filters={"name": ["in", list(group_names)]},
		fields=["name", "parent_item_group", "lft", "rgt"],
		order_by="lft asc",
	)

	meta_map = {row.name: row for row in initial_meta}
	ancestor_names = set()

	for row in initial_meta:
		parent = row.parent_item_group
		while parent and parent not in meta_map and parent not in ancestor_names:
			ancestor_names.add(parent)
			parent = frappe.db.get_value("Item Group", parent, "parent_item_group")

	if ancestor_names:
		ancestor_meta = frappe.get_all(
			"Item Group",
			filters={"name": ["in", list(ancestor_names)]},
			fields=["name", "parent_item_group", "lft", "rgt"],
			order_by="lft asc",
		)
		for row in ancestor_meta:
			meta_map[row.name] = row

	return dict(sorted(meta_map.items(), key=lambda x: x[1].lft or 0))


def build_data(grouped_data, root_groups=None, all_selected_groups=None, include_reason=False):
	data = []

	group_meta = get_display_group_meta(
		grouped_data=grouped_data,
		root_groups=root_groups,
		all_selected_groups=all_selected_groups
	)

	if not group_meta:
		row = {
			"node_name": _("Grand Total"),
			"parent_node": None,
			"qty": 0,
			"unit_cost": 0,
			"total_cost": 0,
			"indent": 0,
			"is_total_row": 1,
		}
		if include_reason:
			row["reason"] = None
		return [row]

	children_map = {}
	for group_name, row in group_meta.items():
		parent = row.parent_item_group or None
		children_map.setdefault(parent, []).append(group_name)

	def own_valid_totals(group_name):
		items = grouped_data.get(group_name, {}).get("valid_items", [])
		qty = sum(flt(d["qty"]) for d in items)
		total_cost = sum(flt(d["total_cost"]) for d in items)
		return qty, total_cost

	rollup_cache = {}

	def get_rollup_totals(group_name):
		if group_name in rollup_cache:
			return rollup_cache[group_name]

		qty, total_cost = own_valid_totals(group_name)

		for child in children_map.get(group_name, []):
			child_qty, child_cost = get_rollup_totals(child)
			qty += child_qty
			total_cost += child_cost

		rollup_cache[group_name] = (qty, total_cost)
		return rollup_cache[group_name]

	def has_any_rows(group_name):
		valid_items = grouped_data.get(group_name, {}).get("valid_items", [])
		invalid_items = grouped_data.get(group_name, {}).get("invalid_items", [])

		if valid_items or invalid_items:
			return True

		for child in children_map.get(group_name, []):
			if has_any_rows(child):
				return True

		return False

	def add_group_row(group_name, parent_name=None, indent=0):
		if not has_any_rows(group_name):
			return

		group_qty, group_total_cost = get_rollup_totals(group_name)
		group_unit_cost = (group_total_cost / group_qty) if group_qty else 0

		row = {
			"node_name": group_name,
			"parent_node": parent_name,
			"qty": round(group_qty, 3) if group_qty else 0,
			"unit_cost": round(group_unit_cost, 4) if group_qty else 0,
			"total_cost": round(group_total_cost, 2) if group_total_cost else 0,
			"indent": indent,
			"is_group_row": 1,
		}

		if include_reason:
			row["reason"] = None
		row["conversion_basis"] = None

		data.append(row)

	def add_item_rows(group_name, indent=0):
		for item in grouped_data.get(group_name, {}).get("valid_items", []):
			row = {
				"node_name": item["node_name"],
				"parent_node": group_name,
				"qty": round(item["qty"], 3),
				"unit_cost": round(item["unit_cost"], 4),
				"total_cost": round(item["total_cost"], 2),
				"indent": indent,
				"conversion_basis": item.get("conversion_basis"),
			}
			if include_reason:
				row["reason"] = item.get("reason")
			data.append(row)

		for item in grouped_data.get(group_name, {}).get("invalid_items", []):
			row = {
				"node_name": item["node_name"],
				"parent_node": group_name,
				"qty": None,
				"unit_cost": None,
				"total_cost": None,
				"indent": indent,
				"is_error_row": 1,
				"conversion_basis": item.get("conversion_basis"),
			}
			if include_reason:
				row["reason"] = item.get("reason") or _("Unknown reason.")
			data.append(row)

	def append_group(group_name, parent_name=None, indent=0):
		if not has_any_rows(group_name):
			return

		add_group_row(group_name, parent_name, indent)
		add_item_rows(group_name, indent + 1)

		for child in children_map.get(group_name, []):
			append_group(child, group_name, indent + 1)

	def find_root_groups():
		if root_groups:
			roots = []
			root_set = set(root_groups)
			for g in root_groups:
				if g not in group_meta:
					continue
				parent = group_meta[g].parent_item_group
				if parent not in root_set:
					roots.append(g)
			return roots

		roots = []
		for g in group_meta:
			parent = group_meta[g].parent_item_group
			if not parent or parent not in group_meta:
				roots.append(g)
		return roots

	root_nodes = find_root_groups()

	for root in root_nodes:
		append_group(root, None, 0)

	grand_total_qty = 0.0
	grand_total_cost = 0.0

	for root in root_nodes:
		qty, total_cost = get_rollup_totals(root)
		grand_total_qty += qty
		grand_total_cost += total_cost

	grand_unit_cost = (grand_total_cost / grand_total_qty) if grand_total_qty else 0.0

	total_row = {
		"node_name": _("Grand Total"),
		"parent_node": None,
		"qty": round(grand_total_qty, 3),
		"unit_cost": round(grand_unit_cost, 4),
		"total_cost": round(grand_total_cost, 2),
		"indent": 0,
		"is_total_row": 1,
	}

	if include_reason:
		total_row["conversion_basis"] = None

	data.append(total_row)

	return data