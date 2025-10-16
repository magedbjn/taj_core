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
    """Check if supplier group requires qualification"""
    if not group:
        return False
    
    try:
        settings = frappe.get_cached_doc("Supplier Qualification Settings")
        qualified_groups = [row.supplier_group for row in settings.get("supplier_group", [])]
        return group in qualified_groups
    except Exception:
        return False

def _clear_qualified_groups_cache(doc=None, method=None):
    """Clear cache when Supplier Qualification Settings change"""
    try:
        is_qualified_supplier_group.cache_clear()
        frappe.logger().debug("Supplier Qualification cache cleared")
    except Exception as e:
        frappe.log_error(f"Error clearing qualified groups cache: {str(e)}")

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