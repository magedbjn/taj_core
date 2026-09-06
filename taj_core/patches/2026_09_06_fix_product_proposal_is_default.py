import frappe


def execute():
    frappe.db.sql(
        """
        UPDATE `tabProduct Proposal`
        SET is_default = CASE
            WHEN sensory_decision = 'Approve' THEN 1
            ELSE 0
        END
        WHERE COALESCE(is_default, 0) <> CASE
            WHEN sensory_decision = 'Approve' THEN 1
            ELSE 0
        END
        """
    )
