import frappe
from frappe.utils import cint, get_datetime, getdate, now_datetime, nowdate

from taj_core.checklist.doctype.checklist_answer.checklist_answer import (
    create_checklist_answer_from_template,
)
from taj_core.checklist.rules import summarize_required_answers


PRODUCTION_STOCK_ENTRY_PURPOSES = {
    "Material Transfer for Manufacture",
    "Material Consumption for Manufacture",
    "Manufacture",
}


def _production_started_at(doc):
    value = getattr(doc, "actual_start_date", None)
    if value:
        return get_datetime(value)
    return now_datetime()


def on_work_order_update_after_submit(doc, method=None):
    """Record readiness once ERPNext considers the Work Order active."""
    if getattr(doc, "docstatus", 0) != 1:
        return
    if getattr(doc, "status", None) not in ("In Process", "Completed"):
        return
    record_production_start(doc.name, started_at=_production_started_at(doc))


def on_stock_entry_submit(doc, method=None):
    """Fallback/confirmation for manufacturing activity linked to a Work Order."""
    work_order = getattr(doc, "work_order", None)
    purpose = getattr(doc, "purpose", None)
    if not work_order or purpose not in PRODUCTION_STOCK_ENTRY_PURPOSES:
        return
    record_production_start(work_order, started_at=now_datetime())


def _today_answer_for_template(template_name, cycle_date):
    names = frappe.get_all(
        "Checklist Answer",
        filters={
            "template": template_name,
            "source_due_date": cycle_date,
        },
        order_by="creation desc",
        pluck="name",
        limit_page_length=1,
    )
    if names:
        return frappe.get_doc("Checklist Answer", names[0])
    return None


def _incomplete_snapshot(answer_doc):
    summary = summarize_required_answers(getattr(answer_doc, "answer", None) or [])
    incomplete = list(summary["incomplete"])

    if cint(getattr(answer_doc, "enable_worker_check", 0)):
        shortage = cint(getattr(answer_doc, "worker_shortage_count", 0))
        if shortage > 0:
            incomplete.append(f"Worker requirement short by {shortage}")

    if not incomplete and not (getattr(answer_doc, "docstatus", 0) == 1 and getattr(answer_doc, "status", None) == "Completed"):
        incomplete.append("Checklist not submitted")

    return summary, incomplete


def record_production_start(work_order_name, started_at=None):
    """Snapshot required pre-production checklists without blocking production.

    Idempotent per checklist occurrence: the first observed production start is
    the audit point preserved for management reporting.
    """
    if not work_order_name:
        return 0

    started_at = get_datetime(started_at or now_datetime())
    cycle_date = getdate(started_at or nowdate())

    template_names = frappe.get_all(
        "Checklist Question Template",
        filters={"required_before_production": 1},
        pluck="name",
    )

    violations = 0
    for template_name in template_names:
        try:
            answer = _today_answer_for_template(template_name, cycle_date)
            if not answer:
                answer = create_checklist_answer_from_template(
                    template_name=template_name,
                    source_due_date=cycle_date,
                    ignore_permissions=True,
                    from_scheduler=True,
                )

            if getattr(answer, "production_started_at", None):
                continue

            if getattr(answer, "docstatus", 0) == 1 and getattr(answer, "status", None) == "Completed":
                continue

            summary, incomplete = _incomplete_snapshot(answer)
            updates = {
                "production_started_before_completion": 1,
                "production_started_at": started_at,
                "production_work_order": work_order_name,
                "completion_percent_at_production_start": summary["percent"],
                "incomplete_items_at_production_start": "\n".join(incomplete),
            }
            if getattr(answer, "result_status", None) == "Normal":
                updates["result_status"] = "Has Issue"

            frappe.db.set_value(
                "Checklist Answer",
                answer.name,
                updates,
                update_modified=False,
            )
            violations += 1
        except Exception:
            frappe.log_error(
                title=f"Checklist production readiness snapshot failed for {template_name}",
                message=frappe.get_traceback(),
            )

    return violations
