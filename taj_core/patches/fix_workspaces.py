import frappe
from taj_core.install import ensure_workspace, ensure_module

def execute():
    ensure_module("QC")
    ensure_module("RND")
    ensure_module("Engineering")
    ensure_module("Company Documents")

    ensure_workspace(name="QC",          module="QC",                 label="QC")
    ensure_workspace(name="RND",         module="RND",                label="R&D")
    ensure_workspace(name="Engineering", module="Engineering",        label="Engineering")
    ensure_workspace(name="Documents",   module="Company Documents",  label="Documents")
    frappe.db.commit()
