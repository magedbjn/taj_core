"""Pure rules for Checklist Action identity and lifecycle semantics."""

from datetime import datetime
import hashlib

OPEN_ACTION_STATUSES = ("Open", "In Progress", "Waiting", "Pending Verification")


def _text(value):
    return str(value or "").strip()


def _normalized_multi(value):
    """Return stable, de-duplicated newline values for identity and display."""
    values = {
        line.strip()
        for line in _text(value).replace(",", "\n").splitlines()
        if line and line.strip()
    }
    return sorted(values, key=str.casefold)


def build_issue_key(
    template,
    question,
    plant_floor=None,
    warehouse=None,
    *,
    asset=None,
    company=None,
    department=None,
    affected_items=None,
    issue_type=None,
):
    parts = [
        _text(template),
        _text(question),
        _text(plant_floor),
        _text(warehouse),
    ]
    # Preserve legacy hashes when optional operational scope is blank. Scheduled
    # callers can add Company/Department so Actions never cross operating contexts,
    # while existing unscheduled records continue to reuse their legacy hashes.
    if _text(company) or _text(department):
        parts.append("company:" + _text(company))
        parts.append("department:" + _text(department))

    # Preserve legacy hashes when Asset is blank. This keeps existing open Actions
    # reusable after migrate, while a real Asset scopes the issue to one machine.
    if _text(asset):
        parts.append(_text(asset))

    # Broad questions can now create distinct Actions for distinct physical items
    # and problem types. Blank scope deliberately preserves all legacy hashes.
    affected = _normalized_multi(affected_items)
    issue = _text(issue_type)
    if affected or issue:
        parts.append("affected:" + "|".join(affected))
        parts.append("type:" + issue.casefold())

    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_action_title(question_text, affected_items=None, issue_type=None):
    question = _text(question_text)
    affected = ", ".join(_normalized_multi(affected_items))
    issue = _text(issue_type)

    if affected and issue:
        title = f"{affected} — {issue}"
    elif affected:
        title = f"{affected} — {question}" if question else affected
    elif issue:
        title = f"{question} — {issue}" if question else issue
    else:
        title = question

    # Frappe Data/title fields are most portable when kept compact.
    return title[:140]


def operational_scope_matches(
    candidate_company,
    candidate_department,
    target_company,
    target_department,
    *,
    scheduled_scope=False,
):
    if not scheduled_scope:
        return True

    candidate_department = _text(candidate_department)
    target_department = _text(target_department)
    if candidate_department != target_department:
        return False

    candidate_company = _text(candidate_company)
    target_company = _text(target_company)
    # Legacy Actions did not snapshot Company. Same Department is safe because
    # ERPNext Department names are company-scoped and unique in this context.
    return not candidate_company or candidate_company == target_company


def is_open_action_status(status):
    return _text(status) in OPEN_ACTION_STATUSES


def observation_effect(has_issue, require_follow_up, has_open_action):
    if has_open_action:
        return "append_issue" if bool(has_issue) else "append_pass"
    if bool(has_issue) and bool(require_follow_up):
        return "create_issue_action"
    return "none"


def next_resolution_status(require_verification):
    return "Pending Verification" if bool(require_verification) else "Closed"


def _as_datetime(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def action_is_overdue(status, due_at, now_value):
    if not is_open_action_status(status) or due_at in (None, ""):
        return False
    due_dt = _as_datetime(due_at)
    now_dt = _as_datetime(now_value)
    return bool(due_dt and now_dt and due_dt < now_dt)
