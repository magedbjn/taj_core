"""Pick List Receiving: server-authoritative review and UAT-only stock transfer.

Every transfer uses the native ERPNext Pick List mapper and Stock Entry
insert/submit path. User-provided items, quantities and warehouses are ignored.
Production is hard-blocked; enable via Stock Settings > Taj on test1.com.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from .logic import ReceivingRuleError, fingerprint, verify_rows
from .settings import is_transfer_enabled, status as settings_status

ROLE = "Pick List Receiver"
PURPOSE = "Material Transfer for Manufacture"
TEST_SITE = "test1.com"


def _require_receiver():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(_("Please log in to receive material."), frappe.PermissionError)
    if user != "Administrator" and ROLE not in frappe.get_roles(user):
        frappe.throw(_("You do not have permission to receive Pick Lists."), frappe.PermissionError)


def _permission_docs(doctype: str, scope: set[str]) -> set[str]:
    """Only applicable User Permissions authorize receiving, never an empty set.

    Frappe expands Warehouse group permissions to descendants when permitted.
    A Permission scoped only to an unrelated DocType cannot grant receiving access.
    """
    from frappe.core.doctype.user_permission.user_permission import get_user_permissions

    permissions = get_user_permissions(frappe.session.user).get(doctype) or []
    return {
        p.doc
        for p in permissions
        if not p.get("applicable_for") or p.get("applicable_for") in scope
    }


def _check_company_and_warehouses(pl, ste_rows):
    company = pl.get("company")
    if not company:
        frappe.throw(_("Company is required."))

    company_permissions = _permission_docs("Company", {"Company", "Pick List", "Stock Entry"})
    if company_permissions and company not in company_permissions:
        frappe.throw(_("Not permitted for company {0}").format(company), frappe.PermissionError)

    # Explicit Warehouse User Permissions required even for Administrator testing.
    allowed_warehouses = _permission_docs("Warehouse", {"Warehouse", "Pick List", "Stock Entry"})
    if not allowed_warehouses:
        frappe.throw(
            _("Set explicit Warehouse User Permissions before using Pick List Receiving."),
            frappe.PermissionError,
        )

    warehouses = set()
    for row in ste_rows:
        source = row.get("s_warehouse")
        target = row.get("t_warehouse")
        if not source or not target:
            frappe.throw(
                _("Source and target warehouses must be set for every receiving row.")
            )
        warehouses.add(source)
        warehouses.add(target)

    for warehouse in sorted(warehouses):
        if warehouse not in allowed_warehouses:
            frappe.throw(
                _("Not permitted to receive through warehouse {0}").format(warehouse),
                frappe.PermissionError,
            )
        details = frappe.db.get_value(
            "Warehouse", warehouse, ["company", "is_group", "disabled"], as_dict=True
        )
        if not details or details.company != company or details.is_group or details.disabled:
            frappe.throw(_("Invalid warehouse for company: {0}").format(warehouse))


def _precheck_pick_source_scope(pl):
    """Fail closed before the native mapper reads rates/availability."""
    allowed = _permission_docs("Warehouse", {"Warehouse", "Pick List", "Stock Entry"})
    if not allowed:
        frappe.throw(
            _("Set explicit Warehouse User Permissions before using Pick List Receiving."),
            frappe.PermissionError,
        )
    company_access = _permission_docs("Company", {"Company", "Pick List", "Stock Entry"})
    if company_access and pl.company not in company_access:
        frappe.throw(_("Not permitted for company {0}").format(pl.company), frappe.PermissionError)
    for row in pl.get("locations") or []:
        warehouse = row.get("warehouse")
        if warehouse and warehouse not in allowed:
            frappe.throw(
                _("Not permitted to receive through warehouse {0}").format(warehouse),
                frappe.PermissionError,
            )
        # First release accepts a single full receipt only, not prior partials.
        if flt(row.get("transferred_qty")) > 0:
            frappe.throw(_("This Pick List has previous partial transfers. Review it in ERPNext."))


def _get_pick(name: str):
    _require_receiver()
    if not isinstance(name, str) or len(name) > 140 or not name.strip():
        frappe.throw(_("A valid Pick List number is required."))
    pl = frappe.get_doc("Pick List", name.strip())
    pl.check_permission("read")  # standard Role + User Permissions + doc-level permissions
    if pl.docstatus != 1:
        frappe.throw(_("Only submitted Pick Lists can be received."))
    if pl.get("purpose") != PURPOSE:
        frappe.throw(_("Only Material Transfer for Manufacture Pick Lists can be received."))
    work_order = pl.get("work_order")
    if not isinstance(work_order, str) or not work_order.strip():
        frappe.throw(_("A linked Work Order is required for Pick List Receiving."))
    if pl.get("status") in {"Completed", "Cancelled"}:
        frappe.throw(_("This Pick List is already completed or cancelled."))
    return pl


def _review(name: str) -> dict:
    pl = _get_pick(name)
    _precheck_pick_source_scope(pl)

    # Neither drafts nor prior submitted Stock Entries may be silently superseded.
    existing = frappe.get_all(
        "Stock Entry",
        filters={"pick_list": pl.name, "docstatus": ["<", 2]},
        fields=["name", "docstatus"],
        limit_page_length=10,
    )
    if existing:
        frappe.throw(
            _("A Stock Entry already exists for Pick List {0}. Review it in ERPNext first.").format(pl.name)
        )

    from erpnext.stock.doctype.pick_list.pick_list import create_stock_entry

    # ERPNext's standard mapper builds an UNSAVED Stock Entry dictionary.
    mapped = create_stock_entry(pl.as_dict())
    if not isinstance(mapped, dict) or not mapped.get("items"):
        frappe.throw(_("No pending picked items were found for this Pick List."))
    mapped_rows = mapped["items"]
    _check_company_and_warehouses(pl, mapped_rows)

    originals = {r.name: r for r in pl.get("locations") or []}
    rows, signature_rows = [], []
    seen_row_ids = set()
    for entry in mapped_rows:
        row_name = entry.get("pick_list_item")
        if not row_name or row_name not in originals or row_name in seen_row_ids:
            frappe.throw(_("Unable to map Stock Entry rows to unique Pick List rows."))
        seen_row_ids.add(row_name)
        original = originals[row_name]
        pending = flt(entry.get("transfer_qty"))
        if pending <= 0:
            frappe.throw(_("Invalid pending transfer quantity."))
        info = {
            "row_id": row_name,
            "item_code": entry.get("item_code"),
            "item_name": entry.get("item_name") or original.get("item_name"),
            "requested_qty": flt(original.get("qty")),
            "requested_uom": original.get("uom"),
            "picked_qty": flt(original.get("picked_qty")),
            "transferred_qty": flt(original.get("transferred_qty")),
            "pending_qty": pending,
            "stock_uom": entry.get("stock_uom") or original.get("stock_uom"),
            "source": entry.get("s_warehouse"),
            "target": entry.get("t_warehouse"),
            "batch_no": entry.get("batch_no"),
            "serial_and_batch_bundle": entry.get("serial_and_batch_bundle") or original.get("serial_and_batch_bundle"),
            "serial_no": entry.get("serial_no"),
            "required_brand": original.get("taj_required_brand"),
        }
        rows.append(info)
        signature_rows.append(info)

    raw_signature = {
        "name": pl.name,
        "modified": str(pl.modified),
        "status": pl.get("status"),
        "purpose": pl.get("purpose"),
        "company": pl.company,
        "reference": pl.get("work_order"),
        "rows": signature_rows,
    }
    return {
        "pick_list": pl.name,
        "company": pl.company,
        "purpose": pl.purpose,
        "reference_doctype": "Work Order",
        "reference": pl.get("work_order"),
        "rows": rows,
        "signature": fingerprint(raw_signature),
        "mode": "READ_ONLY",
    }


@frappe.whitelist()
def get_review(pick_list: str):
    """Scan QR -> check live permissions -> show ERPNext-mapped pending quantities."""
    return _review(pick_list)


@frappe.whitelist()
def list_pending(limit=20):
    """Optional receiving queue; never bypass Frappe's document read filters."""
    _require_receiver()
    size = min(max(int(limit), 1), 30)
    candidates = frappe.get_list(
        "Pick List",
        filters={"docstatus": 1, "purpose": PURPOSE, "work_order": ["!=", ""]},
        fields=["name", "work_order", "status"],
        order_by="modified desc",
        limit_page_length=size,
    )
    results = []
    for item in candidates:
        if item.status in {"Completed", "Cancelled"}:
            continue
        try:
            review = _review(item.name)
        except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
            continue
        # Some ERPNext validation errors use frappe.ValidationError or subtypes;
        # unreadable/invalid requests are not displayed as ready.
        results.append({
            "pick_list": review["pick_list"],
            "reference": review["reference"],
            "purpose": review["purpose"],
            "item_count": len(review["rows"]),
        })
    return results


