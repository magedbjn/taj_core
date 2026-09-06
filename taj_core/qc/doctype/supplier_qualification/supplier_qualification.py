# -*- coding: utf-8 -*-
# File: taj_core/qc/doctype/supplier_qualification/supplier_qualification.py
from __future__ import annotations
import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, add_days, nowdate


class SupplierQualification(Document):
    """Holds supplier approval state, approved items, certificates, audits, and scopes."""
    pass


def _is_checked(val) -> bool:
    try:
        return int(val or 0) == 1
    except Exception:
        return False


def get_active_qualification(supplier: str | None) -> str | None:
    """Return the latest active Supplier Qualification docname for a supplier."""
    if not supplier:
        return None
    rows = frappe.db.sql(
        """
        SELECT name
        FROM `tabSupplier Qualification`
        WHERE supplier = %s
          AND approval_status IN ('Approved','Partially Approved')
          AND (valid_from IS NULL OR valid_from <= %s)
          AND (valid_to   IS NULL OR valid_to   >= %s)
        ORDER BY COALESCE(valid_from, '1900-01-01') DESC, modified DESC
        LIMIT 1
        """,
        (supplier, today(), today()),
        as_dict=True,
    )
    return rows[0]["name"] if rows else None


def get_partial_approved_items_set(qualification: str | None, doc_items: list | None = None) -> set[str]:
    """
    Returns item codes approved when status is Partially Approved.
    Optimized: only fetch items that exist in the purchasing document.
    """
    if not qualification or not doc_items:
        return set()

    doc_item_codes = {
        getattr(it, "item_code", None) for it in doc_items if getattr(it, "item_code", None)
    }
    if not doc_item_codes:
        return set()

    rows = frappe.get_all(
        "Supplier Approved Item",
        filters={
            "parent": qualification,
            "parenttype": "Supplier Qualification",
            "item_status": "Approved",
            "item": ["in", list(doc_item_codes)],
        },
        fields=["item"],
        limit=len(doc_item_codes),
    )
    return {r["item"] for r in rows if r.get("item")}


def validate_items_against_qualification(doc, method=None) -> None:
    """
    نسخة دقيقة - تفرق بين الحالات المختلفة
    """
    supplier = getattr(doc, "supplier", None)
    if not supplier:
        return

    from taj_core.integrations.supplier_hooks import is_qualified_supplier_group
    supplier_group = frappe.db.get_value("Supplier", supplier, "supplier_group")
    if not is_qualified_supplier_group(supplier_group):
        return

    # البحث عن آخر مؤهلية بجميع حالاتها
    last_qual = frappe.get_all(
        "Supplier Qualification",
        filters={"supplier": supplier},
        fields=["name", "approval_status", "valid_to"],
        order_by="creation DESC",
        limit=1
    )
    
    if not last_qual:
        # لا توجد أي مؤهلية
        create_auto_qualification(supplier)
        frappe.throw(_("❌ Qualification required - request sent to quality"))
        return

    status = (last_qual[0]["approval_status"] or "").strip()
    
    # التحقق إذا كانت المؤهلية منتهية الصلاحية
    is_expired = False
    if last_qual[0]["valid_to"]:
        from frappe.utils import today
        if last_qual[0]["valid_to"] < today():
            is_expired = True

    # إظهار الرسالة المناسبة
    if status == "Rejected":
        frappe.throw(_("❌ Supplier rejected by quality team"))
    elif status == "Request Approval":
        frappe.throw(_("❌ Awaiting quality team approval")) 
    elif status == "Partially Approved" and not is_expired:
        validate_partial_approval_items(doc, last_qual[0]["name"])
    elif status == "Approved" and not is_expired:
        return  # السماح بالاعتماد
    else:
        # حالات أخرى أو منتهية الصلاحية
        frappe.throw(_("❌ Supplier qualification issue - contact quality team"))
      
