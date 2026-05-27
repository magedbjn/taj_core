# taj_core/overrides/leave_application.py
# HRMS: v15.55.0
#
# -------------------------------------------------------------------------
# Customization Note
# Date: 2026-05-25
#
# Purpose:
# Keep the standard HRMS Leave Application behavior unchanged by default.
#
# Custom logic is applied only when the Leave Type has:
# - include_holiday = 1
# - taj_exclude_public_holidays = 1
#
# In that custom case:
# - Weekends are counted as leave days.
# - Public / official holidays are excluded from leave deduction.
# - Attendance is not created for public / official holidays.
# - Attendance is still created for weekends and normal deducted days.
#
# No other standard HRMS Leave Application behavior is intentionally changed.
# -------------------------------------------------------------------------

from __future__ import annotations

import datetime
from typing import Any, Dict, Optional, Set, Tuple

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate
from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

from hrms.hr.doctype.leave_application import leave_application as core_leave_application
from hrms.hr.doctype.leave_application.leave_application import (
	LeaveApplication as HRMSLeaveApplication,
)


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _as_date(d: Any) -> Optional[datetime.date]:
	"""Normalize incoming date/date-string to datetime.date."""
	if not d:
		return None

	return getdate(d)


def _get_leave_type_flags(leave_type: str) -> Dict[str, int]:
	"""
	Return Leave Type flags.

	Internal normalized keys:
	- include_holiday: HRMS standard field
	- exclude_public: custom field taj_exclude_public_holidays
	"""
	if not leave_type:
		return {"include_holiday": 0, "exclude_public": 0}

	fields = ["include_holiday"]

	try:
		if frappe.get_meta("Leave Type").has_field("taj_exclude_public_holidays"):
			fields.append("taj_exclude_public_holidays")
	except Exception:
		# During unusual migration/meta states, fall back safely to standard behavior.
		pass

	try:
		vals = frappe.get_cached_value("Leave Type", leave_type, fields, as_dict=True) or {}
	except Exception:
		vals = frappe.db.get_value("Leave Type", leave_type, ["include_holiday"], as_dict=True) or {}

	return {
		"include_holiday": cint(vals.get("include_holiday") or 0),
		"exclude_public": cint(vals.get("taj_exclude_public_holidays") or 0),
	}


def _use_taj_public_holiday_policy(leave_type: str) -> bool:
	"""
	Return True only for the custom Taj policy.

	This keeps HRMS standard behavior untouched for all other Leave Types.
	"""
	flags = _get_leave_type_flags(leave_type)
	return bool(flags["include_holiday"] and flags["exclude_public"])


def _get_employee_holiday_list(employee: str) -> Optional[str]:
	"""Return the employee holiday list without raising if missing."""
	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
	return holiday_list or None


def _get_holiday_dates(
	holiday_list: str,
	from_date: datetime.date,
	to_date: datetime.date,
	*,
	weekly_off: Optional[int] = None,
) -> Set[datetime.date]:
	"""
	Fetch holiday dates from Holiday child table.

	weekly_off=None -> all holidays
	weekly_off=0    -> public / official holidays only
	weekly_off=1    -> weekly offs only
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
	Replicate HRMS-style inclusive date counting.

	Returns:
	- base_days
	- effective_half_day_date only when the half-day deduction is applied
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

		return flt(date_diff(td, fd)) + 1.0, None

	return flt(date_diff(td, fd)) + 1.0, None


def _deduction_units_for_holidays(
	holiday_dates: Set[datetime.date],
	effective_half_day_date: Optional[datetime.date],
) -> float:
	"""
	Calculate holiday deduction units.

	Normally each holiday deducts 1 day.
	If the applied half-day date is a holiday, deduct only 0.5 for that date.
	"""
	if not holiday_dates:
		return 0.0

	deduct = float(len(holiday_dates))

	if effective_half_day_date and effective_half_day_date in holiday_dates:
		deduct -= 0.5

	return max(0.0, deduct)


def _compute_taj_public_holiday_leave_days(
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
	Custom Taj leave calculation.

	This is used only when:
	- include_holiday = 1
	- taj_exclude_public_holidays = 1

	Policy:
	- Count weekends as leave days.
	- Exclude only public / official holidays where weekly_off = 0.
	"""
	fd = _as_date(from_date)
	td = _as_date(to_date)

	if not (employee and leave_type and fd and td):
		return 0.0

	base_days, effective_half_day_date = _compute_base_leave_days(
		fd,
		td,
		half_day,
		half_day_date,
	)

	if base_days <= 0:
		return 0.0

	holiday_list = holiday_list or _get_employee_holiday_list(employee)

	if not holiday_list:
		return flt(base_days)

	public_holiday_dates = _get_holiday_dates(
		holiday_list,
		fd,
		td,
		weekly_off=0,
	)

	deduct = _deduction_units_for_holidays(public_holiday_dates, effective_half_day_date)

	return flt(max(0.0, flt(base_days) - flt(deduct)))


