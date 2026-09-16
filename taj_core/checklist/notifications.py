import frappe
from frappe import _

from taj_core.checklist.notification_rules import build_issue_message, deduplicate_recipients


EXCLUDED_RECIPIENTS = {"Guest", "Administrator"}


def _department_users(department):
    if not department:
        return []

    employee_users = frappe.get_all(
        "Employee",
        filters={
            "department": department,
            "status": "Active",
            "user_id": ["is", "set"],
        },
        pluck="user_id",
    )
    employee_users = deduplicate_recipients(employee_users, excluded=EXCLUDED_RECIPIENTS)
    if not employee_users:
        return []

    return frappe.get_all(
        "User",
        filters={
            "name": ["in", employee_users],
            "enabled": 1,
            "user_type": "System User",
        },
        pluck="name",
    )


def _row_recipients(row):
    recipients = []
    notify_user = getattr(row, "notify_user", None)
    if notify_user:
        recipients.append(notify_user)

    notify_department = getattr(row, "notify_department", None)
    if notify_department:
        recipients.extend(_department_users(notify_department))

    return deduplicate_recipients(recipients, excluded=EXCLUDED_RECIPIENTS)


def _notification_subject(doc, row):
    severity = getattr(row, "issue_severity", None) or "Medium"
    question = getattr(row, "question", None) or _("Checklist issue")
    return _("Checklist {0}: {1} - {2}").format(doc.name, severity, question)


def _insert_notification(doc, row, user):
    message = build_issue_message(
        question=getattr(row, "question", None),
        severity=getattr(row, "issue_severity", None) or "Medium",
        failure_reason=getattr(row, "failure_reason", None),
        user_note=getattr(row, "user_note", None),
        responsible_department=getattr(row, "responsible_department", None),
        responsible_user=getattr(row, "responsible_user", None),
    )

    frappe.get_doc({
        "doctype": "Notification Log",
        "subject": _notification_subject(doc, row),
        "for_user": user,
        "type": "Alert",
        "document_type": "Checklist Answer",
        "document_name": doc.name,
        "from_user": getattr(doc, "answer_by", None) or frappe.session.user,
        "email_content": message,
    }).insert(ignore_permissions=True)


def notify_checklist_issues(doc):
    """Create persistent in-app notifications for configured failed questions.

    This function is intentionally called only from Checklist Answer.on_submit,
    so autosave and repeated draft edits never create duplicate notification
    noise.
    """
    if getattr(doc, "docstatus", 0) != 1 or getattr(doc, "status", None) != "Completed":
        return 0

    created = 0
    for row in getattr(doc, "answer", None) or []:
        if not getattr(row, "has_issue", 0):
            continue
        if getattr(row, "require_follow_up", 0):
            continue

        recipients = _row_recipients(row)
        for user in recipients:
            try:
                _insert_notification(doc, row, user)
                created += 1
            except Exception:
                frappe.log_error(
                    title="Checklist Notification Failed",
                    message=frappe.get_traceback(),
                )
    return created


def _checklist_responsible_users(doc):
    user = getattr(doc, "taken_by", None) or getattr(doc, "assigned_user", None)
    if user:
        return deduplicate_recipients([user], excluded=EXCLUDED_RECIPIENTS)
    return deduplicate_recipients(
        _department_users(getattr(doc, "department", None)),
        excluded=EXCLUDED_RECIPIENTS,
    )


def notify_checklist_overdue(doc, escalation=False):
    """Notify the operational owner, or a configured escalation user."""
    if escalation:
        recipients = deduplicate_recipients(
            [getattr(doc, "escalation_user", None)], excluded=EXCLUDED_RECIPIENTS
        )
        subject = _("Checklist Escalated: {0}").format(doc.name)
        message = _(
            "Checklist {0} is still incomplete after its deadline. Template: {1}. Deadline: {2}."
        ).format(doc.name, getattr(doc, "template", ""), getattr(doc, "deadline_at", ""))
    else:
        recipients = _checklist_responsible_users(doc)
        subject = _("Checklist Overdue: {0}").format(doc.name)
        message = _(
            "Checklist {0} has passed its deadline and is still incomplete. Template: {1}. Deadline: {2}."
        ).format(doc.name, getattr(doc, "template", ""), getattr(doc, "deadline_at", ""))

    created = 0
    for user in recipients:
        try:
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": subject,
                "for_user": user,
                "type": "Alert",
                "document_type": "Checklist Answer",
                "document_name": doc.name,
                "from_user": frappe.session.user,
                "email_content": message,
            }).insert(ignore_permissions=True)
            created += 1
        except Exception:
            frappe.log_error(
                title="Checklist Overdue Notification Failed",
                message=frappe.get_traceback(),
            )
    return created
