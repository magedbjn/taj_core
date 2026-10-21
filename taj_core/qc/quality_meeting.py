"""Meeting attendee rules, limited to the standard ERPNext Quality Meeting."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import escape_html


def _get_employee(employee: str):
    return frappe.db.get_value(
        "Employee", employee, ["employee_name", "status"], as_dict=True
    )


@frappe.whitelist()
def get_attendee_name(employee: str, meeting: str | None = None) -> str:
    """Return one active employee's name to a user editing a Quality Meeting.

    Users may select cross-department employees in this particular document;
    grant no general Read permission on Employee and expose no other fields.
    """
    employee = (employee or "").strip() if isinstance(employee, str) else ""
    meeting = (meeting or "").strip() if isinstance(meeting, str) else ""

    if meeting:
        meeting_doc = frappe.get_doc("Quality Meeting", meeting)
        meeting_doc.check_permission("write")
    elif not frappe.has_permission("Quality Meeting", "create"):
        frappe.throw(_("Not permitted to retrieve meeting attendee names."), frappe.PermissionError)

    if not employee or len(employee) > 140:
        frappe.throw(_("Select a valid Employee."), frappe.ValidationError)

    data = _get_employee(employee)
    if not data:
        frappe.throw(_("Employee {0} could not be found.").format(escape_html(employee)))
    if data.status != "Active":
        frappe.throw(_("Only active employees may be added to Attendees: {0}.").format(
            escape_html(employee)
        ))

    return data.employee_name or employee


def validate_attendees(doc, method: str | None = None) -> None:
    """Validate one Employee per meeting and persist trusted display names.

    This is a parent validate hook because child DocType validate methods are
    not called automatically on saves of a parent Table in Frappe.
    """
    if doc.doctype != "Quality Meeting":
        return
    rows = doc.get("taj_attendees") or []
    if not rows:
        return

    seen: dict[str, int] = {}
    employee_ids: list[str] = []
    for row in rows:
        employee = (row.get("employee") or "").strip()
        if not employee:
            continue  # The required Link field is validated by Frappe.
        if employee in seen:
            frappe.throw(
                _("Employee {0} is already in Attendees (rows {1} and {2}).").format(
                    escape_html(employee), seen[employee], row.idx
                ),
                title=_("Duplicate Attendee"),
            )
        seen[employee] = row.idx
        employee_ids.append(employee)

    if not employee_ids:
        return

    data = frappe.get_all(
        "Employee",
        filters={"name": ["in", employee_ids]},
        fields=["name", "employee_name", "status"],
        limit_page_length=len(employee_ids),
    )
    by_id = {row.name: row for row in data}

    # Historical attendees who have since left may remain in old meetings.
    # Only newly selected or changed Employee values must be Active.
    old_doc = doc.get_doc_before_save()
    previous = (
        {row.name: row.employee for row in (old_doc.get("taj_attendees") or [])}
        if old_doc else {}
    )
    for row in rows:
        employee = (row.get("employee") or "").strip()
        if not employee:
            continue
        details = by_id.get(employee)
        if not details:
            frappe.throw(_("Employee {0} could not be found.").format(escape_html(employee)))
        if details.status != "Active" and previous.get(row.name) != employee:
            frappe.throw(
                _("Only active employees may be added to Attendees: {0}.").format(
                    escape_html(employee)
                )
            )
        # Never trust a manually supplied name, including via REST/API.
        row.employee_name = details.employee_name or employee
