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
    except Exception as e:
        frappe.log_error(f"Error clearing qualified groups cache: {str(e)}")

def create_qualification_for_new_supplier(doc, method=None):
    """Create Supplier Qualification automatically for new suppliers in qualified groups"""
    try:
        if not is_qualified_supplier_group(doc.supplier_group):
            return

        # تأخير استراتيجي لضمان حفظ المستند
        time.sleep(0.5)
        frappe.db.commit()

        # التحقق إذا كان موجود مسبقاً
        if not frappe.db.exists("Supplier Qualification", {"supplier": doc.name}):
            qualification = frappe.get_doc({
                "doctype": "Supplier Qualification",
                "supplier": doc.name,
                "approval_status": "Request Approval"
            })
            qualification.insert(ignore_permissions=True)
            
    except Exception as e:
        frappe.log_error(f"Error creating qualification for {doc.name}: {str(e)}")

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
