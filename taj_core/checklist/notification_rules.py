"""Pure helpers for Checklist notifications.

No Frappe imports are used here so notification semantics remain testable outside
of a bench/site runtime.
"""


def deduplicate_recipients(recipients, excluded=None):
    excluded = set(excluded or ())
    seen = set()
    result = []
    for recipient in recipients or []:
        value = str(recipient or "").strip()
        if not value or value in excluded or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def build_issue_message(
    *,
    question,
    severity="Medium",
    failure_reason="",
    user_note="",
    responsible_department="",
    responsible_user="",
):
    lines = [
        f"Question: {str(question or '').strip()}",
        f"Severity: {str(severity or 'Medium').strip()}",
    ]
    if str(failure_reason or "").strip():
        lines.append(f"Reason: {str(failure_reason).strip()}")
    if str(user_note or "").strip():
        lines.append(f"Note: {str(user_note).strip()}")
    if str(responsible_department or "").strip():
        lines.append(f"Responsible Department: {str(responsible_department).strip()}")
    if str(responsible_user or "").strip():
        lines.append(f"Responsible User: {str(responsible_user).strip()}")
    return "\n".join(lines)
