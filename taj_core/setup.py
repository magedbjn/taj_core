# setup.py

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
    """
    يُنشئ الحقول الأساسية دائمًا (Core)،
    ويُنشئ حقول HRMS فقط في حال كان تطبيق HRMS مثبتًا.
    """
    create_core_fields()

    if "hrms" in frappe.get_installed_apps():
        create_hrms_fields()


def before_uninstall():
    """
    يحذف الحقول التي أُنشئت بواسطة التطبيق، مع استثناء الحقول المحمية.
    """
    KEEP_FIELDS = {
        # لا نحذف هذين الحقلين عند إزالة التطبيق:
        "Employee": ["taj_nationality"],
        "Item": ["taj_sub_warehouse"],
    }

    # حذف حقول Core (مع الاستثناءات)
    delete_custom_fields(get_core_fields(), keep=KEEP_FIELDS)

    # حذف حقول HRMS فقط إن كانت مثبتة (مع الاستثناءات)
    if "hrms" in frappe.get_installed_apps():
        delete_custom_fields(get_hrms_fields(), keep=KEEP_FIELDS)


# -------------------------------
# إنشاء الحقول
# -------------------------------

def create_core_fields():
    create_custom_fields(get_core_fields(), ignore_validate=True)


def create_hrms_fields():
    create_custom_fields(get_hrms_fields(), ignore_validate=True)


def get_core_fields():
    """
    حقول عامة (ERPNext Core) تُنشأ دائمًا.
    """
    return {
        "Item": [
            {
                "fieldname": "taj_sub_warehouse",
                "fieldtype": "Select",
                "label": _("Sub Warehouse"),
                "options": "\nDry\nChiller\nFreezer",
                "insert_after": "item_group",
            },
        ],
        "Supplier": [
            {
                "fieldname": "taj_ignore_due_date_validation",
                "fieldtype": "Check",
                "label": _("Ignore due date validation"),
                "description": _(
                    "If enabled, the system will skip the validation “Due Date cannot be before Posting / Supplier Invoice Date”."
                ),
                "insert_after": "disabled",
            },
            {
                "fieldname": "taj_blocked_by_qualification",
                "fieldtype": "Check",
                "label": _("Blocked By Qualification"),
                "description": _(
                    "Supplier requires qualification approval before purchasing"
                ),
                "read_only": 1,
                "insert_after": "taj_ignore_due_date_validation",
            },
        ],
        "Supplier Group": [
            {
                "fieldname": "taj_manufacturing_related",
                "fieldtype": "Check",
                "label": _("Manufacturing Related"),
                "description": _(
                    "Mark this group as manufacturing-related to enforce quality approval for its suppliers."
                ),
            },
        ],
    }


def get_hrms_fields():
    """
    حقول تتطلب HRMS (لن تُنشأ أو تُحذف إلا إذا كان HRMS مُثبتًا).
    """
    return {
        "Payroll Settings": [
            {
                "fieldname": "taj_salary_days_basis",
                "fieldtype": "Select",
                "label": _("Salary Days Calculation"),
                "options": "Actual Month Days\nFixed 30 Days",
                "default": "Fixed 30 Days",
                "description": _(
                    "Choose whether salary is calculated based on actual month days (28-31) or fixed 30 days."
                ),
                "insert_after": "payroll_based_on",
            },
        ],
        "Employee": [
            {
                "fieldname": "taj_nationality",
                "fieldtype": "Link",
                "label": _("Nationality"),
                "options": "Country",
                "insert_after": "date_of_joining",
            },
        ],
    }


# -------------------------------
# حذف الحقول (مع استثناءات)
# -------------------------------

def delete_custom_fields(custom_fields: dict, keep: dict | None = None):
    """
    يحذف الحقول المعرفة في custom_fields مع السماح باستثناء حقول محددة.

    :param custom_fields: dict مثل {'Doctype': [{'fieldname': 'x', ...}, ...], ...}
    :param keep: dict مثل {'Doctype': ['fieldname1', 'fieldname2', ...]}
                 أي حقل ضمن keep لن يُحذف حتى لو كان ضمن custom_fields.
    """
    keep = keep or {}
    for doctype, fields in custom_fields.items():
        keep_set = set(keep.get(doctype, []))
        names_to_delete = [
            field.get("fieldname")
            for field in fields
            if field.get("fieldname") and field.get("fieldname") not in keep_set
        ]

        if not names_to_delete:
            continue

        frappe.db.delete(
            "Custom Field",
            {"fieldname": ("in", names_to_delete), "dt": doctype},
        )
        frappe.clear_cache(doctype=doctype)
