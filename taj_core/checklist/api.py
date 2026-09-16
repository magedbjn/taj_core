import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.exceptions import TimestampMismatchError
from frappe.utils import nowdate, now_datetime, get_datetime, cint, flt, cstr

from taj_core.checklist.doctype.checklist_answer.checklist_answer import (
    create_checklist_answer_from_template,
    get_question_meta,
)
from taj_core.checklist.permissions import (
    is_checklist_manager,
    checklist_answer_has_permission,
    checklist_user_belongs_to_department,
)
from taj_core.checklist.rules import (
    is_before_scheduled_start,
    normalize_multi_value,
    quick_pass_value,
    summarize_workers,
)
from taj_core.checklist.action_rules import action_is_overdue, build_issue_key


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
    "plant_floor",
    "warehouse",
    "asset",
    "source_due_date",
    "generation_key",
    "cycle_behavior",
    "required_before_production",
    "production_started_before_completion",
    "production_started_at",
    "production_work_order",
    "completion_percent_at_production_start",
    "incomplete_items_at_production_start",
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
        "plant_floor": doc.get("plant_floor"),
        "warehouse": doc.get("warehouse"),
        "asset": doc.get("asset"),
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
        "cycle_behavior": doc.get("cycle_behavior") or "",
        "required_before_production": cint(doc.get("required_before_production") or 0),
        "production_started_before_completion": cint(doc.get("production_started_before_completion") or 0),
        "production_started_at": str(doc.get("production_started_at") or ""),
        "production_work_order": doc.get("production_work_order") or "",
        "completion_percent_at_production_start": doc.get("completion_percent_at_production_start") or 0,
        "incomplete_items_at_production_start": doc.get("incomplete_items_at_production_start") or "",
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
    _ensure_manager()

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

    if not is_manager:
        if doc.assignment_type == "Specific User":
            if doc.assigned_user != user:
                frappe.throw(
                    _("This checklist is assigned to another user."),
                    frappe.PermissionError,
                )

        elif doc.assignment_type == "Any User in Department":
            if not checklist_user_belongs_to_department(doc, user):
                frappe.throw(
                    _("You do not belong to the department assigned to this checklist."),
                    frappe.PermissionError,
                )

        else:
            frappe.throw(
                _("This checklist does not have a valid assignment."),
                frappe.PermissionError,
            )

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

    taken_by = getattr(doc, "taken_by", None)

    if not taken_by:
        frappe.throw(
            _("This checklist is not currently claimed.")
        )

    if taken_by != user and not is_manager:
        frappe.throw(
            _("Only the current claimant or manager can release this checklist."),
            frappe.PermissionError,
        )

    doc.taken_by = None
    doc.flags.ignore_due_date_update = True
    doc.save(ignore_permissions=True)
    doc.reload()

    return serialize_checklist_answer(doc)


def _is_operational_for_date(row, selected_date):
    posting_date = cstr(row.get("posting_date") or "")
    if row.get("docstatus") == 0:
        return (not posting_date) or posting_date <= cstr(selected_date or "")
    return posting_date == cstr(selected_date or "")


def _operational_bucket(row):
    if row.get("docstatus") == 1 and row.get("status") == "Completed":
        return "completed"

    if row.get("docstatus") != 0 or row.get("status") not in OPEN_STATUSES:
        return "other"

    if (
        row.get("status") == "Expired"
        or cstr(row.get("time_status") or "").lower() == "overdue"
        or flt(row.get("delay_minutes") or 0) > 0
    ):
        return "overdue"

    if row.get("status") == "In Progress" or row.get("started_at") or row.get("taken_by"):
        return "in_progress"

    return "not_started"


def _merge_operational_docs(open_docs, dated_docs):
    merged = {}
    for doc in list(open_docs or []) + list(dated_docs or []):
        row = _serialize_row_doc(doc)
        if row.get("name"):
            merged[row["name"]] = row
    return list(merged.values())