@frappe.whitelist(methods=["POST"])
def simulate_confirm(pick_list, signature, confirmations):
    """Server-side verification; NEVER saves/submits a Stock Entry."""
    _require_receiver()
    review = _review(pick_list)
    if not isinstance(signature, str) or review["signature"] != signature:
        frappe.throw(_("Pick List details changed. Refresh and review the items again."))
    if isinstance(confirmations, str):
        confirmations = frappe.parse_json(confirmations)
    try:
        verify_rows(review["rows"], confirmations)
    except ReceivingRuleError as exc:
        frappe.throw(_(str(exc)))
    return {
        "status": "SIMULATION_ONLY",
        "pick_list": review["pick_list"],
        "item_count": len(review["rows"]),
        "stock_entry_created": False,
        "stock_entry_submitted": False,
        "message": _("All items verified. This was a simulation; no Stock Entry was created."),
    }


@frappe.whitelist(methods=["POST"])
def submit_receipt(*args, **kwargs):
    """Old endpoint disabled to prevent accidental bypass of the new guarded route."""
    frappe.throw(_("Use Confirm & Transfer on the Pick List Receiving page."))



def _require_transfer_enabled():
    """Two independent guards: hard-coded UAT site and explicit opt-in."""
    if getattr(frappe.local, "site", None) != TEST_SITE:
        frappe.throw(_("Stock transfer is available only on test1.com."), frappe.PermissionError)
    if not is_transfer_enabled():
        frappe.throw(_("Stock transfer is disabled. Enable it in Stock Settings > Taj."), frappe.PermissionError)


