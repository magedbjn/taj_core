import frappe


LEGACY_DOCTYPE = "Product Proposal Trial Cooking"


def execute():
    """Permanently retire the legacy Product Proposal child table.

    The user explicitly approved deletion of its historical rows. Product Proposal
    Trial is the supported R&D trial model going forward.
    """
    if frappe.db.exists("DocType", LEGACY_DOCTYPE):
        frappe.delete_doc(
            "DocType",
            LEGACY_DOCTYPE,
            force=1,
            ignore_permissions=True,
            ignore_missing=True,
        )

    # Defensive cleanup for sites where the DocType metadata was removed earlier
    # but the child table still exists.
    if frappe.db.table_exists(LEGACY_DOCTYPE):
        frappe.db.sql_ddl(
            "DROP TABLE IF EXISTS `tabProduct Proposal Trial Cooking`"
        )

    frappe.clear_cache(doctype="Product Proposal")
    frappe.clear_cache()
