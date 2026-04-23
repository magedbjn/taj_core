import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.exceptions import TimestampMismatchError
from frappe.utils import nowdate, cint, flt, cstr, getdate

from taj_core.checklist.doctype.checklist_answer.checklist_answer import (
    create_checklist_answer_from_template,
    get_question_meta,
)
from taj_core.checklist.permissions import is_checklist_manager, checklist_answer_has_permission


OPEN_STATUSES = ("Draft", "In Progress", "Expired")

BASE_LIST_FIELDS = [
    "name",
    "template",
    "posting_date",
    "status",
    "department",
    "assigned_user",
    "assignment_type",
    "docstatus",
    "modified",
    "answer_by",
    "result_status",
    "scheduled_start_at",
    "deadline_at",
    "started_at",
    "completed_at",
    "time_status",
    "delay_minutes",
]

OPTIONAL_FIELDS = [
    "taken_by",
    "source_due_date",
    "generation_key",
]


def _ensure_manager():
    if not is_checklist_manager(frappe.session.user):
        frappe.throw(_("Only Checklist Manager can access this screen."), frappe.PermissionError)


def _has_db_column(doctype: str, fieldname: str) -> bool:
    try:
        return bool(frappe.db.has_column(doctype, fieldname))
    except Exception:
        return False


def _has_meta_field(doctype: str, fieldname: str) -> bool:
    try:
        return frappe.get_meta(doctype).has_field(fieldname)
    except Exception:
        return False


def _get_list_fields():
    fields = [f for f in BASE_LIST_FIELDS if _has_db_column("Checklist Answer", f)]
    for fieldname in OPTIONAL_FIELDS:
        if _has_db_column("Checklist Answer", fieldname):
            fields.append(fieldname)
    return fields


def _get_checklist_settings():
    settings = {"enable_auto_save": 1}
    if frappe.db.exists("DocType", "Checklist Settings"):
        try:
            doc = frappe.get_single("Checklist Settings")
            settings["enable_auto_save"] = cint(getattr(doc, "enable_auto_save", 1))
        except Exception:
            pass
    return settings


def _status_filter_dict(status):
    if not status or status == "All":
        return {}

    if status == "Open":
        return {"docstatus": 0, "status": ["in", list(OPEN_STATUSES)]}

    if status == "Completed":
        return {"docstatus": 1, "status": "Completed"}

    if status == "Auto Closed":
        return {"docstatus": 1, "status": "Auto Closed"}

    if status in OPEN_STATUSES:
        return {"docstatus": 0, "status": status}

    return {"status": status}


def _issue_filter_dict(issue_filter):
    if not _has_db_column("Checklist Answer", "result_status"):
        return {}

    if not issue_filter or issue_filter == "All":
        return {}

    if issue_filter == "Has Issue Only":
        return {"result_status": ["!=", "Normal"]}

    if issue_filter == "No Issue Only":
        return {"result_status": "Normal"}

    return {}


def _serialize_row_doc(doc):
    result_status = doc.get("result_status") if _has_db_column("Checklist Answer", "result_status") else "Normal"
    has_issue = 1 if result_status and result_status != "Normal" else 0

    posting_date = cstr(doc.get("posting_date") or "")
    today = nowdate()
    is_previous_cycle_open = cint(bool(doc.get("docstatus") == 0 and posting_date and posting_date < today))
    is_today_new = cint(bool(doc.get("docstatus") == 0 and doc.get("status") == "Draft" and posting_date == today))

    return {
        "name": doc.get("name"),
        "template": doc.get("template"),
        "posting_date": posting_date,
        "status": doc.get("status"),
        "department": doc.get("department"),
        "assigned_user": doc.get("assigned_user"),
        "assignment_type": doc.get("assignment_type"),
        "docstatus": doc.get("docstatus"),
        "modified": str(doc.get("modified") or ""),
        "answer_by": doc.get("answer_by"),
        "taken_by": doc.get("taken_by"),
        "has_issue": has_issue,
        "result_status": result_status or "Normal",
        "scheduled_start_at": str(doc.get("scheduled_start_at") or ""),
        "deadline_at": str(doc.get("deadline_at") or ""),
        "started_at": str(doc.get("started_at") or ""),
        "completed_at": str(doc.get("completed_at") or ""),
        "time_status": doc.get("time_status") or "",
        "delay_minutes": doc.get("delay_minutes") or 0,
        "source_due_date": str(doc.get("source_due_date") or ""),
        "is_previous_cycle_open": is_previous_cycle_open,
        "is_today_new": is_today_new,
        "open_from_date": posting_date,
    }


