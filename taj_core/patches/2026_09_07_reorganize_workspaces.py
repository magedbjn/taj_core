import frappe


WORKSPACES = {
    "Taj": {
        "module": "Company Documents",
        "parent_page": "",
        "sequence_id": 33,
    },
    "Production": {
        "module": "Taj Manufacturing",
        "parent_page": "Taj",
        "sequence_id": 34,
    },
    "R&D": {
        "module": "RND",
        "parent_page": "Taj",
        "sequence_id": 35,
    },
    "QC": {
        "module": "QC",
        "parent_page": "Taj",
        "sequence_id": 36,
    },
    "Engineering": {
        "module": "Engineering",
        "parent_page": "Taj",
        "sequence_id": 37,
    },
    "Documents": {
        "module": "Company Documents",
        "parent_page": "Taj",
        "sequence_id": 38,
    },
    "PeopleOps": {
        "module": "PeopleOps",
        "parent_page": "Taj",
        "sequence_id": 39,
    },
    "Checklist": {
        "module": "Checklist",
        "parent_page": "Taj",
        "sequence_id": 40,
    },
    "Catering": {
        "module": "Catering",
        "parent_page": "Taj",
        "sequence_id": 41,
    },
}


def execute():
    _rename_engineering_workspace()
    _normalize_workspaces()


def _rename_engineering_workspace():
    old_name = "Engennering"
    new_name = "Engineering"

    old_exists = frappe.db.exists(
        "Workspace",
        old_name,
    )

    if not old_exists:
        return

    new_exists = frappe.db.exists(
        "Workspace",
        new_name,
    )

    if not new_exists:
        frappe.rename_doc(
            "Workspace",
            old_name,
            new_name,
            force=True,
            ignore_permissions=True,
        )
        return

    # If sync already created the corrected Workspace,
    # the misspelled legacy record is no longer needed.
    frappe.delete_doc(
        "Workspace",
        old_name,
        force=True,
        ignore_permissions=True,
    )


def _normalize_workspaces():
    for name, values in WORKSPACES.items():
        if not frappe.db.exists(
            "Workspace",
            name,
        ):
            continue

        frappe.db.set_value(
            "Workspace",
            name,
            values,
            update_modified=False,
        )
