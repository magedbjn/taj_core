# -*- coding: utf-8 -*-
# File: taj_core/qc/doctype/supplier_qualification/supplier_qualification.py
from __future__ import annotations
import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, add_days, getdate, nowdate


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
        try:
            queue_auto_qualification_request(
                supplier
            )
        except Exception:
            frappe.logger("taj_core").exception(
                "Failed to queue supplier "
                "qualification request for %s",
                supplier,
            )
            frappe.throw(
                _(
                    "❌ Qualification required - "
                    "quality request could not be queued. "
                    "Contact quality team."
                )
            )

        frappe.throw(
            _(
                "❌ Qualification required - "
                "request queued for quality"
            )
        )

    status = (last_qual[0]["approval_status"] or "").strip()
    
    # التحقق إذا كانت المؤهلية منتهية الصلاحية
    is_expired = False
    if last_qual[0]["valid_to"]:
        if getdate(last_qual[0]["valid_to"]) < getdate(today()):
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

_AUTO_QUALIFICATION_JOB = (
    "taj_core.qc.doctype.supplier_qualification."
    "supplier_qualification.create_auto_qualification"
)


def queue_auto_qualification_request(
    supplier: str,
):
    """
    Queue the request outside the current DB transaction.

    The purchasing document can then roll back normally while
    the background job creates the Qualification and ToDo in
    its own transaction.
    """
    job_id = (
        "taj_core:auto_supplier_qualification:"
        f"{supplier}"
    )

    return frappe.enqueue(
        _AUTO_QUALIFICATION_JOB,
        queue="short",
        job_id=job_id,
        deduplicate=True,
        enqueue_after_commit=False,
        supplier=supplier,
    )


def create_auto_qualification(supplier: str):
    """
    Atomically create a pending Supplier Qualification and ToDo.

    Lock the Supplier row so concurrent jobs for the same supplier
    cannot create duplicate qualifications.
    """
    supplier_rows = frappe.db.sql(
        """
        select
            name,
            supplier_name
        from
            `tabSupplier`
        where
            name = %s
        for update
        """,
        (supplier,),
        as_dict=True,
    )

    if not supplier_rows:
        frappe.throw(
            _("Supplier {0} does not exist").format(
                supplier
            )
        )

    supplier_row = supplier_rows[0]

    existing = frappe.db.sql(
        """
        select
            name
        from
            `tabSupplier Qualification`
        where
            supplier = %s
        order by
            creation desc
        limit 1
        for update
        """,
        (supplier,),
        as_dict=True,
    )

    if existing:
        return existing[0].name

    qualification = frappe.get_doc({
        "doctype": "Supplier Qualification",
        "supplier": supplier,
        "supplier_name": supplier_row.supplier_name,
        "approval_status": "Request Approval",
        "valid_from": frappe.utils.nowdate(),
    })

    qualification.insert(
        ignore_permissions=True
    )

    create_approval_todo(
        qualification.name,
        supplier,
    )

    return qualification.name


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
    """Request qualification review for items from an authorized Purchase Order."""

    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.PermissionError)

    if isinstance(items, str):
        try:
            items = json.loads(items or "[]")
        except json.JSONDecodeError:
            frappe.throw(_("Invalid items payload"))

    if not isinstance(items, list):
        frappe.throw(_("Items must be a list"))

    clean_items = list(
        dict.fromkeys(
            item.strip()
            for item in items
            if isinstance(item, str) and item.strip()
        )
    )

    if not supplier or not clean_items:
        return {
            "message": _("No items provided"),
            "success": False,
            "added": [],
            "pending": [],
            "approved": [],
            "rejected": [],
        }

    # This endpoint is intentionally scoped to the Purchase Order workflow.
    if reference_doctype != "Purchase Order" or not reference_name:
        frappe.throw(
            _("A valid Purchase Order reference is required"),
            frappe.PermissionError,
        )

    purchase_order = frappe.get_doc(
        "Purchase Order",
        reference_name,
    )

    purchase_order.check_permission("write")

    if purchase_order.supplier != supplier:
        frappe.throw(
            _("Supplier does not match Purchase Order {0}").format(
                reference_name
            )
        )

    po_item_codes = {
        row.item_code
        for row in purchase_order.items
        if row.item_code
    }

    invalid_items = [
        item
        for item in clean_items
        if item not in po_item_codes
    ]

    if invalid_items:
        frappe.throw(
            _(
                "The following items do not belong to Purchase Order {0}: {1}"
            ).format(
                reference_name,
                ", ".join(invalid_items),
            )
        )

    qualification_name = frappe.db.get_value(
        "Supplier Qualification",
        {"supplier": supplier},
        "name",
        order_by="creation desc",
    )

    if not qualification_name:
        return {
            "message": _("No qualification found"),
            "success": False,
            "added": [],
            "pending": [],
            "approved": [],
            "rejected": [],
        }

    existing_items = frappe.get_all(
        "Supplier Approved Item",
        filters={
            "parent": qualification_name,
            "parenttype": "Supplier Qualification",
            "item": ["in", clean_items],
        },
        fields=[
            "item",
            "item_status",
        ],
        limit=len(clean_items),
    )

    existing_item_map = {
        row["item"]: row["item_status"]
        for row in existing_items
    }

    pending_items = []
    approved_items = []
    rejected_items = []
    new_items = []

    for item_code in clean_items:
        status = existing_item_map.get(item_code)

        if status == "Request Approval":
            pending_items.append(item_code)
        elif status == "Approved":
            approved_items.append(item_code)
        elif status == "Rejected":
            rejected_items.append(item_code)
        elif status is None:
            new_items.append(item_code)

    # Explicit authorization has already happened against the Purchase Order.
    # Qualification modification is a controlled service operation because
    # purchasing users are not expected to have direct QC write permission.
    qualification = frappe.get_doc(
        "Supplier Qualification",
        qualification_name,
    )

    for item_code in new_items:
        qualification.append(
            "sq_items",
            {
                "item": item_code,
                "item_status": "Request Approval",
                "remarks": note or "",
            },
        )

    if new_items:
        qualification.flags.ignore_permissions = True
        qualification.save()

    return {
        "message": _("Qualification request processed"),
        "success": True,
        "added": new_items,
        "pending": pending_items,
        "approved": approved_items,
        "rejected": rejected_items,
    }

