"""Explicit destructive seed for Engineering / Maintenance checklists.

This is intentionally *not* a patch and is not exposed over HTTP.  Run it only
when a site should replace all existing Checklist Answers, Templates and
Questions with the engineering-maintenance seed dataset.
"""

import frappe

from taj_core.checklist.engineering_maintenance_data import (
    QUESTION_LIBRARY,
    TEMPLATES,
    validate_seed_data,
)


CONFIRMATION_PHRASE = "DELETE ALL CHECKLIST DATA"
TARGET_DEPARTMENT = "Maintenance - Taj"
RESET_DOCTYPES = ("Checklist Answer", "Checklist Question Template", "Checklist Question")


def replace_all_checklist_data(confirm=""):
    """Delete requested Checklist data and seed 21 maintenance templates.

    Call with::

        bench --site <site> execute \
          taj_core.checklist.engineering_maintenance_seed.replace_all_checklist_data \
          --kwargs '{"confirm":"DELETE ALL CHECKLIST DATA"}'

    No database commit occurs until all deletes and inserts complete.
    """
    if confirm != CONFIRMATION_PHRASE:
        frappe.throw(
            "Destructive Checklist reset blocked. "
            f'Pass confirm="{CONFIRMATION_PHRASE}" to continue.'
        )

    data_errors = validate_seed_data()
    if data_errors:
        frappe.throw("Engineering maintenance seed data is invalid:<br>" + "<br>".join(data_errors))

    if not frappe.db.exists("Department", TARGET_DEPARTMENT):
        frappe.throw(
            f'Department "{TARGET_DEPARTMENT}" was not found. '
            "Nothing was deleted."
        )

    try:
        deleted = {}
        for doctype in RESET_DOCTYPES:
            deleted[doctype] = _delete_parent_docs(doctype)

        question_names = _create_questions()
        created_templates = _create_templates(question_names)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        raise

    return {
        "status": "completed",
        "department": TARGET_DEPARTMENT,
        "deleted": deleted,
        "questions_created": len(question_names),
        "templates_created": len(created_templates),
        "templates": created_templates,
        "source_codes": [row["code"] for row in TEMPLATES],
    }


def _delete_parent_docs(doctype):
    names = frappe.get_all(doctype, pluck="name", order_by="creation desc")
    for name in names:
        doc = frappe.get_doc(doctype, name)
        if doc.docstatus == 1:
            doc.flags.ignore_permissions = True
            doc.flags.ignore_links = True
            doc.cancel()

        frappe.delete_doc(
            doctype,
            name,
            force=1,
            ignore_permissions=True,
        )
    return len(names)


def _create_questions():
    question_names = {}
    for key, spec in QUESTION_LIBRARY.items():
        doc = frappe.new_doc("Checklist Question")
        doc.update(spec)
        if spec.get("require_follow_up"):
            doc.responsible_department = TARGET_DEPARTMENT
        doc.insert(ignore_permissions=True)
        question_names[key] = doc.name
    return question_names


def _create_templates(question_names):
    created = []
    for template in TEMPLATES:
        doc = frappe.new_doc("Checklist Question Template")
        doc.update(
            {
                "template_name": template["template_name"],
                "department": TARGET_DEPARTMENT,
                "assignment_type": "Any User in Department",
                "periodicity": "None",
                "enable_time_control": 0,
                "enable_quick_pass": 1,
                "enable_worker_check": 0,
                "cycle_behavior": "Fresh Every Cycle",
                "required_before_production": 0,
                "notify_on_overdue": 0,
            }
        )
        for key in template["question_keys"]:
            doc.append("questions", {"question": question_names[key]})
        doc.insert(ignore_permissions=True)
        created.append(doc.name)
    return created