def _sort_operational_rows(rows):
    priority = {
        "overdue": 0,
        "in_progress": 1,
        "not_started": 2,
        "completed": 3,
        "other": 4,
    }

    return sorted(
        rows,
        key=lambda row: (
            priority.get(_operational_bucket(row), 9),
            0 if row.get("result_status") == "Critical" else 1,
            cstr(row.get("deadline_at") or "9999-12-31 23:59:59"),
            cstr(row.get("template") or row.get("name") or ""),
        ),
    )


def _build_operational_summary(rows):
    buckets = defaultdict(int)
    for row in rows:
        buckets[_operational_bucket(row)] += 1

    return {
        "total": len(rows),
        "not_started": buckets["not_started"],
        "in_progress": buckets["in_progress"],
        "overdue": buckets["overdue"],
        "completed": buckets["completed"],
        "issues": sum(1 for row in rows if row.get("has_issue")),
        "critical": sum(1 for row in rows if row.get("result_status") == "Critical"),
        "production_started_early": sum(1 for row in rows if row.get("production_started_before_completion")),
    }


def _build_department_health(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.get("department") or _("No Department")].append(row)

    result = []
    for department, department_rows in grouped.items():
        summary = _build_operational_summary(department_rows)
        actionable_total = summary["not_started"] + summary["in_progress"] + summary["overdue"] + summary["completed"]
        completion_percent = round((summary["completed"] / actionable_total) * 100, 1) if actionable_total else 0

        if summary["critical"] or summary["production_started_early"]:
            health = "critical"
        elif summary["overdue"] or completion_percent < 70:
            health = "danger"
        elif summary["issues"] or completion_percent < 90:
            health = "warning"
        else:
            health = "good"

        result.append({
            "department": department,
            "completion_percent": completion_percent,
            "health": health,
            **summary,
        })

    health_order = {"critical": 0, "danger": 1, "warning": 2, "good": 3}
    result.sort(key=lambda row: (health_order.get(row["health"], 9), row["department"]))
    return result


def _build_team_summary(rows):
    grouped = defaultdict(list)
    for row in rows:
        owner = row.get("taken_by") or row.get("assigned_user") or _("Unassigned")
        grouped[owner].append(row)

    result = []
    for user, user_rows in grouped.items():
        summary = _build_operational_summary(user_rows)
        result.append({"user": user, **summary})

    result.sort(key=lambda row: (-row["overdue"], -row["in_progress"], row["user"]))
    return result


def _build_attention_rows(rows):
    attention = []
    for row in rows:
        bucket = _operational_bucket(row)
        if not (
            bucket == "overdue"
            or row.get("result_status") == "Critical"
            or row.get("production_started_before_completion")
            or (row.get("has_issue") and row.get("docstatus") == 0)
        ):
            continue

        item = dict(row)
        item["operational_bucket"] = bucket
        if row.get("production_started_before_completion"):
            item["attention_reason"] = _("Production started before completion")
            item["attention_level"] = "critical"
        elif row.get("result_status") == "Critical":
            item["attention_reason"] = _("Critical issue")
            item["attention_level"] = "critical"
        elif bucket == "overdue":
            item["attention_reason"] = _("Overdue")
            item["attention_level"] = "danger"
        else:
            item["attention_reason"] = _("Open issue")
            item["attention_level"] = "warning"
        attention.append(item)

    level_order = {"critical": 0, "danger": 1, "warning": 2}
    attention.sort(
        key=lambda row: (
            level_order.get(row.get("attention_level"), 9),
            -flt(row.get("delay_minutes") or 0),
            cstr(row.get("deadline_at") or "9999-12-31 23:59:59"),
        )
    )
    return attention


def _get_operational_docs(selected_date, manager=False, department=None):
    fields = _get_list_fields()
    getter = frappe.get_all if manager else frappe.get_list
    query_kwargs = {"fields": fields, "order_by": "modified desc"}
    if manager:
        query_kwargs["limit_page_length"] = 1000
    else:
        query_kwargs["page_length"] = 500

    open_filters = {"docstatus": 0, "status": ["in", list(OPEN_STATUSES)]}
    dated_filters = {"posting_date": selected_date}
    if department:
        open_filters["department"] = department
        dated_filters["department"] = department

    open_docs = getter("Checklist Answer", filters=open_filters, **query_kwargs)
    dated_docs = getter("Checklist Answer", filters=dated_filters, **query_kwargs)
    return _merge_operational_docs(open_docs, dated_docs)


