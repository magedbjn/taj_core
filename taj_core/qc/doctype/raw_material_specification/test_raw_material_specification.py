# Copyright (c) 2024, MAged BAjandooh and Contributors
# See license.txt

# import frappe
from frappe.tests.utils import FrappeTestCase


class TestRawMaterialSpecification(FrappeTestCase):
	def on_submit(self):
		if self.status in ["Open", "Cancelled"]:
			frappe.throw(_("Only Raw MAterial Specification with status 'Approved' and 'Rejected' can be submitted"))