# -------------------------------------------------------------------------
# Whitelisted Method Override
# -------------------------------------------------------------------------


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
	Return leave days.

	Use standard HRMS calculation by default.
	Use custom Taj public holiday calculation only when:
	- include_holiday = 1
	- taj_exclude_public_holidays = 1
	"""
	if not _use_taj_public_holiday_policy(leave_type):
		return core_leave_application.get_number_of_leave_days(
			employee=employee,
			leave_type=leave_type,
			from_date=from_date,
			to_date=to_date,
			half_day=half_day,
			half_day_date=half_day_date,
			holiday_list=holiday_list,
		)

	return _compute_taj_public_holiday_leave_days(
		employee=employee,
		leave_type=leave_type,
		from_date=from_date,
		to_date=to_date,
		half_day=half_day,
		half_day_date=half_day_date,
		holiday_list=holiday_list,
	)


# -------------------------------------------------------------------------
# Doc Event
# -------------------------------------------------------------------------


def before_save_set_total_leave_days(doc, method=None):
	"""
	Server-side enforcement for the custom Taj public holiday policy.

	Only applies when:
	- include_holiday = 1
	- taj_exclude_public_holidays = 1

	All other Leave Types keep standard HRMS behavior.
	"""
	if not (doc and doc.employee and doc.leave_type and doc.from_date and doc.to_date):
		return

	if not _use_taj_public_holiday_policy(doc.leave_type):
		return

	holiday_list = _get_employee_holiday_list(doc.employee)
	from_date = getdate(doc.from_date)
	to_date = getdate(doc.to_date)

	public_holiday_dates = (
		_get_holiday_dates(holiday_list, from_date, to_date, weekly_off=0) if holiday_list else set()
	)

	doc.total_leave_days = _compute_taj_public_holiday_leave_days(
		employee=doc.employee,
		leave_type=doc.leave_type,
		from_date=doc.from_date,
		to_date=doc.to_date,
		half_day=doc.half_day,
		half_day_date=doc.half_day_date,
		holiday_list=holiday_list,
	)

	if (
		public_holiday_dates
		and not getattr(frappe.flags, "in_patch", False)
		and not getattr(frappe.flags, "in_migrate", False)
	):
		if not getattr(doc.flags, "taj_pub_hol_msg_shown", False):
			frappe.msgprint(
				_("Public holidays have been excluded from the leave deduction. Weekends are still counted.")
			)
			doc.flags.taj_pub_hol_msg_shown = True


# -------------------------------------------------------------------------
# Doctype Class Override
# -------------------------------------------------------------------------


class LeaveApplication(HRMSLeaveApplication):
	def validate_balance_leaves(self):
		"""
		Use standard HRMS balance validation by default.

		For the custom Taj policy, calculate total_leave_days before checking
		the leave balance so balance validation uses the correct deduction days.
		"""
		if not _use_taj_public_holiday_policy(self.leave_type):
			return super().validate_balance_leaves()

		precision = cint(frappe.db.get_single_value("System Settings", "float_precision")) or 2

		if self.from_date and self.to_date:
			self.total_leave_days = _compute_taj_public_holiday_leave_days(
				employee=self.employee,
				leave_type=self.leave_type,
				from_date=self.from_date,
				to_date=self.to_date,
				half_day=self.half_day,
				half_day_date=self.half_day_date,
			)

			if self.total_leave_days <= 0:
				frappe.throw(
					_(
						"The day(s) on which you are applying for leave are holidays. You need not apply for leave."
					)
				)

			if not core_leave_application.is_lwp(self.leave_type):
				leave_balance = core_leave_application.get_leave_balance_on(
					self.employee,
					self.leave_type,
					self.from_date,
					self.to_date,
					consider_all_leaves_in_the_allocation_period=True,
					for_consumption=True,
				)

				leave_balance_for_consumption = flt(
					leave_balance.get("leave_balance_for_consumption"),
					precision,
				)

				if self.status != "Rejected" and (
					leave_balance_for_consumption < self.total_leave_days
					or not leave_balance_for_consumption
				):
					self.show_insufficient_balance_message(leave_balance_for_consumption)

	def update_attendance(self):
		"""
		Use standard HRMS attendance behavior by default.

		For the custom Taj policy:
		- Skip public / official holidays.
		- Create Attendance for weekends and normal deducted days.
		"""
		if self.status != "Approved":
			return super().update_attendance()

		if not _use_taj_public_holiday_policy(self.leave_type):
			return super().update_attendance()

		holiday_list = _get_employee_holiday_list(self.employee)
		public_holiday_dates = (
			_get_holiday_dates(
				holiday_list,
				getdate(self.from_date),
				getdate(self.to_date),
				weekly_off=0,
			)
			if holiday_list
			else set()
		)

		day = getdate(self.from_date)
		end = getdate(self.to_date)

		while day <= end:
			if day in public_holiday_dates:
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

			self.create_or_update_attendance(attendance_name, date_str)

			day = add_days(day, 1)