def _get_current_employee_identity(user):
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        ["name", "employee_name", "department"],
        as_dict=True,
    )
    if employee:
        return {
            "employee": employee.get("name"),
            "employee_name": employee.get("employee_name") or user,
            "department": employee.get("department") or "",
        }

    return {
        "employee": "",
        "employee_name": frappe.db.get_value("User", user, "full_name") or user,
        "department": "",
    }


ACTION_LIST_FIELDS = [
    "name",
    "status",
    "severity",
    "quality_impact",
    "responsible_department",
    "responsible_user",
    "verification_user",
    "verification_department",
    "due_at",
    "requires_verification",
    "latest_observation",
    "latest_answer",
    "occurrence_count",
    "question_text",
    "source_template",
    "source_checklist",
    "latest_checklist",
    "department",
    "plant_floor",
    "warehouse",
    "first_detected_at",
    "last_detected_at",
    "owner",
    "modified",
]


def _serialize_action_row(row):
    data = dict(row)
    data["is_overdue"] = cint(
        action_is_overdue(
            data.get("status"),
            data.get("due_at"),
            now_datetime(),
        )
    )
    return data


def _get_open_action_rows(department=None):
    rows = frappe.get_list(
        "Checklist Action",
        filters={"status": ["!=", "Closed"]},
        fields=ACTION_LIST_FIELDS,
        order_by="modified desc",
        page_length=500,
    )
    serialized = [_serialize_action_row(row) for row in rows]
    if department:
        serialized = [
            row for row in serialized
            if department in (row.get("department"), row.get("responsible_department"))
        ]
    severity_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return sorted(
        serialized,
        key=lambda row: (
            0 if row.get("is_overdue") else 1,
            0 if row.get("status") == "Pending Verification" else 1,
            severity_rank.get(row.get("severity"), 9),
            cstr(row.get("due_at") or "9999-12-31"),
        ),
    )


def _my_action_rows(rows, user, identity):
    department = (identity or {}).get("department")
    result = []
    for row in rows:
        is_mine = (
            row.get("responsible_user") == user
            or row.get("verification_user") == user
            or (department and row.get("responsible_department") == department)
            or (department and row.get("verification_department") == department)
            or (
                not row.get("responsible_user")
                and not row.get("responsible_department")
                and department
                and row.get("department") == department
            )
        )
        if is_mine:
            result.append(row)
    return result


def _build_action_summary(rows):
    rows = rows or []
    return {
        "open": len(rows),
        "overdue": sum(1 for row in rows if row.get("is_overdue")),
        "critical": sum(1 for row in rows if row.get("severity") == "Critical"),
        "pending_verification": sum(1 for row in rows if row.get("status") == "Pending Verification"),
        "pass_observed": sum(1 for row in rows if row.get("latest_observation") == "Pass Observation"),
    }


@frappe.whitelist()
def get_checklist_today_data(search_date=None):
    user = frappe.session.user
    selected_date = search_date or nowdate()
    manager = is_checklist_manager(user)
    rows = _get_operational_docs(selected_date, manager=manager)
    rows = _sort_operational_rows(rows)
    identity = _get_current_employee_identity(user)
    open_actions = _get_open_action_rows()
    my_actions = _my_action_rows(open_actions, user, identity)

    today_rows = [row for row in rows if _is_operational_for_date(row, nowdate())]
    history_rows = [row for row in rows if row.get("posting_date") == selected_date]

    if manager:
        primary_rows = today_rows
        team_rows = [row for row in today_rows if row.get("docstatus") == 0]
    else:
        primary_rows = []
        team_rows = []
        for row in today_rows:
            is_mine = (
                row.get("assigned_user") == user
                or row.get("answer_by") == user
                or row.get("taken_by") == user
                or (
                    row.get("assignment_type") == "Any User in Department"
                    and not row.get("assigned_user")
                    and not row.get("answer_by")
                    and not row.get("taken_by")
                )
            )
            if is_mine:
                primary_rows.append(row)
            else:
                team_rows.append(row)

    return {
        "selected_date": selected_date,
        "user": user,
        "is_manager": cint(manager),
        "identity": identity,
        "settings": _get_checklist_settings(),
        "summary": _build_operational_summary(primary_rows),
        "today": _sort_operational_rows(primary_rows),
        "team": _sort_operational_rows(team_rows),
        "issues": _build_attention_rows(today_rows),
        "history": _sort_operational_rows(history_rows),
        "department_health": _build_department_health(today_rows) if manager else [],
        "team_summary": _build_team_summary(today_rows) if manager else [],
        "my_actions": my_actions,
        "action_summary": _build_action_summary(my_actions),
    }


