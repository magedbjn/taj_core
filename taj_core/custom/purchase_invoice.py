# لتجاهل الرسالة التي تظهر عند الحفظ إذا كان تاريخ المستند أصغر من تاريخ الفاتورة
# Due Date cannot be fore Posting / Supplier Invoice Date
import frappe
def before_validate(doc, method):
    """Clear bill_date temporarily to bypass system validation"""
    ignore = frappe.db.get_value("Supplier", doc.supplier, "taj_ignore_due_date_validation")
    if ignore:
        doc.bill_date_temp = doc.bill_date
        doc.bill_date = ''


def before_save(doc, method):
    """Restore bill_date after validation"""
    ignore = frappe.db.get_value("Supplier", doc.supplier, "taj_ignore_due_date_validation")
    if ignore:
        doc.bill_date = doc.bill_date_temp
