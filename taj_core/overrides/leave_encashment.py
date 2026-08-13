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

    Calculation Methods
    -------------------
    1. Fixed Amount Per Day
       Uses the standard Frappe HR Leave Encashment calculation.

    2. Based on Monthly Salary
       Calculates the employee's monthly salary using the active
       Salary Structure Assignment on the Encashment Date.

       The calculation intentionally does NOT use Salary Slip Net Pay,
       because Net Pay may include transactional deductions such as
       Loan Repayment.

       Monthly Salary for Leave Encashment =
           Structured Earnings - Structured Deductions

       Excluded from the calculation:
       - Loan Repayment
       - Additional Salary earnings
       - Additional Salary deductions
       - LWP / Attendance reduction because for_preview=1 is used

    This keeps Leave Encashment independent from payroll transactions
    such as employee loans.
    """

    def set_encashment_amount(self):
        calculation_method = (
            self.get("taj_encashment_calculation_method")
            or FIXED_AMOUNT_PER_DAY
        )

        # Standard HRMS calculation
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

        monthly_salary = self.get_monthly_salary_for_encashment()

        daily_salary = (
            monthly_salary / MONTHLY_SALARY_DIVISOR
        )

        self.encashment_amount = flt(
            encashment_days * daily_salary,
            self.precision("encashment_amount"),
        )

    def get_monthly_salary_for_encashment(self):
        """
        Calculate the monthly salary used for Leave Encashment.

        The Salary Slip preview is used only as a calculation engine
        to evaluate the active Salary Structure Assignment.

        IMPORTANT:
        salary_slip.net_pay is intentionally NOT used.

        This avoids Loan Repayment or other payroll transactions
        reducing the salary basis used for Leave Encashment.

        Formula:

            Monthly Salary =
                Structured Earnings
                - Structured Deductions

        Additional Salary entries are excluded because they are not
        part of the employee's regular Salary Structure Assignment.

        No Salary Slip document is saved in the database.
        """

        if not self.employee:
            frappe.throw(
                _("Please select an Employee first.")
            )

        if not self.encashment_date:
            frappe.throw(
                _("Please set the Encashment Date first.")
            )

        # ---------------------------------------------------------
        # Get active Salary Structure for employee
        # on the Encashment Date
        # ---------------------------------------------------------
        if not getattr(self, "_salary_structure", None):
            self.set_salary_structure()

        if not self._salary_structure:
            frappe.throw(
                _(
                    "No active Salary Structure was found for "
                    "Employee {0} on Encashment Date {1}."
                ).format(
                    frappe.bold(self.employee),
                    frappe.bold(self.encashment_date),
                )
            )

        # ---------------------------------------------------------
        # Create temporary Salary Slip preview
        #
        # for_preview=1:
        # - calculates a full salary period
        # - does not save Salary Slip
        #
        # posting_date:
        # - ensures the Salary Structure Assignment applicable
        #   on Encashment Date is used
        # ---------------------------------------------------------
        salary_slip = make_salary_slip(
            source_name=self._salary_structure,
            employee=self.employee,
            posting_date=self.encashment_date,
            for_preview=1,
        )

        if not salary_slip:
            frappe.throw(
                _(
                    "Unable to calculate the monthly salary "
                    "for Employee {0}."
                ).format(
                    frappe.bold(self.employee)
                )
            )

        # ---------------------------------------------------------
        # Timesheet-based Salary Structures are not supported
        # ---------------------------------------------------------
        if salary_slip.get("salary_slip_based_on_timesheet"):
            frappe.throw(
                _(
                    "Based on Monthly Salary is not supported "
                    "for Salary Structures based on Timesheets."
                )
            )

        # ---------------------------------------------------------
        # Only Monthly Salary Structures are supported
        # ---------------------------------------------------------
        if salary_slip.get("payroll_frequency") != "Monthly":
            frappe.throw(
                _(
                    "The assigned Salary Structure must have "
                    "Monthly as its Payroll Frequency."
                )
            )

        # ---------------------------------------------------------
        # Calculate regular structured earnings
        #
        # Do NOT use Net Pay.
        # Do NOT use Loan Repayment.
        # Do NOT include Additional Salary.
        # ---------------------------------------------------------
        structured_earnings = self._get_structured_component_total(
            salary_slip.get("earnings")
        )

        structured_deductions = self._get_structured_component_total(
            salary_slip.get("deductions")
        )

        monthly_salary = flt(
            structured_earnings - structured_deductions,
            self.precision("encashment_amount"),
        )

        # ---------------------------------------------------------
        # Diagnostic values only.
        #
        # These values do NOT affect Leave Encashment calculation.
        # They are useful if the calculated salary is invalid.
        # ---------------------------------------------------------
        payroll_gross_pay = flt(
            salary_slip.get("gross_pay")
        )

        payroll_total_deduction = flt(
            salary_slip.get("total_deduction")
        )

        payroll_loan_repayment = flt(
            salary_slip.get("total_loan_repayment")
        )

        payroll_net_pay = flt(
            salary_slip.get("net_pay")
        )

        if monthly_salary <= 0:
            frappe.throw(
                _(
                    "The calculated monthly salary for Employee {0} "
                    "is zero or negative."
                    "<br><br>"
                    "<b>Leave Encashment Salary Calculation</b>"
                    "<br>"
                    "Structured Earnings: {1}"
                    "<br>"
                    "Structured Deductions: {2}"
                    "<br>"
                    "Monthly Salary Used: {3}"
                    "<br><br>"
                    "<b>Payroll Preview Information</b>"
                    "<br>"
                    "Gross Pay: {4}"
                    "<br>"
                    "Total Deduction: {5}"
                    "<br>"
                    "Loan Repayment: {6}"
                    "<br>"
                    "Payroll Net Pay: {7}"
                ).format(
                    frappe.bold(self.employee),
                    frappe.bold(structured_earnings),
                    frappe.bold(structured_deductions),
                    frappe.bold(monthly_salary),
                    frappe.bold(payroll_gross_pay),
                    frappe.bold(payroll_total_deduction),
                    frappe.bold(payroll_loan_repayment),
                    frappe.bold(payroll_net_pay),
                )
            )

        return monthly_salary

    @staticmethod
    def _get_structured_component_total(components):
        """
        Sum regular Salary Structure components.

        Excludes:
        - Components marked 'Do Not Include in Total'
        - Additional Salary rows

        Loan Repayment is not included because Loan Repayment
        is not considered a regular Salary Structure component.

        This method intentionally calculates from component rows
        instead of relying on Salary Slip total_deduction/net_pay.
        """

        total = 0.0

        for component in components or []:
            # Ignore components that should not affect salary total
            if component.get("do_not_include_in_total"):
                continue

            # Ignore Additional Salary transactions.
            #
            # Examples:
            # - Bonus
            # - One-time deduction
            # - Adjustment
            #
            # These are payroll transactions and are not part
            # of the regular Salary Structure Assignment.
            if component.get("additional_salary"):
                continue

            total += flt(
                component.get("amount")
            )

        return flt(total)

    # -------------------------------------------------------------
    # Backward-compatible helper
    #
    # Keep this method in case another part of the custom app
    # already calls get_monthly_net_salary().
    #
    # It now returns the Leave Encashment salary basis rather than
    # the actual Payroll Net Pay.
    # -------------------------------------------------------------
    def get_monthly_net_salary(self):
        return self.get_monthly_salary_for_encashment()