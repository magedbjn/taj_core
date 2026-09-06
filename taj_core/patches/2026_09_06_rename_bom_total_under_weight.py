
import frappe

from frappe.custom.doctype.custom_field.custom_field import rename_fieldname
from frappe.model.rename_doc import rename_doc


DOCTYPE = "BOM"

OLD_FIELDNAME = "taj_total_under_weight_"
NEW_FIELDNAME = "taj_total_under_weight"

OLD_NAME = "BOM-taj_total_under_weight_"
NEW_NAME = "BOM-taj_total_under_weight"


def execute():
    old_column_exists = frappe.db.has_column(
        DOCTYPE,
        OLD_FIELDNAME,
    )

    new_column_exists = frappe.db.has_column(
        DOCTYPE,
        NEW_FIELDNAME,
    )

    old_name_exists = bool(
        frappe.db.exists(
            "Custom Field",
            OLD_NAME,
        )
    )

    new_name_exists = bool(
        frappe.db.exists(
            "Custom Field",
            NEW_NAME,
        )
    )

    old_field_doc = frappe.db.get_value(
        "Custom Field",
        {
            "dt": DOCTYPE,
            "fieldname": OLD_FIELDNAME,
        },
        "name",
    )

    new_field_doc = frappe.db.get_value(
        "Custom Field",
        {
            "dt": DOCTYPE,
            "fieldname": NEW_FIELDNAME,
        },
        "name",
    )

    # Already fully migrated.
    if (
        new_field_doc == NEW_NAME
        and new_column_exists
        and not old_column_exists
        and not old_name_exists
    ):
        return

    # Partial state: fieldname/column was already renamed,
    # but the Custom Field document still has its old name.
    if (
        new_field_doc == OLD_NAME
        and new_column_exists
        and not old_column_exists
        and old_name_exists
        and not new_name_exists
    ):
        rename_doc(
            doctype="Custom Field",
            old=OLD_NAME,
            new=NEW_NAME,
            force=True,
            ignore_permissions=True,
            show_alert=False,
            rebuild_search=False,
        )

        frappe.clear_cache(
            doctype=DOCTYPE
        )
        return

    # Expected legacy state.
    if (
        old_field_doc == OLD_NAME
        and old_column_exists
        and not new_column_exists
        and old_name_exists
        and not new_name_exists
    ):
        rename_fieldname(
            OLD_NAME,
            NEW_FIELDNAME,
        )

        current_name = frappe.db.get_value(
            "Custom Field",
            {
                "dt": DOCTYPE,
                "fieldname": NEW_FIELDNAME,
            },
            "name",
        )

        if current_name != OLD_NAME:
            frappe.throw(
                "Unexpected Custom Field state after renaming "
                f"{OLD_FIELDNAME} to {NEW_FIELDNAME}: {current_name}"
            )

        rename_doc(
            doctype="Custom Field",
            old=OLD_NAME,
            new=NEW_NAME,
            force=True,
            ignore_permissions=True,
            show_alert=False,
            rebuild_search=False,
        )

        frappe.clear_cache(
            doctype=DOCTYPE
        )
        return

    frappe.throw(
        "Cannot safely migrate BOM Total Under Weight. "
        f"old_field_doc={old_field_doc}, "
        f"new_field_doc={new_field_doc}, "
        f"old_column_exists={old_column_exists}, "
        f"new_column_exists={new_column_exists}, "
        f"old_name_exists={old_name_exists}, "
        f"new_name_exists={new_name_exists}"
    )