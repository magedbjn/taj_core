#delete_slnee.py
import frappe

def execute():
    module_name = "Slnee"
    frappe.db.sql("""DELETE FROM `tabReport` WHERE module=%s""", (module_name,))
    frappe.db.sql("""DELETE FROM `tabDocType` WHERE module=%s""", (module_name,))
    frappe.db.sql("""DELETE FROM `tabDashboard Chart` WHERE module=%s""", (module_name,))
    frappe.db.sql("""DELETE FROM `tabModule Def` WHERE module_name=%s""", (module_name,))
    frappe.db.commit()
    print("✅ All data related to module Slnee has been deleted.")