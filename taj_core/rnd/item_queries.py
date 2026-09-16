import frappe

from erpnext.controllers.queries import item_query


RAW_MATERIALS_ITEM_GROUP = "Raw Materials"


def get_raw_material_item_groups():
    """Return Raw Materials and every descendant Item Group."""
    bounds = frappe.db.get_value(
        "Item Group",
        RAW_MATERIALS_ITEM_GROUP,
        ["lft", "rgt"],
        as_dict=True,
    )

    if not bounds:
        return []

    return frappe.get_all(
        "Item Group",
        filters={
            "lft": [">=", bounds.lft],
            "rgt": ["<=", bounds.rgt],
        },
        order_by="lft asc",
        pluck="name",
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def raw_material_item_query(
    doctype,
    txt,
    searchfield,
    start,
    page_len,
    filters=None,
):
    """Item link query restricted to Raw Materials and child groups."""
    groups = get_raw_material_item_groups()
    if not groups:
        return []

    filters = frappe.parse_json(filters) if filters else {}
    filters["item_group"] = ["in", groups]

    return item_query(
        "Item",
        txt,
        searchfield,
        start,
        page_len,
        filters,
    )
