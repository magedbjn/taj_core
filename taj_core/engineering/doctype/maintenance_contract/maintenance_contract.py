import frappe
from frappe.model.document import Document
from frappe import _

class MaintenanceContract(Document):
    def validate(self):
        # اقفال التعديل إذا السجل مسبقاً Completed
        self._enforce_lock_if_completed()

        self.validate_dates()
        self.validate_visits()
        self.update_status()

    def _enforce_lock_if_completed(self):
        """امنع أي تعديل على السجل إذا كانت حالته في قاعدة البيانات Completed."""
        # إذا السجل موجود (ليس جديد) و حالته في الـ DB = Completed -> امنع الحفظ
        if self.name and frappe.db.exists(self.doctype, self.name):
            current_status_in_db = frappe.db.get_value(self.doctype, self.name, "contract_status")
            if current_status_in_db == "Completed":
                frappe.throw(_("This Maintenance Contract is Completed and cannot be modified."))

    def validate_visits(self):
        total_visits_allowed = self.total_visits or 0
        visits_count = len(self.maintenance_visit or [])

        if visits_count > total_visits_allowed:
            frappe.throw(_("Number of Maintenance Visits cannot exceed Total Visits"))

    def validate_dates(self):
        # start_date <= end_date
        if self.start_date and self.end_date and self.start_date > self.end_date:
            frappe.throw(_("Start Date cannot be after End Date"))

        # تحقق أن كل زيارة ضمن فترة العقد
        for visit in (self.maintenance_visit or []):
            if visit.visit_date:
                if self.start_date and visit.visit_date < self.start_date:
                    frappe.throw(_("Visit Date cannot be before Contract Start Date"))
                if self.end_date and visit.visit_date > self.end_date:
                    frappe.throw(_("Visit Date cannot be after Contract End Date"))

    def update_status(self):
        total_visits_allowed = self.total_visits or 0
        visits_done = sum(1 for v in (self.maintenance_visit or []) if getattr(v, "done", 0) == 1)

        if visits_done == 0:
            self.contract_status = "Draft"
        elif visits_done >= total_visits_allowed and total_visits_allowed > 0:
            self.contract_status = "Completed"
        else:
            self.contract_status = "Active"

    # (اختياري) منع الحذف أيضاً إذا كانت Completed
    def on_trash(self):
        if self.contract_status == "Completed":
            frappe.throw(_("Completed Maintenance Contracts cannot be deleted."))
