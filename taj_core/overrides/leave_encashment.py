import frappe
from frappe import _
from frappe.utils import flt

from hrms.hr.doctype.leave_encashment.leave_encashment import LeaveEncashment
from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip


FIXED_AMOUNT_PER_DAY = "Fixed Amount Per Day"
BASED_ON_MONTHLY_SALARY = "Based on Monthly Salary"

MONTHLY_SALARY_DIVISOR = 30.0


class TajLeaveEncashment(LeaveEncashment):
    """
    Custom Leave Encashment calculation.

    Methods:
    1. Fixed Amount Per Day:
       Uses the standard Frappe HR calculation.

    2. Based on Monthly Salary:
       Uses the Net Pay calculated from the employee's active
       Salary Structure and Salary Structure Assignment.
    """

    def set_encashment_amount(self):
        calculation_method = (
            self.get("taj_encashment_calculation_method")
            or FIXED_AMOUNT_PER_DAY
        )

        # الطريقة القياسية الحالية
        if calculation_method == FIXED_AMOUNT_PER_DAY:
            super().set_encashment_amount()
            return

        if calculation_method != BASED_ON_MONTHLY_SALARY:
            frappe.throw(
                _("Invalid Encashment Calculation Method: {0}").format(
                    frappe.bold(calculation_method)
                )
            )

        encashment_days = flt(self.encashment_days)

        if encashment_days <= 0:
            self.encashment_amount = 0
            return

        monthly_net_salary = self.get_monthly_net_salary()

        daily_salary = monthly_net_salary / MONTHLY_SALARY_DIVISOR

        self.encashment_amount = flt(
            encashment_days * daily_salary,
            self.precision("encashment_amount"),
        )

    def get_monthly_net_salary(self):
        """
        Returns the calculated monthly Net Pay from a temporary
        Salary Slip preview.

        Net Pay = Gross Pay - Total Deductions

        No Salary Slip document is saved in the database.
        """

        if not self.employee:
            frappe.throw(_("Please select an Employee first."))

        if not self.encashment_date:
            frappe.throw(_("Please set the Encashment Date first."))

        # الحصول على Salary Structure الفعالة للموظف
        # في تاريخ تعويض الإجازة
        if not getattr(self, "_salary_structure", None):
            self.set_salary_structure()

        if not self._salary_structure:
            frappe.throw(
                _(
                    "No active Salary Structure was found for Employee {0} "
                    "on Encashment Date {1}."
                ).format(
                    frappe.bold(self.employee),
                    frappe.bold(self.encashment_date),
                )
            )

        # إنشاء Salary Slip مؤقتة داخل الذاكرة فقط
        salary_slip = make_salary_slip(
            source_name=self._salary_structure,
            employee=self.employee,
            posting_date=self.encashment_date,
            for_preview=1,
            ignore_permissions=True,
        )

        if not salary_slip:
            frappe.throw(
                _("Unable to calculate the monthly salary for Employee {0}.").format(
                    frappe.bold(self.employee)
                )
            )

        if salary_slip.get("salary_slip_based_on_timesheet"):
            frappe.throw(
                _(
                    "Based on Monthly Salary is not supported for "
                    "Salary Structures based on Timesheets."
                )
            )

        if salary_slip.get("payroll_frequency") != "Monthly":
            frappe.throw(
                _(
                    "The assigned Salary Structure must have Monthly "
                    "as its Payroll Frequency."
                )
            )

        gross_pay = flt(salary_slip.get("gross_pay"))
        total_deduction = flt(salary_slip.get("total_deduction"))
        monthly_net_salary = flt(salary_slip.get("net_pay"))

        if monthly_net_salary <= 0:
            frappe.throw(
                _(
                    "The calculated Net Pay for Employee {0} is zero or negative."
                    "<br><br>"
                    "Gross Pay: {1}"
                    "<br>"
                    "Total Deduction: {2}"
                    "<br>"
                    "Net Pay: {3}"
                ).format(
                    frappe.bold(self.employee),
                    frappe.bold(gross_pay),
                    frappe.bold(total_deduction),
                    frappe.bold(monthly_net_salary),
                )
            )

        return monthly_net_salary