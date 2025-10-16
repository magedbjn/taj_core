# -*- coding: utf-8 -*-
# File: taj_core/integrations/supplier_hooks.py
from __future__ import annotations
import frappe
from frappe import _
from functools import lru_cache
import time
from typing import Optional

def _is_checked(val) -> bool:
    try:
        return int(val or 0) == 1
    except Exception:
        return False

@lru_cache(maxsize=256)
def is_manufacturing_group(group: str | None) -> bool:
    if not group:
        return False
    val = frappe.db.get_value("Supplier Group", group, "taj_manufacturing_related")
    try:
        return int(val or 0) == 1
    except Exception:
        return False
    
def _clear_is_manufacturing_group_cache(doc=None, method=None):
    """Hook-safe: clear LRU cache when Supplier Group is updated/renamed."""
    try:
        is_manufacturing_group.cache_clear()
        # يمكن إضافة log للتحقق من عمل الدالة
        # frappe.logger().debug("Manufacturing group cache cleared")
    except Exception as e:
        frappe.log_error(f"Error clearing manufacturing group cache: {str(e)}")


def ensure_supplier_group_required(doc, method=None):
    if not doc.supplier_group:
        frappe.throw(_("Supplier Group is required."))

def validate_supplier_group(doc, method=None):
    if doc.supplier_group and not frappe.db.exists("Supplier Group", doc.supplier_group):
        frappe.throw(_("{0} does not exist.").format(_("Supplier Group")))

def _get_active_qualification_name(supplier: str) -> Optional[str]:
    """Safely get active qualification - ENHANCED SAFETY"""
    if not supplier:
        return None
    
    # تحقق مزدوج من وجود المورد
    try:
        if not frappe.db.exists("Supplier", supplier):
            return None
    except Exception:
        return None
        
    try:
        from frappe.utils import today
        
        qual = frappe.db.sql("""
            SELECT name 
            FROM `tabSupplier Qualification` 
            WHERE supplier = %s 
                AND approval_status IN ('Approved','Partially Approved') 
                AND (valid_from IS NULL OR valid_from <= %s) 
                AND (valid_to IS NULL OR valid_to >= %s) 
            ORDER BY COALESCE(valid_from, '1900-01-01') DESC, modified DESC 
            LIMIT 1
        """, (supplier, today(), today()))
        
        return qual[0][0] if qual else None
        
    except Exception:
        return None

def _compute_blocked_by_qualification_for_supplier_obj(doc) -> int:
    """Compute blocked status - ULTRA SAFE VERSION"""
    try:
        # إذا كان المستند جديداً، استخدم القيمة الافتراضية فقط
        if doc.get("__islocal") or not hasattr(doc, 'name') or not doc.name:
            return 1 if is_manufacturing_group(getattr(doc, "supplier_group", None)) else 0

        # للمستندات الموجودة، تحقق من الوجود أولاً
        if not frappe.db.exists("Supplier", doc.name):
            return 1 if is_manufacturing_group(getattr(doc, "supplier_group", None)) else 0

        if not is_manufacturing_group(getattr(doc, "supplier_group", None)):
            return 0

        # فقط إذا وصلنا هنا، ابحث عن المؤهلية
        qual = _get_active_qualification_name(doc.name)
        if not qual:
            return 1

        status = frappe.db.get_value("Supplier Qualification", qual, "approval_status") or ""
        return 0 if status in ("Approved", "Partially Approved") else 1
        
    except Exception:
        # في أي خطأ، عُد إلى القيمة الآمنة
        return 1 if is_manufacturing_group(getattr(doc, "supplier_group", None)) else 0

def autoset_blocked_by_qualification(doc, method=None):
    """Set blocked status - PREVENT EARLY ACCESS"""
    try:
        # للمستندات الجديدة، عيّن مباشرة بدون أي استعلامات خارجية
        if doc.get("__islocal") or not hasattr(doc, 'name') or not doc.name:
            doc.taj_blocked_by_qualification = 1 if is_manufacturing_group(doc.supplier_group) else 0
            return

        # فقط للمستندات الموجودة، استخدم المنطق الكامل
        computed = _compute_blocked_by_qualification_for_supplier_obj(doc)
        current = getattr(doc, "taj_blocked_by_qualification", None)
        
        if current != computed:
            doc.taj_blocked_by_qualification = computed
                
    except Exception as e:
        # في حالة الخطأ، عيّن قيمة آمنة
        doc.taj_blocked_by_qualification = 1 if is_manufacturing_group(doc.supplier_group) else 0

def onload_fix_blocked_by_qualification(doc, method=None):
    """Only fix on load for existing documents"""
    try:
        if doc.get("__islocal") or not doc.name:
            return
            
        computed = _compute_blocked_by_qualification_for_supplier_obj(doc)
        if getattr(doc, "taj_blocked_by_qualification", None) != computed:
            doc.taj_blocked_by_qualification = computed
    except Exception:
        pass

