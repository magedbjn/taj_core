import frappe


WORKSPACE = "Manufacturing"
TAJ_PAGE = "job-card-board"


def execute():
    if not frappe.db.exists("Workspace", WORKSPACE):
        return

    workspace = frappe.get_doc("Workspace", WORKSPACE)
    stale_links = [
        row
        for row in workspace.links
        if row.link_to == TAJ_PAGE
    ]

    if not stale_links:
        return

    for row in stale_links:
        workspace.remove(row)

    workspace.save(ignore_permissions=True)
    frappe.clear_cache()
