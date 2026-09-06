import frappe


def execute():
    values = {
        "item_naming_series": "FG.####.P",
        "shelf_life_in_days": 720,
    }

    if frappe.db.exists(
        "Item Group",
        "Finished Goods",
    ):
        values["default_item_group"] = (
            "Finished Goods"
        )

    if frappe.db.exists("UOM", "Pouch"):
        values["stock_uom"] = "Pouch"

    if frappe.db.exists("Brand", "Taj"):
        values["default_brand"] = "Taj"

    default_company = frappe.db.get_single_value(
        "Global Defaults",
        "default_company",
    )

    if default_company:
        warehouse = (
            frappe.db.get_value(
                "Warehouse",
                {
                    "company": default_company,
                    "is_group": 0,
                    "warehouse_name":
                        ["like", "%Finished Goods%"],
                },
                "name",
            )
            or frappe.db.get_value(
                "Warehouse",
                {
                    "company": default_company,
                    "is_group": 0,
                },
                "name",
            )
        )

        if warehouse:
            values["default_warehouse"] = (
                warehouse
            )

    for fieldname, value in values.items():
        if not frappe.db.get_single_value(
            "RND Settings",
            fieldname,
        ):
            frappe.db.set_single_value(
                "RND Settings",
                fieldname,
                value,
            )
