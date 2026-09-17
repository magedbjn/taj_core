"""Explicit seed/sync utilities for the lean GMP checklist catalog.

Nothing in this module runs during migrate.  An administrator invokes
``seed_gmp_checklists`` deliberately after schema migration and supplies the
site-specific Department that will own the GMP checklists.
"""

import calendar

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate

from taj_core.checklist.gmp_catalog import GMP_QUESTIONS, GMP_TEMPLATES, validate_gmp_catalog
from taj_core.checklist.permissions import is_checklist_manager
from taj_core.checklist.rules import parse_weeks_of_month
from taj_core.checklist.schedule_migration import legacy_schedule_name


STANDARD_DEFAULTS = {
    "GMP": "Good Manufacturing Practices",
    "ISO 22000": "Food safety management systems",
    "HACCP": "Hazard Analysis and Critical Control Points",
    "SFDA": "Saudi Food and Drug Authority",
    "Internal SOP": "Internal standard operating procedure",
}


def _ensure_seed_manager():
    if not is_checklist_manager(frappe.session.user):
        frappe.throw(
            _("Only Checklist Manager or System Manager can synchronize the GMP catalog."),
            frappe.PermissionError,
        )


QUESTION_DEFAULTS = {
    "type": "Pass/Fail/NA",
    "is_required": 1,
    "quick_pass_allowed": 1,
    "require_failure_reason": 1,
    "require_failure_note": 0,
    "require_failure_photo": 0,
    "allow_no_photo_with_reason": 0,
    "require_follow_up": 1,
    "require_verification": 0,
}


def _get_or_create_standard(standard_name):
    existing_name = frappe.db.exists("Checklist Standard", standard_name)
    if existing_name:
        return existing_name, False

    doc = frappe.new_doc("Checklist Standard")
    doc.standard_name = standard_name
    doc.active = 1
    doc.description = STANDARD_DEFAULTS.get(standard_name, "")
    doc.insert(ignore_permissions=True)
    return doc.name, True


def _merge_question_standards(doc, definition):
    changed = False
    existing = {
        str(getattr(row, "standard", None) or "").strip(): row
        for row in (doc.get("standards") or [])
        if str(getattr(row, "standard", None) or "").strip()
    }
    for standard_row in definition.get("standards") or []:
        standard_name = str(standard_row.get("standard") or "").strip()
        reference = str(standard_row.get("reference") or "").strip()
        if not standard_name:
            continue
        row = existing.get(standard_name)
        if row is None:
            doc.append("standards", {"standard": standard_name, "reference": reference})
            changed = True
        elif str(getattr(row, "reference", None) or "").strip() != reference:
            row.reference = reference
            changed = True
    return changed


def _get_or_create_question(definition):
    question_text = definition["question"].strip()
    existing_name = frappe.db.exists("Checklist Question", {"question": question_text})

    if not existing_name:
        for legacy_text in definition.get("legacy_questions") or []:
            legacy_text = str(legacy_text or "").strip()
            if not legacy_text:
                continue
            existing_name = frappe.db.exists("Checklist Question", {"question": legacy_text})
            if existing_name:
                break

    values = dict(QUESTION_DEFAULTS)
    values.update({
        "question": question_text,
        "question_group": definition["question_group"],
        "standard_reference": definition["standard_reference"],
        "issue_severity": definition.get("issue_severity") or "Medium",
        "quality_impact": int(definition.get("quality_impact") or 0),
        "require_failure_reason": int(definition.get("require_failure_reason") or 0),
        "require_failure_note": int(definition.get("require_failure_note") or 0),
        "require_failure_photo": int(definition.get("require_failure_photo") or 0),
        "allow_no_photo_with_reason": int(definition.get("allow_no_photo_with_reason") or 0),
        "require_affected_item": int(definition.get("require_affected_item") or 0),
        "affected_item_options": definition.get("affected_item_options") or "",
        "require_issue_type": int(definition.get("require_issue_type") or 0),
        "issue_type_options": definition.get("issue_type_options") or "",
    })

    if existing_name:
        doc = frappe.get_doc("Checklist Question", existing_name)
        metadata_changed = False

        # Explicit GMP seed owns this catalog configuration. Stable legacy aliases
        # let wording improve without creating duplicate Q records.
        if getattr(doc, "question", None) != question_text:
            doc.question = question_text
            metadata_changed = True

        for fieldname, value in values.items():
            if fieldname == "question":
                continue
            if hasattr(doc, fieldname) and getattr(doc, fieldname, None) != value:
                setattr(doc, fieldname, value)
                metadata_changed = True

        if hasattr(doc, "standards") and _merge_question_standards(doc, definition):
            metadata_changed = True

        if metadata_changed:
            doc.save(ignore_permissions=True)
        return doc.name, False

    doc = frappe.new_doc("Checklist Question")
    doc.update(values)
    for standard_row in definition.get("standards") or []:
        doc.append("standards", standard_row)
    doc.insert(ignore_permissions=True)
    return doc.name, True


