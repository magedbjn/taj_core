# taj_core/overrides/leave_application.py
# version Frappe HR: v15.55.0
import datetime
import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

from hrms.hr.doctype.leave_application.leave_application import LeaveApplication as HRMSLeaveApplication


# ----------------------------
# Helpers
# ----------------------------
def _get_leave_type_flags(leave_type: str) -> dict:
    """Return stable internal flags (do NOT expose fieldnames as dict keys)."""
    vals = frappe.db.get_value(
        "Leave Type",
        leave_type,
        ["include_holiday", "taj_exclude_public_holidays"],
        as_dict=True,
    ) or {}

    return {
        "include_holiday": cint(vals.get("include_holiday") or 0),
        "exclude_public": cint(vals.get("taj_exclude_public_holidays") or 0),
    }


def _get_employee_holiday_list(employee: str) -> str | None:
    hl = get_holiday_list_for_employee(employee, raise_exception=False)
    return hl or None


def _get_official_holiday_dates(employee: str, from_date, to_date, holiday_list: str | None = None) -> set:
    """Official/Public holidays only (weekly_off = 0)."""
    if not holiday_list:
        holiday_list = _get_employee_holiday_list(employee)
    if not holiday_list:
        return set()

    rows = frappe.get_all(
        "Holiday",
        filters={
            "parent": holiday_list,
            "holiday_date": ["between", [from_date, to_date]],
            "weekly_off": 0,
        },
        pluck="holiday_date",
    )
    return set(rows or [])


def _get_official_holidays_count(employee: str, from_date, to_date, holiday_list: str | None = None) -> int:
    return len(_get_official_holiday_dates(employee, from_date, to_date, holiday_list=holiday_list))


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
    """
    UI Calculation Override

    Policy:
    - include_holiday=1 AND taj_exclude_public_holidays=1:
        subtract ONLY official/public holidays (weekly_off=0)
        (weekends weekly_off=1 are still counted)
    - Otherwise: behave like HRMS default
        - include_holiday=0 -> subtract ALL holidays (weekly_off 0 + 1)
        - include_holiday=1 -> subtract nothing
    """
    flags = _get_leave_type_flags(leave_type)
    include_holiday = flags["include_holiday"]
    exclude_public = flags["exclude_public"]

    # Base inclusive days (HRMS style)
    if cint(half_day) == 1:
        if getdate(from_date) == getdate(to_date):
            number_of_days = 0.5
        elif half_day_date and getdate(from_date) <= getdate(half_day_date) <= getdate(to_date):
            number_of_days = date_diff(to_date, from_date) + 0.5
        else:
            number_of_days = date_diff(to_date, from_date) + 1
    else:
        number_of_days = date_diff(to_date, from_date) + 1

    # Our special policy
    if include_holiday and exclude_public:
        official_cnt = _get_official_holidays_count(employee, from_date, to_date, holiday_list=holiday_list)
        return flt(number_of_days) - flt(official_cnt)

    # HRMS default behavior without importing HRMS method
    if not include_holiday:
        hl = holiday_list or _get_employee_holiday_list(employee)
        if not hl:
            return flt(number_of_days)

        all_holidays = frappe.get_all(
            "Holiday",
            filters={
                "parent": hl,
                "holiday_date": ["between", [from_date, to_date]],
            },
            pluck="holiday_date",
        )
        return flt(number_of_days) - flt(len(all_holidays or []))

    return flt(number_of_days)


# ----------------------------
# Doc Event: before_save
# ----------------------------
def before_save_set_total_leave_days(doc, method=None):
    """
    Server-side enforcement:
    - Only when include_holiday=1 AND taj_exclude_public_holidays=1
    - Set total_leave_days
    - Show message only if official holidays exist
    """
    if not (doc and doc.employee and doc.leave_type and doc.from_date and doc.to_date):
        return

    flags = _get_leave_type_flags(doc.leave_type)
    if not (flags["include_holiday"] and flags["exclude_public"]):
        # include_holiday=0 OR policy not enabled -> do nothing
        return

    official_cnt = _get_official_holidays_count(doc.employee, doc.from_date, doc.to_date)

    doc.total_leave_days = get_number_of_leave_days(
        employee=doc.employee,
        leave_type=doc.leave_type,
        from_date=doc.from_date,
        to_date=doc.to_date,
        half_day=doc.half_day,
        half_day_date=doc.half_day_date,
    )

    # Message: only if official holidays exist; no listing
    if official_cnt > 0 and not getattr(frappe.flags, "in_patch", False) and not getattr(frappe.flags, "in_migrate", False):
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
        We DO create Attendance for weekends (weekly_off=1) and normal days (since they are deducted).
        """
        if self.status != "Approved":
            return super().update_attendance()

        flags = _get_leave_type_flags(self.leave_type)
        if not (flags["include_holiday"] and flags["exclude_public"]):
            return super().update_attendance()

        official_dates = _get_official_holiday_dates(self.employee, self.from_date, self.to_date)

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

            # Uses HRMS built-in helper
            self.create_or_update_attendance(attendance_name, date_str)

            day = add_days(day, 1)