def _validated_fresh_mapping(pl, reviewed_rows):
    """Rebuild the Stock Entry from trusted Pick List rows, never client rows.

    Full-only release: every submitted Pick List Item must be picked, and
    nothing may have been transferred already. The mapper must match the
    *same* reviewed rows and source/target warehouses/quantities.
    """
    from erpnext.stock.doctype.pick_list.pick_list import create_stock_entry

    mapped = create_stock_entry(pl.as_dict())
    if not isinstance(mapped, dict) or not mapped.get("items"):
        frappe.throw(_("No pending picked items were found for this Pick List."))
    if (
        mapped.get("doctype") != "Stock Entry"
        or mapped.get("pick_list") != pl.name
        or mapped.get("purpose") != PURPOSE
        or mapped.get("work_order") != pl.work_order
        or mapped.get("company") != pl.company
    ):
        frappe.throw(_("ERPNext mapped Stock Entry does not match the Pick List."))

    originals = {row.name: row for row in pl.get("locations") or []}
    expected = {row["row_id"]: row for row in reviewed_rows}
    if not originals or len(originals) != len(pl.locations) or set(originals) != set(expected):
        frappe.throw(_("Every Pick List row must be fully picked and confirmed."))
    mapped_rows = mapped.get("items") or []
    if len(mapped_rows) != len(originals):
        frappe.throw(_("Every Pick List row must be fully picked and confirmed."))

    seen = set()
    for row in mapped_rows:
        rid = row.get("pick_list_item")
        if not rid or rid not in originals or rid in seen:
            frappe.throw(_("Stock Entry mapping has invalid Pick List row references."))
        seen.add(rid)
        source = originals[rid]
        confirmed = expected[rid]
        if flt(source.get("picked_qty")) <= 0 or flt(source.get("transferred_qty")) != 0:
            frappe.throw(_("This Pick List is not eligible for a single full transfer."))
        # Stock UOM and the mapped transaction quantity are source-authoritative.
        if (
            abs(flt(row.get("transfer_qty")) - flt(source.get("picked_qty"))) > 0.000001
            or abs(flt(row.get("transfer_qty")) - flt(confirmed["pending_qty"])) > 0.000001
            or row.get("item_code") != source.get("item_code")
            or row.get("s_warehouse") != source.get("warehouse")
            or row.get("s_warehouse") != confirmed["source"]
            or row.get("t_warehouse") != confirmed["target"]
            or row.get("batch_no") != confirmed["batch_no"]
        ):
            frappe.throw(_("Mapped Stock Entry changed. Refresh the Pick List and confirm again."))
    if seen != set(originals):
        frappe.throw(_("Every Pick List row must be fully picked and confirmed."))
    _check_company_and_warehouses(pl, mapped_rows)
    return mapped