def _sync_gmp_template(template_name, definition, department, question_names):
    if not template_name.startswith("GMP - "):
        frappe.throw(_("Refusing to seed a non-GMP template: {0}").format(template_name))

    existing_name = frappe.db.exists("Checklist Question Template", template_name)
    if existing_name:
        template = frappe.get_doc("Checklist Question Template", existing_name)
        created = False
    else:
        template = frappe.new_doc("Checklist Question Template")
        template.template_name = template_name
        created = True

    template.enable_quick_pass = 1

    template.set("questions", [])
    for question_name in question_names:
        template.append("questions", {"question": question_name})

    if created:
        template.insert(ignore_permissions=True)
    else:
        template.save(ignore_permissions=True)

    return template.name, created


def _sync_gmp_schedule(template_name, definition, department):
    schedule_name = legacy_schedule_name(template_name)
    existing_name = frappe.db.exists("Checklist Schedule", schedule_name)
    if existing_name:
        schedule = frappe.get_doc("Checklist Schedule", existing_name)
        if cint(schedule.is_active):
            return schedule.name, False
        created = False
    else:
        schedule = frappe.new_doc("Checklist Schedule")
        schedule.schedule_name = schedule_name
        created = True

    schedule.template = template_name
    schedule.department = department
    schedule.is_active = 0
    schedule.assignment_type = "Any User in Department"
    schedule.schedule_type = "Weeks of Month"
    schedule.interval = 1
    schedule.cycle_behavior = "Fresh Every Cycle"

    weeks = parse_weeks_of_month(definition["weeks_of_month"])
    for week in range(1, 6):
        setattr(schedule, f"week_{week}", 1 if week in weeks else 0)

    if not schedule.start_date:
        schedule.start_date = nowdate()
    if not schedule.day_of_week:
        schedule.day_of_week = calendar.day_name[getdate(schedule.start_date).weekday()]

    if created:
        schedule.insert(ignore_permissions=True)
    else:
        schedule.save(ignore_permissions=True)

    return schedule.name, created


@frappe.whitelist()
def seed_gmp_checklists(department=None):
    """Create/reuse lean GMP questions and synchronize the nine GMP templates.

    Existing non-GMP data is never deleted or changed. Existing GMP catalog
    questions are reused by current or legacy text and synchronized to the
    catalog configuration. Existing catalog-owned GMP templates are synchronized
    only when this explicit seed function is run.
    """
    _ensure_seed_manager()

    department = str(department or "").strip()
    if not department:
        frappe.throw(_("Department is required."))
    if not frappe.db.exists("Department", department):
        frappe.throw(_("Department does not exist: {0}").format(department))

    errors = validate_gmp_catalog()
    if errors:
        frappe.throw(_("GMP catalog validation failed: {0}").format("; ".join(errors)))

    created_standards = []
    reused_standards = []
    standard_names = sorted(STANDARD_DEFAULTS)
    for standard_name in standard_names:
        name, created = _get_or_create_standard(standard_name)
        (created_standards if created else reused_standards).append(name)

    question_name_by_key = {}
    created_questions = []
    reused_questions = []

    for key, definition in GMP_QUESTIONS.items():
        question_name, created = _get_or_create_question(definition)
        question_name_by_key[key] = question_name
        (created_questions if created else reused_questions).append(question_name)

    created_templates = []
    updated_templates = []
    created_schedules = []
    reused_schedules = []
    for template_name, definition in GMP_TEMPLATES.items():
        question_names = [question_name_by_key[key] for key in definition["questions"]]
        name, created = _sync_gmp_template(
            template_name=template_name,
            definition=definition,
            department=department,
            question_names=question_names,
        )
        (created_templates if created else updated_templates).append(name)

        schedule_name, schedule_created = _sync_gmp_schedule(
            template_name=template_name,
            definition=definition,
            department=department,
        )
        (created_schedules if schedule_created else reused_schedules).append(schedule_name)

    return {
        "department": department,
        "question_count": len(question_name_by_key),
        "created_standards": created_standards,
        "reused_standards": reused_standards,
        "created_questions": created_questions,
        "reused_questions": reused_questions,
        "created_templates": created_templates,
        "updated_templates": updated_templates,
        "created_schedules": created_schedules,
        "reused_schedules": reused_schedules,
        "schedules_inactive_until_activated": [
            schedule_name
            for schedule_name in (created_schedules + reused_schedules)
            if not cint(frappe.db.get_value("Checklist Schedule", schedule_name, "is_active"))
        ],
    }
