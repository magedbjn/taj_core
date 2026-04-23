import frappe
from frappe import _
from frappe.model.document import Document

from taj_core.checklist.doctype.checklist_answer.checklist_answer import create_checklist_answer_from_template
from taj_core.checklist.permissions import is_checklist_manager


class ChecklistQuestionTemplate(Document):
    def validate(self):
        validate_template(self)


def validate_template(doc):
    if not doc.template_name:
        frappe.throw(_("Template Name is required."))

    if not doc.department:
        frappe.throw(_("Department is required."))

    if not doc.questions:
        frappe.throw(_("At least one checklist question is required."))

    question_names = []
    for row in doc.questions:
        if not row.question:
            frappe.throw(_("Checklist question row cannot be empty."))
        question_names.append(row.question)

    if len(question_names) != len(set(question_names)):
        frappe.throw(_("Duplicate questions are not allowed in the same template."))

    if doc.assignment_type == "Specific User" and not doc.assigned_user:
        frappe.throw(_("Assigned User is required when Assignment Type is Specific User."))

    if frappe.utils.cint(doc.enable_time_control):
        if not doc.schedule_time:
            frappe.throw(_("Schedule Time is required when Time Control is enabled."))

        if not frappe.utils.cint(doc.completion_window_minutes):
            frappe.throw(_("Completion Window Minutes is required when Time Control is enabled."))


@frappe.whitelist()
def create_checklist_answer_from_template_form(template_name=None):
    if not is_checklist_manager(frappe.session.user):
        frappe.throw(_("Only Checklist Manager can generate checklist from template."), frappe.PermissionError)

    if not template_name:
        frappe.throw(_("Template is required."))

    doc = frappe.get_doc("Checklist Question Template", template_name)
    validate_template(doc)

    created = create_checklist_answer_from_template(template_name=doc.name)
    return {
        "name": created.name,
        "redirect_to": f"Form/Checklist Answer/{created.name}",
    }
