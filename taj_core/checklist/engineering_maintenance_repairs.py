"""Targeted, non-destructive repairs for reviewed maintenance templates.

This module is intentionally manual: it is not a patch and is not called by
migrate. It only corrects the specific test-data deviations confirmed in the
2026-09-16 Checklist export review.
"""

import frappe

from taj_core.checklist.engineering_maintenance_data import REVIEWED_TEMPLATE_REPAIRS


CONFIRMATION_PHRASE = "APPLY REVIEWED CHECKLIST TEMPLATE FIXES"


def apply_reviewed_template_repairs(confirm=""):
    """Apply only the reviewed template-setting corrections.

    Scheduling, questions, locations and Asset assignment are intentionally
    preserved. Missing templates are reported and skipped.
    """
    if confirm != CONFIRMATION_PHRASE:
        frappe.throw(
            "Checklist template repair blocked. "
            f'Pass confirm="{CONFIRMATION_PHRASE}" to continue.'
        )

    updated = {}
    missing = []

    for template_name, values in REVIEWED_TEMPLATE_REPAIRS.items():
        if not frappe.db.exists("Checklist Question Template", template_name):
            missing.append(template_name)
            continue

        frappe.db.set_value(
            "Checklist Question Template",
            template_name,
            values,
            update_modified=True,
        )
        updated[template_name] = values

    frappe.db.commit()
    return {
        "status": "completed",
        "updated": updated,
        "missing": missing,
    }