def validate_partial_approval_items(doc, qualification: str):
    """التحقق من الأصناف مع أولوية Pending approval"""
    doc_items = getattr(doc, "items", []) or []
    codes = [d.item_code for d in doc_items if getattr(d, "item_code", None)]
    if not codes:
        return

    status_map = _get_items_status_map_for_qualification(qualification, codes)

    rejected = []
    pending = []
    
    for d in doc_items:
        code = getattr(d, "item_code", None)
        if not code:
            continue
            
        st = (status_map.get(code) or "").strip()
        if st == "Approved":
            continue
        elif st == "Rejected":
            rejected.append(code)
        else:
            pending.append(code)

    # إعطاء الأولوية: Pending approval أولاً
    if pending:
        if len(pending) > 3:
            frappe.throw(_("❌ {} items need approval (first 3: {})").format(len(pending), ", ".join(pending[:3])))
        else:
            frappe.throw(_("❌ Pending approval: {}").format(", ".join(pending)))
    
    # إذا لا توجد pending، عرض rejected
    elif rejected:
        if len(rejected) > 3:
            frappe.throw(_("❌ {} items rejected (first 3: {})").format(len(rejected), ", ".join(rejected[:3])))
        else:
            frappe.throw(_("❌ Rejected items: {}").format(", ".join(rejected)))

def create_auto_qualification(supplier: str):
    """إنشاء مؤهلية تلقائية بدون رسائل للمستخدم"""
    try:
        qualification = frappe.get_doc({
            "doctype": "Supplier Qualification",
            "supplier": supplier,
            "supplier_name": frappe.db.get_value("Supplier", supplier, "supplier_name"),
            "approval_status": "Request Approval",
            "valid_from": frappe.utils.nowdate()
        })
        qualification.insert(ignore_permissions=True)
        create_approval_todo(qualification.name, supplier)
    except Exception:
        pass  # صامت - لا تظهر رسائل للمستخدم

def dedupe_approved_items(doc, method=None):
    """Remove duplicate items in the child table (fieldname: sq_items)."""
    seen = set()
    rows = []
    for row in (doc.get("sq_items") or []):
        if not getattr(row, "item", None):
            continue
        if row.item in seen:
            continue
        seen.add(row.item)
        rows.append(row)
    doc.set("sq_items", rows)


# ----------------------------
# Smart Item Status helpers / API
# ----------------------------

@frappe.whitelist()
def get_supplier_item_status(supplier: str, item_code: str) -> str:
    """
    Get item status for supplier based on qualification status.
    Returns: "Approved", "Rejected", or "Request Approval"
    Rules:
      - If qualification.status == "Approved" -> "Approved"
      - Else -> check specific item status row
    """
    default_status = "Request Approval"
    if not supplier or not item_code:
        return default_status

    qual = get_active_qualification(supplier)
    if not qual:
        return default_status

    qual_status = frappe.db.get_value("Supplier Qualification", qual, "approval_status") or ""
    if qual_status == "Approved":
        return "Approved"

    item_status = frappe.db.get_value(
        "Supplier Approved Item",
        {
            "parent": qual,
            "parenttype": "Supplier Qualification",
            "item": item_code,
        },
        "item_status",
    )
    return item_status or default_status


@frappe.whitelist()
def get_supplier_items_status_map(supplier: str, item_codes: list[str] | None = None) -> dict:
    """
    Batch version: return {item_code: status} for given list of codes.
    Rules:
      - If qualification.status == "Approved" -> every code => "Approved"
      - Else -> read rows (Approved/Rejected), anything missing => "Request Approval"
    """
    # may arrive from frappe.call as JSON string
    if isinstance(item_codes, str):
        try:
            item_codes = json.loads(item_codes or "[]")
        except json.JSONDecodeError:
            item_codes = []

    out: dict[str, str] = {}
    if not supplier or not item_codes:
        return out

    # dedupe while preserving order
    seen = set()
    dedup_codes = []
    for c in item_codes:
        if c and c not in seen:
            seen.add(c)
            dedup_codes.append(c)

    qual = get_active_qualification(supplier)
    if not qual:
        return {c: "Request Approval" for c in dedup_codes}

    qual_status = frappe.db.get_value("Supplier Qualification", qual, "approval_status") or ""
    if qual_status == "Approved":
        return {c: "Approved" for c in dedup_codes}

    rows = frappe.get_all(
        "Supplier Approved Item",
        filters={
            "parent": qual,
            "parenttype": "Supplier Qualification",
            "item": ["in", dedup_codes],
        },
        fields=["item", "item_status"],
        limit=len(dedup_codes),
    )

    found = {r["item"]: (r["item_status"] or "Request Approval") for r in rows}
    for code in dedup_codes:
        out[code] = found.get(code, "Request Approval")
    return out


