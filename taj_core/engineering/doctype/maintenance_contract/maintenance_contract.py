import frappe
from frappe.model.document import Document
from frappe import _

class MaintenanceContract(Document):
    def validate(self):
        self.validate_dates()
        self.validate_visits()
        self.update_status()

    def validate_visits(self):
        total_visits_allowed = self.total_visits or 0
        visits_count = len(self.maintenance_visit)

        if visits_count > total_visits_allowed:
            frappe.throw(_("Number of Maintenance Visits cannot exceed Total Visits"))
            
    def validate_dates(self):
        # start_date <= end_date
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                frappe.throw(_("Start Date cannot be after End Date"))

        # تحقق من أن كل زيارة ضمن فترة العقد
        for visit in self.maintenance_visit:
            if visit.visit_date:
                if self.start_date and visit.visit_date < self.start_date:
                    frappe.throw(_("Visit Date cannot be before Contract Start Date"))
                if self.end_date and visit.visit_date > self.end_date:
                    frappe.throw(_("Visit Date cannot be after Contract End Date"))

    def update_status(self):
        total_visits_allowed = self.total_visits or 0
        visits_count = sum(1 for visit in self.maintenance_visit if visit.visit_date)

        if visits_count == 0:
            self.contract_status = "Draft"
        elif visits_count >= total_visits_allowed:
            self.contract_status = "Completed"
        else:
            self.contract_status = "Active"
