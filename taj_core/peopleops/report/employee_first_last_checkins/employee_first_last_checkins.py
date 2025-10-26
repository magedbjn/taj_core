# ------------ Report: Employee First/Last Checkins (Monthly) — IN/OUT based; no-punch days show code in Span
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Extract
from frappe.utils import cint, getdate, now_datetime

# ------------ Entry Point ------------

def execute(filters=None):
    f = frappe._dict(filters or {})
    normalize_filters(f)

    start_date, end_date, mode = month_effective_range(f.year, f.month)
    if start_date is None:
        return get_columns(f), [], message_for_mode(mode), None

    columns = get_columns(f)
    
    if f.get("show_horizontal"):
        data = get_horizontal_data(f, start_date, end_date)
    else:
        data = get_data(f, start_date, end_date)
        
    message = legend_message() + (" " + message_for_mode(mode) if mode else "")
    return columns, data, message, None


# ------------ Filters & Range Logic ------------

def normalize_filters(f):
    if not f.get("month") or not f.get("year"):
        dt = now_datetime()
        f.month = cint(f.get("month") or dt.month)
        f.year = cint(f.get("year") or dt.year)
    f.month = cint(f.month)
    f.year = cint(f.year)
    if f.month < 1 or f.month > 12:
        frappe.throw(_("Month must be 1..12"))

def month_range_full(year: int, month: int) -> tuple[date, date]:
    last_day = calendar.monthrange(int(year), int(month))[1]
    return date(int(year), int(month), 1), date(int(year), int(month), last_day)

def month_effective_range(year: int, month: int) -> tuple[date|None, date|None, str]:
    """Return (start, end, mode):
    - current month  -> (1st, today), mode='current'
    - past month     -> (1st, end_of_month), mode='past'
    - future month   -> (None, None), mode='future' (no rows)
    """
    today = getdate(now_datetime())
    sel_start, sel_end = month_range_full(year, month)
    if year == today.year and month == today.month:
        return sel_start, today, "current"
    elif sel_end < today:
        return sel_start, sel_end, "past"
    elif sel_start > today:
        return None, None, "future"
    else:
        return sel_start, today, "current"

def message_for_mode(mode: str) -> str:
    if mode == "current":
        return "<span style='color:#6b7280'>Showing 1st of month through today.</span>"
    if mode == "past":
        return "<span style='color:#6b7280'>Showing full month.</span>"
    if mode == "future":
        return "<span style='color:#6b7280'>Selected month is in the future — no data.</span>"
    return ""


# ------------ Columns ------------

def get_columns(f):
    # إذا كان العرض الأفقي مفعل، نعيد أعمدة مختلفة
    if f.get("show_horizontal"):
        return get_horizontal_columns(f)
    
    cols = []

    if f.get("group_by"):
        mapping = {
            "Branch": "Branch",
            "Grade": "Employee Grade",
            "Department": "Department",
            "Designation": "Designation",
        }
        options = mapping.get(f.group_by)
        cols.append({
            "label": f.group_by,
            "fieldname": frappe.scrub(f.group_by),
            "fieldtype": "Link" if options else "Data",
            "options": options or "",
            "width": 150,
        })

    cols.extend([
        {"label": "Employee",      "fieldname": "employee",      "fieldtype": "Link", "options": "Employee", "width": 140},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 300},
        {"label": "Date",          "fieldname": "log_date",      "fieldtype": "Date", "width": 110},
        {"label": "Check In",      "fieldname": "check_in",      "fieldtype": "Data", "width": 100},
        {"label": "Check Out",     "fieldname": "check_out",     "fieldtype": "Data", "width": 100},
        {"label": "Span (Hours)",  "fieldname": "span_hours",    "fieldtype": "Data", "width": 130},
    ])
    return cols

