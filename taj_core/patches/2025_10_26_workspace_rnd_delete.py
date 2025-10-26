import frappe

def execute():
    # --- Workspaces ---
    # Try exact names first
    for ws in ["RND"]:
        if frappe.db.exists("Workspace", ws):
            frappe.delete_doc("Workspace", ws, force=1, ignore_permissions=True)

    # Also defensively remove by title (in case of different 'name' vs 'title')
    for title in ["RND"]:
        for d in frappe.get_all("Workspace", filters={"title": title}, pluck="name"):
            frappe.delete_doc("Workspace", d, force=1, ignore_permissions=True)


    # Reflect workspace changes immediately
    frappe.clear_cache()
