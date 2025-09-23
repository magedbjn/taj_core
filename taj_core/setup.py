# setup.py

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
# from frappe.desk.page.setup_wizard.install_fixtures import (
# 	_,  # NOTE: this is not the real translation function
# )
# from frappe.desk.page.setup_wizard.setup_wizard import make_records
# from frappe.installer import update_site_config


def after_install():
	create_taj_hrms_fields()

def before_uninstall():
	delete_custom_fields(get_taj_hrms_fields())

def create_taj_hrms_fields():
	if "hrms" in frappe.get_installed_apps():
		create_custom_fields(get_taj_hrms_fields(), ignore_validate=True)

def get_taj_hrms_fields():
	return {
		"Payroll Settings": [
			{
				"fieldname": "taj_salary_days_basis",
				"fieldtype": "Select",
				"label": _("Salary Days Calculation"),
				"options": "Actual Month Days\nFixed 30 Days",
				"default": "Fixed 30 Days",
				"description": _("Choose whether salary is calculated based on actual month days (28-31) or fixed 30 days."),
				"insert_after": "payroll_based_on"
			},
		],
		"Supplier": [
			{
				"fieldname": "taj_ignore_due_date_validation",
				"fieldtype": "Check",
				"label": _("Ignore due date validation"),
				"description": _("If enabled, the system will skip the validation “Due Date cannot be before Posting / Supplier Invoice Date” for this supplier."),
				"insert_after": "disabled"
			}
		],
		"Employee": [
			{
				"fieldname": "taj_nationality",
				"fieldtype": "Link",
				"label": _("Nationality"),
				"options": "Country",
				"insert_after": "date_of_joining"
			},
		],
		"Production Plan": [
			{
				"fieldname": "taj_label",
				"label": _("Taj Label"),
				"fieldtype": "Tab Break",
				"insert_after":"amended_from"
			},
			{
				"fieldname": "production_label_detail",
				"fieldtype": "Table",
				"label": _("Production Label Detail"),
				"options": "Production Label Detail",
				"read_only": 1,
				"insert_after":"taj_label"
			},
		],
	}

def delete_custom_fields(custom_fields: dict):
	"""
	:param custom_fields: a dict like `{'Leave Application': [{fieldname: 'Travels', ...}]}`
	"""
	for doctype, fields in custom_fields.items():
		frappe.db.delete(
			"Custom Field",
			{
				"fieldname": ("in", [field["fieldname"] for field in fields]),
				"dt": doctype,
			},
		)

		frappe.clear_cache(doctype=doctype)
