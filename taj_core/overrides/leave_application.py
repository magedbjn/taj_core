# taj_core/overrides/leave_application.py
# version Frappe HR: v15.55.0

from __future__ import annotations

import datetime
from typing import Optional, Set, Tuple, Dict, Any

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

from hrms.hr.doctype.leave_application.leave_application import (
    LeaveApplication as HRMSLeaveApplication,
)

# ----------------------------
# Helpers (dates / db)
# ----------------------------

def _as_date(d: Any) -> Optional[datetime.date]:
    """Normalize incoming date/date-string to datetime.date (or None)."""
    if not d:
        return None
    return getdate(d)


def _get_leave_type_flags(leave_type: str) -> Dict[str, int]:
    """
    Return stable internal flags (do NOT expose fieldnames as dict keys).
    - include_holiday: HRMS standard
    - exclude_public: custom policy flag (taj_exclude_public_holidays)
    """
    vals = None
    # Prefer cached value if available
    try:
        vals = frappe.get_cached_value(
            "Leave Type",
            leave_type,
            ["include_holiday", "taj_exclude_public_holidays"],
            as_dict=True,
        )
    except Exception:
        vals = frappe.db.get_value(
            "Leave Type",
            leave_type,
            ["include_holiday", "taj_exclude_public_holidays"],
            as_dict=True,
        )

    vals = vals or {}
    return {
        "include_holiday": cint(vals.get("include_holiday") or 0),
        "exclude_public": cint(vals.get("taj_exclude_public_holidays") or 0),
    }


def _get_employee_holiday_list(employee: str) -> Optional[str]:
    hl = get_holiday_list_for_employee(employee, raise_exception=False)
    return hl or None


def _get_holiday_dates(
    holiday_list: str,
    from_date: datetime.date,
    to_date: datetime.date,
    *,
    weekly_off: Optional[int] = None,
) -> Set[datetime.date]:
    """
    Fetch holiday dates from Holiday child table:
    - weekly_off=None -> all holidays
    - weekly_off=0 -> official/public holidays only
    - weekly_off=1 -> weekly offs only
    """
    if not holiday_list:
        return set()

    filters = {
        "parent": holiday_list,
        "holiday_date": ["between", [from_date, to_date]],
    }
    if weekly_off is not None:
        filters["weekly_off"] = weekly_off

    rows = frappe.get_all("Holiday", filters=filters, pluck="holiday_date") or []
    return {getdate(d) for d in rows}


def _compute_base_leave_days(
    from_date: datetime.date,
    to_date: datetime.date,
    half_day: int | str | None,
    half_day_date: datetime.date | str | None,
) -> Tuple[float, Optional[datetime.date]]:
    """
    Replicates HRMS-style inclusive counting, returning:
    - base_days (float)
    - effective_half_day_date (date|None) ONLY if the 0.5 was actually applied
    """
    fd = getdate(from_date)
    td = getdate(to_date)

    if fd > td:
        return 0.0, None

    if cint(half_day) == 1:
        if fd == td:
            return 0.5, fd

        hd = _as_date(half_day_date)
        if hd and fd <= hd <= td:
            return flt(date_diff(td, fd)) + 0.5, hd

        # half_day flag set but date invalid/outside -> treat as full days
        return flt(date_diff(td, fd)) + 1.0, None

    return flt(date_diff(td, fd)) + 1.0, None


def _deduction_units_for_holidays(
    holiday_dates: Set[datetime.date],
    effective_half_day_date: Optional[datetime.date],
) -> float:
    """
    Count holiday deductions with half-day safety:
    - normally each holiday date deducts 1.0
    - if the only applied half-day date falls on a holiday, that holiday should deduct 0.5 not 1.0
    """
    if not holiday_dates:
        return 0.0

    deduct = float(len(holiday_dates))
    if effective_half_day_date and effective_half_day_date in holiday_dates:
        deduct -= 0.5

    return max(0.0, deduct)