def get_horizontal_columns(f):
    """إنشاء أعمدة العرض الأفقي: Employee, Employee Name, ثم أيام الشهر"""
    cols = []

    # إضافة Group By إذا تم اختياره
    if f.get("group_by"):
        mapping = {
            "Branch": "Branch",
            "Grade": "Employee Grade",
            "Department": "Department",
            "Designation": "Designation",
        }
        options = mapping.get(f.group_by)
        cols.append({
            "label": f.group_by,
            "fieldname": frappe.scrub(f.group_by),
            "fieldtype": "Link" if options else "Data",
            "options": options or "",
            "width": 150,
        })

    # الأعمدة الأساسية
    cols.extend([
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 300},
    ])

    # إضافة أعمدة الأيام
    start_date, end_date = month_range_full(f.year, f.month)
    current_date = start_date
    day_number = 1
    
    while current_date <= end_date:
        day_label = f"{day_number}" #f"{day_number}/{f.month}"
        day_fieldname = f"day_{day_number:02d}"
        
        cols.append({
            "label": day_label,
            "fieldname": day_fieldname,
            "fieldtype": "Data",
            "width": 50,
        })
        
        current_date += timedelta(days=1)
        day_number += 1

    return cols


# ------------ Helpers ------------

def fmt_time(val) -> str | None:
    """Return 'HH:MM' string or None from datetime / string / None."""
    if not val:
        return None
    try:
        dt = val if isinstance(val, datetime) else frappe.utils.get_datetime(val)
        return dt.strftime("%H:%M")
    except Exception:
        return None


# ------------ Data Assembly ------------

STATUS_CODE_MAP = {
    "Present": "P",
    "Absent": "A",
    "Half Day/Other Half Absent": "HD/A",
    "Half Day/Other Half Present": "HD/P",
    "Work From Home": "WFH",
    "On Leave": "L",
    "Holiday": "H",
    "Weekly Off": "WO",
    "No Punch": "NP",
}

def daterange(d1: date, d2: date):
    cur = d1
    while cur <= d2:
        yield cur
        cur = cur + timedelta(days=1)

def get_shift_info_for_employee(emp_id, log_date):
    """دالة ذكية لتحديد إذا كانت البصمة الواحدة أقرب لـ Check In أو Check Out"""
    try:
        emp = frappe.get_cached_value("Employee", emp_id, ["default_shift", "company"], as_dict=1)
        
        if emp and emp.default_shift:
            shift_times = frappe.get_cached_value("Shift Type", emp.default_shift, 
                                                ["start_time", "end_time"], as_dict=1)
            if shift_times and shift_times.start_time and shift_times.end_time:
                return shift_times.start_time, shift_times.end_time
        
        return "08:00:00", "17:00:00"
    except Exception:
        return "08:00:00", "17:00:00"

def classify_single_checkin(checkin_time, emp_id, log_date):
    """تصنيف البصمة الواحدة إلى Check In أو Check Out بناءً على الوقت"""
    try:
        if isinstance(checkin_time, str):
            checkin_dt = frappe.utils.get_datetime(checkin_time)
        else:
            checkin_dt = checkin_time
        
        shift_start_str, shift_end_str = get_shift_info_for_employee(emp_id, log_date)
        
        shift_start = frappe.utils.get_datetime(f"{log_date} {shift_start_str}")
        shift_end = frappe.utils.get_datetime(f"{log_date} {shift_end_str}")
        
        if shift_end < shift_start:
            shift_end += timedelta(days=1)
            if checkin_dt.hour < 12:
                checkin_dt += timedelta(days=1)
        
        distance_from_start = abs((checkin_dt - shift_start).total_seconds())
        distance_from_end = abs((checkin_dt - shift_end).total_seconds())
        
        if distance_from_start <= distance_from_end:
            return "check_in", checkin_time
        else:
            return "check_out", checkin_time
            
    except Exception:
        checkin_hour = checkin_time.hour if hasattr(checkin_time, 'hour') else checkin_dt.hour
        if checkin_hour < 12:
            return "check_in", checkin_time
        else:
            return "check_out", checkin_time

