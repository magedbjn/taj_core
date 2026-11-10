import frappe
from frappe import _
from frappe.model.document import Document
class MockRecallDistribution(Document):
    def validate(self):
        frappe.throw(_("Evidence rows can only be saved through the parent Mock Recall actions."))

    def on_trash(self):
        frappe.throw(_("Evidence rows cannot be deleted independently of their Mock Recall."))