def update_certificate_statuses():
    """
    Daily job: update status on Supplier Certificate rows based on expiry_date.

    The scheduler owns the transaction: successful jobs are committed by
    Frappe, while uncaught failures roll the whole job back.

    Rules:
      - expiry_date < today           -> Expired
      - today <= expiry_date < +30d   -> About to Expire
      - otherwise leave as-is (Active / Pending / Renewal)
    """
    frappe.db.sql(
        """
        UPDATE `tabSupplier Certificate`
           SET certificate_status = 'Expired'
         WHERE COALESCE(expiry_date, '1900-01-01') < %(today)s
           AND certificate_status <> 'Expired'
        """,
        {"today": today()},
    )

    frappe.db.sql(
        """
        UPDATE `tabSupplier Certificate`
           SET certificate_status = 'About to Expire'
         WHERE COALESCE(expiry_date, '9999-12-31') >= %(today)s
           AND expiry_date < %(limit)s
           AND certificate_status = 'Active'
        """,
        {
            "today": today(),
            "limit": add_days(today(), 30),
        },
    )



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

def create_approval_todo(
    qualification_name: str,
    supplier: str,
):
    """
    Create the approval ToDo as part of the caller's transaction.

    No manual commit is performed here. If ToDo creation fails,
    the surrounding Qualification transaction must fail as well.
    """
    existing_todo = frappe.db.exists(
        "ToDo",
        {
            "reference_type": "Supplier Qualification",
            "reference_name": qualification_name,
        },
    )

    if existing_todo:
        return existing_todo

    supplier_name = frappe.db.get_value(
        "Supplier",
        supplier,
        "supplier_name",
    )

    settings = frappe.get_cached_doc(
        "Supplier Qualification Settings"
    )

    assigned_role = (
        getattr(
            settings,
            "default_todo_role",
            None,
        )
        or "Quality Manager"
    )

    users_with_role = frappe.get_all(
        "Has Role",
        filters={
            "role": assigned_role,
            "parenttype": "User",
        },
        fields=["parent"],
        distinct=True,
    )

    if not users_with_role:
        allocated_to = frappe.session.user
    else:
        allocated_to = users_with_role[0]["parent"]

    description = _(
        "🆕 New supplier requires qualification: "
        "{0} ({1})"
    ).format(
        supplier_name,
        supplier,
    )

    todo = frappe.get_doc({
        "doctype": "ToDo",
        "description": description,
        "reference_type": "Supplier Qualification",
        "reference_name": qualification_name,
        "allocated_to": allocated_to,
        "priority": "High",
        "date": frappe.utils.nowdate(),
        "role": assigned_role,
    })

    todo.insert(
        ignore_permissions=True
    )

    return todo.name


def auto_set_item_status_for_po(doc, method=None):
    """Set supplier qualification status on Purchase Order items."""
    if (
        not doc
        or doc.is_new()
        or not getattr(doc, "supplier", None)
        or not getattr(doc, "items", None)
    ):
        return

    item_codes = []
    seen = set()

    for item in doc.items:
        code = getattr(item, "item_code", None)

        if code and code not in seen:
            item_codes.append(code)
            seen.add(code)

    if not item_codes:
        return

    status_map = get_supplier_items_status_map(
        doc.supplier,
        item_codes,
    )

    for item in doc.items:
        code = getattr(item, "item_code", None)

        if code and code in status_map:
            item.item_status = status_map[code]
