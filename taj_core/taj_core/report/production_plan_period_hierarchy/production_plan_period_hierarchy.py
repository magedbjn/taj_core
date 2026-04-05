import json
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate, strip_html_tags


def execute(filters=None):
	filters = frappe._dict(filters or {})
	set_default_filters(filters)
	validate_filters(filters)

	columns = get_columns(filters)
	data, summary_meta = build_hierarchy_data(filters)

	message = _(
		"Hierarchy is built by period. "
		"Production view shows Assemble and Sub Assemble items only. "
		"Raw Materials view shows Raw Materials only, exploded from Sub Assemble BOMs."
	)

	report_summary = get_report_summary(summary_meta)
	return columns, data, message, None, report_summary, 1


# ---------------------------------------------------------------------
# Filters / Validation
# ---------------------------------------------------------------------


def set_default_filters(filters):
	if filters.get("group_assemble_items") is None:
		filters.group_assemble_items = 1

	if filters.get("group_sub_assemble_items") is None:
		filters.group_sub_assemble_items = 1

	if filters.get("group_raw_materials") is None:
		filters.group_raw_materials = 1

	if not filters.get("period_bucket"):
		filters.period_bucket = "None"

	if not filters.get("planning_view"):
		filters.planning_view = "Production"


def validate_filters(filters):
	if not filters.get("production_plan"):
		frappe.throw(_("Production Plan is required."))


def parse_multi_select(value):
	if not value:
		return []

	if isinstance(value, (list, tuple, set)):
		return [v for v in value if v]

	if isinstance(value, str):
		value = value.strip()
		if not value:
			return []

		try:
			loaded = json.loads(value)
			if isinstance(loaded, list):
				return [v for v in loaded if v]
		except Exception:
			pass

		if "\n" in value:
			return [v.strip() for v in value.split("\n") if v.strip()]

		if "," in value:
			return [v.strip() for v in value.split(",") if v.strip()]

		return [value]

	return []


def get_planning_view(filters):
	view = (filters.get("planning_view") or "Production").strip()
	return "Raw Materials" if view == "Raw Materials" else "Production"


def apply_sub_assembly_view_filter(conditions, filters):
	planning_view = get_planning_view(filters)

	# في Raw Materials لا نفلتر Sub Assemble على type_of_manufacturing
	# حتى لا يختفي التقرير إذا كانت البيانات غير مضبوطة
	if planning_view == "Production":
		conditions.append("COALESCE(ppsi.type_of_manufacturing, '') != 'Purchase'")


def get_raw_material_filter_condition(filters):
	planning_view = get_planning_view(filters)

	if planning_view == "Raw Materials":
		return "COALESCE(i.default_material_request_type, '') = 'Purchase'"

	return None


# ---------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------


def get_columns(filters=None):
	filters = frappe._dict(filters or {})

	period_bucket = (filters.get("period_bucket") or "None").strip()

	hide_last_date = period_bucket == "None"
	hide_count = period_bucket == "None"

	return [
		{
			"label": _("Group / Item"),
			"fieldname": "label",
			"fieldtype": "Data",
			"width": 360,
		},
		{
			"label": _("Grouped Items Count"),
			"fieldname": "row_count",
			"fieldtype": "Int",
			"width": 180,
			"hidden": 1 if hide_count else 0,
		},
		{
			"label": _("Qty"),
			"fieldname": "qty",
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"label": _("Shelf Life (Days)"),
			"fieldname": "shelf_life_in_days",
			"fieldtype": "Int",
			"width": 150,
		},
		{
			"label": _("Date"),
			"fieldname": "first_date",
			"fieldtype": "Datetime",
			"width": 170,
		},
		{
			"label": _("Last Date"),
			"fieldname": "last_date",
			"fieldtype": "Datetime",
			"width": 170,
			"hidden": 1 if hide_last_date else 0,
		},
		{
			"label": _("Row Type"),
			"fieldname": "row_type",
			"fieldtype": "Data",
			"hidden": 1,
		},
	]

