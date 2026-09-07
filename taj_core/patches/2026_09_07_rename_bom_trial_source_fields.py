import frappe
from frappe.custom.doctype.custom_field.custom_field import rename_fieldname
from frappe.model.rename_doc import rename_doc


DOCTYPE = "BOM"
RENAMES = (
    ("custom_product_proposal", "taj_product_proposal"),
    (
        "custom_product_proposal_trial",
        "taj_product_proposal_trial",
    ),
)


def execute():
    for old_fieldname, new_fieldname in RENAMES:
        _rename_custom_field(old_fieldname, new_fieldname)

    trial_field = "BOM-taj_product_proposal_trial"
    if frappe.db.exists("Custom Field", trial_field):
        frappe.db.set_value(
            "Custom Field",
            trial_field,
            "insert_after",
            "taj_product_proposal",
            update_modified=False,
        )

    frappe.clear_cache(doctype=DOCTYPE)


def _rename_custom_field(old_fieldname, new_fieldname):
    old_name = f"{DOCTYPE}-{old_fieldname}"
    new_name = f"{DOCTYPE}-{new_fieldname}"

    old_column_exists = frappe.db.has_column(
        DOCTYPE,
        old_fieldname,
    )
    new_column_exists = frappe.db.has_column(
        DOCTYPE,
        new_fieldname,
    )

    old_name_exists = bool(
        frappe.db.exists("Custom Field", old_name)
    )
    new_name_exists = bool(
        frappe.db.exists("Custom Field", new_name)
    )

    old_field_doc = frappe.db.get_value(
        "Custom Field",
        {
            "dt": DOCTYPE,
            "fieldname": old_fieldname,
        },
        "name",
    )
    new_field_doc = frappe.db.get_value(
        "Custom Field",
        {
            "dt": DOCTYPE,
            "fieldname": new_fieldname,
        },
        "name",
    )

    # Already migrated.
    if (
        new_field_doc == new_name
        and new_column_exists
        and not old_column_exists
        and not old_name_exists
    ):
        _set_system_generated(new_name, 1)
        return

    # Fieldname/column already changed, Custom Field name still legacy.
    # This can happen if a previous run reached rename_fieldname(), which
    # commits internally, but stopped before the Custom Field document name
    # was normalized.
    if (
        new_field_doc == old_name
        and new_column_exists
        and not old_column_exists
        and old_name_exists
        and not new_name_exists
    ):
        _set_system_generated(old_name, 0)
        try:
            _rename_custom_field_doc(old_name, new_name)
        finally:
            target_name = (
                new_name
                if frappe.db.exists("Custom Field", new_name)
                else old_name
            )
            _set_system_generated(target_name, 1)
        return

    # Expected state after the previous add-BOM-source-fields patch.
    if (
        old_field_doc == old_name
        and old_column_exists
        and not new_column_exists
        and old_name_exists
        and not new_name_exists
    ):
        # These fields were created by create_custom_fields(), therefore
        # Frappe marks them as system-generated. rename_fieldname() blocks
        # interactive renaming of such fields, but this migration owns both
        # the old and new definitions. Temporarily clear the guard, perform
        # Frappe's normal field/column/reference rename, then restore it.
        _set_system_generated(old_name, 0)

        try:
            rename_fieldname(old_name, new_fieldname)

            current_name = frappe.db.get_value(
                "Custom Field",
                {
                    "dt": DOCTYPE,
                    "fieldname": new_fieldname,
                },
                "name",
            )

            if current_name != old_name:
                frappe.throw(
                    "Unexpected Custom Field state after renaming "
                    f"{old_fieldname} to {new_fieldname}: "
                    f"{current_name}"
                )

            _rename_custom_field_doc(old_name, new_name)
        finally:
            target_name = None
            if frappe.db.exists("Custom Field", new_name):
                target_name = new_name
            elif frappe.db.exists("Custom Field", old_name):
                target_name = old_name

            if target_name:
                _set_system_generated(target_name, 1)

        return

    frappe.throw(
        "Cannot safely migrate BOM Trial source field "
        f"{old_fieldname} to {new_fieldname}. "
        f"old_field_doc={old_field_doc}, "
        f"new_field_doc={new_field_doc}, "
        f"old_column_exists={old_column_exists}, "
        f"new_column_exists={new_column_exists}, "
        f"old_name_exists={old_name_exists}, "
        f"new_name_exists={new_name_exists}"
    )


def _rename_custom_field_doc(old_name, new_name):
    rename_doc(
        doctype="Custom Field",
        old=old_name,
        new=new_name,
        force=True,
        ignore_permissions=True,
        show_alert=False,
        rebuild_search=False,
    )


def _set_system_generated(name, value):
    if not name or not frappe.db.exists("Custom Field", name):
        return

    frappe.db.set_value(
        "Custom Field",
        name,
        "is_system_generated",
        value,
        update_modified=False,
    )
