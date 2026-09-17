"""Pure Checklist answer rules.

This module intentionally has no Frappe imports so the core answer semantics can
be tested outside a bench/site runtime. Frappe documents call these helpers and
translate messages when presenting validation errors to users.
"""


def _sha256_text(value):
    import hashlib

    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def stable_generation_key(template_name, source_due_date, schedule_name=None, cycle_token=None):
    """Return a fixed-length idempotency key for one checklist cycle.

    ``cycle_token`` is optional and is used by Manual schedules when every
    button press represents a distinct inspection cycle on the same date.
    Automatic schedules omit it so Schedule + Due Date remains idempotent.
    """
    if not template_name or not source_due_date:
        return None
    if schedule_name:
        raw = f"schedule::{schedule_name}::{source_due_date}"
    else:
        raw = f"{template_name}::{source_due_date}"
    if cycle_token:
        raw = f"{raw}::cycle::{cycle_token}"
    return _sha256_text(raw)


def normalize_generation_key_value(value):
    """Convert legacy readable generation keys to their fixed-length form."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) == 64 and all(char in "0123456789abcdef" for char in raw.lower()):
        return raw.lower()
    return _sha256_text(raw)


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


def parse_weeks_of_month(value):
    """Parse a comma-separated week-of-month list into sorted unique week numbers.

    Week numbers use calendar day buckets: 1=days 1-7, 2=8-14, ... 5=29-31.
    """
    if value is None:
        raise ValueError("At least one week of month is required")

    if isinstance(value, (list, tuple, set)):
        parts = list(value)
    else:
        parts = str(value).split(",")

    weeks = []
    for raw in parts:
        token = str(raw).strip()
        if not token:
            continue
        try:
            week = int(token)
        except (TypeError, ValueError) as exc:
            raise ValueError("Weeks of month must be numbers from 1 to 5") from exc
        if week < 1 or week > 5:
            raise ValueError("Weeks of month must be between 1 and 5")
        if week in weeks:
            raise ValueError("Duplicate weeks of month are not allowed")
        weeks.append(week)

    if not weeks:
        raise ValueError("At least one week of month is required")

    return sorted(weeks)


def next_week_of_month_due_date(reference_date, weeks):
    """Return the next selected week-of-month occurrence on the same weekday.

    The next date is always strictly after ``reference_date``. This prevents
    14-day drift when a 1,3 or 2,4 schedule crosses month boundaries.
    """
    from datetime import timedelta

    selected_weeks = set(parse_weeks_of_month(weeks))
    weekday = reference_date.weekday()
    candidate = reference_date + timedelta(days=1)

    # Within 14 months every valid weekday/week pattern must have an occurrence.
    for _ in range(430):
        week_of_month = ((candidate.day - 1) // 7) + 1
        if candidate.weekday() == weekday and week_of_month in selected_weeks:
            return candidate
        candidate += timedelta(days=1)

    raise ValueError("Unable to calculate next weeks-of-month due date")



_WEEKDAY_NAMES = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def _schedule_value(schedule, fieldname, default=None):
    if isinstance(schedule, dict):
        return schedule.get(fieldname, default)
    return getattr(schedule, fieldname, default)


def _as_date(value):
    from datetime import date, datetime

    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _positive_int(value, default=1):
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(parsed, 1)


def _days_in_month(year, month):
    import calendar

    return calendar.monthrange(year, month)[1]


def _clamped_date(year, month, day):
    from datetime import date

    return date(year, month, min(max(int(day), 1), _days_in_month(year, month)))


def _add_months_clamped(value, months, day=None):
    month_index = (value.year * 12 + (value.month - 1)) + int(months)
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    target_day = value.day if day in (None, "") else int(day)
    return _clamped_date(year, month, target_day)


def normalize_schedule_weeks(schedule):
    """Return selected week-of-month numbers from schedule checkbox fields.

    The function also accepts the legacy comma-separated ``weeks_of_month``
    value so migrated schedules and pure-rule tests share one parser.
    """
    weeks = [
        week
        for week in range(1, 6)
        if bool(int(_schedule_value(schedule, f"week_{week}", 0) or 0))
    ]
    if weeks:
        return weeks

    legacy = _schedule_value(schedule, "weeks_of_month", None)
    if legacy not in (None, ""):
        return parse_weeks_of_month(legacy)
    return []


def _weekday_index(name):
    if name not in _WEEKDAY_NAMES:
        raise ValueError("A valid day of week is required")
    return _WEEKDAY_NAMES[name]


def _first_weekday_on_or_after(start_date, weekday):
    from datetime import timedelta

    offset = (weekday - start_date.weekday()) % 7
    return start_date + timedelta(days=offset)


def _next_week_of_month_candidate(start_date, weeks, weekday, include_start=False):
    from datetime import timedelta

    selected_weeks = set(weeks)
    candidate = start_date if include_start else start_date + timedelta(days=1)
    for _ in range(800):
        week_of_month = ((candidate.day - 1) // 7) + 1
        if candidate.weekday() == weekday and week_of_month in selected_weeks:
            return candidate
        candidate += timedelta(days=1)
    raise ValueError("Unable to calculate weeks-of-month due date")


def calculate_schedule_due_date(schedule, reference_date=None, initial=False):
    """Calculate the first or next due date for a Checklist Schedule.

    ``initial=True`` returns the first valid occurrence on or after Start Date.
    Subsequent calls return an occurrence strictly after ``reference_date``.
    """
    from datetime import timedelta

    schedule_type = str(_schedule_value(schedule, "schedule_type", "Manual") or "Manual").strip()
    if schedule_type == "Manual":
        return None

    start_date = _as_date(_schedule_value(schedule, "start_date", None))
    reference = _as_date(reference_date)
    if initial:
        base = reference or start_date
        if not base:
            raise ValueError("Start Date is required")
    else:
        base = reference or start_date
        if not base:
            raise ValueError("A reference date or Start Date is required")

    interval = _positive_int(_schedule_value(schedule, "interval", 1), 1)

    if schedule_type == "Daily":
        return base if initial else base + timedelta(days=interval)

    if schedule_type == "Weekly":
        weekday = _weekday_index(_schedule_value(schedule, "day_of_week", None))
        if initial:
            return _first_weekday_on_or_after(base, weekday)
        return base + timedelta(weeks=interval)

    if schedule_type == "Monthly":
        day = int(_schedule_value(schedule, "day_of_month", 0) or 0)
        if not 1 <= day <= 31:
            raise ValueError("Day of month must be between 1 and 31")
        if initial:
            candidate = _clamped_date(base.year, base.month, day)
            if candidate >= base:
                return candidate
            return _add_months_clamped(candidate, interval, day)
        return _add_months_clamped(base, interval, day)

    if schedule_type == "Weeks of Month":
        weeks = normalize_schedule_weeks(schedule)
        if not weeks:
            raise ValueError("At least one week of month is required")
        weekday = _weekday_index(_schedule_value(schedule, "day_of_week", None))
        return _next_week_of_month_candidate(base, weeks, weekday, include_start=bool(initial))

    if schedule_type == "Quarterly":
        day = int(_schedule_value(schedule, "day_of_month", 0) or 0)
        if not 1 <= day <= 31:
            raise ValueError("Day of month must be between 1 and 31")
        if initial:
            candidate = _clamped_date(base.year, base.month, day)
            if candidate >= base:
                return candidate
            return _add_months_clamped(candidate, 3, day)
        return _add_months_clamped(base, 3, day)

    if schedule_type == "Yearly":
        month = int(_schedule_value(schedule, "month_of_year", 0) or 0)
        day = int(_schedule_value(schedule, "day_of_month", 0) or 0)
        if not 1 <= month <= 12:
            raise ValueError("Month of year must be between 1 and 12")
        if not 1 <= day <= 31:
            raise ValueError("Day of month must be between 1 and 31")
        candidate = _clamped_date(base.year, month, day)
        if initial and candidate >= base:
            return candidate
        return _clamped_date(base.year + 1, month, day)

    raise ValueError(f"Unsupported schedule type: {schedule_type}")


def schedule_due_occurrences(schedule, next_due_date, through_date, max_cycles=366):
    """Return a bounded batch of due dates through ``through_date``.

    This helper is intentionally pure so scheduler catch-up behavior can be
    tested outside Frappe. It fails closed if recurrence calculation does not
    advance. ``max_cycles`` bounds work per scheduler run; any remaining backlog
    stays due and is processed by the next run.
    """
    due_date = _as_date(next_due_date)
    through = _as_date(through_date)
    if not due_date or not through or due_date > through:
        return []

    try:
        cap = max(int(max_cycles), 1)
    except (TypeError, ValueError):
        cap = 366

    occurrences = []
    current = due_date
    for _ in range(cap):
        if current > through:
            return occurrences
        occurrences.append(current)
        following = calculate_schedule_due_date(schedule, reference_date=current, initial=False)
        if not following or following <= current:
            raise ValueError("Schedule recurrence did not advance")
        current = following

    return occurrences

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


def should_reuse_manual_open_checklist(cycle_behavior):
    """Return whether an open Manual-schedule checklist should be reused.

    Fresh Every Cycle treats every explicit Create Checklist click as a new
    inspection. Continue Until Completed keeps returning the existing open
    inspection until it is completed.
    """
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