@frappe.whitelist()
def request_items_approval(
    supplier: str,
    items: list[str] | None = None,
    reference_doctype: str | None = None,
    reference_name: str | None = None,
    note: str | None = None,
) -> dict:
    """
    نسخة مصححة - تفرق بين الأصناف المعلقة والمعتمدة والمرفوضة
    """
    if isinstance(items, str):
        try:
            items = json.loads(items or "[]")
        except json.JSONDecodeError:
            items = []

    if not supplier or not items:
        return {"message": "No items provided", "success": False}

    if not frappe.db.exists("Supplier", supplier):
        return {"message": "Supplier not found", "success": False}

    qual = frappe.get_all(
        "Supplier Qualification",
        filters={"supplier": supplier},
        fields=["name"],
        limit=1,
        order_by="creation DESC"
    )
    
    if not qual:
        return {"message": "No qualification found", "success": False}

    qual_name = qual[0]["name"]
    
    # تنظيف وتفريغ الأصناف
    clean_items = list(set([item.strip() for item in items if item and item.strip()]))
    
    if not clean_items:
        return {"message": "No valid items provided", "success": False}

    # الحصول على الأصناف الموجودة مع حالتها
    existing_items = frappe.get_all(
        "Supplier Approved Item",
        filters={
            "parent": qual_name,
            "item": ["in", clean_items]
        },
        fields=["item", "item_status"],
        limit=len(clean_items)
    )
    
    # تصنيف الأصناف حسب حالتها
    pending_items = []   # Request Approval
    approved_items = []  # Approved
    rejected_items = []  # Rejected
    new_items = []       # غير موجودة
    
    existing_item_map = {row["item"]: row["item_status"] for row in existing_items}
    
    for item_code in clean_items:
        if item_code in existing_item_map:
            status = existing_item_map[item_code]
            if status == "Request Approval":
                pending_items.append(item_code)
            elif status == "Approved":
                approved_items.append(item_code)
            elif status == "Rejected":
                rejected_items.append(item_code)
        else:
            new_items.append(item_code)

    # إضافة الأصناف الجديدة فقط
    added = []
    for item_code in new_items:
        try:
            doc = frappe.get_doc({
                "doctype": "Supplier Approved Item",
                "parent": qual_name,
                "parenttype": "Supplier Qualification",
                "parentfield": "sq_items",
                "item": item_code,
                "item_status": "Request Approval",
                "remarks": note or "",
            })
            doc.insert(ignore_permissions=True)
            added.append(item_code)
        except Exception:
            pass

    frappe.db.commit()

    # بناء رسالة واضحة
    message_parts = []
    
    if added:
        message_parts.append(f"✅ Added for review: {', '.join(added)}")
    
    if pending_items:
        message_parts.append(f"⏳ Already pending: {', '.join(pending_items)}")
    
    if approved_items:
        message_parts.append(f"🔵 Already approved: {len(approved_items)} items")
    
    if rejected_items:
        message_parts.append(f"🔴 Already rejected: {len(rejected_items)} items")

    message = " • ".join(message_parts) if message_parts else "No action needed"

    return {
        "message": message,
        "success": True,
        "added": added,
        "pending": pending_items,
        "approved": approved_items,
        "rejected": rejected_items
    }


@frappe.whitelist()
def update_certificate_statuses():
    """
    Daily job: update status on Supplier Certificate rows based on expiry_date.
    Rules:
      - expiry_date < today           -> Expired
      - today <= expiry_date < +30d   -> About to Expire  (إن كانت حالتها Active)
      - otherwise leave as-is (Active / Pending / Renewal)
    """
    try:
        # Expired
        frappe.db.sql("""
            UPDATE `tabSupplier Certificate`
               SET certificate_status = 'Expired'
             WHERE COALESCE(expiry_date, '1900-01-01') < %(today)s
               AND certificate_status <> 'Expired'
        """, {"today": today()})

        # About to Expire (within next 30 days) — فقط لمن حالته Active الآن
        frappe.db.sql("""
            UPDATE `tabSupplier Certificate`
               SET certificate_status = 'About to Expire'
             WHERE COALESCE(expiry_date, '9999-12-31') >= %(today)s
               AND expiry_date < %(limit)s
               AND certificate_status = 'Active'
        """, {"today": today(), "limit": add_days(today(), 30)})

        frappe.db.commit()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "update_certificate_statuses error")



