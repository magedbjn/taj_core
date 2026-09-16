"""Create and update Checklist Action records from submitted inspections."""

import frappe
from frappe.utils import cint, cstr, now_datetime

from taj_core.checklist.action_rules import build_issue_key, observation_effect


def _question_identity(row):
    return cstr(getattr(row, "question_link", None) or getattr(row, "question", None)).strip()


def _issue_key(doc, row):
    return build_issue_key(
        getattr(doc, "template", None),
        _question_identity(row),
        getattr(doc, "plant_floor", None),
        getattr(doc, "warehouse", None),
        asset=getattr(doc, "asset", None),
    )


def _observation_time(doc):
    return getattr(doc, "completed_at", None) or now_datetime()


def _append_occurrence(action, doc, row, observation_type):
    for occurrence in getattr(action, "occurrences", None) or []:
        if (
            getattr(occurrence, "checklist_answer", None) == doc.name
            and getattr(occurrence, "checklist_row_id", None) == row.name
        ):
            return False

    action.append(
        "occurrences",
        {
            "observation_type": observation_type,
            "checklist_answer": doc.name,
            "checklist_row_id": row.name,
            "posting_date": getattr(doc, "posting_date", None),
            "observed_at": _observation_time(doc),
            "observer": getattr(doc, "answer_by", None)
            or getattr(doc, "taken_by", None)
            or frappe.session.user,
            "answer": getattr(row, "answer", None),
            "issue_note": getattr(row, "issue_note", None),
            "failure_reason": getattr(row, "failure_reason", None),
            "user_note": getattr(row, "user_note", None),
            "evidence_photo": getattr(row, "evidence_photo", None),
            "severity": getattr(row, "issue_severity", None) or "Medium",
            "quality_impact": cint(getattr(row, "quality_impact", 0)),
        },
    )
    return True


def _set_row_action(row, action_name):
    row.checklist_action = action_name
    if getattr(row, "name", None):
        frappe.db.set_value(
            "Checklist Answer Question",
            row.name,
            "checklist_action",
            action_name,
            update_modified=False,
        )


def _create_action(doc, row, issue_key):
    observed_at = _observation_time(doc)
    action = frappe.new_doc("Checklist Action")
    action.status = "Open"
    action.issue_key = issue_key
    action.open_issue_key = issue_key
    action.source_checklist = doc.name
    action.latest_checklist = doc.name
    action.source_template = getattr(doc, "template", None)
    action.question = getattr(row, "question_link", None)
    action.question_text = getattr(row, "question", None)
    action.department = getattr(doc, "department", None)
    action.plant_floor = getattr(doc, "plant_floor", None)
    action.warehouse = getattr(doc, "warehouse", None)
    action.asset = getattr(doc, "asset", None)
    action.severity = getattr(row, "issue_severity", None) or "Medium"
    action.quality_impact = cint(getattr(row, "quality_impact", 0))
    action.responsible_department = getattr(row, "responsible_department", None) or getattr(doc, "department", None)
    action.responsible_user = getattr(row, "responsible_user", None)
    action.requires_verification = cint(getattr(row, "require_verification", 0))
    action.latest_observation = "Issue"
    action.latest_answer = getattr(row, "answer", None)
    action.latest_issue_note = getattr(row, "issue_note", None)
    action.latest_failure_reason = getattr(row, "failure_reason", None)
    action.latest_evidence_photo = getattr(row, "evidence_photo", None)
    action.occurrence_count = 1
    action.first_detected_at = observed_at
    action.last_detected_at = observed_at
    _append_occurrence(action, doc, row, "Issue")
    action.insert(ignore_permissions=True)
    return action


def _update_action(action, doc, row, effect):
    observation_type = "Issue" if effect == "append_issue" else "Pass Observation"
    appended = _append_occurrence(action, doc, row, observation_type)
    if not appended:
        return action

    action.latest_checklist = doc.name
    action.latest_observation = observation_type
    action.latest_answer = getattr(row, "answer", None)

    if effect == "append_issue":
        action.occurrence_count = cint(getattr(action, "occurrence_count", 0)) + 1
        action.last_detected_at = _observation_time(doc)
        action.severity = getattr(row, "issue_severity", None) or action.severity or "Medium"
        action.quality_impact = max(
            cint(getattr(action, "quality_impact", 0)),
            cint(getattr(row, "quality_impact", 0)),
        )
        action.latest_issue_note = getattr(row, "issue_note", None)
        action.latest_failure_reason = getattr(row, "failure_reason", None)
        action.latest_evidence_photo = getattr(row, "evidence_photo", None)
        if action.status == "Pending Verification":
            action.status = "In Progress"

    action.save(ignore_permissions=True)
    return action


def process_checklist_actions(doc):
    """Create/reuse follow-up Actions and record later Pass observations.

    A Pass observation never closes an existing Action. It is evidence about the
    current inspection only. Closing remains an explicit resolution/verification
    lifecycle decision on Checklist Action.
    """
    processed = []

    for row in getattr(doc, "answer", None) or []:
        question_identity = _question_identity(row)
        if not question_identity:
            continue

        issue_key = _issue_key(doc, row)
        action_name = frappe.db.get_value(
            "Checklist Action",
            {"open_issue_key": issue_key},
            "name",
        )
        effect = observation_effect(
            cint(getattr(row, "has_issue", 0)),
            cint(getattr(row, "require_follow_up", 0)),
            bool(action_name),
        )

        if effect == "none":
            continue

        if effect == "create_issue_action":
            action = _create_action(doc, row, issue_key)
        else:
            action = frappe.get_doc("Checklist Action", action_name)
            action = _update_action(action, doc, row, effect)

        _set_row_action(row, action.name)
        processed.append(action.name)

    return processed
