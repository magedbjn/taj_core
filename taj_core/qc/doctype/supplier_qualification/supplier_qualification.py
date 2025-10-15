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
    Purchasing guard (hook-safe signature: (doc, method=None)).

    Manufacturing suppliers only:
      - No active qualification  -> block (مع رسالة أدق لو آخر حالة Request Approval / Rejected)
      - Approved                -> allow all items
      - Partially Approved      -> 
            * items with status == Approved      -> allowed
            * items with status == Rejected      -> block برسالة "مرفوض"
            * items missing / Request Approval   -> block برسالة "تحتاج موافقة"
    """
    supplier = getattr(doc, "supplier", None)
    if not supplier:
        return

    # تخطَّ اللا-تصنيعي
    from taj_core.integrations.supplier_hooks import is_manufacturing_group
    supplier_group = frappe.db.get_value("Supplier", supplier, "supplier_group")
    if not is_manufacturing_group(supplier_group):
        return

    qual = get_active_qualification(supplier)
    if not qual:
        # لا توجد مؤهلية فعّالة: افحص آخر مؤهلية لرسالة أوضح
        last_qual = frappe.get_all(
            "Supplier Qualification",
            filters={"supplier": supplier},
            fields=["name", "approval_status"],
            order_by="modified desc",
            limit=1,
        )
        if last_qual:
            last_status = (last_qual[0].get("approval_status") or "").strip()
            if last_status == "Request Approval":
                frappe.throw(_("Supplier qualification is pending review (Request Approval). Purchasing is not allowed."))
            if last_status == "Rejected":
                frappe.throw(_("Supplier qualification is Rejected. Purchasing is not allowed."))
        frappe.throw(_("No active Supplier Qualification found for supplier {0}.").format(supplier))

    status = (frappe.db.get_value("Supplier Qualification", qual, "approval_status") or "").strip()

    if status == "Rejected":
        frappe.throw(_("Supplier qualification is Rejected. Purchasing is not allowed."))

    if status == "Approved":
        return

    if status == "Partially Approved":
        doc_items = getattr(doc, "items", []) or []
        codes = [d.item_code for d in doc_items if getattr(d, "item_code", None)]
        if not codes:
            return

        status_map = _get_items_status_map_for_qualification(qual, codes)

        rejected = []
        pending  = []  # missing or Request Approval
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
                # إما غير موجود بالجدول أو حالته Request Approval
                pending.append(code)

        if rejected or pending:
            parts = []
            if rejected:
                parts.append(
                    _("These items are explicitly Rejected for this supplier:")
                    + "<br>" + "<br>".join(frappe.utils.cstr(i) for i in rejected)
                )
            if pending:
                parts.append(
                    _("These items are not approved yet (missing or Request Approval):")
                    + "<br>" + "<br>".join(frappe.utils.cstr(i) for i in pending)
                    + "<br><br>"
                    + _("Add them to the Supplier Approved Item table with Item Status = 'Approved', or remove them.")
                )
            frappe.throw("<br><br>".join(parts))


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
    Create/update Supplier Qualification rows for given item codes with item_status='Request Approval'.
    - Creates draft Supplier Qualification if none exists.
    - Skips duplicates (doesn't re-add same item).
    - Creates a ToDo for QA team.
    Returns: {"added": [...], "skipped": [...]}
    """
    if isinstance(items, str):
        try:
            items = json.loads(items or "[]")
        except json.JSONDecodeError:
            items = []

    if not supplier or not items:
        return {"added": [], "skipped": []}

    qual = get_active_qualification(supplier)
    if not qual:
        # bootstrap new (draft) qualification
        q = frappe.new_doc("Supplier Qualification")
        q.supplier = supplier
        q.insert(ignore_permissions=True)
        qual = q.name

    existing = set(
        r["item"]
        for r in frappe.get_all(
            "Supplier Approved Item",
            filters={
                "parent": qual,
                "parenttype": "Supplier Qualification",
                "item": ["in", items],
            },
            fields=["item"],
            limit=len(items),
        )
    )

    added, skipped = [], []
    for code in items:
        if code in existing:
            skipped.append(code)
            continue
        row = frappe.get_doc({
            "doctype": "Supplier Approved Item",
            "parent": qual,
            "parenttype": "Supplier Qualification",
            "parentfield": "sq_items",  # ⚠️ تأكد أن اسم حقل الجدول في DocType هو sq_items
            "item": code,
            "item_status": "Request Approval",
            "remarks": note or "",
        })
        row.insert(ignore_permissions=True)
        added.append(code)

    # ToDo for QA
    todo_desc = _("PO Items need qualification review for supplier {0}: {1}").format(
        supplier, ", ".join(added) if added else ", ".join(skipped)
    )
    if reference_doctype and reference_name:
        todo_desc += _(" (ref: {0} {1})").format(reference_doctype, reference_name)

    frappe.get_doc({
        "doctype": "ToDo",
        "description": todo_desc,
        "reference_type": "Supplier Qualification",
        "reference_name": qual,
    }).insert(ignore_permissions=True)

    return {"added": added, "skipped": skipped}

def auto_set_item_status_for_po(doc, method=None):
    """
    Auto-set item_status on Purchase Order items (client can also trigger via button).
    """
    if not getattr(doc, "supplier", None) or not hasattr(doc, "items"):
        return

    codes = [d.item_code for d in (doc.items or []) if getattr(d, "item_code", None)]
    if not codes:
        return

    status_map = get_supplier_items_status_map(doc.supplier, codes)
    # تحويل status_map إلى dict إذا كان _dict
    status_dict = dict(status_map) if hasattr(status_map, 'items') else status_map
    
    for d in (doc.items or []):
        code = getattr(d, "item_code", None)
        if code and code in status_dict:
            d.item_status = status_dict[code]



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
               SET status = 'Expired'
             WHERE COALESCE(expiry_date, '1900-01-01') < %(today)s
               AND status <> 'Expired'
        """, {"today": today()})

        # About to Expire (within next 30 days) — فقط لمن حالته Active الآن
        frappe.db.sql("""
            UPDATE `tabSupplier Certificate`
               SET status = 'About to Expire'
             WHERE COALESCE(expiry_date, '9999-12-31') >= %(today)s
               AND expiry_date < %(limit)s
               AND status = 'Active'
        """, {"today": today(), "limit": add_days(today(), 30)})

        frappe.db.commit()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "update_certificate_statuses error")


from frappe import _

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