def _aggregate_summary_rows(docs, key_field, fallback_label):
    summary_map = defaultdict(lambda: {"total": 0, "completed": 0, "remaining": 0})

    for doc in docs:
        key = doc.get(key_field) or fallback_label
        summary_map[key]["total"] += 1

        if doc.get("status") == "Completed" and doc.get("docstatus") == 1:
            summary_map[key]["completed"] += 1
        elif doc.get("status") in OPEN_STATUSES and doc.get("docstatus") == 0:
            summary_map[key]["remaining"] += 1

    rows = []
    for key, values in summary_map.items():
        rows.append({
            "label": key,
            "total": values["total"],
            "completed": values["completed"],
            "remaining": values["remaining"],
        })

    rows.sort(key=lambda d: (-d["total"], d["label"]))
    return rows


@frappe.whitelist()
def create_checklist_answer(template_name):
    _ensure_manager()

    if not template_name:
        frappe.throw(_("Template is required."))

    doc = create_checklist_answer_from_template(template_name=template_name)
    reused_existing = cint(getattr(doc.flags, "reused_existing", 0))
    reuse_reason = getattr(doc.flags, "reuse_reason", None)

    response = {
        "name": doc.name,
        "redirect_to": f"Form/Checklist Answer/{doc.name}",
        "reused_existing": reused_existing,
        "doc": serialize_checklist_answer(doc),
    }

    if reused_existing:
        if reuse_reason == "same_day_open":
            response["notice"] = _("An open checklist already exists for this template today, so no new checklist was created.")
        elif reuse_reason == "previous_unanswered_open":
            response["notice"] = _("A previous open checklist exists for this template without answers, so no new checklist was created.")
        else:
            response["notice"] = _("An existing open checklist was reused, so no new checklist was created.")

        response["open_reference"] = {
            "name": doc.name,
            "posting_date": cstr(doc.posting_date or ""),
        }

    return response


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_reassign_users(doctype, txt, searchfield, start, page_len, filters):
    filters = filters or {}
    department = filters.get("department")

    conditions = [
        "u.enabled = 1",
        "u.user_type = 'System User'",
        "e.status = 'Active'",
        "u.name NOT IN ('Administrator', 'Guest')",
        "("
        "u.name LIKE %(txt)s "
        "OR COALESCE(e.employee_name, '') LIKE %(txt)s "
        "OR COALESCE(u.full_name, '') LIKE %(txt)s"
        ")",
    ]

    if department:
        conditions.append("e.department = %(department)s")

    return frappe.db.sql(
        f"""
        SELECT DISTINCT
            u.name,
            COALESCE(e.employee_name, u.full_name, u.name) AS employee_name
        FROM `tabUser` u
        INNER JOIN `tabEmployee` e
            ON e.user_id = u.name
        WHERE {' AND '.join(conditions)}
        ORDER BY employee_name ASC, u.name ASC
        LIMIT %(start)s, %(page_len)s
        """,
        {
            "department": department,
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len,
        },
    )


@frappe.whitelist()
def reassign_checklist_answer(docname, new_user):
    _ensure_manager()

    if not docname:
        frappe.throw(_("Checklist Answer is required."))
    if not new_user:
        frappe.throw(_("User is required."))

    doc = frappe.get_doc("Checklist Answer", docname)

    if doc.docstatus != 0 or doc.status in ("Completed", "Auto Closed"):
        frappe.throw(_("Only open checklist can be reassigned."))

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": new_user},
        ["department", "status"],
        as_dict=True,
    )

    if not employee:
        frappe.throw(_("Selected user is not linked to an Employee record."))

    if employee.status != "Active":
        frappe.throw(_("Selected employee is not Active."))

    if doc.department and employee.department != doc.department:
        frappe.throw(_("Selected user does not belong to the same department."))

    doc.assignment_type = "Specific User"
    doc.assigned_user = new_user
    if hasattr(doc, "taken_by"):
        doc.taken_by = None

    doc.flags.ignore_due_date_update = True
    doc.save(ignore_permissions=True)
    doc.reload()

    return serialize_checklist_answer(doc)


