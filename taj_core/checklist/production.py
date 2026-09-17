import frappe
from frappe.utils import cint, get_datetime, getdate, now_datetime, nowdate

from taj_core.checklist.doctype.checklist_answer.checklist_answer import (
    create_checklist_answer_from_schedule,
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


def _today_answer_for_schedule(schedule_name, cycle_date):
    names = frappe.get_all(
        "Checklist Answer",
        filters={
            "schedule": schedule_name,
            "source_due_date": cycle_date,
        },
        order_by="creation desc",
        pluck="name",
        limit_page_length=1,
    )
    if names:
        return frappe.get_doc("Checklist Answer", names[0])
    return None


def _mark_production_violation(answer, work_order_name, started_at):
    if getattr(answer, "production_started_at", None):
        return 0
    if getattr(answer, "docstatus", 0) == 1 and getattr(answer, "status", None) == "Completed":
        return 0

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

    frappe.db.set_value("Checklist Answer", answer.name, updates, update_modified=False)
    return 1


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
    """Snapshot required pre-production checklists without blocking production."""
    if not work_order_name:
        return 0

    started_at = get_datetime(started_at or now_datetime())
    cycle_date = getdate(started_at or nowdate())
    violations = 0
    work_order_company = frappe.db.get_value("Work Order", work_order_name, "company")
    if not work_order_company:
        return 0

    schedules = frappe.get_all(
        "Checklist Schedule",
        filters={
            "required_before_production": 1,
            "is_active": 1,
            "company": work_order_company,
        },
        fields=["name", "template", "company"],
        limit_page_length=1000,
    )
    all_scheduled_templates = {
        template
        for template in frappe.get_all(
            "Checklist Schedule",
            pluck="template",
            limit_page_length=1000,
        )
        if template
    }

    for row in schedules:
        schedule_name = row.name
        try:
            answer = _today_answer_for_schedule(schedule_name, cycle_date)
            if not answer:
                answer = create_checklist_answer_from_schedule(
                    schedule_name=schedule_name,
                    source_due_date=cycle_date,
                    ignore_permissions=True,
                    from_scheduler=True,
                )
            violations += _mark_production_violation(answer, work_order_name, started_at)
        except Exception:
            frappe.log_error(
                title=f"Checklist production readiness snapshot failed for schedule {schedule_name}",
                message=frappe.get_traceback(),
            )

    # Backward compatibility for old templates that have not yet been moved to a Schedule.
    template_rows = frappe.get_all(
        "Checklist Question Template",
        filters={"required_before_production": 1},
        fields=["name", "department"],
    )
    for template_row in template_rows:
        template_name = template_row.name
        if template_name in all_scheduled_templates:
            continue
        template_department_company = (
            frappe.db.get_value("Department", template_row.department, "company")
            if template_row.department
            else None
        )
        if template_department_company and template_department_company != work_order_company:
            continue
        try:
            answer = _today_answer_for_template(template_name, cycle_date)
            if not answer:
                answer = create_checklist_answer_from_template(
                    template_name=template_name,
                    source_due_date=cycle_date,
                    ignore_permissions=True,
                    from_scheduler=True,
                )
            violations += _mark_production_violation(answer, work_order_name, started_at)
        except Exception:
            frappe.log_error(
                title=f"Checklist production readiness snapshot failed for {template_name}",
                message=frappe.get_traceback(),
            )

    return violations
