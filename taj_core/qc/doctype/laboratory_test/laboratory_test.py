import frappe
from frappe import _
from frappe.model.document import Document


class LaboratoryTest(Document):
	def validate(self):
		if self.batch_no_link and self.item:
			batch_item = frappe.db.get_value("Batch", self.batch_no_link, "item")
			if batch_item and batch_item != self.item:
				frappe.throw(_("Selected Batch does not belong to the selected Item."))