def get_data(f, dfrom: date, dto: date):
    emp_filters = {"status": "Active"}
    if f.get("employee"):
        emp_filters["name"] = f.employee

    employees = frappe.get_all(
        "Employee",
        fields=["name as employee", "employee_name", "company", "branch", "grade", "department", "designation", "holiday_list"],
        filters=emp_filters,
        order_by="employee_name asc",
    )
    if not employees:
        return []

    emp_map = {e.employee: e for e in employees}
    emp_list = [e.employee for e in employees]

    # جلب بيانات البصمات
    checkins = frappe.db.sql(
        """
        SELECT
            employee,
            employee_name,
            DATE(`time`) AS log_date,
            `time` AS log_time,
            log_type
        FROM `tabEmployee Checkin`
        WHERE employee IN %(emp_list)s
          AND DATE(`time`) BETWEEN %(dfrom)s AND %(dto)s
        ORDER BY employee, DATE(`time`), `time`
        """,
        {"emp_list": emp_list, "dfrom": dfrom, "dto": dto},
        as_dict=True,
    )

    per_day = defaultdict(list)
    for r in checkins:
        per_day[(r["employee"], r["log_date"])].append(r)

    attendance_code_map = build_attendance_code_map(emp_list, f.year, f.month)
    holiday_map = get_holiday_map_per_employee(employees, f.year, f.month)
    leave_map = get_leave_map_per_employee(emp_list, f.year, f.month)

    group_by = f.get("group_by")
    rows = []

    def emit_row(emp_id, log_date, items_for_day=None):
        emp_doc = emp_map[emp_id]

        # تهيئة القيم الافتراضية
        check_in_time = None
        check_out_time = None
        display_value = "0.00"

        if items_for_day and len(items_for_day) > 0:
            sorted_checkins = sorted(items_for_day, key=lambda x: x["log_time"])
            
            if len(sorted_checkins) == 1:
                # حالة البصمة الواحدة
                single_checkin = sorted_checkins[0]
                checkin_type, checkin_time = classify_single_checkin(
                    single_checkin["log_time"], emp_id, log_date
                )
                
                if checkin_type == "check_in":
                    check_in_time = fmt_time(checkin_time)
                else:
                    check_out_time = fmt_time(checkin_time)
                
                display_value = "0.00"
                
            else:
                # حالات متعددة البصمات
                in_times = []
                out_times = []
                
                for it in sorted_checkins:
                    log_type = (it.get("log_type") or "").upper()
                    if log_type == "IN":
                        in_times.append(it["log_time"])
                    elif log_type == "OUT":
                        out_times.append(it["log_time"])
                    else:
                        # إذا لم يكن هناك log_type، إضافة إلى كلا القائمتين
                        in_times.append(it["log_time"])
                        out_times.append(it["log_time"])
                
                # تحديد أول بصمة كـ Check In
                if in_times:
                    check_in_dt = min(in_times)
                    check_in_time = fmt_time(check_in_dt)
                elif sorted_checkins:
                    check_in_dt = sorted_checkins[0]["log_time"]
                    check_in_time = fmt_time(check_in_dt)
                
                # تحديد آخر بصمة كـ Check Out
                if out_times:
                    check_out_dt = max(out_times)
                    check_out_time = fmt_time(check_out_dt)
                elif sorted_checkins:
                    check_out_dt = sorted_checkins[-1]["log_time"]
                    check_out_time = fmt_time(check_out_dt)
                
                # حساب المدة بين أول وآخر بصمة
                if check_in_dt and check_out_dt:
                    time_diff = check_out_dt - check_in_dt
                    span_hours = round(time_diff.total_seconds() / 3600.0, 2)
                    display_value = f"{span_hours:.2f}"
                else:
                    display_value = "0.00"
                    
        else:
            # لا توجد بصمات - تحديد الحالة
            if (emp_id, log_date) in leave_map:
                display_value = "L"
            elif (emp_id, log_date) in holiday_map:
                display_value = holiday_map[(emp_id, log_date)]
            elif (emp_id, log_date) in attendance_code_map:
                display_value = attendance_code_map[(emp_id, log_date)]
            else:
                display_value = "NP"

        rows.append({
            "employee": emp_id,
            "employee_name": emp_doc.employee_name,
            "log_date": log_date,
            "check_in": check_in_time,
            "check_out": check_out_time,
            "span_hours": display_value,
            "branch": emp_doc.branch,
            "grade": emp_doc.grade,
            "department": emp_doc.department,
            "designation": emp_doc.designation,
        })

    if group_by:
        keyname = frappe.scrub(group_by)
        groups = defaultdict(list)
        for e in employees:
            groups[(getattr(e, keyname) or "")].append(e.employee)
        for group_value in sorted(groups.keys(), key=lambda x: (str(x).lower())):
            rows.append({keyname: group_value})
            for emp_id in sorted(groups[group_value], key=lambda eid: emp_map[eid].employee_name or ""):
                for d in daterange(dfrom, dto):
                    items = per_day.get((emp_id, d))
                    emit_row(emp_id, d, items)
    else:
        for emp_id in emp_list:
            for d in daterange(dfrom, dto):
                items = per_day.get((emp_id, d))
                emit_row(emp_id, d, items)

    return rows

