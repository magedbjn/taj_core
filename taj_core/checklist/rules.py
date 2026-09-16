"""Pure Checklist answer rules.

This module intentionally has no Frappe imports so the core answer semantics can
be tested outside a bench/site runtime. Frappe documents call these helpers and
translate messages when presenting validation errors to users.
"""


def split_lines(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return [str(item).strip() for item in raw if str(item).strip()]


def normalize_multi_value(value):
    return "\n".join(split_lines(value))


def quick_pass_value(question_type, enabled, *, issue_if_no=False):
    if not enabled:
        return None
    if question_type == "Pass/Fail/NA":
        return "Pass"
    if question_type in ("Yes/No", "Yes/No/NA") and bool(issue_if_no):
        return "Yes"
    return None


def failure_photo_requirement_satisfied(
    evidence_photo,
    allow_no_photo_with_reason=False,
    photo_unavailable_reason=None,
):
    """Return whether required failure-photo evidence is satisfied.

    A real photo always satisfies the rule. When the question explicitly allows
    a no-photo exception, a non-empty reason can be used instead.
    """
    if str(evidence_photo or "").strip():
        return True

    try:
        allow_reason = bool(int(allow_no_photo_with_reason or 0))
    except (TypeError, ValueError):
        allow_reason = bool(allow_no_photo_with_reason)

    return bool(allow_reason and str(photo_unavailable_reason or "").strip())


def is_valid_answer(answer_value, question_type, answer_options=None):
    if answer_value in (None, ""):
        return True

    value = str(answer_value).strip()
    qtype = str(question_type or "").strip()

    if qtype == "Yes/No":
        return value in ("Yes", "No")
    if qtype == "Yes/No/NA":
        return value in ("Yes", "No", "N/A")
    if qtype == "Pass/Fail/NA":
        return value in ("Pass", "Fail", "N/A")
    if qtype == "Int":
        try:
            int(value)
            return True
        except (TypeError, ValueError):
            return False
    if qtype == "Float":
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False
    if qtype in ("Select", "Single Select"):
        options = set(split_lines(answer_options))
        return not options or value in options
    if qtype == "Multi Select":
        options = set(split_lines(answer_options))
        selected = set(split_lines(value))
        return bool(selected) and (not options or selected.issubset(options))
    if qtype in ("Text", "Photo"):
        return True

    return True


def evaluate_issue(
    answer_value,
    question_type,
    *,
    issue_if_no=False,
    issue_select_values=None,
    min_value=None,
    max_value=None,
):
    if answer_value in (None, ""):
        return False, ""

    value = str(answer_value).strip()
    qtype = str(question_type or "").strip()

    if qtype == "Pass/Fail/NA":
        if value == "Fail":
            return True, "Issue because answer is Fail"
        return False, ""

    if qtype in ("Yes/No", "Yes/No/NA"):
        if bool(issue_if_no) and value == "No":
            return True, "Issue because answer is No"
        return False, ""

    if qtype == "Int":
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return False, ""
        if min_value not in (None, "") and parsed < int(min_value):
            return True, "Value is below minimum allowed"
        if max_value not in (None, "") and parsed > int(max_value):
            return True, "Value is above maximum allowed"
        return False, ""

    if qtype == "Float":
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return False, ""
        if min_value not in (None, "") and parsed < float(min_value):
            return True, "Value is below minimum allowed"
        if max_value not in (None, "") and parsed > float(max_value):
            return True, "Value is above maximum allowed"
        return False, ""

    if qtype in ("Select", "Single Select"):
        issue_values = set(split_lines(issue_select_values))
        if issue_values and value in issue_values:
            return True, "Issue option selected"
        return False, ""

    if qtype == "Multi Select":
        issue_values = set(split_lines(issue_select_values))
        selected = set(split_lines(value))
        if issue_values.intersection(selected):
            return True, "Issue option selected"
        return False, ""

    return False, ""


def question_configuration_errors(
    question_type,
    *,
    answer_options=None,
    issue_select_values=None,
    min_value=None,
    max_value=None,
):
    errors = []
    qtype = str(question_type or "").strip()

    if qtype in ("Int", "Float") and min_value not in (None, "") and max_value not in (None, ""):
        caster = int if qtype == "Int" else float
        try:
            if caster(min_value) > caster(max_value):
                errors.append("Minimum value cannot be greater than maximum value")
        except (TypeError, ValueError):
            pass

    if qtype in ("Select", "Single Select", "Multi Select"):
        options = set(split_lines(answer_options))
        issue_values = set(split_lines(issue_select_values))
        if issue_values and not issue_values.issubset(options):
            errors.append("Issue values must be included in answer options")

    return errors


def summarize_workers(rows, required_count=0):
    """Return lightweight staffing counts for a checklist worker roster.

    Only workers marked Present count toward the staffing requirement. A
    replacement counts as a replacement only when that worker is actually
    present. A zero/blank required count means the requirement is informational
    only and is therefore not enforced.
    """
    try:
        required = max(int(required_count or 0), 0)
    except (TypeError, ValueError):
        required = 0

    present = 0
    absent = 0
    replacements = 0

    for row in rows or []:
        if isinstance(row, dict):
            status = str(row.get("presence_status") or "").strip()
            is_replacement = bool(row.get("is_replacement"))
        else:
            status = str(getattr(row, "presence_status", "") or "").strip()
            is_replacement = bool(getattr(row, "is_replacement", 0))

        if status == "Present":
            present += 1
            if is_replacement:
                replacements += 1
        elif status == "Absent":
            absent += 1

    shortage = max(required - present, 0) if required else 0
    status = "Not Set" if not required else ("Met" if shortage == 0 else "Short")

    return {
        "required": required,
        "present": present,
        "absent": absent,
        "replacements": replacements,
        "shortage": shortage,
        "status": status,
    }


def should_reuse_open_checklist(cycle_behavior, *, same_cycle):
    """Return whether an existing open checklist should be reused.

    Same-cycle documents are always reused. Across cycles, only templates that
    explicitly continue until completion keep the same open document.
    """
    if same_cycle:
        return True
    return str(cycle_behavior or "Fresh Every Cycle").strip() == "Continue Until Completed"


def classify_auto_close_status(answered_count, total_count):
    """Classify an unfinished Fresh Every Cycle occurrence at cycle rollover."""
    try:
        answered = max(int(answered_count or 0), 0)
    except (TypeError, ValueError):
        answered = 0
    try:
        total = max(int(total_count or 0), 0)
    except (TypeError, ValueError):
        total = 0

    if answered == 0:
        return "Missed"
    if total == 0 or answered < total:
        return "Auto Closed - Incomplete"
    return "Auto Closed - Incomplete"


def summarize_required_answers(rows):
    """Summarize completion of required checklist rows for operational snapshots."""
    required = 0
    answered = 0
    incomplete = []

    for row in rows or []:
        if isinstance(row, dict):
            is_required = row.get("is_required", 1)
            answer = row.get("answer")
            question = row.get("question") or "Checklist item"
        else:
            is_required = getattr(row, "is_required", 1)
            answer = getattr(row, "answer", None)
            question = getattr(row, "question", None) or "Checklist item"

        try:
            required_flag = bool(int(is_required))
        except (TypeError, ValueError):
            required_flag = bool(is_required)

        if not required_flag:
            continue

        required += 1
        if answer not in (None, "") and str(answer).strip():
            answered += 1
        else:
            incomplete.append(str(question).strip())

    percent = 100 if required == 0 else int(round((answered / required) * 100))
    return {
        "required": required,
        "answered": answered,
        "percent": percent,
        "incomplete": incomplete,
    }


def is_before_scheduled_start(scheduled_start, now):
    """Return True only while a time-controlled checklist is not open yet."""
    if not scheduled_start or not now:
        return False
    return now < scheduled_start


def deadline_notification_state(
    *,
    deadline,
    now,
    overdue_notified=False,
    escalated=False,
    escalate_after_minutes=0,
):
    """Return notification decisions for an open checklist deadline."""
    overdue = bool(deadline and now and now > deadline)
    if not overdue:
        return {
            "overdue": False,
            "delay_minutes": 0,
            "notify_overdue": False,
            "notify_escalation": False,
        }

    delay_seconds = (now - deadline).total_seconds()
    delay_minutes = max(int(delay_seconds // 60), 0)
    try:
        escalation_delay = max(int(escalate_after_minutes or 0), 0)
    except (TypeError, ValueError):
        escalation_delay = 0

    notify_overdue = not bool(overdue_notified)
    notify_escalation = bool(
        escalation_delay
        and delay_minutes >= escalation_delay
        and not bool(escalated)
    )

    return {
        "overdue": True,
        "delay_minutes": delay_minutes,
        "notify_overdue": notify_overdue,
        "notify_escalation": notify_escalation,
    }
