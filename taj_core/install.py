#install.py
import click

from taj_core.setup import after_install as setup
from taj_core.qc.doctype.visitor.visitor import create_new_visitor_notification

def after_install():
	try:
		print("Setting up Tajff...")

		setup()

		# إنشاء Notification "New Visitor"
		create_new_visitor_notification()
	
		click.secho("Thank you for installing Taj Food Factory for Ready Meals!", fg="green")

	except Exception as e:
		BUG_REPORT_URL = "https://github.com/frappe/hrms/issues/new"
		click.secho(
			"Installation for Tajff app failed due to an error."
			" Please try re-installing the app or"
			f" report the issue on {BUG_REPORT_URL} if not resolved.",
			fg="bright_red",
		)
		raise e

# import frappe
# from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# LOAN_CUSTOM_FIELDS = {
# 	"Leave Application": [
# 		{
# 			"fieldname": "custom_overlapping_days_compensated",
# 			"label": "Overlapping Days Compensated with Public Holidays",
# 			"fieldtype": "Int",
# 			"insert_after": "to_date",
# 			"read_only": 1,
# 			"depends_on": "eval:doc.custom_overlapping_days_compensated!=0",
# 		},
# 		{
# 			"fieldname": "custom_travel",
# 			"label": "Travel",
# 			"fieldtype": "Tab Break",
# 			"insert_after": "amended_from",
# 		},
# 		{
# 			"fieldname": "custom_travel_ticket",
# 			"label": "Travel Ticket",
# 			"fieldtype": "Check",
# 			"default": 0,
# 			"insert_after": "custom_travel",
# 		},
# 		{
# 			"fieldname": "custom_last_travel_ticket",
# 			"label": "Last Travel Ticket",
# 			"fieldtype": "Read Only",
# 			"insert_after": "custom_travel_ticket",
# 		},
# 		{
# 			"fieldname": "custom_status_travel_ticket",
# 			"label": "Status Travel Ticket",
# 			"fieldtype": "Select",
# 			"insert_after": "custom_travel_ticket",
# 			"options": "\nCovered by company\nReimbursable Expense\nNon-Reimbursable Expense",
# 			"read_only_depends_on": "eval:doc.custom_travel_ticket==0",
# 		},
# 		{
# 			"fieldname": "custom_column_break_mhfpk",
# 			"label": "",
# 			"fieldtype": "Column Break",
# 			"insert_after": "custom_status_travel_ticket",
# 		},
# 		{
# 			"fieldname": "custom_return_visa",
# 			"label": "Return Visa",
# 			"fieldtype": "Check",
# 			"default": 0,
# 			"insert_after": "custom_column_break_mhfpk",
# 		},
# 		{
# 			"fieldname": "custom_last_return_visa",
# 			"label": "Last Return Visa",
# 			"fieldtype": "Read Only",
# 			"insert_after": "custom_return_visa",
# 		},
# 		{
# 			"fieldname": "custom_last_return_visa",
# 			"label": "Status Return Visa",
# 			"fieldtype": "Select",
# 			"insert_after": "custom_return_visa",
# 			"options": "\nCovered by company\nReimbursable Expense\nNon-Reimbursable Expense",
# 			"read_only_depends_on": "eval:doc.custom_return_visa==0",
# 		}
# 	]
# }

# def get_post_install_patches():
# 	return (
# 		"rename_loan_type_to_loan_product",
# 		"generate_loan_repayment_schedule",
# 		"update_loan_types",
# 		"make_loan_type_non_submittable",
# 		"migrate_loan_type_to_loan_product",
# 		"add_loan_product_code_and_rename_loan_name",
# 		"update_penalty_interest_method_in_loan_products",
# 	)


# def after_install():
# 	create_custom_fields(LOAN_CUSTOM_FIELDS, ignore_validate=True)

# def before_uninstall():
# 	delete_custom_fields(LOAN_CUSTOM_FIELDS)

# def delete_custom_fields(custom_fields):
# 	"""
# 	:param custom_fields: a dict like `{'Customer': [{fieldname: 'test', ...}]}`
# 	"""

# 	for doctypes, fields in custom_fields.items():
# 		if isinstance(fields, dict):
# 			# only one field
# 			fields = [fields]

# 		if isinstance(doctypes, str):
# 			# only one doctype
# 			doctypes = (doctypes,)

# 		for doctype in doctypes:
# 			frappe.db.delete(
# 				"Custom Field",
# 				{
# 					"fieldname": ("in", [field["fieldname"] for field in fields]),
# 					"dt": doctype,
# 				},
# 			)

# 			frappe.clear_cache(doctype=doctype)
