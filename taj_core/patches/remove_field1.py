import frappe

def execute():
    frappe.delete_doc("Custom Field", "taj_manufacturing_related")
    frappe.delete_doc("Custom Field", "taj_blocked_by_qualification")
    