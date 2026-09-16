"""Pure rules for Checklist Action identity and lifecycle semantics."""

from datetime import datetime
import hashlib

OPEN_ACTION_STATUSES = ("Open", "In Progress", "Waiting", "Pending Verification")


def _text(value):
    return str(value or "").strip()


def build_issue_key(template, question, plant_floor=None, warehouse=None, *, asset=None):
    parts = [
        _text(template),
        _text(question),
        _text(plant_floor),
        _text(warehouse),
    ]
    # Preserve legacy hashes when Asset is blank. This keeps existing open Actions
    # reusable after migrate, while a real Asset scopes the issue to one machine.
    if _text(asset):
        parts.append(_text(asset))
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