# ---------------------------------------------------------------------
# Build hierarchy
# ---------------------------------------------------------------------


def build_hierarchy_data(filters):
	group_assemble_items = cint(filters.get("group_assemble_items"))
	group_sub_assemble_items = cint(filters.get("group_sub_assemble_items"))
	group_raw_materials = cint(filters.get("group_raw_materials"))
	period_bucket = filters.get("period_bucket") or "None"
	planning_view = get_planning_view(filters)

	assembly_sources = get_assembly_source_rows(filters)
	sub_sources = get_sub_assembly_source_rows(filters)

	assembly_lookup_by_row = {}
	assembly_lookup_by_item = {}

	for row in assembly_sources:
		norm = normalize_assembly_source(row, period_bucket)
		assembly_lookup_by_row[norm.source_key] = norm
		assembly_lookup_by_item.setdefault(norm.item_code, norm)

	period_buckets = {}

	# 1) Build hierarchy from Sub Assemble rows first
	for sub_row in sub_sources:
		parent_assembly = get_parent_assembly_for_sub_row(
			sub_row=sub_row,
			assembly_lookup_by_row=assembly_lookup_by_row,
			assembly_lookup_by_item=assembly_lookup_by_item,
			period_bucket=period_bucket,
		)

		period_key = parent_assembly.period_key
		period_label = parent_assembly.period_label

		period_bucket_row = period_buckets.setdefault(
			period_key,
			{
				"label": period_label,
				"sort_date": parent_assembly.period_sort_date,
				"assembly_groups": {},
			},
		)

		assembly_group_key = get_assembly_group_key(parent_assembly, period_key, group_assemble_items)
		assembly_group = period_bucket_row["assembly_groups"].get(assembly_group_key)

		if not assembly_group:
			assembly_group = frappe._dict(
				{
					"label": parent_assembly.label,
					"item_code": parent_assembly.item_code,
					"bom_no": parent_assembly.bom_no,
					"qty": 0.0,
					"grouped_rows_count": 0,
					"first_date": parent_assembly.first_date,
					"last_date": parent_assembly.last_date,
					"row_type": "Assemble Item",
					"source_keys": set(),
					"sub_groups": {},
				}
			)
			period_bucket_row["assembly_groups"][assembly_group_key] = assembly_group

		if parent_assembly.source_key not in assembly_group.source_keys:
			assembly_group.source_keys.add(parent_assembly.source_key)
			assembly_group.qty += flt(parent_assembly.qty)
			assembly_group.grouped_rows_count += 1

			if parent_assembly.first_date and (
				not assembly_group.first_date
				or getdate(parent_assembly.first_date) < getdate(assembly_group.first_date)
			):
				assembly_group.first_date = parent_assembly.first_date

			if parent_assembly.last_date and (
				not assembly_group.last_date
				or getdate(parent_assembly.last_date) > getdate(assembly_group.last_date)
			):
				assembly_group.last_date = parent_assembly.last_date

		sub_norm = normalize_sub_source(sub_row, assembly_group_key)

		sub_group_key = get_sub_group_key(sub_norm, group_sub_assemble_items)
		sub_group = assembly_group.sub_groups.get(sub_group_key)

		if not sub_group:
			sub_group = frappe._dict(
				{
					"label": sub_norm.label,
					"item_code": sub_norm.item_code,
					"bom_no": sub_norm.bom_no,
					"qty": 0.0,
					"grouped_rows_count": 0,
					"first_date": sub_norm.first_date,
					"last_date": sub_norm.last_date,
					"type_of_manufacturing": sub_norm.type_of_manufacturing,
					"row_type": "Sub Assemble Item",
				}
			)
			assembly_group.sub_groups[sub_group_key] = sub_group

		sub_group.qty += flt(sub_norm.qty)
		sub_group.grouped_rows_count += 1

		if sub_norm.first_date and (
			not sub_group.first_date or getdate(sub_norm.first_date) < getdate(sub_group.first_date)
		):
			sub_group.first_date = sub_norm.first_date

		if sub_norm.last_date and (
			not sub_group.last_date or getdate(sub_norm.last_date) > getdate(sub_group.last_date)
		):
			sub_group.last_date = sub_norm.last_date

	# 2) Add assemblies without sub rows only in Production view and only when no sub filter is applied
	selected_sub_items = parse_multi_select(filters.get("sub_assembly_items"))
	if planning_view == "Production" and not selected_sub_items:
		for parent_assembly in assembly_lookup_by_row.values():
			period_bucket_row = period_buckets.setdefault(
				parent_assembly.period_key,
				{
					"label": parent_assembly.period_label,
					"sort_date": parent_assembly.period_sort_date,
					"assembly_groups": {},
				},
			)

			assembly_group_key = get_assembly_group_key(
				parent_assembly, parent_assembly.period_key, group_assemble_items
			)
			assembly_group = period_bucket_row["assembly_groups"].get(assembly_group_key)

			if not assembly_group:
				assembly_group = frappe._dict(
					{
						"label": parent_assembly.label,
						"item_code": parent_assembly.item_code,
						"bom_no": parent_assembly.bom_no,
						"qty": flt(parent_assembly.qty),
						"grouped_rows_count": 1,
						"first_date": parent_assembly.first_date,
						"last_date": parent_assembly.last_date,
						"row_type": "Assemble Item",
						"source_keys": {parent_assembly.source_key},
						"sub_groups": {},
					}
				)
				period_bucket_row["assembly_groups"][assembly_group_key] = assembly_group
			else:
				if parent_assembly.source_key not in assembly_group.source_keys:
					assembly_group.source_keys.add(parent_assembly.source_key)
					assembly_group.qty += flt(parent_assembly.qty)
					assembly_group.grouped_rows_count += 1

					if parent_assembly.first_date and (
						not assembly_group.first_date
						or getdate(parent_assembly.first_date) < getdate(assembly_group.first_date)
					):
						assembly_group.first_date = parent_assembly.first_date

					if parent_assembly.last_date and (
						not assembly_group.last_date
						or getdate(parent_assembly.last_date) > getdate(assembly_group.last_date)
					):
						assembly_group.last_date = parent_assembly.last_date

	# 3) Render rows
	data = []
	periods_count = 0
	assemblies_count = 0
	subs_count = 0
	raws_count = 0

	total_assemble_count = 0
	total_sub_count = 0
	total_raw_count = 0

	sorted_periods = sorted(
		period_buckets.items(),
		key=lambda x: getdate(x[1].get("sort_date")),
	)

	for period_key, period_bucket_row in sorted_periods:
		assembly_groups = list(period_bucket_row["assembly_groups"].values())
		assembly_groups.sort(key=lambda r: (sort_value(r.first_date), r.item_code or "", r.label or ""))

		period_assemble_count = len(assembly_groups)
		period_sub_count = 0
		period_raw_map = {}
		period_raw_rows = []

		# Pre-calc summaries and raw materials
		for assembly_group in assembly_groups:
			sub_groups = list(assembly_group.sub_groups.values())
			sub_groups.sort(key=lambda r: (sort_value(r.first_date), r.item_code or "", r.label or ""))

			for sub_group in sub_groups:
				period_sub_count += 1

				if planning_view == "Raw Materials":
					raw_rows = explode_raw_materials_from_bom(
						bom_no=sub_group.bom_no,
						planned_qty=sub_group.qty,
						filters=filters,
					)

					for raw in raw_rows:
						if group_raw_materials:
							raw_key = "::".join(
								[
									raw.get("item_code") or "",
									raw.get("uom") or "",
									raw.get("material_request_type") or "",
								]
							)

							raw_bucket = period_raw_map.get(raw_key)
							if not raw_bucket:
								raw_bucket = frappe._dict(
									{
										"label": build_raw_label(raw),
										"item_code": raw.get("item_code"),
										"qty": 0.0,
										"shelf_life_in_days": raw.get("shelf_life_in_days"),
										"first_date": sub_group.first_date,
										"last_date": sub_group.last_date,
										"row_count": 0,
									}
								)
								period_raw_map[raw_key] = raw_bucket

							raw_bucket.qty += flt(raw.required_qty)
							raw_bucket.row_count += 1

							if sub_group.first_date and (
								not raw_bucket.first_date
								or getdate(sub_group.first_date) < getdate(raw_bucket.first_date)
							):
								raw_bucket.first_date = sub_group.first_date

							if sub_group.last_date and (
								not raw_bucket.last_date
								or getdate(sub_group.last_date) > getdate(raw_bucket.last_date)
							):
								raw_bucket.last_date = sub_group.last_date

						else:
							period_raw_rows.append(
								frappe._dict(
									{
										"label": build_raw_label(raw),
										"item_code": raw.get("item_code"),
										"qty": flt(raw.required_qty),
										"shelf_life_in_days": raw.get("shelf_life_in_days"),
										"first_date": sub_group.first_date,
										"last_date": sub_group.last_date,
										"row_count": 1,
									}
								)
							)

		# Skip empty raw-material periods
		if planning_view == "Raw Materials" and not period_raw_map and not period_raw_rows:
			continue

		period_header_index = len(data)
		data.append(
			{
				"label": period_bucket_row["label"],
				"row_count": None,
				"qty": None,
				"shelf_life_in_days": None,
				"first_date": None,
				"last_date": None,
				"row_type": "Period",
				"indent": 0,
			}
		)
		periods_count += 1

		if planning_view == "Production":
			for assembly_group in assembly_groups:
				data.append(
					{
						"label": assembly_group.label,
						"row_count": assembly_group.grouped_rows_count,
						"qty": assembly_group.qty,
						"shelf_life_in_days": None,
						"first_date": assembly_group.first_date,
						"last_date": assembly_group.last_date,
						"row_type": "Assemble Item",
						"indent": 1,
					}
				)
				assemblies_count += 1

				sub_groups = list(assembly_group.sub_groups.values())
				sub_groups.sort(key=lambda r: (sort_value(r.first_date), r.item_code or "", r.label or ""))

				for sub_group in sub_groups:
					data.append(
						{
							"label": sub_group.label,
							"row_count": sub_group.grouped_rows_count,
							"qty": sub_group.qty,
							"shelf_life_in_days": None,
							"first_date": sub_group.first_date,
							"last_date": sub_group.last_date,
							"row_type": "Sub Assemble Item",
							"indent": 2,
						}
					)
					subs_count += 1

			assemble_count_label = _("Grouped Items Count") if period_bucket == "None" else _("Assemble Count")

			data[period_header_index]["label"] = (
				f"{period_bucket_row['label']} | "
				f"{assemble_count_label}: {period_assemble_count} | "
				f"{_('Sub Assemble Count')}: {period_sub_count}"
			)

			total_assemble_count += period_assemble_count
			total_sub_count += period_sub_count

		else:
			if group_raw_materials:
				raw_rows_sorted = list(period_raw_map.values())
			else:
				raw_rows_sorted = list(period_raw_rows)

			raw_rows_sorted.sort(key=lambda r: (sort_value(r.first_date), r.item_code or "", r.label or ""))

			for raw in raw_rows_sorted:
				data.append(
					{
						"label": raw.label,
						"row_count": raw.get("row_count"),
						"qty": raw.qty,
						"shelf_life_in_days": raw.get("shelf_life_in_days"),
						"first_date": raw.first_date,
						"last_date": raw.last_date,
						"row_type": "Raw Material",
						"indent": 1,
					}
				)
				raws_count += 1

			data[period_header_index]["label"] = (
				f"{period_bucket_row['label']} | "
				f"{_('Raw Materials Count')}: {len(raw_rows_sorted)}"
			)

			total_raw_count += len(raw_rows_sorted)

	meta = {
		"periods_count": periods_count,
		"assemblies_count": total_assemble_count,
		"subs_count": total_sub_count,
		"raws_count": total_raw_count,
		"planning_view": planning_view,
		"period_bucket": period_bucket,
	}
	return data, meta