@frappe.whitelist()
def get_checklist_control_room_data(search_date=None, department=None):
    _ensure_manager()

    selected_date = search_date or nowdate()
    rows = _get_operational_docs(selected_date, manager=True, department=department)
    rows = _sort_operational_rows(rows)
    current_rows = [row for row in rows if _is_operational_for_date(row, selected_date)]
    summary = _build_operational_summary(current_rows)
    action_rows = _get_open_action_rows(department=department)
    action_summary = _build_action_summary(action_rows)
    actionable_total = summary["not_started"] + summary["in_progress"] + summary["overdue"] + summary["completed"]
    summary["completion_percent"] = round((summary["completed"] / actionable_total) * 100, 1) if actionable_total else 0

    buckets = {
        "not_started": [],
        "in_progress": [],
        "overdue": [],
        "completed": [],
    }
    for row in current_rows:
        bucket = _operational_bucket(row)
        if bucket in buckets:
            buckets[bucket].append(row)

    return {
        "selected_date": selected_date,
        "department": department or "",
        "summary": summary,
        "department_health": _build_department_health(current_rows),
        "attention": _build_attention_rows(current_rows),
        "team_summary": _build_team_summary(current_rows),
        "buckets": buckets,
        "actions": action_rows,
        "action_summary": action_summary,
    }


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
    today_production_started_early = [
        row for row in serialized_today_docs
        if row.get("production_started_before_completion")
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
            "today_production_started_early": len({
                row.get("production_work_order") or row.get("name")
                for row in today_production_started_early
            }),
        },
        "today_all": serialized_today_docs,
        "today_open": today_open,
        "today_completed": today_completed,
        "today_remaining_docs": today_open,
        "today_has_issue_docs": today_has_issue,
        "today_production_started_early_docs": today_production_started_early,
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

                if "answer" in item:
                    _set_row_answer_by_type(row, item.get("answer"))

                for fieldname in ("failure_reason", "user_note", "evidence_photo", "photo_unavailable_reason"):
                    if fieldname in item and hasattr(row, fieldname):
                        setattr(row, fieldname, cstr(item.get(fieldname) or "").strip())

            doc.flags.ignore_due_date_update = True
            doc.save(ignore_permissions=True)
            doc.reload()

            return serialize_checklist_answer(doc)

        except TimestampMismatchError:
            if attempt == 0:
                continue
            raise


@frappe.whitelist()
def update_required_worker_count(docname, required_worker_count):
    doc = frappe.get_doc("Checklist Answer", docname)
    if not checklist_answer_has_permission(doc, frappe.session.user, "write") and not is_checklist_manager(frappe.session.user):
        frappe.throw(_("No permission to edit this checklist."), frappe.PermissionError)
    if doc.docstatus != 0:
        frappe.throw(_("Only draft checklist can be edited."))
    if not cint(getattr(doc, "enable_worker_check", 0)):
        frappe.throw(_("Worker Check is not enabled for this checklist."))

    count = cint(required_worker_count)
    if count < 0:
        frappe.throw(_("Required Worker Count cannot be negative."))

    doc.required_worker_count = count
    if hasattr(doc, "taken_by") and not doc.taken_by:
        doc.taken_by = frappe.session.user
    doc.flags.ignore_due_date_update = True
    doc.save(ignore_permissions=True)
    doc.reload()
    return serialize_checklist_answer(doc)


