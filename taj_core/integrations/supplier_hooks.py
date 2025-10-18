# -*- coding: utf-8 -*-
# File: taj_core/integrations/supplier_hooks.py
from __future__ import annotations
import frappe
from frappe import _
from functools import lru_cache
import time
from typing import Optional

@lru_cache(maxsize=256)
def is_qualified_supplier_group(group: str | None) -> bool:
    """نسخة محسنة مع Cache للعلاقات الهرمية"""
    if not group:
        return False
    
    try:
        settings = frappe.get_cached_doc("Supplier Qualification Settings")
        qualified_groups = [row.supplier_group for row in settings.get("supplier_group", [])]
        
        # التحقق المباشر أولاً
        if group in qualified_groups:
            return True
            
        # التحقق من الـ Hierarchy
        return check_group_hierarchy(group, qualified_groups)
        
    except Exception:
        return False

def check_group_hierarchy(group: str, qualified_groups: list) -> bool:
    """التحقق من التسلسل الهرمي للمجموعة"""
    # Cache للعلاقات الهرمية
    cache_key = f"group_hierarchy_{group}"
    cached_result = frappe.cache().get_value(cache_key)
    
    if cached_result is not None:
        return cached_result
    
    result = _check_group_hierarchy_recursive(group, qualified_groups, set())
    
    # حفظ النتيجة في Cache لمدة ساعة
    frappe.cache().set_value(cache_key, result, expires_in_sec=3600)
    return result

def _check_group_hierarchy_recursive(group: str, qualified_groups: list, visited: set) -> bool:
    """دالة متكررة للتحقق من الـ Hierarchy"""
    if group in visited:
        return False
    visited.add(group)
    
    # إذا كانت المجموعة مؤهلة مباشرة
    if group in qualified_groups:
        return True
    
    # الحصول على Parent Group
    parent = frappe.db.get_value("Supplier Group", group, "parent_supplier_group")
    if not parent:
        return False
    
    # التحقق من Parent بشكل متكرر
    return _check_group_hierarchy_recursive(parent, qualified_groups, visited)

def _clear_qualified_groups_cache(doc=None, method=None):
    """مسح جميع أنواع الـ Cache المتعلقة بالمجموعات"""
    try:
        # مسح LRU Cache
        is_qualified_supplier_group.cache_clear()
        
        # مسح Frappe Cache للعلاقات الهرمية
        frappe.cache().delete_keys("group_hierarchy_*")
        
    except Exception as e:
        frappe.log_error(f"Error clearing groups cache: {str(e)}")

def ensure_supplier_group_required(doc, method=None):
    """إلزامية إدخال supplier group لأي مورد جديد"""
    if not doc.supplier_group:
        frappe.throw(_("Supplier Group is required for all suppliers."))

def validate_supplier_group(doc, method=None):
    """التحقق من وجود supplier group في النظام"""
    if doc.supplier_group and not frappe.db.exists("Supplier Group", doc.supplier_group):
        frappe.throw(_("Supplier Group {0} does not exist.").format(doc.supplier_group))

def create_qualification_for_new_supplier(doc, method=None):
    """إنشاء تلقائي لـ Supplier Qualification للمجموعات المؤهلة"""
    try:
        # تأخير بسيط لضمان حفظ المستند
        time.sleep(0.3)
        frappe.db.commit()

        # التحقق إذا كانت المجموعة تتطلب تأهيل
        if not is_qualified_supplier_group(doc.supplier_group):
            frappe.logger().debug(f"Supplier group {doc.supplier_group} does not require qualification")
            return

        # التحقق إذا كان المؤهل موجود مسبقاً
        if frappe.db.exists("Supplier Qualification", {"supplier": doc.name}):
            frappe.logger().debug(f"Qualification already exists for supplier {doc.name}")
            return

        # إنشاء Supplier Qualification جديد
        qualification = frappe.get_doc({
            "doctype": "Supplier Qualification",
            "supplier": doc.name,
            "supplier_name": doc.supplier_name,
            "approval_status": "Request Approval",
            "valid_from": frappe.utils.nowdate()
        })
        
        qualification.flags.ignore_permissions = True
        qualification.flags.ignore_mandatory = True
        qualification.insert()
        
        frappe.db.commit()
        
        frappe.logger().debug(f"Auto-created qualification for supplier {doc.name}")
        
    except Exception as e:
        frappe.log_error(
            title=f"Error creating qualification for {doc.name}",
            message=frappe.get_traceback()
        )

def is_supplier_approved(supplier: str) -> bool:
    """Check if supplier has approved qualification"""
    try:
        status = frappe.db.get_value("Supplier Qualification", 
            {"supplier": supplier}, "approval_status")
        return status == "Approved"
    except Exception:
        return False

def get_supplier_qualification_status(supplier: str) -> str:
    """Get current qualification status for supplier"""
    try:
        status = frappe.db.get_value("Supplier Qualification", 
            {"supplier": supplier}, "approval_status")
        return status or "Request Approval"
    except Exception:
        return "Request Approval"

def get_qualified_supplier_groups() -> list:
    """Get list of all supplier groups that require qualification"""
    try:
        settings = frappe.get_cached_doc("Supplier Qualification Settings")
        return [row.supplier_group for row in settings.get("supplier_group", [])]
    except Exception:
        return []