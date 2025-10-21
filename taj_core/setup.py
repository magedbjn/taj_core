# setup.py
import click
import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields



def after_install():
    """للتثبيت الأولي"""
    create_all_custom_fields()
    click.secho("✅ Taj Core custom fields created successfully", fg="green")


def after_migrate():
    """للتأكد من وجود الحقول بعد كل تحديث"""
    create_all_custom_fields()
    click.secho("✅ Taj Core custom fields verified after migration", fg="green")


def before_uninstall():
    KEEP_FIELDS = {
        "Employee": ["taj_nationality"],
        "Item": ["taj_sub_warehouse"],
    }
    delete_custom_fields(get_all_custom_fields(), keep=KEEP_FIELDS)


def create_all_custom_fields():
    """ينشئ كل الحقول مع التحقق من الوجود أولاً"""
    core_fields = get_core_fields()
    hrms_fields = get_hrms_fields() if "hrms" in frappe.get_installed_apps() else {}
    
    # دمج كل الحقول
    all_fields = merge_field_dicts(core_fields, hrms_fields)
    
    # إنشاء الحقول مع التحقق
    create_custom_fields_safely(all_fields)


def create_custom_fields_safely(custom_fields: dict):
    """ينشئ الحقول فقط إذا لم تكن موجودة مسبقاً"""
    for doctype, fields in custom_fields.items():
        existing_fields = frappe.get_all("Custom Field", 
            filters={"dt": doctype}, 
            pluck="fieldname"
        )
        
        fields_to_create = [
            field for field in fields 
            if field.get("fieldname") not in existing_fields
        ]
        
        if fields_to_create:
            create_custom_fields({doctype: fields_to_create}, ignore_validate=True)
            frappe.db.commit()
            click.secho(f"✅ Created {len(fields_to_create)} fields in {doctype}", fg="green")


def merge_field_dicts(dict1: dict, dict2: dict) -> dict:
    """يدمج قاموسين للحقول"""
    result = dict1.copy()
    for doctype, fields in dict2.items():
        if doctype in result:
            result[doctype].extend(fields)
        else:
            result[doctype] = fields
    return result


def get_all_custom_fields() -> dict:
    """يرجع كل الحقول المخصصة (للاستخدام في الإزالة)"""
    core_fields = get_core_fields()
    hrms_fields = get_hrms_fields()
    return merge_field_dicts(core_fields, hrms_fields)


def get_core_fields():
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
                    "If enabled, the system will skip the validation 'Due Date cannot be before Posting / Supplier Invoice Date'."
                ),
                "insert_after": "disabled",
            },
        ],
    }


def get_hrms_fields():
    return {
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


def delete_custom_fields(custom_fields: dict, keep: dict | None = None):
    """
    يحذف الحقول المعرفة في custom_fields مع السماح باستثناء حقول محددة.
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

        # تحسين: التحقق من وجود الحقول قبل الحذف
        existing_fields = frappe.get_all(
            "Custom Field",
            filters={"fieldname": ("in", names_to_delete), "dt": doctype},
            pluck="name"
        )
        
        if existing_fields:
            frappe.db.delete("Custom Field", {"name": ("in", existing_fields)})
            frappe.clear_cache(doctype=doctype)
            click.secho(f"🗑️ Deleted {len(existing_fields)} fields from {doctype}", fg="yellow")