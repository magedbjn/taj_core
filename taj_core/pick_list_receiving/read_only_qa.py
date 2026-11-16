"""Inspect ERPNext v16 fields and Pick List Receiving status without creating stock documents."""

import frappe
from .settings import status as settings_status

REQUIRED_FIELDS = {
    "Pick List": ["company", "locations", "purpose", "material_request", "work_order", "status"],
    "Pick List Item": ["name", "item_code", "qty", "picked_qty", "transferred_qty", "warehouse", "batch_no"],
    "Stock Entry": ["pick_list", "purpose", "items", "company"],
    "Stock Entry Detail": ["pick_list_item", "s_warehouse", "t_warehouse", "transfer_qty"],
    "Warehouse": ["company", "is_group", "disabled"],
}


def run():
    if frappe.local.site != "test1.com":
        frappe.throw("Pick List Receiving test only: test1.com")
    errors = {}
    for dt, fields in REQUIRED_FIELDS.items():
        meta = frappe.get_meta(dt)
        missing = [name for name in fields if name != "name" and not meta.has_field(name)]
        if missing:
            errors[dt] = missing
    hooks = frappe.get_hooks()
    return {
        "mode": "READ_ONLY",
        "site": frappe.local.site,
        "submit_supported": True,
        "transfer_enabled": settings_status()["transfer_enabled"],
        "settings_source": "Stock Settings > Taj",
        "settings_field_present": settings_status()["setting_present"],
        "transfer_test_site_only": True,
        "stock_entries_created": 0,
        "stock_entries_submitted": 0,
        "missing_fields": errors,
        "role_exists": bool(frappe.db.exists("Role", "Pick List Receiver")),
        "page_exists": bool(frappe.db.exists("Page", "pick-list-receiving")),
        "custom_stock_entry_override": hooks.get("override_doctype_class", {}).get("Stock Entry"),
        "existing_pick_list_extensions": hooks.get("extend_doctype_class", {}).get("Pick List"),
        "stock_entry_doc_events": hooks.get("doc_events", {}).get("Stock Entry"),
        "pick_list_doc_events": hooks.get("doc_events", {}).get("Pick List"),
    }