def _get_items_status_map_for_qualification(qualification: str, item_codes: list[str]) -> dict[str, str]:
    """Return map {item_code: item_status} for given qualification and item codes.
       item_status is one of: 'Approved', 'Rejected', 'Request Approval' (or missing -> None)."""
    if not qualification or not item_codes:
        return {}

    # إزالة التكرارات
    codes = []
    seen = set()
    for c in item_codes:
        if c and c not in seen:
            seen.add(c)
            codes.append(c)

    rows = frappe.get_all(
        "Supplier Approved Item",
        filters={
            "parent": qualification,
            "parenttype": "Supplier Qualification",
            "item": ["in", codes],
        },
        fields=["item", "item_status"],
        limit=len(codes),
    )
    out = {r["item"]: (r.get("item_status") or "").strip() for r in rows}
    return out

def validate_approval_status(doc, method=None):
    """
    منع المستخدمين من تغيير الحالة إلى 'Request Approval' يدوياً
    """
    if doc.is_new():
        return
    
    # احصل على الحالة السابقة من قاعدة البيانات
    previous_status = frappe.db.get_value("Supplier Qualification", doc.name, "approval_status")
    
    # إذا كانت الحالة السابقة ليست 'Request Approval' والمستخدم يحاول تغييرها إلى 'Request Approval'
    if previous_status != "Request Approval" and doc.approval_status == "Request Approval":
        frappe.throw(
            _('Cannot set status to "Request Approval" manually. Please select another status.')
        )

def before_save_capture_status(doc, method=None):
    """احفظ الحالة الأصلية قبل التعديل (اختياري)"""
    if not doc.is_new():
        doc._previous_approval_status = frappe.db.get_value(
            "Supplier Qualification", 
            doc.name, 
            "approval_status"
        )

def create_approval_todo(qualification_name: str, supplier: str):
    """إنشاء ToDo تلقائي لموافقة المورد الجديد"""
    try:
        supplier_name = frappe.db.get_value("Supplier", supplier, "supplier_name")
        
        # الحصول على الإعدادات
        settings = frappe.get_cached_doc("Supplier Qualification Settings")
        assigned_role = getattr(settings, "default_todo_role", "Quality Manager")
        
        # البحث عن مستخدمين بالدور المحدد
        users_with_role = frappe.get_all(
            "Has Role",
            filters={"role": assigned_role, "parenttype": "User"},
            fields=["parent"],
            distinct=True
        )
        
        if not users_with_role:
            assigned_to = frappe.session.user
        else:
            assigned_to = users_with_role[0]["parent"]
        
        # وصف المهمة
        description = _("🆕 New supplier requires qualification: {0} ({1})").format(
            supplier_name, supplier
        )
        
        # إنشاء ToDo
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "description": description,
            "reference_type": "Supplier Qualification",
            "reference_name": qualification_name,
            "assigned_to": assigned_to,
            "priority": "High",
            "date": frappe.utils.nowdate(),
            "role": assigned_role
        })
        
        todo.flags.ignore_permissions = True
        todo.insert()
        
        frappe.db.commit()
        
    except Exception as e:
        frappe.log_error(f"Error creating approval todo for {supplier}: {str(e)}")

def auto_set_item_status_for_po(doc, method=None):
    """
    تعيين تلقائي لحالة الأصناف في Purchase Order مع معالجة الأخطاء
    """
    try:
        if not doc or doc.is_new() or not getattr(doc, "supplier", None):
            return

        if not hasattr(doc, "items") or not doc.items:
            return

        # جمع أكواد الأصناف الفريدة
        item_codes = []
        seen = set()
        
        for item in doc.items:
            code = getattr(item, "item_code", None)
            if code and code not in seen:
                item_codes.append(code)
                seen.add(code)

        if not item_codes:
            return

        # الحصول على حالات الأصناف
        status_map = get_supplier_items_status_map(doc.supplier, item_codes)
        
        # تعيين الحالة لكل صنف
        for item in doc.items:
            code = getattr(item, "item_code", None)
            if code and code in status_map:
                item.item_status = status_map[code]
                
    except Exception as e:
        # تسجيل الخطأ بدون إيقاف العملية
        frappe.log_error(f"Error in auto_set_item_status_for_po: {str(e)}")