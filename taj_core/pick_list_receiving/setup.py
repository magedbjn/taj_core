"""Explicit, opt-in UAT role setup. Does not create warehouse user permissions."""

import frappe

ROLE = "Pick List Receiver"


def _test_site_only():
    if frappe.local.site != "test1.com":
        frappe.throw("Pick List Receiving test package is restricted to test1.com")


def ensure_role():
    """Create the receiving role before importing the new page."""
    _test_site_only()
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager may create the Pick List Receiver role", frappe.PermissionError)
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({
            "doctype": "Role", "role_name": ROLE,
            "desk_access": 1, "disabled": 0,
        }).insert()
    return {"role": ROLE, "created_or_present": True, "stock_writes": False}


def cleanup_previous_release():
    """Remove the previous *Page and Role metadata only* after new page works.

    Restricts deletion to the known test page, never a stock document.
    Refuses deletion if the old role has any remaining assignments.
    """
    _test_site_only()
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("System Manager access is required", frappe.PermissionError)

    old_page = "mst01-receiving"  # legacy database identifier only
    old_role = "MST Preparation Receiver"  # legacy database identifier only
    if not frappe.db.exists("Page", "pick-list-receiving") or not frappe.db.exists("Role", ROLE):
        frappe.throw("Create and verify the new Pick List Receiving page and role first")

    page = frappe.db.get_value("Page", old_page, ["module", "standard", "title"], as_dict=True)
    if page and (page.module != "Taj Core" or page.standard != "Yes" or page.title != "MST-01 Receiving"):
        frappe.throw("Old page metadata differs from the expected test page; manual review required")

    if frappe.db.exists("Has Role", {"role": old_role, "parenttype": ["in", ["User", "Role Profile"]]}):
        frappe.throw("Previous receiver role is assigned to a user or profile; move assignments manually first")
    if frappe.db.exists("Custom DocPerm", {"role": old_role}):
        frappe.throw("Old receiver role is referenced in custom permissions; review it manually first")
    if page:
        frappe.delete_doc("Page", old_page)

    if frappe.db.exists("Role", old_role):
        if frappe.db.exists("Has Role", {"role": old_role}):
            frappe.throw("Old receiver role still referenced elsewhere; cannot delete it safely")
        frappe.delete_doc("Role", old_role)

    return {"old_page_removed": bool(page), "old_role_present": bool(frappe.db.exists("Role", old_role)),
            "stock_entries_created": 0, "stock_entries_submitted": 0}
