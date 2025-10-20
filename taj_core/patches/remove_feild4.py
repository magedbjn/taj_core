import frappe

def execute():
    targets = {
        "Supplier": ["taj_blocked_by_qualification"],
        "Supplier Group": ["taj_manufacturing_related"],
    }

    # نفذ كل عمليات الحذف في خطوة واحدة بعد ال commit
    for dt, fields in targets.items():
        if not frappe.db.exists("DocType", dt):
            continue

        # احذف التعاريف
        frappe.db.delete("DocField", {"parent": dt, "fieldname": ["in", fields]})
        frappe.db.delete("Custom Field", {"dt": dt, "fieldname": ["in", fields]})

    frappe.db.commit()
    frappe.clear_cache()