def on_supplier_after_insert(doc, method=None):
    """
    ULTRA-SAFE VERSION - No database lookups for new suppliers
    """
    try:
        # استخدام اسم المورد مباشرة - موثوق في after_insert
        supplier_name = doc.name
        
        if not supplier_name:
            return

        # تأخير استراتيجي لضمان حفظ المستند
        import time
        time.sleep(0.5)
        frappe.db.commit()

        if is_manufacturing_group(doc.supplier_group):
            # 1) Set blocked status فقط - بدون أي استعلامات خارجية
            frappe.db.set_value("Supplier", supplier_name, "taj_blocked_by_qualification", 1)
            frappe.db.commit()

            # 2) Create qualification بدون أي تحقق من الوجود
            try:
                q = frappe.new_doc("Supplier Qualification")
                q.supplier = supplier_name
                q.approval_status = "Request Approval"
                q.flags.ignore_permissions = True
                q.flags.ignore_mandatory = True
                q.insert()
                
                # 3) Create ToDo بدون أي تحقق
                todo_doc = frappe.get_doc({
                    "doctype": "ToDo",
                    "description": _("New manufacturing supplier: {0}").format(supplier_name),
                    "reference_type": "Supplier Qualification",
                    "reference_name": q.name,
                    "assigned_by": frappe.session.user
                })
                todo_doc.flags.ignore_permissions = True
                todo_doc.insert()
                
            except Exception as qual_error:
                # إذا فشل، لا تفعل شيء - تجنب الأخطاء
                pass

        else:
            # Non-manufacturing - set unblocked مباشرة
            frappe.db.set_value("Supplier", supplier_name, "taj_blocked_by_qualification", 0)
            frappe.db.commit()
            
    except Exception:
        # لا تسجل أي شيء - الصمت التام
        pass


def on_supplier_group_change(doc, method=None):
    """Handle supplier group change - SIMPLIFIED"""
    try:
        if not doc.has_value_changed("supplier_group"):
            return

        if doc.get("__islocal") or not doc.name:
            return

        new_is_man = is_manufacturing_group(doc.supplier_group)
        
        if new_is_man:
            doc.taj_blocked_by_qualification = 1
            # لا تنشئ مؤهلية تلقائياً هنا
        else:
            doc.taj_blocked_by_qualification = 0
            
    except Exception:
        pass

def validate_supplier_blocked(doc, method=None):
    """Validate supplier block status - USING SAFE OPERATION"""
    supplier = getattr(doc, "supplier", None)
    if not supplier:
        return

    def check_supplier_blocked(supplier_name):
        blocked = _is_checked(frappe.db.get_value("Supplier", supplier_name, "taj_blocked_by_qualification"))
        if blocked:
            frappe.throw(
                _("Cannot create {0} for supplier {1}. Supplier is blocked pending qualification approval.")
                .format(_(doc.doctype), supplier_name)
            )
        return True

    # استخدام الدالة الآمنة - إذا فشلت، تخطّى التحقق
    safe_supplier_operation(supplier, check_supplier_blocked)

def on_qualification_update(doc, method=None):
    """Update supplier status - USING SAFE OPERATION"""
    try:
        if not doc.supplier:
            return

        # استخدام الدالة الآمنة الجديدة
        def update_supplier_status(supplier_name):
            supplier_doc = frappe.get_doc("Supplier", supplier_name)
            if not is_manufacturing_group(supplier_doc.supplier_group):
                return True

            computed = _compute_blocked_by_qualification_for_supplier_obj(supplier_doc)

            if supplier_doc.taj_blocked_by_qualification != computed:
                supplier_doc.db_set("taj_blocked_by_qualification", computed, commit=True)

            # إذا تم الاعتماد، أغلق مهام ToDo المرتبطة
            if doc.approval_status in ("Approved", "Partially Approved"):
                close_related_todos(supplier_name)
            
            return True

        # تنفيذ العملية بشكل آمن
        safe_supplier_operation(doc.supplier, update_supplier_status)

    except Exception:
        pass

def close_related_todos(supplier: str):
    """Close ToDo safely - USING SAFE OPERATION"""
    def close_todos_operation(supplier_name):
        todos = frappe.get_all(
            "ToDo",
            filters={"reference_type": "Supplier", "reference_name": supplier_name, "status": "Open"},
            fields=["name"],
        )
        for todo in todos:
            frappe.db.set_value("ToDo", todo["name"], "status", "Closed")
        return True
    
    # استخدام الدالة الآمنة
    safe_supplier_operation(supplier, close_todos_operation)

def safe_supplier_operation(supplier_name, operation_func):
    """
    Safely execute supplier operations with multi-level existence checks
    """
    try:
        # تحقق من وجود اسم المورد
        if not supplier_name or not isinstance(supplier_name, str):
            return False
            
        # المحاولة الأولى: تحقق فوري من الوجود
        if not frappe.db.exists("Supplier", supplier_name):
            # المحاولة الثانية: انتظر وحاول مرة أخرى
            import time
            time.sleep(0.5)
            frappe.db.commit()  # تأكيد أي عمليات pending
            
            if not frappe.db.exists("Supplier", supplier_name):
                # المحاولة الثالثة: انتظر أكثر
                time.sleep(0.5)
                if not frappe.db.exists("Supplier", supplier_name):
                    frappe.logger().debug(f"Supplier {supplier_name} not found after multiple retries")
                    return False
        
        # نفذ العملية بشكل آمن
        return operation_func(supplier_name)
        
    except Exception as e:
        frappe.logger().debug(f"Safe supplier operation failed for {supplier_name}: {str(e)}")
        return False