# ---------------------------------------------------------------------
# Source queries
# ---------------------------------------------------------------------


def get_assembly_source_rows(filters):
	return frappe.db.sql(
		"""
		SELECT
			ppi.name AS row_name,
			ppi.item_code,
			ppi.description,
			ppi.bom_no,
			ppi.planned_qty AS qty,
			ppi.planned_start_date AS schedule_date,
			ppi.idx
		FROM `tabProduction Plan Item` ppi
		WHERE
			ppi.parent = %(production_plan)s
			AND ppi.parenttype = 'Production Plan'
			AND ppi.parentfield = 'po_items'
		ORDER BY ppi.planned_start_date, ppi.idx, ppi.item_code
		""",
		filters,
		as_dict=True,
	)


def get_sub_assembly_source_rows(filters):
	selected_sub_items = parse_multi_select(filters.get("sub_assembly_items"))

	conditions = [
		"ppsi.parent = %(production_plan)s",
		"ppsi.parenttype = 'Production Plan'",
		"ppsi.parentfield = 'sub_assembly_items'",
	]

	if selected_sub_items:
		escaped = ", ".join(frappe.db.escape(x) for x in selected_sub_items)
		conditions.append(f"ppsi.production_item IN ({escaped})")

	apply_sub_assembly_view_filter(conditions, filters)

	return frappe.db.sql(
		f"""
		SELECT
			ppsi.name AS row_name,
			ppsi.production_plan_item,
			ppsi.parent_item_code,
			ppsi.production_item,
			ppsi.item_name,
			ppsi.bom_no,
			ppsi.qty,
			ppsi.schedule_date,
			ppsi.type_of_manufacturing,
			ppsi.idx
		FROM `tabProduction Plan Sub Assembly Item` ppsi
		WHERE {" AND ".join(conditions)}
		ORDER BY ppsi.schedule_date, ppsi.idx, ppsi.production_item
		""",
		filters,
		as_dict=True,
	)


