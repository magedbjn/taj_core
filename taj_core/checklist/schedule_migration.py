import calendar

import frappe
from frappe.utils import getdate, nowdate

from taj_core.checklist.rules import normalize_generation_key_value, parse_weeks_of_month


SUPPORTED_LEGACY_TYPES = {"Daily", "Weekly", "Monthly", "Weeks of Month"}


def legacy_schedule_name(template_name):
    return f"{template_name} - Schedule"


def _weekday_name(value):
    return calendar.day_name[getdate(value).weekday()]


def _legacy_schedule_values(template):
    periodicity = (template.periodicity or "None").strip()
    next_due_date = template.next_due_date
    anchor = getdate(next_due_date or nowdate())
    schedule_type = periodicity if periodicity in SUPPORTED_LEGACY_TYPES else "Manual"

    values = {
        "schedule_name": legacy_schedule_name(template.name),
        "template": template.name,
        "is_active": 1 if next_due_date else 0,
        "company": frappe.db.get_value("Department", template.department, "company") if template.department else None,
        "department": template.department,
        "plant_floor": template.plant_floor,
        "warehouse": template.warehouse,
        "asset": template.asset,
        "assignment_type": template.assignment_type or "Any User in Department",
        "assigned_user": template.assigned_user,
        "schedule_type": schedule_type,
        "interval": 1,
        "start_date": anchor if schedule_type != "Manual" else None,
        "enable_time_control": template.enable_time_control,
        "schedule_time": template.schedule_time,
        "completion_window_minutes": template.completion_window_minutes,
        "cycle_behavior": template.cycle_behavior or "Fresh Every Cycle",
        "required_before_production": template.required_before_production,
        "notify_on_overdue": template.notify_on_overdue,
        "escalate_after_minutes": template.escalate_after_minutes,
        "escalation_user": template.escalation_user,
    }

    if schedule_type in ("Weekly", "Weeks of Month"):
        values["day_of_week"] = _weekday_name(anchor)

    if schedule_type == "Monthly":
        values["day_of_month"] = anchor.day

    if schedule_type == "Weeks of Month":
        weeks = parse_weeks_of_month(template.weeks_of_month)
        for week in range(1, 6):
            values[f"week_{week}"] = 1 if week in weeks else 0

    return values


def sync_legacy_template_schedules():
    if not frappe.db.exists("DocType", "Checklist Schedule"):
        return {"created": [], "reused": []}

    fields = [
        "name", "periodicity", "weeks_of_month", "next_due_date", "department",
        "plant_floor", "warehouse", "asset", "assignment_type", "assigned_user",
        "enable_time_control", "schedule_time", "completion_window_minutes", "cycle_behavior",
        "required_before_production", "notify_on_overdue", "escalate_after_minutes", "escalation_user",
    ]
    templates = frappe.get_all(
        "Checklist Question Template",
        filters={"periodicity": ["!=", "None"]},
        fields=fields,
        limit_page_length=1000,
    )

    created = []
    reused = []
    for template in templates:
        schedule_name = legacy_schedule_name(template.name)
        try:
            if frappe.db.exists("Checklist Schedule", schedule_name):
                reused.append(schedule_name)
                continue

            values = _legacy_schedule_values(template)
            next_due_date = template.next_due_date
            doc = frappe.new_doc("Checklist Schedule")
            doc.update(values)
            doc.insert(ignore_permissions=True)
            doc.db_set("next_due_date", next_due_date, update_modified=False)
            created.append(doc.name)
        except Exception:
            frappe.log_error(
                title=f"Checklist schedule migration failed for {template.name}",
                message=frappe.get_traceback(),
            )

    return {"created": created, "reused": reused}


def _normalize_generation_keys():
    if not frappe.db.table_exists("Checklist Answer"):
        return 0
    if not frappe.db.has_column("Checklist Answer", "generation_key"):
        return 0

    # Empty strings conflict under a unique index; legacy/manual rows should be NULL.
    frappe.db.sql(
        """
        update `tabChecklist Answer`
        set generation_key = null
        where generation_key = ''
        """
    )

    rows = frappe.db.sql(
        """
        select name, generation_key
        from `tabChecklist Answer`
        where generation_key is not null
        """,
        as_list=True,
    )
    updated = 0
    for name, value in rows:
        normalized = normalize_generation_key_value(value)
        if normalized == value:
            continue
        frappe.db.set_value(
            "Checklist Answer",
            name,
            "generation_key",
            normalized,
            update_modified=False,
        )
        updated += 1
    return updated



def _deduplicate_generation_keys():
    if not frappe.db.table_exists("Checklist Answer"):
        return 0
    if not frappe.db.has_column("Checklist Answer", "generation_key"):
        return 0

    duplicate_rows = frappe.db.sql(
        """
        select generation_key
        from `tabChecklist Answer`
        where ifnull(generation_key, '') != ''
        group by generation_key
        having count(*) > 1
        """,
        as_list=True,
    )

    cleared = 0
    for row in duplicate_rows:
        generation_key = row[0]
        names = frappe.db.sql(
            """
            select name
            from `tabChecklist Answer`
            where generation_key = %s
            order by creation asc, name asc
            """,
            (generation_key,),
            as_list=True,
        )
        for duplicate in names[1:]:
            frappe.db.set_value(
                "Checklist Answer",
                duplicate[0],
                "generation_key",
                None,
                update_modified=False,
            )
            cleared += 1
    return cleared


def before_migrate():
    _normalize_generation_keys()
    _deduplicate_generation_keys()

def after_migrate():
    sync_legacy_template_schedules()
