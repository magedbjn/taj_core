import frappe

def execute():
    targets = {
        "Supplier": ["taj_blocked_by_qualification"],
        "Supplier Group": ["taj_manufacturing_related"],
    }

    for dt, fields in targets.items():
        if not frappe.db.exists("DocType", dt):
            continue

        # احذف التعاريف
        frappe.db.delete("DocField", {"parent": dt, "fieldname": ["in", fields]})
        frappe.db.delete("Custom Field", {"dt": dt, "fieldname": ["in", fields]})

        # احذف أعمدة قاعدة البيانات إن وُجدت
        for f in fields:
            if frappe.db.has_column(dt, f):
                frappe.db.sql(f"ALTER TABLE `tab{dt}` DROP COLUMN `{f}`")

        frappe.clear_cache(doctype=dt)

    frappe.db.commit()
    frappe.msgprint("All specified fields processed successfully!")
