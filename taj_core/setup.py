import click
import frappe


TAJ_FIELD_PREFIX = "taj_"

# Keep fields that may intentionally retain data when Taj Core is uninstalled.
KEEP_FIELDS = {
    "Employee": {"taj_nationality"},
    "Item": {"taj_sub_warehouse"},
}


def before_uninstall():
    """Remove Taj-owned Custom Fields while preserving explicitly retained fields."""
    rows = frappe.get_all(
        "Custom Field",
        filters={"fieldname": ["like", f"{TAJ_FIELD_PREFIX}%"]},
        fields=["name", "dt", "fieldname"],
    )

    removable_by_doctype = {}

    for row in rows:
        if row.fieldname in KEEP_FIELDS.get(row.dt, set()):
            continue

        removable_by_doctype.setdefault(row.dt, []).append(row)

    for doctype, fields in removable_by_doctype.items():
        names = [row.name for row in fields]
        fieldnames = [row.fieldname for row in fields]

        frappe.db.delete(
            "Property Setter",
            {
                "doc_type": doctype,
                "field_name": ["in", fieldnames],
            },
        )
        frappe.db.delete(
            "Custom Field",
            {"name": ["in", names]},
        )
        frappe.clear_cache(doctype=doctype)

        click.secho(
            f"Deleted {len(names)} Taj Core custom fields from {doctype}",
            fg="yellow",
        )