@frappe.whitelist(methods=["POST"])
def transfer_confirmed(pick_list, signature, confirmations):
    """Receive a single Pick List and submit exactly one native Stock Entry.

    IMPORTANT: explicit user role, warehouse/company User Permissions, live
    signature, complete Confirmed flags, and exclusive DB Pick List row lock.
    Frappe automatically commits successful POST requests and rolls back
    failed requests. No manual commit, no bypass of standard validations/hooks.
    """
    _require_transfer_enabled()
    _require_receiver()
    pl = _get_pick(pick_list)  # permission check BEFORE attempting a row lock

    # Serialise competing receives for the same Pick List in this endpoint.
    # A retry after successful transfer will see the native updated Pick List
    # and/or the existing Stock Entry and must not post another ledger entry.
    locked = frappe.db.sql(
        "SELECT name FROM `tabPick List` WHERE name = %s FOR UPDATE",
        (pl.name,),
    )
    if not locked:
        frappe.throw(_("Pick List not found."))

    # Re-read all rows and permissions *after* taking the exclusive row lock.
    review = _review(pl.name)
    if not isinstance(signature, str) or review["signature"] != signature:
        frappe.throw(_("Pick List details changed. Refresh and review the items again."))
    if isinstance(confirmations, str):
        confirmations = frappe.parse_json(confirmations)
    try:
        verify_rows(review["rows"], confirmations)
    except ReceivingRuleError as exc:
        frappe.throw(_(str(exc)))

    # A second read under the lock makes the full-item and Work Order checks
    # independent from the client's previous read-only request.
    pl = _get_pick(pl.name)
    mapped = _validated_fresh_mapping(pl, review["rows"])

    # A prior draft or submitted Stock Entry must never be replaced or merged.
    if frappe.db.exists("Stock Entry", {"pick_list": pl.name, "docstatus": ("<", 2)}):
        frappe.throw(_("A Stock Entry already exists for Pick List {0}.").format(pl.name))

    se = frappe.get_doc(mapped)
    # Use standard Frappe create and submit permissions for the current user.
    se.insert()
    se.submit()
    if se.docstatus != 1:
        frappe.throw(_("Stock Entry was not submitted; the transaction will be rolled back."))

    # Native Stock Entry submission must post both source and target ledger
    # movements. If no corresponding entries exist, fail the POST transaction
    # instead of reporting a misleading success to the receiver.
    ledger = frappe.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": "Stock Entry", "voucher_no": se.name, "is_cancelled": 0},
        fields=["warehouse", "actual_qty"],
        limit_page_length=1000,
    )
    if (
        len(ledger) < 2
        or not any(flt(row.actual_qty) < 0 for row in ledger)
        or not any(flt(row.actual_qty) > 0 for row in ledger)
    ):
        frappe.throw(_("Stock Ledger movement was not posted; the transaction will be rolled back."))

    return {
        "status": "TRANSFERRED",
        "pick_list": pl.name,
        "stock_entry": se.name,
        "stock_entry_docstatus": se.docstatus,
        "item_count": len(review["rows"]),
        "stock_entry_created": True,
        "stock_entry_submitted": True,
        "stock_ledger_entries": len(ledger),
        "message": _("Stock Entry {0} submitted and stock transferred.").format(se.name),
    }


