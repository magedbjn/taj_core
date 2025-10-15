# taj_core/patches/fix_manufacturing_on_hold.py
import frappe
from taj_core.integrations.supplier_hooks import is_manufacturing_group
from frappe.utils import today

def execute():
    suppliers = frappe.get_all("Supplier", fields=["name", "supplier_group", "on_hold"])
    for s in suppliers:
        if not is_manufacturing_group(s.supplier_group):
            # غير تصنيعي لازم يكون on_hold=0
            if s.on_hold:
                frappe.db.set_value("Supplier", s.name, "on_hold", 0)
            continue

        # تصنيعي → علّق حتى تكون المؤهلية نشطة
        qual = frappe.db.sql("""
            SELECT name
            FROM `tabSupplier Qualification`
            WHERE supplier=%s
              AND approval_status IN ('Approved','Partially Approved')
              AND (valid_from IS NULL OR valid_from <= %s)
              AND (valid_to   IS NULL OR valid_to   >= %s)
            LIMIT 1
        """, (s.name, today(), today()))
        target = 0 if qual else 1
        if int(s.on_hold or 0) != target:
            frappe.db.set_value("Supplier", s.name, "on_hold", target)
