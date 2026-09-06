import frappe
from frappe.model.rename_doc import rename_doc


RENAMES = (
    {
        "dt": "BOM",
        "fieldname": "taj_liquid_viscosity",
        "old": "BOM-taj_viscosity",
        "new": "BOM-taj_liquid_viscosity",
    },
    {
        "dt": "BOM Operation",
        "fieldname": "taj_split_batch",
        "old": "BOM Operation-custom_split_batch",
        "new": "BOM Operation-taj_split_batch",
    },
    {
        "dt": "Quality Inspection",
        "fieldname": "taj_rnd_sensory",
        "old": "Quality Inspection-taj_pouch_taste",
        "new": "Quality Inspection-taj_rnd_sensory",
    },
)


def execute():
    for row in RENAMES:
        actual = frappe.db.get_value(
            "Custom Field",
            {
                "dt": row["dt"],
                "fieldname": row["fieldname"],
            },
            "name",
        )

        # Already migrated.
        if actual == row["new"]:
            continue

        # Do not rename anything unexpected.
        if actual != row["old"]:
            frappe.throw(
                "Unexpected Custom Field identity for "
                f"{row['dt']}.{row['fieldname']}: {actual}"
            )

        if frappe.db.exists(
            "Custom Field",
            row["new"],
        ):
            frappe.throw(
                f"Target Custom Field already exists: {row['new']}"
            )

        rename_doc(
            doctype="Custom Field",
            old=row["old"],
            new=row["new"],
            force=True,
            ignore_permissions=True,
            show_alert=False,
            rebuild_search=False,
        )

    frappe.clear_cache()