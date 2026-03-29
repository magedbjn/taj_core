#file: taj_core/checklist/api.py
import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.exceptions import TimestampMismatchError
from frappe.utils import nowdate, cint, flt, cstr

from taj_core.checklist.doctype.checklist_answer.checklist_answer import get_question_meta
from taj_core.checklist.permissions import is_checklist_manager


OPEN_STATUSES = ("Draft", "In Progress")

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
    fields = list(BASE_LIST_FIELDS)

    if not _has_db_column("Checklist Answer", "result_status"):
        fields = [f for f in fields if f != "result_status"]

    return fields


def _status_filter_dict(status):
    if not status or status == "All":
        return {}

    if status == "Open":
        return {
            "docstatus": 0,
            "status": ["in", list(OPEN_STATUSES)],
        }

    if status == "Completed":
        return {
            "docstatus": 1,
            "status": "Completed",
        }

    if status == "Auto Closed":
        return {
            "docstatus": 1,
            "status": "Auto Closed",
        }

    if status in OPEN_STATUSES:
        return {
            "docstatus": 0,
            "status": status,
        }

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

    return {
        "name": doc.get("name"),
        "template": doc.get("template"),
        "posting_date": str(doc.get("posting_date") or ""),
        "status": doc.get("status"),
        "department": doc.get("department"),
        "assigned_user": doc.get("assigned_user"),
        "assignment_type": doc.get("assignment_type"),
        "docstatus": doc.get("docstatus"),
        "modified": str(doc.get("modified") or ""),
        "answer_by": doc.get("answer_by"),
        "has_issue": has_issue,
        "result_status": result_status or "Normal",
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
def get_user_dashboard_data(search_date=None):
    user = frappe.session.user
    selected_date = search_date or nowdate()
    fields = _get_list_fields()

    accessible_open_docs = frappe.get_list(
        "Checklist Answer",
        filters={
            "docstatus": 0,
            "status": ["in", list(OPEN_STATUSES)],
        },
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
        assignment_type = doc.get("assignment_type")

        is_unclaimed_department_task = (
            assignment_type == "Any User in Department"
            and not assigned_user
            and not answer_by
        )

        is_mine = (
            assigned_user == user
            or answer_by == user
            or is_unclaimed_department_task
        )

        serialized = _serialize_row_doc(doc)

        if doc.get("status") == "Draft":
            if is_mine:
                my_new.append(serialized)
            else:
                team_open.append(serialized)
        elif doc.get("status") == "In Progress":
            if is_mine:
                my_open.append(serialized)
            else:
                team_open.append(serialized)

    history_results = frappe.get_list(
        "Checklist Answer",
        filters={
            "posting_date": selected_date,
        },
        fields=fields,
        order_by="modified desc",
        page_length=200,
    )

    serialized_history_results = [_serialize_row_doc(doc) for doc in history_results]

    completed_on_date = [
        doc for doc in serialized_history_results
        if doc.get("docstatus") == 1 and doc.get("status") == "Completed"
    ]

    today_results = frappe.get_list(
        "Checklist Answer",
        filters={
            "posting_date": nowdate(),
        },
        fields=fields,
        order_by="modified desc",
        page_length=200,
    )

    serialized_today_results = [_serialize_row_doc(doc) for doc in today_results]

    today_has_issue = [
        doc for doc in serialized_today_results
        if doc.get("has_issue")
    ]

    return {
        "selected_date": selected_date,
        "summary": {
            "my_new_count": len(my_new),
            "my_open_count": len(my_open),
            "team_open_count": len(team_open),
            "completed_count": len(completed_on_date),
            "today_has_issue_count": len(today_has_issue),
        },
        "my_new": my_new,
        "my_open": my_open,
        "team_open": team_open,
        "history_results": serialized_history_results,
        "today_has_issue": today_has_issue,
    }


@frappe.whitelist()
def get_manager_dashboard_data(search_date=None, template=None, assigned_user=None, department=None, status=None, issue_filter=None):
    _ensure_manager()

    selected_date = search_date or nowdate()
    fields = _get_list_fields()

    today_filters = {
        "posting_date": nowdate(),
    }

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

    today_open = [
        row for row in serialized_today_docs
        if row.get("docstatus") == 0 and row.get("status") in OPEN_STATUSES
    ]

    today_completed = [
        row for row in serialized_today_docs
        if row.get("docstatus") == 1 and row.get("status") == "Completed"
    ]

    today_has_issue = [
        row for row in serialized_today_docs
        if row.get("has_issue")
    ]

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

    template_summary = _aggregate_summary_rows(
        serialized_search_docs,
        "template",
        _("No Template"),
    )

    employee_summary = _aggregate_summary_rows(
        serialized_search_docs,
        "assigned_user",
        _("Unassigned"),
    )

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
            doc.check_permission("write")

            if doc.docstatus != 0:
                frappe.throw(_("Only draft checklist can be edited."))

            row_map = {row.name: row for row in doc.answer}

            for item in payload:
                row = row_map.get(item.get("row_name"))
                if not row:
                    continue
                
                value = item.get("answer")
                _set_row_answer_by_type(row, value)

            doc.flags.ignore_due_date_update = True
            doc.save()

            return serialize_checklist_answer(doc)

        except TimestampMismatchError:
            if attempt == 0:
                continue
            raise


@frappe.whitelist()
def submit_checklist_answer(docname):
    doc = frappe.get_doc("Checklist Answer", docname)
    doc.check_permission("submit")
    doc.submit()

    return {
        "name": doc.name,
        "status": doc.status,
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
        "assigned_user": doc.assigned_user,
        "assignment_type": getattr(doc, "assignment_type", None),
        "answer_by": doc.answer_by,
        "docstatus": doc.docstatus,
        "is_editable": doc.docstatus == 0,
        "has_issue": 1 if result_status != "Normal" else 0,
        "result_status": result_status,
        "questions": questions,
    }

def _set_row_answer_by_type(row, value):
    raw_value = cstr(value).strip() if value is not None else ""

    # reset typed fields first
    if hasattr(row, "yes_no_answer"):
        row.yes_no_answer = ""

    if hasattr(row, "int_answer"):
        row.int_answer = None

    if hasattr(row, "float_answer"):
        row.float_answer = None

    if hasattr(row, "select_answer"):
        row.select_answer = ""

    # fill the proper field based on question type
    if row.type == "Yes/No":
        row.yes_no_answer = raw_value

    elif row.type == "Int":
        row.int_answer = cint(raw_value) if raw_value != "" else None

    elif row.type == "Float":
        row.float_answer = flt(raw_value) if raw_value != "" else None

    elif row.type == "Select":
        row.select_answer = raw_value

    # keep unified answer too
    row.answer = raw_value