@frappe.whitelist()
def assign_checklist_answer_to_team(docname):
    _ensure_manager()

    if not docname:
        frappe.throw(_("Checklist Answer is required."))

    doc = frappe.get_doc("Checklist Answer", docname)

    if doc.docstatus != 0 or doc.status in ("Completed", "Auto Closed"):
        frappe.throw(_("Only open checklist can be reassigned."))

    doc.assignment_type = "Any User in Department"
    doc.assigned_user = None
    if hasattr(doc, "taken_by"):
        doc.taken_by = None

    doc.flags.ignore_due_date_update = True
    doc.save(ignore_permissions=True)
    doc.reload()

    return serialize_checklist_answer(doc)


@frappe.whitelist()
def claim_checklist_answer(docname):
    user = frappe.session.user

    if not docname:
        frappe.throw(_("Checklist Answer is required."))

    doc = frappe.get_doc("Checklist Answer", docname)

    if doc.docstatus != 0 or doc.status in ("Completed", "Auto Closed"):
        frappe.throw(_("Only open checklist can be claimed."))

    is_manager = is_checklist_manager(user)

    if doc.assignment_type == "Specific User":
        if not is_manager and doc.assigned_user != user:
            frappe.throw(_("This checklist is assigned to another user."), frappe.PermissionError)

    if getattr(doc, "taken_by", None) and doc.taken_by != user and not is_manager:
        frappe.throw(
            _("This checklist has already been claimed by {0}.").format(doc.taken_by),
            frappe.PermissionError,
        )

    doc.taken_by = user
    doc.flags.ignore_due_date_update = True
    doc.save(ignore_permissions=True)
    doc.reload()

    return serialize_checklist_answer(doc)


@frappe.whitelist()
def release_checklist_answer(docname):
    user = frappe.session.user

    if not docname:
        frappe.throw(_("Checklist Answer is required."))

    doc = frappe.get_doc("Checklist Answer", docname)

    if doc.docstatus != 0 or doc.status in ("Completed", "Auto Closed"):
        frappe.throw(_("Only open checklist can be released."))

    is_manager = is_checklist_manager(user)

    if getattr(doc, "taken_by", None) and doc.taken_by != user and not is_manager:
        frappe.throw(
            _("Only the current claimant or manager can release this checklist."),
            frappe.PermissionError,
        )

    doc.taken_by = None
    doc.flags.ignore_due_date_update = True
    doc.save(ignore_permissions=True)
    doc.reload()

    return serialize_checklist_answer(doc)


@frappe.whitelist()
def get_user_dashboard_data(search_date=None):
    user = frappe.session.user
    selected_date = search_date or nowdate()
    fields = _get_list_fields()
    today = nowdate()

    accessible_open_docs = frappe.get_list(
        "Checklist Answer",
        filters={"docstatus": 0, "status": ["in", list(OPEN_STATUSES)]},
        fields=fields,
        order_by="modified desc",
        page_length=200,
    )

    my_new = []
    my_open = []
    team_open = []

    for doc in accessible_open_docs:
        assigned_user = doc.get("assigned_user")
        answer_by = doc.get("answer_by")
        taken_by = doc.get("taken_by")
        assignment_type = doc.get("assignment_type")
        posting_date = cstr(doc.get("posting_date") or "")
        status = doc.get("status")

        is_unclaimed_department_task = (
            assignment_type == "Any User in Department"
            and not assigned_user
            and not answer_by
            and not taken_by
        )

        is_mine = (
            assigned_user == user
            or answer_by == user
            or taken_by == user
            or is_unclaimed_department_task
        )

        serialized = _serialize_row_doc(doc)

        if is_mine:
            if status == "Draft" and posting_date == today:
                my_new.append(serialized)
            else:
                my_open.append(serialized)
        else:
            team_open.append(serialized)

    history_results = frappe.get_list(
        "Checklist Answer",
        filters={"posting_date": selected_date},
        fields=fields,
        order_by="modified desc",
        page_length=200,
    )

    serialized_history_results = [_serialize_row_doc(doc) for doc in history_results]

    completed_on_date = [
        doc for doc in serialized_history_results
        if doc.get("docstatus") == 1 and doc.get("status") == "Completed"
    ]

    return {
        "selected_date": selected_date,
        "settings": _get_checklist_settings(),
        "summary": {
            "my_new_count": len(my_new),
            "my_open_count": len(my_open),
            "team_open_count": len(team_open),
            "completed_count": len(completed_on_date),
        },
        "my_new": my_new,
        "my_open": my_open,
        "team_open": team_open,
        "history_results": serialized_history_results,
    }


