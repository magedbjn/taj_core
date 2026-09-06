import frappe
from frappe.custom.doctype.custom_field.custom_field import (
    create_custom_fields,
)


FIELDNAME = "taj_pick_list_parent_warehouse"


def execute():
    create_custom_fields(
        {
            "Manufacturing Settings": [
                {
                    "fieldname": FIELDNAME,
                    "label": "Pick List Parent Warehouse",
                    "fieldtype": "Link",
                    "options": "Warehouse",
                    "insert_after": "taj_keep_rm_qty",
                    "description": (
                        "Parent warehouse used to scope raw-material "
                        "locations when creating Pick Lists from "
                        "Work Orders."
                    ),
                }
            ]
        },
        update=True,
    )

    frappe.clear_cache(
        doctype="Manufacturing Settings"
    )

    current = frappe.db.get_single_value(
        "Manufacturing Settings",
        FIELDNAME,
    )

    if current:
        return

    legacy_warehouse = "Raw Materials - Taj"

    if frappe.db.exists(
        "Warehouse",
        legacy_warehouse,
    ):
        frappe.db.set_single_value(
            "Manufacturing Settings",
            FIELDNAME,
            legacy_warehouse,
        )
