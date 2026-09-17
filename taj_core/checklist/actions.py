"""Create and update Checklist Action records from submitted inspections."""

import frappe
from frappe.utils import cint, cstr, now_datetime

from taj_core.checklist.action_rules import (
    build_action_title,
    build_issue_key,
    observation_effect,
    operational_scope_matches,
)


def _question_identity(row):
    return cstr(getattr(row, "question_link", None) or getattr(row, "question", None)).strip()


def _issue_key(doc, row, scheduled_scope=None):
    if scheduled_scope is None:
        scheduled_scope = bool(getattr(doc, "schedule", None))
    return build_issue_key(
        getattr(doc, "template", None),
        _question_identity(row),
        getattr(doc, "plant_floor", None),
        getattr(doc, "warehouse", None),
        asset=getattr(doc, "asset", None),
        company=getattr(doc, "company", None) if scheduled_scope else None,
        department=getattr(doc, "department", None) if scheduled_scope else None,
        affected_items=getattr(row, "affected_items", None),
        issue_type=getattr(row, "issue_type", None),
    )


def _observation_time(doc):
    return getattr(doc, "completed_at", None) or now_datetime()


def _latest_issue_note(row):
    return cstr(
        getattr(row, "user_note", None) or getattr(row, "issue_note", None) or ""
    ).strip() or None


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
            "affected_items": getattr(row, "affected_items", None),
            "issue_type": getattr(row, "issue_type", None),
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
    action.action_title = build_action_title(
        getattr(row, "question", None),
        getattr(row, "affected_items", None),
        getattr(row, "issue_type", None),
    )
    action.source_checklist = doc.name
    action.latest_checklist = doc.name
    action.source_template = getattr(doc, "template", None)
    action.question = getattr(row, "question_link", None)
    action.question_text = getattr(row, "question", None)
    action.company = getattr(doc, "company", None)
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
    action.latest_issue_note = _latest_issue_note(row)
    action.latest_failure_reason = getattr(row, "failure_reason", None)
    action.latest_affected_items = getattr(row, "affected_items", None)
    action.latest_issue_type = getattr(row, "issue_type", None)
    action.latest_evidence_photo = getattr(row, "evidence_photo", None)
    action.occurrence_count = 1
    action.first_detected_at = observed_at
    action.last_detected_at = observed_at
    _append_occurrence(action, doc, row, "Issue")
    action.insert(ignore_permissions=True)
    return action


def _upgrade_legacy_action_scope(action, doc, issue_key):
    action.company = getattr(doc, "company", None)
    action.department = getattr(doc, "department", None)
    action.issue_key = issue_key
    action.open_issue_key = issue_key
    action.save(ignore_permissions=True)
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
        action.action_title = build_action_title(
            getattr(row, "question", None),
            getattr(row, "affected_items", None),
            getattr(row, "issue_type", None),
        )
        action.latest_issue_note = _latest_issue_note(row)
        action.latest_failure_reason = getattr(row, "failure_reason", None)
        action.latest_affected_items = getattr(row, "affected_items", None)
        action.latest_issue_type = getattr(row, "issue_type", None)
        action.latest_evidence_photo = getattr(row, "evidence_photo", None)
        if action.status == "Pending Verification":
            action.status = "In Progress"

    action.save(ignore_permissions=True)
    return action


def _find_open_actions_for_question(doc, row):
    """Find every unresolved Action for the same broad question and location.

    A broad question can now have multiple scoped Actions (for example Light /
    Electrical and Floor / Damage). A later Pass on the broad question is
    evidence for all of those unresolved scopes, without closing any of them.
    """
    question_link = cstr(getattr(row, "question_link", None)).strip()
    question_text = cstr(getattr(row, "question", None)).strip()
    filters = {
        "source_template": getattr(doc, "template", None),
        "open_issue_key": ["is", "set"],
    }
    if question_link:
        filters["question"] = question_link
    elif question_text:
        filters["question_text"] = question_text
    else:
        return []

    candidates = frappe.get_all(
        "Checklist Action",
        filters=filters,
        fields=["name", "company", "department", "plant_floor", "warehouse", "asset"],
        limit_page_length=500,
    )
    scheduled_scope = bool(getattr(doc, "schedule", None))
    scheduled_company = cstr(getattr(doc, "company", None)).strip() if scheduled_scope else ""
    scheduled_department = cstr(getattr(doc, "department", None)).strip() if scheduled_scope else ""
    target = (
        cstr(getattr(doc, "plant_floor", None)).strip(),
        cstr(getattr(doc, "warehouse", None)).strip(),
        cstr(getattr(doc, "asset", None)).strip(),
    )
    return [
        item.get("name")
        for item in candidates
        if (
            operational_scope_matches(
                item.get("company"),
                item.get("department"),
                scheduled_company,
                scheduled_department,
                scheduled_scope=scheduled_scope,
            )
            and (
                cstr(item.get("plant_floor")).strip(),
                cstr(item.get("warehouse")).strip(),
                cstr(item.get("asset")).strip(),
            ) == target
            and item.get("name")
        )
    ]


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

        row_has_issue = cint(getattr(row, "has_issue", 0))
        if not row_has_issue:
            linked = []
            for action_name in _find_open_actions_for_question(doc, row):
                action = frappe.get_doc("Checklist Action", action_name)
                effect = "append_pass"
                action = _update_action(action, doc, row, effect)
                processed.append(action.name)
                linked.append(action.name)
            if linked:
                _set_row_action(row, linked[0])
            continue

        issue_key = _issue_key(doc, row)
        action_name = frappe.db.get_value(
            "Checklist Action",
            {"open_issue_key": issue_key},
            "name",
        )

        if not action_name and getattr(doc, "schedule", None):
            legacy_issue_key = _issue_key(doc, row, scheduled_scope=False)
            legacy_action_name = frappe.db.get_value(
                "Checklist Action",
                {"open_issue_key": legacy_issue_key},
                "name",
            )
            if legacy_action_name:
                legacy_action = frappe.get_doc("Checklist Action", legacy_action_name)
                if operational_scope_matches(
                    getattr(legacy_action, "company", None),
                    getattr(legacy_action, "department", None),
                    getattr(doc, "company", None),
                    getattr(doc, "department", None),
                    scheduled_scope=True,
                ):
                    _upgrade_legacy_action_scope(legacy_action, doc, issue_key)
                    action_name = legacy_action.name

        effect = observation_effect(
            row_has_issue,
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