# ---------------------------------------------------------------------
# Normalize / grouping
# ---------------------------------------------------------------------


def normalize_assembly_source(row, period_bucket):
	period_key, period_label, sort_date = get_period_bucket(row.schedule_date, period_bucket)
	return frappe._dict(
		{
			"source_key": row.row_name,
			"label": build_assemble_label(row),
			"item_code": row.item_code,
			"bom_no": row.bom_no,
			"qty": flt(row.qty),
			"first_date": row.schedule_date,
			"last_date": row.schedule_date,
			"period_key": period_key,
			"period_label": period_label,
			"period_sort_date": sort_date,
		}
	)


def normalize_sub_source(row, assembly_group_key):
	return frappe._dict(
		{
			"source_key": row.row_name,
			"parent_group_key": assembly_group_key,
			"label": build_sub_label(row),
			"item_code": row.production_item,
			"bom_no": row.bom_no,
			"qty": flt(row.qty),
			"first_date": row.schedule_date,
			"last_date": row.schedule_date,
			"type_of_manufacturing": row.type_of_manufacturing or "",
		}
	)


def get_parent_assembly_for_sub_row(sub_row, assembly_lookup_by_row, assembly_lookup_by_item, period_bucket):
	if sub_row.get("production_plan_item") and assembly_lookup_by_row.get(sub_row.production_plan_item):
		return assembly_lookup_by_row[sub_row.production_plan_item]

	if sub_row.get("parent_item_code") and assembly_lookup_by_item.get(sub_row.parent_item_code):
		return assembly_lookup_by_item[sub_row.parent_item_code]

	period_key, period_label, sort_date = get_period_bucket(sub_row.schedule_date, period_bucket)
	return frappe._dict(
		{
			"source_key": f"virtual::{sub_row.parent_item_code}::{sub_row.row_name}",
			"label": sub_row.parent_item_code or _("Unknown Assemble"),
			"item_code": sub_row.parent_item_code or "",
			"bom_no": "",
			"qty": 0,
			"first_date": sub_row.schedule_date,
			"last_date": sub_row.schedule_date,
			"period_key": period_key,
			"period_label": period_label,
			"period_sort_date": sort_date,
		}
	)