def get_horizontal_data(f, dfrom: date, dto: date):
    """إنشاء بيانات العرض الأفقي"""
    emp_filters = {"status": "Active"}
    if f.get("employee"):
        emp_filters["name"] = f.employee

    employees = frappe.get_all(
        "Employee",
        fields=["name as employee", "employee_name", "company", "branch", "grade", "department", "designation", "holiday_list"],
        filters=emp_filters,
        order_by="employee_name asc",
    )
    if not employees:
        return []

    emp_map = {e.employee: e for e in employees}
    emp_list = [e.employee for e in employees]

    # جلب بيانات البصمات
    checkins = frappe.db.sql(
        """
        SELECT
            employee,
            employee_name,
            DATE(`time`) AS log_date,
            `time` AS log_time,
            log_type
        FROM `tabEmployee Checkin`
        WHERE employee IN %(emp_list)s
          AND DATE(`time`) BETWEEN %(dfrom)s AND %(dto)s
        ORDER BY employee, DATE(`time`), `time`
        """,
        {"emp_list": emp_list, "dfrom": dfrom, "dto": dto},
        as_dict=True,
    )

    per_day = defaultdict(list)
    for r in checkins:
        per_day[(r["employee"], r["log_date"])].append(r)

    attendance_code_map = build_attendance_code_map(emp_list, f.year, f.month)
    holiday_map = get_holiday_map_per_employee(employees, f.year, f.month)
    leave_map = get_leave_map_per_employee(emp_list, f.year, f.month)

    group_by = f.get("group_by")
    rows = []

    def get_span_value(emp_id, log_date, items_for_day):
        """دالة مساعدة لحساب قيمة الـ Span فقط"""
        if items_for_day and len(items_for_day) > 0:
            sorted_checkins = sorted(items_for_day, key=lambda x: x["log_time"])
            
            if len(sorted_checkins) == 1:
                return "0.00"
            else:
                in_times = []
                out_times = []
                
                for it in sorted_checkins:
                    log_type = (it.get("log_type") or "").upper()
                    if log_type == "IN":
                        in_times.append(it["log_time"])
                    elif log_type == "OUT":
                        out_times.append(it["log_time"])
                    else:
                        in_times.append(it["log_time"])
                        out_times.append(it["log_time"])
                
                # تحديد أول وآخر بصمة
                check_in_dt = min(in_times) if in_times else sorted_checkins[0]["log_time"]
                check_out_dt = max(out_times) if out_times else sorted_checkins[-1]["log_time"]
                
                # حساب المدة
                if check_in_dt and check_out_dt:
                    time_diff = check_out_dt - check_in_dt
                    span_hours = round(time_diff.total_seconds() / 3600.0, 2)
                    return f"{span_hours:.2f}"
                else:
                    return "0.00"
        else:
            # لا توجد بصمات - تحديد الحالة
            if (emp_id, log_date) in leave_map:
                return "L"
            elif (emp_id, log_date) in holiday_map:
                return holiday_map[(emp_id, log_date)]
            elif (emp_id, log_date) in attendance_code_map:
                return attendance_code_map[(emp_id, log_date)]
            else:
                return "NP"

    # إنشاء بيانات لكل موظف
    def create_employee_row(emp_id):
        emp_doc = emp_map[emp_id]
        row = {
            "employee": emp_id,
            "employee_name": emp_doc.employee_name,
            "branch": emp_doc.branch,
            "grade": emp_doc.grade,
            "department": emp_doc.department,
            "designation": emp_doc.designation,
        }

        # إضافة بيانات كل يوم
        current_date = dfrom
        day_number = 1
        
        while current_date <= dto:
            day_fieldname = f"day_{day_number:02d}"
            items = per_day.get((emp_id, current_date))
            
            span_value = get_span_value(emp_id, current_date, items)
            row[day_fieldname] = span_value
            
            current_date += timedelta(days=1)
            day_number += 1

        return row

    if group_by:
        keyname = frappe.scrub(group_by)
        groups = defaultdict(list)
        for e in employees:
            groups[(getattr(e, keyname) or "")].append(e.employee)
        
        for group_value in sorted(groups.keys(), key=lambda x: (str(x).lower())):
            # إضافة صف المجموعة
            group_row = {keyname: group_value}
            rows.append(group_row)
            
            # إضافة صفوق الموظفين في هذه المجموعة
            for emp_id in sorted(groups[group_value], key=lambda eid: emp_map[eid].employee_name or ""):
                employee_row = create_employee_row(emp_id)
                rows.append(employee_row)
    else:
        for emp_id in emp_list:
            employee_row = create_employee_row(emp_id)
            rows.append(employee_row)

    return rows


