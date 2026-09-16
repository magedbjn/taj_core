import frappe
from frappe.utils import now_datetime, nowdate

from taj_core.checklist.doctype.checklist_answer.checklist_answer import (
    create_checklist_answer_from_template,
)
from taj_core.checklist.notifications import notify_checklist_overdue
from taj_core.checklist.rules import deadline_notification_state


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


def process_open_checklist_deadlines():
    """Mark overdue open checklists and send one overdue/escalation alert.

    The checklist stays editable/open. Time status is operational evidence; it
    never auto-completes or blocks the user from finishing late.
    """
    now_dt = now_datetime()
    names = frappe.get_all(
        "Checklist Answer",
        filters={
            "docstatus": 0,
            "deadline_at": ["<=", now_dt],
            "status": ["in", ["Draft", "In Progress", "Expired"]],
        },
        pluck="name",
        limit_page_length=1000,
    )

    for name in names:
        try:
            doc = frappe.get_doc("Checklist Answer", name)
            state = deadline_notification_state(
                deadline=doc.deadline_at,
                now=now_dt,
                overdue_notified=bool(getattr(doc, "overdue_notified_at", None)),
                escalated=bool(getattr(doc, "escalated_at", None)),
                escalate_after_minutes=getattr(doc, "escalate_after_minutes", 0),
            )
            if not state["overdue"]:
                continue

            updates = {
                "status": "Expired",
                "time_status": "Escalated" if getattr(doc, "escalated_at", None) else "Overdue",
                "delay_minutes": state["delay_minutes"],
            }

            if state["notify_overdue"] and int(getattr(doc, "notify_on_overdue", 0) or 0):
                if notify_checklist_overdue(doc, escalation=False):
                    updates["overdue_notified_at"] = now_dt

            if state["notify_escalation"] and getattr(doc, "escalation_user", None):
                if notify_checklist_overdue(doc, escalation=True):
                    updates["escalated_at"] = now_dt
                    updates["time_status"] = "Escalated"

            frappe.db.set_value("Checklist Answer", name, updates, update_modified=False)
        except Exception:
            frappe.log_error(
                title=f"Checklist deadline processing failed for {name}",
                message=frappe.get_traceback(),
            )


def daily_checklist_scheduler():
    """Backward-compatible scheduler entry used by hooks.py."""
    create_due_checklist_answers()