def get_assembly_group_key(parent_assembly, period_key, group_assemble_items):
	if group_assemble_items:
		return "::".join(
			[
				period_key or "",
				parent_assembly.item_code or "",
				parent_assembly.label or "",
				parent_assembly.bom_no or "",
			]
		)

	return "::".join([period_key or "", parent_assembly.source_key or ""])


def get_sub_group_key(sub_row, group_sub_assemble_items):
	if group_sub_assemble_items:
		return "::".join(
			[
				sub_row.parent_group_key or "",
				sub_row.item_code or "",
				sub_row.label or "",
				sub_row.bom_no or "",
				sub_row.type_of_manufacturing or "",
			]
		)

	return "::".join([sub_row.parent_group_key or "", sub_row.source_key or ""])


# ---------------------------------------------------------------------
# Raw materials by BOM explosion
# ---------------------------------------------------------------------


def explode_raw_materials_from_bom(bom_no, planned_qty, filters=None):
	if not bom_no or not flt(planned_qty):
		return []

	filters = frappe._dict(filters or {})

	conditions = [
		"bei.parent = %(bom_no)s",
		"bei.docstatus < 2",
	]

	raw_filter_condition = get_raw_material_filter_condition(filters)
	if raw_filter_condition:
		conditions.append(raw_filter_condition)

	return frappe.db.sql(
		f"""
		SELECT
			bei.item_code AS item_code,
			MAX(COALESCE(i.item_name, '')) AS item_name,
			MAX(COALESCE(bei.stock_uom, '')) AS uom,
			MAX(COALESCE(i.default_material_request_type, '')) AS material_request_type,
			MAX(i.shelf_life_in_days) AS shelf_life_in_days,
			SUM((COALESCE(bei.stock_qty, 0) / IFNULL(b.quantity, 1)) * %(planned_qty)s) AS required_qty
		FROM `tabBOM Explosion Item` bei
		INNER JOIN `tabBOM` b
			ON b.name = bei.parent
		LEFT JOIN `tabItem` i
			ON i.name = bei.item_code
		WHERE {" AND ".join(conditions)}
		GROUP BY
			bei.item_code,
			COALESCE(bei.stock_uom, ''),
			COALESCE(i.default_material_request_type, '')
		ORDER BY bei.item_code
		""",
		{
			"bom_no": bom_no,
			"planned_qty": flt(planned_qty),
		},
		as_dict=True,
	)


