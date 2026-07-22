import frappe
from frappe import _, bold
from frappe.utils import get_datetime, get_link_to_form

from hrms.payroll.doctype.gratuity.gratuity import Gratuity


class CustomGratuity(Gratuity):
	def get_total_working_days(self) -> float:
		date_of_joining, relieving_date = frappe.db.get_value(
			"Employee",
			self.employee,
			["date_of_joining", "relieving_date"],
		)

		if not date_of_joining:
			frappe.throw(
				_("Please set Date of Joining for employee: {0}").format(
					bold(get_link_to_form("Employee", self.employee))
				)
			)

		if not relieving_date:
			frappe.throw(
				_("Please set Relieving Date for employee: {0}").format(
					bold(get_link_to_form("Employee", self.employee))
				)
			)

		ignore_absence_and_lwp = frappe.db.get_value(
			"Gratuity Rule",
			self.gratuity_rule,
			"taj_ignore_absence_and_lwp",
		)

		if ignore_absence_and_lwp:
			# Calculate the full calendar period.
			# +1 includes the relieving date itself.
			return (
				get_datetime(relieving_date)
				- get_datetime(date_of_joining)
			).days + 1

		# Preserve the standard ERPNext behavior when unchecked.
		return super().get_total_working_days()