import frappe


def execute():
    replacements = (
        "Product Proposal Sensory Evaluation",
        "Sensory Feedback",
    )

    for doctype in replacements:
        frappe.db.sql(
            f"""
            update `tab{doctype}`
            set final_status = %s
            where final_status = %s
            """,
            (
                "Need Improvement",
                "Need Improvemen",
            ),
        )