@frappe.whitelist()
def get_manager_dashboard_data(search_date=None, template=None, assigned_user=None, department=None, status=None, issue_filter=None):
    _ensure_manager()

    selected_date = search_date or nowdate()
    fields = _get_list_fields()

    today_filters = {"posting_date": nowdate()}
    if template:
        today_filters["template"] = template
    if assigned_user:
        today_filters["assigned_user"] = assigned_user
    if department:
        today_filters["department"] = department
    today_filters.update(_issue_filter_dict(issue_filter))

    today_docs = frappe.get_all(
        "Checklist Answer",
        filters=today_filters,
        fields=fields,
        order_by="modified desc",
        limit_page_length=500,
    )

    serialized_today_docs = [_serialize_row_doc(doc) for doc in today_docs]
    today_open = [row for row in serialized_today_docs if row.get("docstatus") == 0 and row.get("status") in OPEN_STATUSES]
    today_completed = [row for row in serialized_today_docs if row.get("docstatus") == 1 and row.get("status") == "Completed"]
    today_has_issue = [row for row in serialized_today_docs if row.get("has_issue")]

    search_filters = {"posting_date": selected_date}
    if template:
        search_filters["template"] = template
    if assigned_user:
        search_filters["assigned_user"] = assigned_user
    if department:
        search_filters["department"] = department

    search_filters.update(_status_filter_dict(status))
    search_filters.update(_issue_filter_dict(issue_filter))

    search_docs = frappe.get_all(
        "Checklist Answer",
        filters=search_filters,
        fields=fields,
        order_by="modified desc",
        limit_page_length=500,
    )

    serialized_search_docs = [_serialize_row_doc(doc) for doc in search_docs]

    template_summary = _aggregate_summary_rows(serialized_search_docs, "template", _("No Template"))
    employee_summary = _aggregate_summary_rows(serialized_search_docs, "assigned_user", _("Unassigned"))

    return {
        "selected_date": selected_date,
        "summary": {
            "today_total": len(serialized_today_docs),
            "today_open": len(today_open),
            "today_completed": len(today_completed),
            "today_remaining": len(today_open),
            "today_has_issue": len(today_has_issue),
        },
        "today_all": serialized_today_docs,
        "today_open": today_open,
        "today_completed": today_completed,
        "today_remaining_docs": today_open,
        "today_has_issue_docs": today_has_issue,
        "search_results": serialized_search_docs,
        "template_summary": template_summary,
        "employee_summary": employee_summary,
    }


@frappe.whitelist()
def get_checklist_answer(docname):
    doc = frappe.get_doc("Checklist Answer", docname)
    doc.check_permission("read")
    return serialize_checklist_answer(doc)


@frappe.whitelist()
def save_answers(docname, answers):
    payload = json.loads(answers) if isinstance(answers, str) else (answers or [])

    for attempt in range(2):
        try:
            doc = frappe.get_doc("Checklist Answer", docname)
            if not checklist_answer_has_permission(doc, frappe.session.user, "write") and not is_checklist_manager(frappe.session.user):
                frappe.throw(_("No permission to edit this checklist."), frappe.PermissionError)

            if doc.docstatus != 0:
                frappe.throw(_("Only draft checklist can be edited."))

            row_map = {row.name: row for row in doc.answer}

            if hasattr(doc, "taken_by") and not doc.taken_by:
                if doc.assignment_type == "Any User in Department" or doc.assigned_user == frappe.session.user:
                    doc.taken_by = frappe.session.user

            for item in payload:
                row = row_map.get(item.get("row_name"))
                if not row:
                    continue
                value = item.get("answer")
                _set_row_answer_by_type(row, value)

            doc.flags.ignore_due_date_update = True
            doc.save(ignore_permissions=True)
            doc.reload()

            return serialize_checklist_answer(doc)

        except TimestampMismatchError:
            if attempt == 0:
                continue
            raise


