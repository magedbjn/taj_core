#ERPNext: v15.94.1
import frappe
from frappe import _
from erpnext.selling.doctype.party_specific_item.party_specific_item import PartySpecificItem


class TajPartySpecificItem(PartySpecificItem):
	def validate(self):
		exists = frappe.db.exists(
			"Party Specific Item",
			{
				"party_type": self.party_type,
				"party": self.party,
				"restrict_based_on": self.restrict_based_on,
				"based_on_value": self.based_on_value,
			},
		)

		if exists and exists != self.name:
			frappe.throw(_("This item filter has already been applied for the {0}").format(self.party_type))