# ------------ Attendance & Holiday Helpers ------------

def build_attendance_code_map(emp_list, year, month):
    """(employee, date) -> code (P/A/HD/A/HD/P/WFH/L)."""
    Attendance = frappe.qb.DocType("Attendance")
    status_expr = (
        Case()
        .when(((Attendance.status == "Half Day") & (Attendance.half_day_status == "Present")),
              "Half Day/Other Half Present")
        .when(((Attendance.status == "Half Day") & (Attendance.half_day_status == "Absent")),
              "Half Day/Other Half Absent")
        .else_(Attendance.status)
    )
    rows = (
        frappe.qb.from_(Attendance)
        .select(Attendance.employee, Attendance.attendance_date, status_expr.as_("norm_status"))
        .where(
            (Attendance.docstatus == 1)
            & (Attendance.employee.isin(emp_list))
            & (Extract("month", Attendance.attendance_date) == int(month))
            & (Extract("year",  Attendance.attendance_date) == int(year))
        )
        .orderby(Attendance.employee, Attendance.attendance_date)
    ).run(as_dict=True)

    code_map = {}
    for r in rows:
        code = STATUS_CODE_MAP.get(r["norm_status"], None)
        if code:
            code_map[(r["employee"], getdate(r["attendance_date"]))] = code
    return code_map