@frappe.whitelist()
def save_workers(docname, workers):
    payload = json.loads(workers) if isinstance(workers, str) else (workers or [])

    for attempt in range(2):
        try:
            doc = frappe.get_doc("Checklist Answer", docname)
            if not checklist_answer_has_permission(doc, frappe.session.user, "write") and not is_checklist_manager(frappe.session.user):
                frappe.throw(_("No permission to edit this checklist."), frappe.PermissionError)
            if doc.docstatus != 0:
                frappe.throw(_("Only draft checklist can be edited."))
            if not cint(getattr(doc, "enable_worker_check", 0)):
                frappe.throw(_("Worker Check is not enabled for this checklist."))

            doc.set("workers", [])
            for item in payload:
                worker_type = cstr(item.get("worker_type") or "").strip()
                presence_status = cstr(item.get("presence_status") or "Present").strip()
                inspection_status = cstr(item.get("inspection_status") or "").strip()
                if worker_type not in ("Internal Employee", "External Worker"):
                    frappe.throw(_("Invalid worker type."))
                if presence_status not in ("Present", "Absent"):
                    frappe.throw(_("Invalid worker presence status."))
                if inspection_status not in ("", "Pass", "Fail", "N/A"):
                    frappe.throw(_("Invalid worker inspection status."))

                doc.append("workers", {
                    "worker_type": worker_type,
                    "employee": cstr(item.get("employee") or "").strip() or None,
                    "external_worker": cstr(item.get("external_worker") or "").strip() or None,
                    "presence_status": presence_status,
                    "is_replacement": cint(item.get("is_replacement")),
                    "inspection_status": inspection_status or None,
                    "failure_reasons": normalize_multi_value(item.get("failure_reasons")),
                    "note": cstr(item.get("note") or "").strip(),
                    "evidence_photo": cstr(item.get("evidence_photo") or "").strip(),
                    "corrected_immediately": cint(item.get("corrected_immediately")),
                })

            if hasattr(doc, "taken_by") and not doc.taken_by:
                doc.taken_by = frappe.session.user
            doc.flags.ignore_due_date_update = True
            doc.save(ignore_permissions=True)
            doc.reload()
            return serialize_checklist_answer(doc)
        except TimestampMismatchError:
            if attempt == 0:
                continue
            raise


@frappe.whitelist()
def quick_create_external_worker(docname, worker_name, company_name=None, supplier=None, badge_no=None):
    doc = frappe.get_doc("Checklist Answer", docname)
    if not checklist_answer_has_permission(doc, frappe.session.user, "write") and not is_checklist_manager(frappe.session.user):
        frappe.throw(_("No permission to edit this checklist."), frappe.PermissionError)
    if doc.docstatus != 0:
        frappe.throw(_("Only draft checklist can be edited."))
    if not cint(getattr(doc, "enable_worker_check", 0)):
        frappe.throw(_("Worker Check is not enabled for this checklist."))

    worker_name = cstr(worker_name or "").strip()
    supplier = cstr(supplier or "").strip() or None
    company_name = cstr(company_name or getattr(doc, "default_worker_company", "") or "").strip()
    badge_no = cstr(badge_no or "").strip()
    if not worker_name:
        frappe.throw(_("Worker Name is required."))
    if supplier and not company_name:
        company_name = cstr(frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier).strip()
    if not company_name:
        frappe.throw(_("Company Name is required for an external worker."))

    filters = {"worker_name": worker_name, "company_name": company_name, "active": 1}
    if badge_no:
        filters["badge_no"] = badge_no
    existing = frappe.db.get_value("Checklist External Worker", filters, ["name", "worker_name", "company_name", "supplier", "badge_no"], as_dict=True)
    if existing:
        return dict(existing)

    worker = frappe.get_doc({
        "doctype": "Checklist External Worker",
        "worker_name": worker_name,
        "company_name": company_name,
        "supplier": supplier,
        "badge_no": badge_no,
        "active": 1,
    })
    worker.insert(ignore_permissions=True)
    return {
        "name": worker.name,
        "worker_name": worker.worker_name,
        "company_name": worker.company_name,
        "supplier": worker.supplier,
        "badge_no": worker.badge_no,
    }


