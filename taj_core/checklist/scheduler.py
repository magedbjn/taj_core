import frappe
from frappe.utils import nowdate
from taj_core.checklist.doctype.checklist_answer.checklist_answer import (
    create_checklist_answer_from_template,
)


def create_due_checklist_answers():
    today = nowdate()

    templates = frappe.get_all(
        "Checklist Question Template",
        filters={
            "periodicity": ["!=", "None"],
            "next_due_date": ["<=", today],
        },
        pluck="name",
    )

    for template_name in templates:
        try:
            create_checklist_answer_from_template(
                template_name=template_name,
                ignore_permissions=True,
                from_scheduler=True,
            )
        except Exception:
            frappe.log_error(
                title=f"Checklist scheduler failed for template {template_name}",
                message=frappe.get_traceback(),
            )