import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, nowdate

from taj_core.checklist.rules import calculate_schedule_due_date, normalize_schedule_weeks


RECURRENCE_FIELDS = (
    "schedule_type",
    "interval",
    "day_of_week",
    "week_1",
    "week_2",
    "week_3",
    "week_4",
    "week_5",
    "day_of_month",
    "month_of_year",
    "start_date",
    "is_active",
)


class ChecklistSchedule(Document):
    def validate(self):
        self._set_compatibility_defaults()
        self._validate_company_scope()
        self._validate_assignment()
        self._validate_recurrence()
        self._validate_time_control()
        self._set_next_due_date_if_needed()

    def _set_compatibility_defaults(self):
        if self.template and not self.department:
            self.department = frappe.db.get_value("Checklist Question Template", self.template, "department")

        if self.department and not self.company:
            self.company = frappe.db.get_value("Department", self.department, "company")

        if not self.assignment_type:
            self.assignment_type = "Any User in Department"

        if not self.cycle_behavior:
            self.cycle_behavior = "Fresh Every Cycle"

    def _validate_company_scope(self):
        if not self.department:
            return

        department_company = frappe.db.get_value("Department", self.department, "company")
        if self.company and department_company and department_company != self.company:
            frappe.throw(
                _("Department {0} does not belong to Company {1}.").format(self.department, self.company)
            )
        if not self.company and department_company:
            self.company = department_company

        for fieldname, doctype in (
            ("plant_floor", "Plant Floor"),
            ("warehouse", "Warehouse"),
            ("asset", "Asset"),
        ):
            value = getattr(self, fieldname, None)
            if not value or not self.company:
                continue
            if not frappe.get_meta(doctype).has_field("company"):
                continue
            linked_company = frappe.db.get_value(doctype, value, "company")
            if linked_company and linked_company != self.company:
                frappe.throw(
                    _("{0} {1} does not belong to Company {2}.").format(doctype, value, self.company)
                )

    def _validate_assignment(self):
        if not self.department:
            frappe.throw(_("Department is required."))

        if self.assignment_type == "Specific User" and not self.assigned_user:
            frappe.throw(_("Assigned User is required when Assignment Type is Specific User."))

    def _validate_recurrence(self):
        schedule_type = (self.schedule_type or "Manual").strip()
        if schedule_type == "Manual":
            self.next_due_date = None
            return

        if not self.start_date:
            frappe.throw(_("Start Date is required for an automatic schedule."))

        if schedule_type in ("Daily", "Weekly", "Monthly") and cint(self.interval) < 1:
            frappe.throw(_("Every must be at least 1."))

        if schedule_type in ("Weekly", "Weeks of Month") and not self.day_of_week:
            frappe.throw(_("Day of Week is required for this schedule type."))

        if schedule_type == "Weeks of Month":
            if not normalize_schedule_weeks(self):
                frappe.throw(_("Select at least one week of month."))

        if schedule_type in ("Monthly", "Quarterly", "Yearly"):
            day = cint(self.day_of_month)
            if day < 1 or day > 31:
                frappe.throw(_("Day of Month must be between 1 and 31."))

        if schedule_type == "Yearly":
            month = cint(self.month_of_year)
            if month < 1 or month > 12:
                frappe.throw(_("Month must be between 1 and 12."))

    def _validate_time_control(self):
        if cint(self.enable_time_control):
            if not self.schedule_time:
                frappe.throw(_("Schedule Time is required when Time Control is enabled."))
            if cint(self.completion_window_minutes) < 1:
                frappe.throw(_("Completion Window Minutes is required when Time Control is enabled."))

        if cint(self.notify_on_overdue) and not cint(self.enable_time_control):
            frappe.throw(_("Time Control must be enabled when overdue notification is enabled."))

        escalation_minutes = cint(self.escalate_after_minutes)
        if escalation_minutes and not cint(self.notify_on_overdue):
            frappe.throw(_("Overdue notification must be enabled before escalation can be configured."))
        if self.escalation_user and not escalation_minutes:
            frappe.throw(_("Escalate After Minutes is required when an Escalation User is configured."))

        if cint(self.required_before_production) and self.cycle_behavior != "Fresh Every Cycle":
            frappe.throw(_("A checklist required before production must use Fresh Every Cycle behavior."))

    def _set_next_due_date_if_needed(self):
        if (self.schedule_type or "Manual") == "Manual":
            self.next_due_date = None
            return

        config_changed = self.is_new() or any(self.has_value_changed(field) for field in RECURRENCE_FIELDS)
        if not config_changed and self.next_due_date:
            return

        start = getdate(self.start_date)
        today = getdate(nowdate())
        anchor = max(start, today)
        self.next_due_date = calculate_schedule_due_date(self, reference_date=anchor, initial=True)

@frappe.whitelist()
def create_checklist(schedule_name):
    schedule = frappe.get_doc("Checklist Schedule", schedule_name)
    schedule.check_permission("read")
    if schedule.schedule_type != "Manual":
        frappe.throw(_("Use automatic scheduling for this schedule. Manual creation is available only for Manual schedules."))

    from taj_core.checklist.doctype.checklist_answer.checklist_answer import create_checklist_answer_from_schedule

    checklist = create_checklist_answer_from_schedule(schedule.name)
    return {
        "name": checklist.name,
        "reused_existing": bool(getattr(checklist.flags, "reused_existing", False)),
        "reuse_reason": getattr(checklist.flags, "reuse_reason", None),
    }
