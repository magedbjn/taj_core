import frappe
from frappe import _

from taj_core.checklist.notification_rules import deduplicate_recipients
from taj_core.checklist.notifications import EXCLUDED_RECIPIENTS, _department_users


def _manager_users():
    role_users = frappe.get_all(
        "Has Role",
        filters={"role": ["in", ["Checklist Manager", "IT Manager", "System Manager"]]},
        pluck="parent",
    )
    role_users = deduplicate_recipients(role_users, excluded=EXCLUDED_RECIPIENTS)
    if not role_users:
        return []
    return frappe.get_all(
        "User",
        filters={
            "name": ["in", role_users],
            "enabled": 1,
            "user_type": "System User",
        },
        pluck="name",
    )


def _created_recipients(action):
    recipients = []
    if getattr(action, "responsible_user", None):
        recipients.append(action.responsible_user)
    if getattr(action, "responsible_department", None):
        recipients.extend(_department_users(action.responsible_department))
    if not recipients and getattr(action, "department", None):
        recipients.extend(_department_users(action.department))
    return deduplicate_recipients(recipients, excluded=EXCLUDED_RECIPIENTS)


def _verification_recipients(action):
    recipients = []
    if getattr(action, "verification_user", None):
        recipients.append(action.verification_user)
    if getattr(action, "verification_department", None):
        recipients.extend(_department_users(action.verification_department))
    if not recipients:
        recipients.extend(_manager_users())
    return deduplicate_recipients(recipients, excluded=EXCLUDED_RECIPIENTS)


def _insert_notification(action, user, subject, message):
    frappe.get_doc(
        {
            "doctype": "Notification Log",
            "subject": subject,
            "for_user": user,
            "type": "Alert",
            "document_type": "Checklist Action",
            "document_name": action.name,
            "from_user": frappe.session.user,
            "email_content": message,
        }
    ).insert(ignore_permissions=True)


def notify_action_created(action):
    subject = _("Checklist Action: {0} - {1}").format(
        getattr(action, "severity", None) or "Medium",
        getattr(action, "question_text", None) or action.name,
    )
    message = _(
        "A checklist issue requires follow-up. Action: {0}. Source checklist: {1}. Responsible department: {2}."
    ).format(
        action.name,
        getattr(action, "source_checklist", None) or "",
        getattr(action, "responsible_department", None) or "",
    )

    created = 0
    for user in _created_recipients(action):
        try:
            _insert_notification(action, user, subject, message)
            created += 1
        except Exception:
            frappe.log_error(
                title="Checklist Action Notification Failed",
                message=frappe.get_traceback(),
            )
    return created


def notify_action_pending_verification(action):
    subject = _("Checklist Action Pending Verification: {0}").format(action.name)
    message = _(
        "Checklist Action {0} has a documented resolution and is waiting for verification."
    ).format(action.name)

    created = 0
    for user in _verification_recipients(action):
        try:
            _insert_notification(action, user, subject, message)
            created += 1
        except Exception:
            frappe.log_error(
                title="Checklist Action Verification Notification Failed",
                message=frappe.get_traceback(),
            )
    return created
