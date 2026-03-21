# your_app/patches/v1_0/remove_old_custom_fields.py

import frappe
from frappe.model.meta import trim_table

# افتراض أسماء الـ DocTypes كالتالي:
# production_plan -> Production Plan
# production_plan_sub_assembly_i -> Production Plan Sub Assembly Item
# work_order_item -> Work Order Item
#
# ملاحظة: أبقيت fieldname كما كتبته أنت: temtaj_batch_consolidate

FIELDS_TO_DELETE = {
    "Production Plan": [
        "taj_days_consolidate",
    ],
    "Production Plan Sub Assembly Item": [
        "temtaj_batch_consolidate",
    ],
    "Work Order Item": [
        "taj_print_label",
    ],
}


def delete_custom_field(doctype: str, fieldname: str) -> bool:
    custom_field_name = frappe.db.get_value(
        "Custom Field",
        {"dt": doctype, "fieldname": fieldname},
        "name",
    )

    if not custom_field_name:
        return False

    frappe.delete_doc("Custom Field", custom_field_name, force=1, ignore_missing=True)
    frappe.clear_cache(doctype=doctype)
    return True


def execute():
    touched_doctypes = set()

    for doctype, fieldnames in FIELDS_TO_DELETE.items():
        for fieldname in fieldnames:
            deleted = delete_custom_field(doctype, fieldname)
            if deleted:
                touched_doctypes.add(doctype)

    # حذف الأعمدة فعليًا من الجداول
    for doctype in touched_doctypes:
        frappe.clear_cache(doctype=doctype)
        trim_table(doctype, dry_run=False)

    frappe.clear_cache()