# ---------------------------------------------------------------------
# Helpers / summary
# ---------------------------------------------------------------------


def get_report_summary(meta):
	planning_view = meta.get("planning_view")
	period_bucket = meta.get("period_bucket") or "None"

	if planning_view == "Raw Materials":
		return [
			{
				"value": meta.get("periods_count", 0),
				"indicator": "Blue",
				"label": _("Periods"),
				"datatype": "Int",
			},
			{
				"value": meta.get("raws_count", 0),
				"indicator": "Red",
				"label": _("Raw Materials Count"),
				"datatype": "Int",
			},
		]

	assemble_summary_label = _("Count") if period_bucket == "None" else _("Assemble Count")

	return [
		{
			"value": meta.get("periods_count", 0),
			"indicator": "Blue",
			"label": _("Periods"),
			"datatype": "Int",
		},
		{
			"value": meta.get("assemblies_count", 0),
			"indicator": "Green",
			"label": assemble_summary_label,
			"datatype": "Int",
		},
		{
			"value": meta.get("subs_count", 0),
			"indicator": "Orange",
			"label": _("Sub Assemble Count"),
			"datatype": "Int",
		},
	]


def build_assemble_label(row):
	description = clean_text(row.get("description"))
	return description or row.get("item_code") or ""


def build_sub_label(row):
	item_name = clean_text(row.get("item_name"))
	return item_name or row.get("production_item") or ""