@frappe.whitelist()
def quick_pass_checklist(docname):
    doc = frappe.get_doc("Checklist Answer", docname)

    if not checklist_answer_has_permission(doc, frappe.session.user, "write") and not is_checklist_manager(frappe.session.user):
        frappe.throw(_("No permission to edit this checklist."), frappe.PermissionError)

    if doc.docstatus != 0:
        frappe.throw(_("Only draft checklist can be edited."))

    if not _template_quick_pass_enabled(doc.template):
        frappe.throw(_("All OK / Quick Pass is disabled for this template."))

    changed = False
    for row in doc.answer:
        if cstr(getattr(row, "answer", "")).strip():
            continue

        meta = get_question_meta(row)
        value = quick_pass_value(
            cstr(getattr(meta, "type", None) or row.type).strip(),
            cint(getattr(meta, "quick_pass_allowed", 0)),
            issue_if_no=cint(getattr(meta, "issue_if_no", 0)),
        )
        if value is None:
            continue

        _set_row_answer_by_type(row, value)
        changed = True

    if changed:
        if hasattr(doc, "taken_by") and not doc.taken_by:
            doc.taken_by = frappe.session.user
        doc.flags.ignore_due_date_update = True
        doc.save(ignore_permissions=True)
        doc.reload()

    return serialize_checklist_answer(doc)


def _template_quick_pass_enabled(template_name):
    if not template_name:
        return False
    if not _has_db_column("Checklist Question Template", "enable_quick_pass"):
        return True
    return cint(frappe.db.get_value("Checklist Question Template", template_name, "enable_quick_pass")) == 1


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


def _get_open_actions_for_answer(doc):
    row_keys = {}
    for row in getattr(doc, "answer", None) or []:
        question_identity = cstr(
            getattr(row, "question_link", None) or getattr(row, "question", None)
        ).strip()
        if not question_identity:
            continue
        row_keys[row.name] = build_issue_key(
            getattr(doc, "template", None),
            question_identity,
            getattr(doc, "plant_floor", None),
            getattr(doc, "warehouse", None),
            asset=getattr(doc, "asset", None),
        )

    if not row_keys:
        return {}

    try:
        rows = frappe.get_all(
            "Checklist Action",
            filters={"open_issue_key": ["in", list(set(row_keys.values()))]},
            fields=["name", "open_issue_key", "status", "latest_observation"],
            limit_page_length=500,
        )
    except Exception:
        return {}

    by_key = {row.get("open_issue_key"): row for row in rows}
    return {
        row_name: by_key.get(issue_key)
        for row_name, issue_key in row_keys.items()
        if by_key.get(issue_key)
    }


