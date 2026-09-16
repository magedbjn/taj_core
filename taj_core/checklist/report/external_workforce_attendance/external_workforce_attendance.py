import frappe
from frappe import _
from frappe.utils import getdate


ALLOWED_ROLES = {"System Manager", "Checklist Manager", "HR Manager", "HR User"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    _ensure_access()
    _validate_dates(filters)
    return get_columns(), get_data(filters)


def _ensure_access():
    roles = set(frappe.get_roles(frappe.session.user))
    if not roles.intersection(ALLOWED_ROLES):
        frappe.throw(_("You do not have access to External Workforce Attendance."), frappe.PermissionError)


def _validate_dates(filters):
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("From Date and To Date are required."))
    if getdate(filters.from_date) > getdate(filters.to_date):
        frappe.throw(_("From Date cannot be after To Date."))


def get_columns():
    return [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
        {"label": _("Checklist"), "fieldname": "checklist", "fieldtype": "Link", "options": "Checklist Answer", "width": 170},
        {"label": _("Template"), "fieldname": "template", "fieldtype": "Link", "options": "Checklist Question Template", "width": 190},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 160},
        {"label": _("External Worker"), "fieldname": "external_worker", "fieldtype": "Link", "options": "Checklist External Worker", "width": 160},
        {"label": _("Worker Name"), "fieldname": "worker_name", "fieldtype": "Data", "width": 180},
        {"label": _("Badge / Worker No."), "fieldname": "badge_no", "fieldtype": "Data", "width": 120},
        {"label": _("Worker Company"), "fieldname": "company_name", "fieldtype": "Data", "width": 180},
        {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 170},
        {"label": _("Presence"), "fieldname": "presence_status", "fieldtype": "Data", "width": 90},
        {"label": _("Replacement"), "fieldname": "is_replacement", "fieldtype": "Check", "width": 90},
        {"label": _("Inspection"), "fieldname": "inspection_status", "fieldtype": "Data", "width": 90},
        {"label": _("Corrected Immediately"), "fieldname": "corrected_immediately", "fieldtype": "Check", "width": 125},
        {"label": _("Required"), "fieldname": "required_worker_count", "fieldtype": "Int", "width": 80},
        {"label": _("Present"), "fieldname": "present_worker_count", "fieldtype": "Int", "width": 75},
        {"label": _("Absent"), "fieldname": "absent_worker_count", "fieldtype": "Int", "width": 75},
        {"label": _("Replacements"), "fieldname": "replacement_worker_count", "fieldtype": "Int", "width": 95},
        {"label": _("Shortage"), "fieldname": "worker_shortage_count", "fieldtype": "Int", "width": 80},
        {"label": _("Staffing Status"), "fieldname": "worker_requirement_status", "fieldtype": "Data", "width": 105},
        {"label": _("Completed At"), "fieldname": "completed_at", "fieldtype": "Datetime", "width": 150},
    ]


def get_data(filters):
    conditions = [
        "ca.docstatus = 1",
        "ca.status = 'Completed'",
        "cw.parenttype = 'Checklist Answer'",
        "cw.parentfield = 'workers'",
        "cw.worker_type = 'External Worker'",
        "ca.posting_date BETWEEN %(from_date)s AND %(to_date)s",
    ]
    params = {
        "from_date": filters.from_date,
        "to_date": filters.to_date,
    }

    for fieldname, column in (
        ("department", "ca.department"),
        ("supplier", "cw.supplier"),
        ("company_name", "cw.company_name"),
        ("external_worker", "cw.external_worker"),
        ("presence_status", "cw.presence_status"),
    ):
        value = filters.get(fieldname)
        if value:
            conditions.append(f"{column} = %({fieldname})s")
            params[fieldname] = value

    return frappe.db.sql(
        f"""
        SELECT
            ca.posting_date,
            ca.name AS checklist,
            ca.template,
            ca.department,
            cw.external_worker,
            cw.worker_name,
            cw.badge_no,
            cw.company_name,
            cw.supplier,
            cw.presence_status,
            cw.is_replacement,
            cw.inspection_status,
            cw.corrected_immediately,
            ca.required_worker_count,
            ca.present_worker_count,
            ca.absent_worker_count,
            ca.replacement_worker_count,
            ca.worker_shortage_count,
            ca.worker_requirement_status,
            ca.completed_at
        FROM `tabChecklist Answer` ca
        INNER JOIN `tabChecklist Worker Entry` cw ON cw.parent = ca.name
        WHERE {' AND '.join(conditions)}
        ORDER BY ca.posting_date DESC, ca.name DESC, cw.idx ASC
        """,
        params,
        as_dict=True,
    )