def build_raw_label(row):
	item_name = clean_text(row.get("item_name"))
	if item_name and row.get("item_code"):
		return f"{item_name} ({row.item_code})"
	return item_name or row.get("item_code") or ""


def clean_text(value):
	if not value:
		return ""
	return strip_html_tags(value).strip()


def get_period_bucket(dt, period_bucket="None"):
	d = getdate(dt or nowdate())
	period_bucket = (period_bucket or "None").strip()

	if period_bucket == "None":
		return d.strftime("%Y-%m-%d"), d.strftime("%d %b %Y"), d

	if period_bucket == "Month":
		start = d.replace(day=1)
		return d.strftime("%Y-%m"), d.strftime("%b %Y"), start

	days_map = {
		"Week": 7,
		"2 Weeks": 14,
		"3 Weeks": 21,
	}
	period_days = days_map.get(period_bucket, 7)

	anchor = date(2000, 1, 3)
	diff_days = (d - anchor).days
	start = anchor + timedelta(days=(diff_days // period_days) * period_days)
	end = start + timedelta(days=period_days - 1)

	key = f"{period_bucket}::{start.isoformat()}"

	if period_bucket == "Week":
		label = _("Week {0}: {1} → {2}").format(
			start.isocalendar()[1],
			start.strftime("%d %b %Y"),
			end.strftime("%d %b %Y"),
		)
	elif period_bucket == "2 Weeks":
		label = _("2 Weeks: {0} → {1}").format(
			start.strftime("%d %b %Y"),
			end.strftime("%d %b %Y"),
		)
	else:
		label = _("3 Weeks: {0} → {1}").format(
			start.strftime("%d %b %Y"),
			end.strftime("%d %b %Y"),
		)

	return key, label, start


def sort_value(dt):
	if not dt:
		return ""
	return getdate(dt).isoformat()


# ---------------------------------------------------------------------
# Filter helpers for JS
# ---------------------------------------------------------------------


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def production_plan_query(doctype, txt, searchfield, start, page_len, filters):
	return frappe.db.sql(
		"""
		SELECT name
		FROM `tabProduction Plan`
		WHERE docstatus < 2
			AND name LIKE %(txt)s
		ORDER BY modified DESC
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"txt": f"%{txt}%",
			"start": start,
			"page_len": page_len,
		},
		as_list=True,
	)


@frappe.whitelist()
def get_sub_assembly_item_options(txt="", production_plan=None):
	if not production_plan:
		return []

	return frappe.db.sql(
		"""
		SELECT DISTINCT
			ppsi.production_item AS value,
			MAX(COALESCE(ppsi.item_name, '')) AS description
		FROM `tabProduction Plan Sub Assembly Item` ppsi
		WHERE
			ppsi.parent = %(production_plan)s
			AND ppsi.parenttype = 'Production Plan'
			AND ppsi.parentfield = 'sub_assembly_items'
			AND (
				ppsi.production_item LIKE %(txt)s
				OR COALESCE(ppsi.item_name, '') LIKE %(txt)s
			)
		GROUP BY ppsi.production_item
		ORDER BY ppsi.production_item
		LIMIT 50
		""",
		{
			"production_plan": production_plan,
			"txt": f"%{txt}%",
		},
		as_dict=True,
	)