def serialize_checklist_answer(doc):
    if isinstance(doc, str):
        doc = frappe.get_doc("Checklist Answer", doc)

    child_has_issue = _has_meta_field("Checklist Answer Question", "has_issue")
    child_issue_note = _has_meta_field("Checklist Answer Question", "issue_note")
    parent_result_status = _has_meta_field("Checklist Answer", "result_status")
    open_actions = _get_open_actions_for_answer(doc)

    questions = []
    for row in doc.answer:
        meta = get_question_meta(row)
        open_action = open_actions.get(row.name) or {}
        questions.append({
            "row_name": row.name,
            "question": row.question,
            "question_text": meta.question_text or row.question,
            "type": meta.type or row.type,
            "answer": row.answer,
            "answer_options": meta.answer_select or "",
            "is_required": cint(getattr(meta, "is_required", 1)),
            "quick_pass_allowed": cint(getattr(meta, "quick_pass_allowed", 0)),
            "answer_min_int": getattr(meta, "answer_min_int", None),
            "answer_max_int": getattr(meta, "answer_max_int", None),
            "answer_min_float": getattr(meta, "answer_min_float", None),
            "answer_max_float": getattr(meta, "answer_max_float", None),
            "issue_if_no": cint(getattr(meta, "issue_if_no", 0)),
            "issue_values": getattr(meta, "issue_select_values", None) or "",
            "issue_severity": getattr(meta, "issue_severity", None) or "Medium",
            "quality_impact": cint(getattr(meta, "quality_impact", 0)),
            "has_issue": getattr(row, "has_issue", 0) if child_has_issue else 0,
            "issue_note": getattr(row, "issue_note", "") if child_issue_note else "",
            "require_failure_reason": cint(getattr(meta, "require_failure_reason", 0)),
            "failure_reason_options": getattr(meta, "failure_reason_options", None) or "",
            "failure_reason": getattr(row, "failure_reason", "") or "",
            "require_failure_note": cint(getattr(meta, "require_failure_note", 0)),
            "user_note": getattr(row, "user_note", "") or "",
            "require_failure_photo": cint(getattr(meta, "require_failure_photo", 0)),
            "allow_no_photo_with_reason": cint(getattr(meta, "allow_no_photo_with_reason", 0)),
            "evidence_photo": getattr(row, "evidence_photo", "") or "",
            "photo_unavailable_reason": getattr(row, "photo_unavailable_reason", "") or "",
            "require_follow_up": cint(getattr(meta, "require_follow_up", 0)),
            "responsible_department": getattr(meta, "responsible_department", None),
            "responsible_user": getattr(meta, "responsible_user", None),
            "notify_department": getattr(meta, "notify_department", None),
            "notify_user": getattr(meta, "notify_user", None),
            "require_verification": cint(getattr(meta, "require_verification", 0)),
            "open_action": open_action.get("name") or "",
            "open_action_status": open_action.get("status") or "",
            "open_action_latest_observation": open_action.get("latest_observation") or "",
        })

    workers = []
    for row in getattr(doc, "workers", None) or []:
        workers.append({
            "row_name": row.name,
            "worker_type": getattr(row, "worker_type", "") or "",
            "employee": getattr(row, "employee", None),
            "external_worker": getattr(row, "external_worker", None),
            "worker_name": getattr(row, "worker_name", "") or "",
            "company_name": getattr(row, "company_name", "") or "",
            "supplier": getattr(row, "supplier", None),
            "badge_no": getattr(row, "badge_no", "") or "",
            "presence_status": getattr(row, "presence_status", "Present") or "Present",
            "is_replacement": cint(getattr(row, "is_replacement", 0)),
            "inspection_status": getattr(row, "inspection_status", "") or "",
            "failure_reasons": getattr(row, "failure_reasons", "") or "",
            "note": getattr(row, "note", "") or "",
            "evidence_photo": getattr(row, "evidence_photo", "") or "",
            "corrected_immediately": cint(getattr(row, "corrected_immediately", 0)),
        })

    worker_summary = summarize_workers(
        workers,
        required_count=getattr(doc, "required_worker_count", 0),
    ) if cint(getattr(doc, "enable_worker_check", 0)) else {
        "required": 0,
        "present": 0,
        "absent": 0,
        "replacements": 0,
        "shortage": 0,
        "status": "Not Set",
    }

    result_status = getattr(doc, "result_status", "Normal") if parent_result_status else "Normal"
    scheduled_start = get_datetime(doc.scheduled_start_at) if getattr(doc, "scheduled_start_at", None) else None
    is_time_locked = bool(
        doc.docstatus == 0
        and is_before_scheduled_start(scheduled_start, now_datetime())
    )
    is_editable = doc.docstatus == 0 and not is_time_locked and (
        checklist_answer_has_permission(doc, frappe.session.user, "write")
        or is_checklist_manager(frappe.session.user)
    )

    return {
        "name": doc.name,
        "template": doc.template,
        "posting_date": str(doc.posting_date) if doc.posting_date else "",
        "status": doc.status,
        "department": doc.department,
        "plant_floor": getattr(doc, "plant_floor", None),
        "warehouse": getattr(doc, "warehouse", None),
        "asset": getattr(doc, "asset", None),
        "assigned_user": getattr(doc, "assigned_user", None),
        "taken_by": getattr(doc, "taken_by", None),
        "assignment_type": getattr(doc, "assignment_type", None),
        "answer_by": doc.answer_by,
        "docstatus": doc.docstatus,
        "is_editable": is_editable,
        "is_time_locked": cint(is_time_locked),
        "can_quick_pass": cint(bool(is_editable and _template_quick_pass_enabled(doc.template))),
        "can_reassign": is_checklist_manager(frappe.session.user) and doc.docstatus == 0 and doc.status not in ("Completed", "Auto Closed"),
        "has_issue": 1 if result_status != "Normal" else 0,
        "result_status": result_status,
        "scheduled_start_at": str(getattr(doc, "scheduled_start_at", "") or ""),
        "deadline_at": str(getattr(doc, "deadline_at", "") or ""),
        "started_at": str(getattr(doc, "started_at", "") or ""),
        "completed_at": str(getattr(doc, "completed_at", "") or ""),
        "time_status": getattr(doc, "time_status", "") or "",
        "delay_minutes": getattr(doc, "delay_minutes", 0) or 0,
        "cycle_behavior": getattr(doc, "cycle_behavior", "") or "",
        "required_before_production": cint(getattr(doc, "required_before_production", 0)),
        "production_started_before_completion": cint(getattr(doc, "production_started_before_completion", 0)),
        "production_started_at": str(getattr(doc, "production_started_at", "") or ""),
        "production_work_order": getattr(doc, "production_work_order", None),
        "completion_percent_at_production_start": cint(getattr(doc, "completion_percent_at_production_start", 0)),
        "incomplete_items_at_production_start": getattr(doc, "incomplete_items_at_production_start", "") or "",
        "is_previous_cycle_open": cint(bool(doc.docstatus == 0 and cstr(doc.posting_date or "") and cstr(doc.posting_date) < nowdate())),
        "is_today_new": cint(bool(doc.docstatus == 0 and doc.status == "Draft" and cstr(doc.posting_date or "") == nowdate())),
        "open_from_date": cstr(doc.posting_date or ""),
        "can_claim": doc.docstatus == 0 and getattr(doc, "assignment_type", None) == "Any User in Department" and (not getattr(doc, "taken_by", None) or getattr(doc, "taken_by", None) == frappe.session.user or is_checklist_manager(frappe.session.user)),
        "can_release": doc.docstatus == 0 and bool(getattr(doc, "taken_by", None)) and (getattr(doc, "taken_by", None) == frappe.session.user or is_checklist_manager(frappe.session.user)),
        "enable_worker_check": cint(getattr(doc, "enable_worker_check", 0)),
        "required_worker_count": cint(getattr(doc, "required_worker_count", 0)),
        "default_worker_company": getattr(doc, "default_worker_company", "") or "",
        "default_worker_supplier": getattr(doc, "default_worker_supplier", None),
        "worker_failure_reason_options": getattr(doc, "worker_failure_reason_options", "") or "",
        "workers": workers,
        "worker_summary": worker_summary,
        "questions": questions,
    }