def get_holiday_map_per_employee(employees, year: int, month: int):
    """Return {(emp, date): 'WO' or 'H'}."""
    companies = {e.company for e in employees if getattr(e, "company", None)}
    default_lists = {}
    if companies:
        for comp in companies:
            if not comp:
                continue
            try:
                default_lists[comp] = frappe.get_cached_value("Company", comp, "default_holiday_list")
            except Exception:
                default_lists[comp] = None

    needed_lists = set()
    for e in employees:
        needed_lists.add(e.holiday_list or default_lists.get(e.company))
    needed_lists = {x for x in needed_lists if x}

    Holiday = frappe.qb.DocType("Holiday")
    holiday_rows_by_list = {}
    for hl in needed_lists:
        rows = (
            frappe.qb.from_(Holiday)
            .select(Holiday.holiday_date, Holiday.weekly_off)
            .where(
                (Holiday.parent == hl)
                & (Extract("month", Holiday.holiday_date) == int(month))
                & (Extract("year",  Holiday.holiday_date) == int(year))
            )
        ).run(as_dict=True)
        holiday_rows_by_list[hl] = rows

    result = {}
    for e in employees:
        hl = e.holiday_list or default_lists.get(e.company)
        if not hl:
            continue
        rows = holiday_rows_by_list.get(hl) or []
        for r in rows:
            d = getdate(r["holiday_date"])
            code = "WO" if cint(r.get("weekly_off")) else "H"
            result[(e.employee, d)] = code
    return result


def get_leave_map_per_employee(emp_list, year: int, month: int):
    """Return {(emp, date): 'L'} for leave days."""
    LeaveApplication = frappe.qb.DocType("Leave Application")
    
    rows = (
        frappe.qb.from_(LeaveApplication)
        .select(LeaveApplication.employee, LeaveApplication.from_date, LeaveApplication.to_date)
        .where(
            (LeaveApplication.docstatus == 1)
            & (LeaveApplication.employee.isin(emp_list))
            & (LeaveApplication.status == "Approved")
            & (
                (Extract("month", LeaveApplication.from_date) == int(month)) |
                (Extract("month", LeaveApplication.to_date) == int(month))
            )
            & (
                (Extract("year", LeaveApplication.from_date) == int(year)) |
                (Extract("year", LeaveApplication.to_date) == int(year))
            )
        )
    ).run(as_dict=True)

    leave_map = {}
    for r in rows:
        from_date = getdate(r["from_date"])
        to_date = getdate(r["to_date"])
        
        current_date = from_date
        while current_date <= to_date:
            if current_date.month == month and current_date.year == year:
                leave_map[(r["employee"], current_date)] = "L"
            current_date += timedelta(days=1)
            
    return leave_map


# ------------ Legend ------------

def legend_message() -> str:
    colors = {
        "P":"green", "A":"red", "HD/A":"orange", "HD/P":"#914EE3", 
        "WFH":"green", "L":"#3187D8", "H":"#878787", "WO":"#878787",
        "NP":"#f59e0b"
    }
    parts = []
    ordered = [
        ("Present","P"), ("Absent","A"), ("Half Day/Other Half Absent","HD/A"), 
        ("Half Day/Other Half Present","HD/P"), ("Work From Home","WFH"), 
        ("On Leave","L"), ("Holiday","H"), ("Weekly Off","WO"),
        ("No Punch","NP")
    ]
    for label, abbr in ordered:
        color = colors.get(abbr, '#999')
        parts.append(
            f"<span style='border-left:2px solid {color}; padding-right:12px; padding-left:5px; margin-right:6px;'>{_(label)} - {abbr}</span>"
        )
    # parts.append("<span style='margin-left:8px;color:#6b7280'>NP = No Punch (نسي البصمة)</span>")
    return " ".join(parts)


# ------------ Whitelist ------------

@frappe.whitelist()
def get_years_for_checkins() -> str:
    res = frappe.db.sql(
        """
        SELECT DISTINCT YEAR(`time`) AS y
        FROM `tabEmployee Checkin`
        WHERE `time` IS NOT NULL
        ORDER BY y DESC
        """,
        as_dict=True,
    )
    if not res:
        return str(now_datetime().year)
    return "\n".join(str(r.y) for r in res)