def _compute_total_leave_days(
    employee: str,
    leave_type: str,
    from_date: datetime.date | str,
    to_date: datetime.date | str,
    *,
    half_day: int | str | None = None,
    half_day_date: datetime.date | str | None = None,
    holiday_list: Optional[str] = None,
) -> float:
    """
    Single source of truth for calculations (UI + server hooks).

    Policy:
    - include_holiday=1 AND taj_exclude_public_holidays=1:
        subtract ONLY official/public holidays (weekly_off=0)
        (weekends weekly_off=1 are still counted)
    - Otherwise: behave like HRMS default
        - include_holiday=0 -> subtract ALL holidays (weekly_off 0 + 1)
        - include_holiday=1 -> subtract nothing
    """
    fd = _as_date(from_date)
    td = _as_date(to_date)
    if not (employee and leave_type and fd and td):
        return 0.0

    base_days, eff_hd = _compute_base_leave_days(fd, td, half_day, half_day_date)
    if base_days <= 0:
        return 0.0

    flags = _get_leave_type_flags(leave_type)
    include_holiday = flags["include_holiday"]
    exclude_public = flags["exclude_public"]

    hl = holiday_list or _get_employee_holiday_list(employee)

    # Special policy: count weekends, exclude official/public only
    if include_holiday and exclude_public:
        if not hl:
            return flt(base_days)

        official_dates = _get_holiday_dates(hl, fd, td, weekly_off=0)
        deduct = _deduction_units_for_holidays(official_dates, eff_hd)
        return flt(max(0.0, flt(base_days) - flt(deduct)))

    # HRMS-like default
    if not include_holiday:
        if not hl:
            return flt(base_days)

        all_holidays = _get_holiday_dates(hl, fd, td, weekly_off=None)
        deduct = _deduction_units_for_holidays(all_holidays, eff_hd)
        return flt(max(0.0, flt(base_days) - flt(deduct)))

    return flt(base_days)


# ----------------------------
# Whitelisted override (UI)
# ----------------------------
@frappe.whitelist()
def get_number_of_leave_days(
    employee: str,
    leave_type: str,
    from_date: datetime.date,
    to_date: datetime.date,
    half_day: int | str | None = None,
    half_day_date: datetime.date | str | None = None,
    holiday_list: str | None = None,
) -> float:
    """UI Calculation Override (delegates to our unified calculator)."""
    return _compute_total_leave_days(
        employee=employee,
        leave_type=leave_type,
        from_date=from_date,
        to_date=to_date,
        half_day=half_day,
        half_day_date=half_day_date,
        holiday_list=holiday_list,
    )


# ----------------------------
# Doc Event: before_save
# ----------------------------
def before_save_set_total_leave_days(doc, method=None):
    """
    Server-side enforcement:
    - Only when include_holiday=1 AND taj_exclude_public_holidays=1
    - Set total_leave_days
    - Show message only if official holidays exist (no listing)
    """
    if not (doc and doc.employee and doc.leave_type and doc.from_date and doc.to_date):
        return

    flags = _get_leave_type_flags(doc.leave_type)
    if not (flags["include_holiday"] and flags["exclude_public"]):
        return

    hl = _get_employee_holiday_list(doc.employee)
    fd = getdate(doc.from_date)
    td = getdate(doc.to_date)

    official_dates = _get_holiday_dates(hl, fd, td, weekly_off=0) if hl else set()

    doc.total_leave_days = _compute_total_leave_days(
        employee=doc.employee,
        leave_type=doc.leave_type,
        from_date=doc.from_date,
        to_date=doc.to_date,
        half_day=doc.half_day,
        half_day_date=doc.half_day_date,
        holiday_list=hl,
    )

    # Message only if official holidays exist; avoid patches/migrate spam
    if (
        official_dates
        and not getattr(frappe.flags, "in_patch", False)
        and not getattr(frappe.flags, "in_migrate", False)
    ):
        if not getattr(doc.flags, "taj_pub_hol_msg_shown", False):
            frappe.msgprint(
                _("Public holidays have been excluded from the leave deduction. Weekends are still counted.")
            )
            doc.flags.taj_pub_hol_msg_shown = True


# ----------------------------
# Doctype Class Override (Attendance)
# ----------------------------
class LeaveApplication(HRMSLeaveApplication):
    def update_attendance(self):
        """
        Create Attendance ONLY for deducted days when:
          - include_holiday=1
          - taj_exclude_public_holidays=1

        We SKIP official/public holidays (weekly_off=0).
        We DO create Attendance for weekends (weekly_off=1) and normal days.
        """
        if self.status != "Approved":
            return super().update_attendance()

        flags = _get_leave_type_flags(self.leave_type)
        if not (flags["include_holiday"] and flags["exclude_public"]):
            return super().update_attendance()

        hl = _get_employee_holiday_list(self.employee)
        official_dates = (
            _get_holiday_dates(hl, getdate(self.from_date), getdate(self.to_date), weekly_off=0)
            if hl
            else set()
        )

        day = getdate(self.from_date)
        end = getdate(self.to_date)

        while day <= end:
            if day in official_dates:
                day = add_days(day, 1)
                continue

            date_str = day.strftime("%Y-%m-%d")

            attendance_name = frappe.db.exists(
                "Attendance",
                {
                    "employee": self.employee,
                    "attendance_date": date_str,
                    "docstatus": ("!=", 2),
                },
            )

            # HRMS helper
            self.create_or_update_attendance(attendance_name, date_str)

            day = add_days(day, 1)
