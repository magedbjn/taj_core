"""Stock Settings > Taj controls Pick List Receiving. No site_config flags.

The Stock Settings custom fields are defined in a source-controlled JSON schema.
Explicit UAT-only setup creates the three custom fields. Production is never
changed by installation or by calling this setup method.
"""

from __future__ import annotations

import json
from pathlib import Path

import frappe
from frappe.utils import cint

TEST_SITE = "test1.com"
SETTING_DOCTYPE = "Stock Settings"
SETTING_FIELD = "taj_enable_pick_list_receiving_transfer"
SCHEMA = Path(__file__).with_name("stock_settings_taj_fields.json")


def _schema() -> list[dict]:
    data = json.loads(SCHEMA.read_text(encoding="utf-8"))
    if data.get("doctype") != SETTING_DOCTYPE:
        raise RuntimeError("Unexpected Stock Settings schema")
    fields = data["fields"]
    if [f["fieldname"] for f in fields] != [
        "taj_settings_tab", "taj_pick_list_receiving_section", SETTING_FIELD,
    ]:
        raise RuntimeError("Unexpected custom field names")
    return fields


def is_transfer_enabled() -> bool:
    """Fail closed for production, missing settings, and an unchecked flag."""
    if getattr(frappe.local, "site", None) != TEST_SITE:
        return False
    if not frappe.get_meta(SETTING_DOCTYPE).has_field(SETTING_FIELD):
        return False
    return bool(cint(frappe.db.get_single_value(SETTING_DOCTYPE, SETTING_FIELD) or 0))


def status() -> dict:
    """Read-only diagnostics for bench execute (not a public API)."""
    exists = bool(frappe.get_meta(SETTING_DOCTYPE).has_field(SETTING_FIELD))
    return {
        "site": getattr(frappe.local, "site", None),
        "test_site_only": getattr(frappe.local, "site", None) == TEST_SITE,
        "settings_doctype": SETTING_DOCTYPE,
        "settings_tab": "Taj",
        "setting_field": SETTING_FIELD,
        "setting_present": exists,
        "transfer_enabled": is_transfer_enabled(),
        "uses_site_config": False,
    }


def ensure_taj_tab():
    """Explicit idempotent test1.com setup for 3 stock-settings custom fields.

    Existing field names are never overwritten. No Stock Entry, stock ledger,
    Work Order or Pick List is created or modified by this setup routine.
    """
    if getattr(frappe.local, "site", None) != TEST_SITE:
        frappe.throw("Pick List Receiving setup is restricted to test1.com", frappe.PermissionError)
    user = frappe.session.user
    if user != "Administrator" and "System Manager" not in frappe.get_roles(user):
        frappe.throw("System Manager is required to configure Stock Settings", frappe.PermissionError)

    meta = frappe.get_meta(SETTING_DOCTYPE)
    if not meta.has_field("transaction_naming_html"):
        frappe.throw("Unsupported Stock Settings layout: missing transaction_naming_html")

    fields = _schema()
    # Check existing field definitions before creating anything; do not
    # overwrite a field added independently by another developer.
    for field in fields:
        existing = frappe.db.get_value(
            "Custom Field",
            {"dt": SETTING_DOCTYPE, "fieldname": field["fieldname"]},
            ["fieldtype", "label", "insert_after", "default"],
            as_dict=True,
        )
        if existing:
            for name in ("fieldtype", "label", "insert_after"):
                if existing.get(name) != field.get(name):
                    frappe.throw("Existing Custom Field definition differs: " + field["fieldname"])
            if field["fieldname"] == SETTING_FIELD and str(existing.get("default") or "0") != "0":
                frappe.throw("Existing Stock Settings transfer field default must be disabled")
        elif frappe.get_meta(SETTING_DOCTYPE).has_field(field["fieldname"]):
            frappe.throw("Field name already exists in Stock Settings: " + field["fieldname"])

    from frappe.custom.doctype.custom_field.custom_field import create_custom_field
    created = []
    for field in fields:
        if not frappe.db.exists("Custom Field", {"dt": SETTING_DOCTYPE, "fieldname": field["fieldname"]}):
            create_custom_field(SETTING_DOCTYPE, field.copy())
            created.append(field["fieldname"])

    frappe.clear_cache(doctype=SETTING_DOCTYPE)
    return {
        "site": TEST_SITE,
        "created": created,
        "fields_present": all(frappe.get_meta(SETTING_DOCTYPE).has_field(f["fieldname"]) for f in fields),
        "enabled": is_transfer_enabled(),
        "stock_entries_created": 0,
        "stock_entries_submitted": 0,
        "settings_path": "/app/stock-settings",
    }