@frappe.whitelist()
def submit_checklist_answer(docname):
    doc = frappe.get_doc("Checklist Answer", docname)

    if not checklist_answer_has_permission(doc, frappe.session.user, "submit") and not is_checklist_manager(frappe.session.user):
        frappe.throw(_("No permission for Checklist Answer"), frappe.PermissionError)

    if doc.docstatus != 0:
        frappe.throw(_("Only open checklist can be submitted."))

    doc.flags.ignore_permissions = True
    doc.submit()
    doc.reload()

    return {
        "name": doc.name,
        "status": doc.status,
        "doc": serialize_checklist_answer(doc),
    }


def serialize_checklist_answer(doc):
    if isinstance(doc, str):
        doc = frappe.get_doc("Checklist Answer", doc)

    child_has_issue = _has_meta_field("Checklist Answer Question", "has_issue")
    child_issue_note = _has_meta_field("Checklist Answer Question", "issue_note")
    parent_result_status = _has_meta_field("Checklist Answer", "result_status")

    questions = []
    for row in doc.answer:
        meta = get_question_meta(row)
        questions.append({
            "row_name": row.name,
            "question": row.question,
            "question_text": meta.question_text or row.question,
            "type": meta.type or row.type,
            "answer": row.answer,
            "answer_options": meta.answer_select or "",
            "has_issue": getattr(row, "has_issue", 0) if child_has_issue else 0,
            "issue_note": getattr(row, "issue_note", "") if child_issue_note else "",
        })

    result_status = getattr(doc, "result_status", "Normal") if parent_result_status else "Normal"

    return {
        "name": doc.name,
        "template": doc.template,
        "posting_date": str(doc.posting_date) if doc.posting_date else "",
        "status": doc.status,
        "department": doc.department,
        "assigned_user": getattr(doc, "assigned_user", None),
        "taken_by": getattr(doc, "taken_by", None),
        "assignment_type": getattr(doc, "assignment_type", None),
        "answer_by": doc.answer_by,
        "docstatus": doc.docstatus,
        "is_editable": doc.docstatus == 0 and (checklist_answer_has_permission(doc, frappe.session.user, "write") or is_checklist_manager(frappe.session.user)),
        "can_reassign": is_checklist_manager(frappe.session.user) and doc.docstatus == 0 and doc.status not in ("Completed", "Auto Closed"),
        "has_issue": 1 if result_status != "Normal" else 0,
        "result_status": result_status,
        "scheduled_start_at": str(getattr(doc, "scheduled_start_at", "") or ""),
        "deadline_at": str(getattr(doc, "deadline_at", "") or ""),
        "started_at": str(getattr(doc, "started_at", "") or ""),
        "completed_at": str(getattr(doc, "completed_at", "") or ""),
        "time_status": getattr(doc, "time_status", "") or "",
        "delay_minutes": getattr(doc, "delay_minutes", 0) or 0,
        "is_previous_cycle_open": cint(bool(doc.docstatus == 0 and cstr(doc.posting_date or "") and cstr(doc.posting_date) < nowdate())),
        "is_today_new": cint(bool(doc.docstatus == 0 and doc.status == "Draft" and cstr(doc.posting_date or "") == nowdate())),
        "open_from_date": cstr(doc.posting_date or ""),
        "can_claim": doc.docstatus == 0 and getattr(doc, "assignment_type", None) == "Any User in Department" and (not getattr(doc, "taken_by", None) or getattr(doc, "taken_by", None) == frappe.session.user or is_checklist_manager(frappe.session.user)),
        "can_release": doc.docstatus == 0 and bool(getattr(doc, "taken_by", None)) and (getattr(doc, "taken_by", None) == frappe.session.user or is_checklist_manager(frappe.session.user)),
        "questions": questions,
    }


def _set_row_answer_by_type(row, value):
    raw_value = cstr(value).strip() if value is not None else ""

    if hasattr(row, "yes_no_answer"):
        row.yes_no_answer = ""
    if hasattr(row, "int_answer"):
        row.int_answer = None
    if hasattr(row, "float_answer"):
        row.float_answer = None
    if hasattr(row, "select_answer"):
        row.select_answer = ""

    if row.type == "Yes/No":
        row.yes_no_answer = raw_value
    elif row.type == "Int":
        row.int_answer = cint(raw_value) if raw_value != "" else None
    elif row.type == "Float":
        row.float_answer = flt(raw_value) if raw_value != "" else None
    elif row.type == "Select":
        row.select_answer = raw_value

    row.answer = raw_value
