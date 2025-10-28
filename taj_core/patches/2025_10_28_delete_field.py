import frappe

def execute():
    if frappe.db.exists("Custom Field", "Payroll Settings-taj_salary_days_basis"):
        frappe.delete_doc("Custom Field", "Payroll Settings-taj_salary_days_basis", force=1, ignore_permissions=True)

    # Reflect workspace changes immediately
    frappe.clear_cache()
