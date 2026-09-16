import frappe


SUB_ASSEMBLY_ROW_FIELDS = [
    "name",
    "parent",
    "production_item",
    "bom_no",
    "planned_start_date",
    "schedule_date",
    "operation",
    "qty",
    "stock_qty",
    "planned_qty",
    "required_qty",
    "sub_assembly_qty",
    "production_qty",
    "taj_merge_group_id",
    "production_plan_item",
    "parent_item_code",
]


def existing_fields(doctype, wanted_fields):
    meta = frappe.get_meta(doctype)
    existing = {"name", "parent"} | {df.fieldname for df in meta.fields}
    return [fieldname for fieldname in wanted_fields if fieldname in existing]


def resolve_pp_item_reference(production_plan, pp_item_ref):
    if not pp_item_ref:
        return None

    if frappe.db.exists("Production Plan Item", pp_item_ref):
        return pp_item_ref

    return frappe.db.get_value(
        "Production Plan Item",
        {
            "parent": production_plan,
            "temporary_name": pp_item_ref,
        },
        "name",
    )


def get_sub_assembly_row_fields():
    return existing_fields("Production Plan Sub Assembly Item", SUB_ASSEMBLY_ROW_FIELDS)