def _set_row_answer_by_type(row, value):
    question_type = cstr(getattr(row, "type", "")).strip()
    if question_type == "Multi Select":
        raw_value = normalize_multi_value(value)
    else:
        raw_value = cstr(value).strip() if value is not None else ""

    if hasattr(row, "yes_no_answer"):
        row.yes_no_answer = ""
    if hasattr(row, "pass_fail_answer"):
        row.pass_fail_answer = ""
    if hasattr(row, "int_answer"):
        row.int_answer = None
    if hasattr(row, "float_answer"):
        row.float_answer = None
    if hasattr(row, "select_answer"):
        row.select_answer = ""
    if hasattr(row, "multi_select_answer"):
        row.multi_select_answer = ""
    if hasattr(row, "text_answer"):
        row.text_answer = ""
    if hasattr(row, "photo_answer"):
        row.photo_answer = ""

    if question_type in ("Yes/No", "Yes/No/NA"):
        row.yes_no_answer = raw_value
    elif question_type == "Pass/Fail/NA":
        row.pass_fail_answer = raw_value
    elif question_type == "Int":
        row.int_answer = cint(raw_value) if raw_value != "" else None
    elif question_type == "Float":
        row.float_answer = flt(raw_value) if raw_value != "" else None
    elif question_type in ("Select", "Single Select"):
        row.select_answer = raw_value
    elif question_type == "Multi Select":
        row.multi_select_answer = raw_value
    elif question_type == "Text":
        row.text_answer = raw_value
    elif question_type == "Photo":
        row.photo_answer = raw_value

    row.answer = raw_value
