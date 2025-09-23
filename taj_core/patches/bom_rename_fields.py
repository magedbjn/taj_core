import frappe
from frappe.model.utils.rename_field import rename_field

def execute():
	try:
		rename_field("BOM", "custom_qc", "taj_qc")

	except Exception as e:
		if e.args[0] != 1054:
			raise