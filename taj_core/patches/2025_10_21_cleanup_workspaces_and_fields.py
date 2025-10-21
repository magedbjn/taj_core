import frappe

def _safe_delete(dt, name):
    """Delete a single doc if it exists (hard delete)."""
    if frappe.db.exists(dt, name):
        frappe.delete_doc(dt, name, force=1, ignore_permissions=True)

def execute():
    # --- Workspaces ---
    # Try exact names first
    for ws in ["R&D", "Engineering"]:
        if frappe.db.exists("Workspace", ws):
            frappe.delete_doc("Workspace", ws, force=1, ignore_permissions=True)

    # Also defensively remove by title (in case of different 'name' vs 'title')
    for title in ["R&D", "Engineering"]:
        for d in frappe.get_all("Workspace", filters={"title": title}, pluck="name"):
            frappe.delete_doc("Workspace", d, force=1, ignore_permissions=True)

    # --- Custom Fields ---
    # Supplier.taj_blocked_by_qualification
    _safe_delete("Custom Field", "Supplier-taj_blocked_by_qualification")

    # Supplier Group.taj_manufacturing_related
    _safe_delete("Custom Field", "Supplier Group-taj_manufacturing_related")

    # Optional: clean any related property setters (safe if none exist)
    for (dt, fieldname) in [
        ("Supplier", "taj_blocked_by_qualification"),
        ("Supplier Group", "taj_manufacturing_related"),
    ]:
        frappe.db.delete("Property Setter", {"doc_type": dt, "property": ("like", f"%{fieldname}%")})

    # Reflect workspace changes immediately
    frappe.clear_cache()
