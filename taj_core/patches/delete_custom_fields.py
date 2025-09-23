import frappe
from frappe import _
import re

# -------------------------
# الدالة الرئيسية
# -------------------------
def execute():
    """
    حذف الحقول المحددة من DocTypes وجداول قاعدة البيانات
    """
    fields_to_delete = {
        "Employee": ["emp_natio", "custom_social_insurance", "custom_social_insurance_no"],
        "BOM": [
            "custom_packing_weight", "custom_liquid_filling", "custom_solid_filling_1",
            "custom_solid_filling_2", "custom_total_weight", "custom_item_name_arabic",
            "custom_qc", "custom_sb1", "custom_salt", "custom_brix", "custom_ph",
            "custom_column_break_8aeau", "custom_viscosity", "custom_spindel_type",
            "custom_rpm", "custom_temperature", "custom_note", "custom_note_qc"
        ],
    }

    for doctype, fields in fields_to_delete.items():
        delete_fields_bulk(doctype, fields)

    frappe.db.commit()

    final_msg = _("🎉 All specified fields processed successfully in bulk mode!")
    log_console(final_msg, "success")
    frappe.msgprint(final_msg)


# -------------------------
# إعداد الألوان للـ Console
# -------------------------
COLORS = {
    "success": "\033[92m",  # أخضر
    "warning": "\033[93m",  # أصفر
    "error": "\033[91m",    # أحمر
    "info": "\033[94m",     # أزرق
    "reset": "\033[0m"      # إعادة الضبط
}

COLUMN_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")  # للتحقق من أسماء الأعمدة

# -------------------------
# دوال مساعدة
# -------------------------
def log_console(message, level="info"):
    """طباعة رسائل ملونة للـ Console"""
    color = COLORS.get(level, COLORS["info"])
    print(f"{color}{message}{COLORS['reset']}")


def get_existing_columns(doctype):
    """الحصول على الأعمدة الموجودة في جدول DocType"""
    if not frappe.db.exists("DocType", doctype):
        return set()
    
    table_name = f"tab{doctype}"
    try:
        return {col[0] for col in frappe.db.sql(f"SHOW COLUMNS FROM `{table_name}`")}
    except Exception as e:
        log_console(f"⚠️ Error getting columns for {doctype}: {e}", "warning")
        return set()


def drop_columns_safe(doctype, columns):
    """حذف أعمدة من جدول DocType بأمان"""
    if not columns:
        return

    # تحقق من أسماء الأعمدة
    invalid = [c for c in columns if not COLUMN_NAME_RE.match(c)]
    if invalid:
        raise ValueError(f"Invalid column name(s): {invalid}")

    # تحقق من الأعمدة الموجودة فعلياً
    existing_columns = get_existing_columns(doctype)
    to_drop = [c for c in columns if c in existing_columns]

    if not to_drop:
        log_console(f"⚠️ No matching columns to drop in {doctype}: {columns}", "warning")
        return

    try:
        frappe.db.commit()  # لتجنب مشاكل القفل قبل ALTER
        columns_str = ", ".join([f"DROP COLUMN `{c}`" for c in to_drop])
        sql = f"ALTER TABLE `tab{doctype}` {columns_str}"
        frappe.db.sql_ddl(sql)
        frappe.db.commit()
        log_console(f"✅ Dropped columns from {doctype}: {to_drop}", "success")
    except Exception as e:
        frappe.log_error(f"Error dropping columns {to_drop} from {doctype}: {e}", "Migration Error")
        log_console(f"❌ Error dropping columns {to_drop} from {doctype}: {e}", "error")
        raise


def delete_fields_bulk(doctype, fields):
    """حذف الحقول بشكل جماعي من DocField, DB, Property Setter, Custom Field"""
    log_console(f"🔹 Processing Doctype: {doctype}", "info")

    if not frappe.db.exists("DocType", doctype):
        log_console(f"❌ DocType {doctype} does not exist. Skipping.", "error")
        return

    try:
        # --- حذف من DocField ---
        frappe.db.delete("DocField", {"parent": doctype, "fieldname": ["in", fields]})
        log_console(f"✅ Deleted fields from DocField in {doctype}: {fields}", "success")

        # --- حذف من قاعدة البيانات ---
        drop_columns_safe(doctype, fields)

        # --- حذف دقيق للـ Property Setter ---
        frappe.db.sql("""
            DELETE FROM `tabProperty Setter`
            WHERE doc_type = %s AND field_name IN %s
        """, (doctype, tuple(fields)))
        log_console(f"✅ Deleted related Property Setters for {doctype} (precise)", "success")

        # --- حذف Custom Field ---
        frappe.db.delete("Custom Field", {"dt": doctype, "fieldname": ["in", fields]})
        log_console(f"✅ Deleted Custom Fields for {doctype}", "success")

        # --- إعادة تحميل الكاش وحفظ DocType بأمان ---
        try:
            doc = frappe.get_doc("DocType", doctype)
            doc.save(ignore_permissions=True)
            log_console(f"✅ Saved DocType {doctype} successfully", "success")
        except Exception as e:
            log_console(f"⚠️ Could not save {doctype}: {e}", "warning")
            frappe.clear_cache(doctype=doctype)

    except Exception as e:
        frappe.log_error(f"Error processing {doctype}: {e}", "Migration Error")
        log_console(f"❌ Error processing {doctype}: {e}", "error")
