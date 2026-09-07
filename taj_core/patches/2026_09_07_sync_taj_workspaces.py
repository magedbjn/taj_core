import frappe
from frappe.modules.import_file import import_file_by_path


WORKSPACE_FILES = (
    ("checklist", "checklist"),
    ("taj_manufacturing", "production"),
    ("peopleops", "peopleops"),
)


def execute():
    """Force-sync Taj standard Workspaces changed by this release.

    Frappe skips non-DocType JSON imports when the database document has a
    newer modified timestamp than the file. These Workspaces may have been
    edited/exported previously, so a normal migrate can leave stale runtime
    links even though the source JSON is correct.
    """
    for module_name, workspace_name in WORKSPACE_FILES:
        path = frappe.get_app_path(
            "taj_core",
            module_name,
            "workspace",
            workspace_name,
            f"{workspace_name}.json",
        )
        import_file_by_path(
            path,
            force=True,
            ignore_version=True,
        )

    frappe.clear_cache()