def transfer_status():
    """Read-only bench diagnostic. Not a whitelisted endpoint."""
    return {**settings_status(), "uses_native_stock_entry": True}


@frappe.whitelist(methods=["GET"])
def get_receipt_view(pick_list: str):
    """Read-only, QR-scoped mobile view for one Pick List.

    An open list uses exactly the v0.7 server-side mapped review. For a
    completed list, show a submitted Stock Entry only after standard Pick List
    read permission and explicit company/source/target Warehouse permission
    checks. This method never inserts, submits or edits any document.
    """
    _require_receiver()
    if not isinstance(pick_list, str) or not pick_list.strip() or len(pick_list) > 140:
        frappe.throw(_("A valid Pick List number is required."))

    pl = frappe.get_doc("Pick List", pick_list.strip())
    pl.check_permission("read")
    if pl.get("purpose") != PURPOSE or not pl.get("work_order"):
        frappe.throw(_("Only manufacturing Pick Lists linked to a Work Order are supported."))

    if pl.docstatus == 1 and pl.get("status") not in {"Completed", "Cancelled"}:
        return {"status": "OPEN", "review": _review(pl.name)}

    if pl.docstatus == 0:
        frappe.throw(_("Only submitted Pick Lists can be received."))
    if pl.docstatus == 2 or pl.get("status") == "Cancelled":
        return {"status": "CANCELLED", "pick_list": pl.name}

    # Only a submitted Stock Entry proves that a completed Pick List was
    # transferred. Never call the pending-transfer mapper on completed rows.
    existing = frappe.get_all(
        "Stock Entry",
        filters={"pick_list": pl.name, "docstatus": 1},
        fields=["name"],
        limit_page_length=2,
    )
    if len(existing) != 1:
        return {"status": "COMPLETED_REVIEW", "pick_list": pl.name}

    se = frappe.get_doc("Stock Entry", existing[0].name)
    if (se.docstatus != 1 or se.get("pick_list") != pl.name
            or se.get("company") != pl.get("company")
            or se.get("purpose") != PURPOSE
            or se.get("work_order") != pl.get("work_order")):
        return {"status": "COMPLETED_REVIEW", "pick_list": pl.name}

    # Prevent the extra status endpoint from bypassing the warehouse guard
    # enforced by the existing transfer/review methods. In particular, the
    # destination may not be visible just because Pick List read is allowed.
    _check_company_and_warehouses(pl, se.get("items") or [])
    ledger = frappe.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": "Stock Entry", "voucher_no": se.name, "is_cancelled": 0},
        fields=["actual_qty"], limit_page_length=1000,
    )
    if (not any(flt(m.actual_qty) < 0 for m in ledger)
            or not any(flt(m.actual_qty) > 0 for m in ledger)):
        return {"status": "COMPLETED_REVIEW", "pick_list": pl.name}
    locations = {row.name: row for row in pl.get("locations") or []}
    mapped_rows = {row.get("pick_list_item"): row for row in se.get("items") or []}
    if (not locations or len(mapped_rows) != len(locations)
            or set(mapped_rows) != set(locations)):
        return {"status": "COMPLETED_REVIEW", "pick_list": pl.name}

    rows = []
    for row_id, row in locations.items():
        movement = mapped_rows[row_id]
        if (movement.get("item_code") != row.get("item_code")
                or movement.get("s_warehouse") != row.get("warehouse")):
            return {"status": "COMPLETED_REVIEW", "pick_list": pl.name}
        rows.append({
            "row_id": row_id,
            "item_code": row.get("item_code"),
            "item_name": row.get("item_name") or movement.get("item_name"),
            "requested_qty": flt(row.get("qty")),
            "requested_uom": row.get("uom"),
            "picked_qty": flt(row.get("picked_qty")),
            "stock_uom": movement.get("stock_uom") or row.get("stock_uom"),
            "source": movement.get("s_warehouse"),
            "target": movement.get("t_warehouse"),
            "batch_no": row.get("batch_no") or movement.get("batch_no"),
            "required_brand": row.get("taj_required_brand"),
        })
    return {
        "status": "TRANSFERRED",
        "pick_list": pl.name,
        "reference": pl.get("work_order"),
        "stock_entry": se.name,
        "rows": rows,
    }
