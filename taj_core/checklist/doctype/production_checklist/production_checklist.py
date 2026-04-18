# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from taj_core.checklist.doctype.production_checklist_template.production_checklist_template import (
	get_template_details,
)

class ProductionChecklist(Document):
	pass

	@frappe.whitelist()
	def get_item_specification_details(self):
		if not self.quality_inspection_template:
			self.quality_inspection_template = frappe.db.get_value(
				"Item", self.item_code, "quality_inspection_template"
			)

		if not self.quality_inspection_template:
			return

		self.set("readings", [])
		parameters = get_template_details(self.quality_inspection_template)
		for d in parameters:
			child = self.append("readings", {})
			child.update(d)
			child.status = "Accepted"
			child.parameter_group = frappe.get_value(
				"Production Checklist Parameter", d.specification, "parameter_group"
			)