# Copyright (c) 2026, Maged Bajandooh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ProductionChecklistTemplate(Document):
	pass

def get_template_details(template):
	if not template:
		return []

	return frappe.get_all(
		"Production Checklist Parameter Item",
		fields=[
			"paramteter",
			"numeric",
			"min_value",
			"max_value",
		],
		filters={"parenttype": "Production Checklist Template", "parent": template},
		order_by="idx",
	)