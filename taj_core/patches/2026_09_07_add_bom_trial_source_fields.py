from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {
            "BOM": [
                {
                    "fieldname": "taj_product_proposal",
                    "label": "Product Proposal",
                    "fieldtype": "Link",
                    "options": "Product Proposal",
                    "insert_after": "project",
                    "read_only": 1,
                    "no_copy": 1,
                    "print_hide": 1,
                },
                {
                    "fieldname": "taj_product_proposal_trial",
                    "label": "Product Proposal Trial",
                    "fieldtype": "Link",
                    "options": "Product Proposal Trial",
                    "insert_after": "taj_product_proposal",
                    "read_only": 1,
                    "no_copy": 1,
                    "print_hide": 1,
                },
            ]
        },
        update=True,
    )
