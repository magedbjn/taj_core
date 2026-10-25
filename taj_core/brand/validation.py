"""Non-bypassable server validations for source-specific manufacturing.

The feature is opt-in per site via taj_brand_requirements_enabled.  Standard
ERPNext is untouched when the flag is off or the BOM brand is empty.
"""
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt

from .bom import bom_brand_map, validate_bom_item_restrictions
from .rules import MixedBrandRequirementError, brand, same_requirement, unique_brand_requirements
from .setup import batch_brand_field


def enabled():
    return bool(cint(frappe.conf.get("taj_brand_requirements_enabled")))


def _lineage_brand(doctype, name):
    if not name:
        return None
    return brand(frappe.db.get_value(doctype, name, "taj_required_brand"))


def _sync_required(row, source_doctype, source_row, label, include_brand=False):
    if not source_row:
        return
    # A child-row reference alone is not proof of item lineage.  Validate the
    # referenced item before copying its requirement to protect manual/API edits.
    columns = ["item_code", "taj_required_brand"]
    if include_brand:
        columns.append("brand")
    source = frappe.db.get_value(source_doctype, source_row, columns, as_dict=True)
    if not source or source.item_code != row.get("item_code"):
        frappe.throw(_("{0}, row {1}: {2} source does not belong to Item {3}.").format(
            label, row.idx, source_doctype, row.get("item_code")
        ))
    source_value = brand(source.taj_required_brand)
    current = brand(row.get("taj_required_brand"))
    if source_value and current and current != source_value:
        frappe.throw(_("{0}, row {1}: Required Brand must match {2} ({3}).").format(
            label, row.idx, source_doctype, source_row
        ))
    # An upstream 'Any' does not prevent a direct purchase from requesting a
    # more specific brand.  A specific upstream Brand must never be weakened.
    if source_value:
        row.taj_required_brand = source_value
    return source


def _validate_item_tracking_contract(item, item_code=None):
    if not item or not item.get("taj_brand_tracking"):
        return False

    item_code = item_code or item.get("name") or item.get("item_code") or _("New")

    if not item.get("is_stock_item"):
        frappe.throw(_(
            "Item {0}: Brand Tracking requires a Stock Item."
        ).format(item_code))

    if not item.get("has_batch_no"):
        frappe.throw(_(
            "Item {0}: Brand Tracking requires Batch tracking. "
            "Migrate existing stock first; the application will not change historical stock."
        ).format(item_code))

    if brand(item.get("brand")):
        frappe.throw(_(
            "Item {0}: Item Brand must be blank when Brand Tracking is enabled; "
            "the actual Brand is stored on each Batch."
        ).format(item_code))

    return True


def _tracked(item_code):
    data = frappe.get_cached_value(
        "Item",
        item_code,
        ["taj_brand_tracking", "has_batch_no", "is_stock_item", "brand"],
        as_dict=True,
    )
    return _validate_item_tracking_contract(data, item_code)


def _batches(row):
    batch_names = set()
    if row.get("batch_no"):
        batch_names.add(row.batch_no)
    bundle = row.get("serial_and_batch_bundle")
    if bundle:
        bundle_doc = frappe.get_doc("Serial and Batch Bundle", bundle)
        batch_names.update(e.batch_no for e in bundle_doc.get("entries") if e.batch_no)
    return batch_names


def _brand_from_batch(item, batch_name):
    field = batch_brand_field()
    data = frappe.db.get_value("Batch", batch_name, ["item", field], as_dict=True)
    if not data or data.item != item:
        frappe.throw(_("Invalid batch {0} for Item {1}.").format(batch_name, item))
    return brand(data.get(field))


def _stock_moved_before(batch_name, current_doctype, current_name):
    # SLE.batch_no covers legacy bundle-less postings.  SABB covers v16 bundle
    # rows where SLE.batch_no may be blank.  Never relabel an old batch silently.
    rows = frappe.db.sql(
        """SELECT 1 FROM `tabStock Ledger Entry`
           WHERE batch_no = %s AND is_cancelled = 0
             AND NOT (voucher_type = %s AND voucher_no = %s) LIMIT 1""",
        (batch_name, current_doctype, current_name),
    )
    if rows:
        return True
    rows = frappe.db.sql(
        """SELECT 1 FROM `tabSerial and Batch Entry` e
           INNER JOIN `tabSerial and Batch Bundle` b ON e.parent = b.name
           WHERE e.batch_no = %s AND b.docstatus = 1
             AND NOT (b.voucher_type = %s AND b.voucher_no = %s) LIMIT 1""",
        (batch_name, current_doctype, current_name),
    )
    return bool(rows)


def validate_bom(doc, method=None):
    if not enabled():
        return
    validate_bom_item_restrictions(doc)
    # Work Order Item in v16 is an Item-level row; two different required
    # brands for a single item inside ONE BOM cannot be represented safely.
    try:
        unique_brand_requirements([
            {"item_code": row.item_code, "required_brand": row.get("taj_required_brand")}
            for row in doc.get("items") or [] if row.item_code
        ])
    except MixedBrandRequirementError as exc:
        frappe.throw(_(
            "Mixed Brand requirements for Item {0}. "
            "Use separate BOMs/Work Orders for these requirements."
        ).format(exc.item_code))


def validate_batch(doc, method=None):
    if not doc.get("item"):
        return
    # Mandatory identity of a tracked Batch is not conditional on either of
    # the independent feature switches; otherwise a partially enabled site
    # may create unlabeled physical inventory.
    tracked = bool(frappe.get_cached_value("Item", doc.item, "taj_brand_tracking"))
    field = batch_brand_field()
    current = brand(doc.get(field))
    if tracked and not current:
        frappe.throw(_("Batch {0}: Actual Brand is required for a Brand-tracked Item.").format(
            doc.name or _("New")))
    if doc.is_new():
        return
    previous = brand(frappe.db.get_value("Batch", doc.name, field))
    if previous != current and _stock_moved_before(doc.name, "Batch", doc.name):
        frappe.throw(_("Batch {0}: Actual Brand cannot be changed after stock movements.").format(doc.name))



def _first_unbranded_batch_with_stock(item_code, field):
    # Historical zero-stock Batches do not block enabling Brand Tracking.
    # Stock Entry validation still rejects an unbranded Batch for a tracked Item.
    from erpnext.stock.doctype.batch.batch import get_batch_qty

    batches = frappe.get_all(
        "Batch",
        filters={"item": item_code},
        fields=["name", field],
        order_by="name",
        limit_page_length=100000,
    )

    for batch in batches:
        if brand(batch.get(field)):
            continue

        balances = get_batch_qty(
            batch_no=batch.name,
            item_code=item_code,
            for_stock_levels=True,
            consider_negative_batches=True,
            ignore_reserved_stock=True,
        ) or []

        for balance in balances:
            current_qty = flt(balance.get("qty"))
            if abs(current_qty) > 0.000001:
                return batch.name, current_qty

    return None


def validate_item_tracking_transition(doc, method=None):
    """Prevent legacy unbranded Batches or old stock history losing identity.

    The Item validator separately enforces the ordinary stock/Batch and
    Item.brand invariants; this only handles changes to an *existing* Item.
    """
    _validate_item_tracking_contract(
        doc,
        doc.get("name") or doc.get("item_code"),
    )

    if frappe.flags.in_migrate or frappe.flags.in_install:
        return
    previous = doc.get_doc_before_save()
    if not previous:
        return
    before = bool(previous.get("taj_brand_tracking"))
    after = bool(doc.get("taj_brand_tracking"))
    if before == after:
        return
    if after:
        field = batch_brand_field()  # validated hard-coded physical identity field
        missing = _first_unbranded_batch_with_stock(doc.name, field)
        if missing:
            batch_no, current_qty = missing
            frappe.throw(_(
                "Item {0}: existing Batch {1} has current stock {2} but no Actual Brand. "
                "Assign the actual Brand to current stock before enabling Brand Tracking."
            ).format(doc.name, batch_no, current_qty))
    else:
        history = frappe.db.sql(
            "SELECT 1 FROM `tabStock Ledger Entry` WHERE item_code = %s LIMIT 1",
            (doc.name,),
        )
        if history:
            frappe.throw(_(
                "Item {0}: Brand Tracking cannot be disabled after stock movements. "
                "Use a controlled migration for historical inventory."
            ).format(doc.name))

def validate_production_plan(doc, method=None):
    if not enabled() or doc.docstatus == 2:
        return
    from .planning import restricted_items, get_items_for_material_requests
    affected = restricted_items(doc)
    if not affected:
        return
    # Only check the mandatory pairing; do not mutate submitted plan rows.
    # During draft authoring, users need to press Get Items to calculate.
    existing = [r for r in doc.get("mr_items") or [] if r.item_code in affected]
    if doc.docstatus == 0 and doc._action != "submit" and not existing:
        return
    expected = get_items_for_material_requests(doc)
    expected_keys = defaultdict(float)
    actual_keys = defaultdict(float)
    for r in expected:
        if r["item_code"] in affected:
            key = (r["item_code"], brand(r.get("taj_required_brand")), r.get("warehouse") or "")
            expected_keys[key] += flt(r.get("quantity")) * (flt(r.get("conversion_factor")) or 1)
    for r in existing:
        key = (r.item_code, brand(r.get("taj_required_brand")), r.warehouse or "")
        actual_keys[key] += flt(r.quantity) * (flt(r.conversion_factor) or 1)
    for key, required_qty in expected_keys.items():
        if abs(actual_keys.get(key, 0) - required_qty) > 1e-5:
            frappe.throw(_("Production Plan brand quantities are stale for {0} ({1}). Use Get Items to refresh before submission.").format(key[0], key[1] or _("Any")))
    for key in actual_keys:
        if key not in expected_keys:
            frappe.throw(_("Production Plan contains an unexpected brand requirement for item {0}. Recalculate Material Requests.").format(key[0]))


def validate_material_request(doc, method=None):
    if not enabled() or doc.docstatus == 2:
        return
    for row in doc.get("items") or []:
        _sync_required(row, "Material Request Plan Item", row.get("material_request_plan_item"), "Material Request")
        if brand(row.get("taj_required_brand")):
            _tracked(row.item_code)  # A restricted BOM may be brand-specific even if tracking flag is off.
            if not frappe.get_cached_value("Item", row.item_code, "has_batch_no"):
                frappe.throw(_("Material Request item {0} needs Batch tracking for the required brand.").format(row.item_code))


def _resolve_stock_actual_brand(row, label, infer=True):
    """Infer the row's physical Brand only when every selected Batch agrees.

    A missing Batch identity must never be inferred from a different Batch.
    Explicit row.brand still has to match every verified Batch.
    """
    chosen = brand(row.get("brand"))
    physical = set()
    missing_identity = False
    for batch_name in _batches(row):
        actual = _brand_from_batch(row.item_code, batch_name)
        if not actual:
            missing_identity = True
            continue
        physical.add(actual)
        if chosen and actual != chosen:
            frappe.throw(_("{0}, row {1}: Batch {2} belongs to Brand {3}, not {4}.").format(
                label, row.idx, batch_name, actual, chosen
            ))
    if len(physical) > 1:
        frappe.throw(_("{0}, row {1}: Selected Batches have different actual Brands. Split the receipt into separate Brand rows.").format(
            label, row.idx
        ))
    if infer and not chosen and len(physical) == 1 and not missing_identity:
        chosen = next(iter(physical))
        row.brand = chosen
    return chosen


def _purchase_lines(doc, source_doctype, source_link, label, is_submit=False, stock=False):
    for row in doc.get("items") or []:
        _sync_required(row, source_doctype, row.get(source_link), label)
        required = brand(row.get("taj_required_brand"))
        # The native row.brand is the single purchasing identity: offered or
        # ordered on SQ/PO, physically verified on PR/stock-updating PI.
        tracking = _tracked(row.item_code)
        actual = (
            _resolve_stock_actual_brand(row, label, infer=bool(tracking or required))
            if stock else brand(row.get("brand"))
        )
        if required and not frappe.get_cached_value("Item", row.item_code, "has_batch_no"):
            frappe.throw(_("Item {0} cannot require a brand without Batch tracking.").format(row.item_code))
        if required and actual and required != actual:
            frappe.throw(_("{0}, row {1}: Brand {2} differs from required Brand {3}.").format(
                label, row.idx, actual, required
            ))
        # A quotation/order may be 'Any'; the actual Brand is mandatory only
        # when physically moving inbound stock, including direct stock invoices.
        if stock and is_submit and (tracking or required) and not actual:
            frappe.throw(_("{0}, row {1}: Select the actual received Brand for Item {2}.").format(
                label, row.idx, row.item_code
            ))


def _check_source_brand(doc, row, upstream_doctype, link, label, inherit_on_order=False):
    source_name = row.get(link)
    if not source_name:
        return
    source = _sync_required(row, upstream_doctype, source_name, label, include_brand=True)
    source_brand = brand(source.brand)
    chosen = brand(row.get("brand"))
    if source_brand and chosen and source_brand != chosen:
        frappe.throw(_("{0}, row {1}: Brand differs from referenced {2} ({3}).").format(
            label, row.idx, upstream_doctype, source_name
        ))
    # A supplier quotation is a commercial offer; inherit its requested brand
    # into a PO. Never silently claim that a physical receipt matches an order.
    if source_brand and not chosen and inherit_on_order:
        row.brand = source_brand


def validate_request_for_quotation(doc, method=None):
    if not enabled() or doc.docstatus == 2:
        return
    for row in doc.get("items") or []:
        _sync_required(row, "Material Request Item", row.get("material_request_item"), "Request for Quotation")


def validate_supplier_quotation(doc, method=None):
    if not enabled() or doc.docstatus == 2:
        return
    _purchase_lines(doc, "Request for Quotation Item", "request_for_quotation_item", "Supplier Quotation", doc._action == "submit")


def validate_purchase_order(doc, method=None):
    if not enabled() or doc.docstatus == 2:
        return
    for row in doc.get("items") or []:
        _check_source_brand(doc, row, "Supplier Quotation Item", "supplier_quotation_item", "Purchase Order", inherit_on_order=True)
    _purchase_lines(doc, "Material Request Item", "material_request_item", "Purchase Order", doc._action == "submit")


def validate_purchase_receipt(doc, method=None):
    if not enabled() or doc.docstatus == 2:
        return
    _purchase_lines(doc, "Purchase Order Item", "purchase_order_item", "Purchase Receipt", doc._action == "submit", stock=True)
    # Compare after deriving row.brand from Batch; otherwise a blank commercial
    # field could bypass the purchased supplier Brand restriction.
    for row in doc.get("items") or []:
        _check_source_brand(doc, row, "Purchase Order Item", "purchase_order_item", "Purchase Receipt")


def validate_purchase_invoice(doc, method=None):
    if not enabled() or doc.docstatus == 2:
        return
    _purchase_lines(doc, "Purchase Order Item", "po_detail", "Purchase Invoice", doc._action == "submit", stock=bool(doc.get("update_stock")))
    for row in doc.get("items") or []:
        _check_source_brand(doc, row, "Purchase Receipt Item", "pr_detail", "Purchase Invoice")
        _check_source_brand(doc, row, "Purchase Order Item", "po_detail", "Purchase Invoice")


def _bind_batches(doc):
    if doc.docstatus != 1:
        return

    requirements_enabled = enabled()

    for row in doc.get("items") or []:
        if not row.get("item_code"):
            continue
        tracked = _tracked(row.item_code)
        required = (
            brand(row.get("taj_required_brand"))
            if requirements_enabled
            else ""
        )
        if not tracked and not required:
            continue
        actual = _resolve_stock_actual_brand(row, doc.doctype)
        if not actual:
            frappe.throw(_("{0}, row {1}: Cannot bind a Batch without an actual received Brand.").format(
                doc.doctype, row.idx
            ))
        if required and required != actual:
            frappe.throw(_("{0}, row {1}: Received Brand does not match required Brand.").format(
                doc.doctype, row.idx
            ))
        batches = _batches(row)
        if frappe.get_cached_value("Item", row.item_code, "has_batch_no") and not batches:
            frappe.throw(_("Cannot establish Batch traceability on {0}, row {1}.").format(doc.doctype, row.idx))
        for batch_no in batches:
            locked_batch = frappe.get_doc("Batch", batch_no, for_update=True)
            if locked_batch.item != row.item_code:
                frappe.throw(_("Batch {0} is not linked to Item {1}.").format(batch_no, row.item_code))
            field = batch_brand_field()
            existing = brand(locked_batch.get(field))
            if existing and existing != actual:
                frappe.throw(_("Batch {0} has a different Brand. Receipt submission rolled back.").format(batch_no))
            if not existing:
                if _stock_moved_before(batch_no, doc.doctype, doc.name):
                    frappe.throw(_("Batch {0} has historical stock activity without a verified Brand. Assign Brand only after auditing its provenance.").format(batch_no))
                frappe.db.set_value("Batch", batch_no, field, actual, update_modified=True)


def bind_purchase_receipt_batches(doc, method=None):
    _bind_batches(doc)


def bind_purchase_invoice_batches(doc, method=None):
    if doc.get("update_stock"):
        _bind_batches(doc)


def validate_work_order(doc, method=None):
    """Capture BOM Brand on creation; preserve saved brand on later edits.

    Once a Work Order exists, its required-item Brands are a historical
    snapshot. Editing the BOM does NOT silently rewrite those requirements.
    An intentional BOM / multi-level setting change recalculates the snapshot.
    """
    if not enabled() or doc.docstatus == 2 or not doc.get("bom_no"):
        return

    rows = [row for row in doc.get("required_items") or [] if row.get("item_code")]
    previous = None if doc.is_new() else doc.get_doc_before_save()
    if not doc.is_new() and previous is None:
        frappe.throw(_(
            "Work Order {0}: Previous required-item Brand snapshot is unavailable; "
            "reload the document before saving."
        ).format(doc.name))

    same_bom = bool(
        previous
        and previous.get("bom_no") == doc.get("bom_no")
        and bool(previous.get("use_multi_level_bom")) == bool(doc.get("use_multi_level_bom"))
    )
    requirements = {}

    if same_bom:
        # Existing rows are authoritative even if someone later revises the
        # live BOM or its nested default BOMs.
        saved_by_name = {}
        for old in previous.get("required_items") or []:
            code = old.get("item_code")
            if not code:
                continue
            old_brand = brand(old.get("taj_required_brand"))
            if code in requirements and requirements[code] != old_brand:
                frappe.throw(_(
                    "Work Order {0}: conflicting saved Required Brands for Item {1}."
                ).format(doc.name, code))
            requirements[code] = old_brand
            saved_by_name[old.name] = old

        current_codes = {row.item_code for row in rows}
        for code, required in requirements.items():
            if required and code not in current_codes:
                frappe.throw(_(
                    "Work Order {0}: Cannot remove Brand-restricted Item {1} "
                    "without an explicit BOM change."
                ).format(doc.name, code))

        # Standard ERPNext may permit adding or substituting required items.
        # Only newly introduced Item Codes consult the current BOM.
        new_codes = current_codes - set(requirements)
        if new_codes:
            current_bom = bom_brand_map(doc.bom_no, bool(doc.get("use_multi_level_bom")))
            for code in new_codes:
                requirements[code] = brand(current_bom.get(code))

        for row in rows:
            old = saved_by_name.get(row.name)
            if old and old.item_code != row.item_code and brand(old.get("taj_required_brand")):
                frappe.throw(_(
                    "Work Order row {0}: Cannot substitute a saved Brand-restricted "
                    "Item without an explicit BOM change."
                ).format(row.idx))
    else:
        # New Work Order, or intentional change of BOM / multi-level setting.
        requirements = bom_brand_map(doc.bom_no, bool(doc.get("use_multi_level_bom")))

    for row in rows:
        expected = brand(requirements.get(row.item_code))
        current = brand(row.get("taj_required_brand"))
        # An intentional BOM change resets the source requirement; otherwise
        # reject attempts to replace an already captured Brand via API.
        if (not previous or same_bom) and current and current != expected:
            frappe.throw(_(
                "Work Order row {0}: Required Brand does not match the saved source."
            ).format(row.idx))
        row.taj_required_brand = expected


def _work_order_brand_requirements(work_order_name):
    work_order = frappe.get_doc("Work Order", work_order_name)
    requirements = {}

    for row in work_order.get("required_items") or []:
        if not row.item_code:
            continue

        required = brand(row.get("taj_required_brand"))

        if (
            row.item_code in requirements
            and requirements[row.item_code] != required
        ):
            frappe.throw(_(
                "Work Order {0}: conflicting Required Brands for Item {1}."
            ).format(work_order.name, row.item_code))

        requirements[row.item_code] = required

    return requirements


def _stock_entry_requirements(doc):
    if doc.get("work_order"):
        return _work_order_brand_requirements(doc.work_order)

    if doc.get("job_card"):
        work_order_name = frappe.db.get_value(
            "Job Card", doc.job_card, "work_order"
        )
        if work_order_name:
            return _work_order_brand_requirements(work_order_name)

    if doc.get("bom_no"):
        return bom_brand_map(
            doc.bom_no,
            bool(doc.get("use_multi_level_bom"))
        )

    return {}


def _validate_tracked_stock_entry_inbound(doc, final=False):
    if not final:
        return

    for row in doc.get("items") or []:
        if (
            not row.get("item_code")
            or not row.get("t_warehouse")
            or not _tracked(row.item_code)
        ):
            continue

        # After v16 has resolved/created the Serial and Batch Bundle but before
        # Stock Ledger is mutated, a tracked Item must not receive stock into an
        # old/unverified Batch.
        incoming_batches = _batches(row)
        if not incoming_batches:
            frappe.throw(_(
                "Stock Entry row {0}: Brand-tracked Item {1} requires a verified Batch for incoming stock."
            ).format(row.idx, row.item_code))

        for batch_name in incoming_batches:
            actual = _brand_from_batch(row.item_code, batch_name)
            if not actual:
                frappe.throw(_(
                    "Stock Entry row {0}: Batch {1} is missing its verified actual Brand."
                ).format(row.idx, batch_name))



def _validate_tracked_stock_entry_outbound(doc, final=False):
    if not final:
        return

    for row in doc.get("items") or []:
        if (
            not row.get("item_code")
            or not row.get("s_warehouse")
            or row.get("t_warehouse")
            or not _tracked(row.item_code)
        ):
            continue

        # Transfer rows are already checked by the inbound guard.
        # Outbound-only rows must have a verified physical Batch.
        batches = _batches(row)
        if not batches:
            frappe.throw(_(
                "Stock Entry row {0}: Brand-tracked Item {1} "
                "requires a verified Batch for outgoing stock."
            ).format(row.idx, row.item_code))

        for batch_name in batches:
            if not _brand_from_batch(row.item_code, batch_name):
                frappe.throw(_(
                    "Stock Entry row {0}: Batch {1} "
                    "is missing its verified actual Brand."
                ).format(row.idx, batch_name))


def preserve_pick_list_stock_entry_batches(doc, method=None):
    """Preserve the physical Batch selected on a brand-restricted Pick List.

    ERPNext v16's Pick List -> Stock Entry mapper copies batch_no but not
    use_serial_batch_fields. Without this *before_validate* guard, Stock Entry
    can auto-generate an Outward bundle for a different Batch, despite the
    earlier Pick List's selection. This guard changes only Brand-restricted
    Pick List transfers; non-restricted Item rows retain native behavior.
    """
    if (
        not enabled()
        or doc.docstatus == 2
        or not doc.get("pick_list")
        or not doc.get("work_order")
    ):
        return

    requirements = _work_order_brand_requirements(doc.work_order)
    relevant = [
        row for row in doc.get("items") or []
        if row.get("s_warehouse") and brand(requirements.get(
            row.get("original_item") or row.get("item_code")
        ))
    ]
    if not relevant:
        return

    source = frappe.get_doc("Pick List", doc.pick_list)
    if source.get("work_order") != doc.work_order or source.get("company") != doc.company:
        frappe.throw(_(
            "Stock Entry: Pick List does not belong to the selected Work Order / Company."
        ))

    by_name = {row.name: row for row in source.get("locations") or []}
    for row in relevant:
        picked = by_name.get(row.get("pick_list_item"))
        if not picked:
            frappe.throw(_(
                "Stock Entry row {0}: Brand-restricted material must reference its Pick List row."
            ).format(row.idx))
        if picked.item_code != row.item_code or picked.warehouse != row.s_warehouse:
            frappe.throw(_(
                "Stock Entry row {0}: Item / source Warehouse differs from Pick List row {1}."
            ).format(row.idx, picked.idx))

        allowed_batches = _batches(picked)
        if not allowed_batches:
            frappe.throw(_(
                "Stock Entry row {0}: Pick List row {1} has no verified Batch selection."
            ).format(row.idx, picked.idx))

        selected_batches = _batches(row)
        if selected_batches and not selected_batches.issubset(allowed_batches):
            frappe.throw(_(
                "Stock Entry row {0}: Batch differs from the selected Pick List Batch."
            ).format(row.idx))

        # A real transaction bundle already has its own selected Batches;
        # do not reuse the Pick List's voucher-specific bundle.
        if row.get("serial_and_batch_bundle"):
            continue

        if not row.get("batch_no"):
            if len(allowed_batches) != 1 or frappe.get_cached_value(
                "Item", row.item_code, "has_serial_no"
            ):
                frappe.throw(_(
                    "Stock Entry row {0}: Select an explicit Serial and Batch Bundle "
                    "matching the Pick List; automatic Batch substitution is blocked."
                ).format(row.idx))
            row.batch_no = next(iter(allowed_batches))

        # Must be set BEFORE ERPNext Stock Entry.validate() tries to pick an
        # automatic outward bundle according to FIFO/LIFO/expiry.
        row.use_serial_batch_fields = 1


def validate_stock_entry(doc, method=None, final=False):
    if doc.docstatus == 2:
        return

    _validate_tracked_stock_entry_inbound(doc, final=final)
    _validate_tracked_stock_entry_outbound(doc, final=final)

    if not enabled():
        return

    restrictions = _stock_entry_requirements(doc)
    for row in doc.get("items") or []:
        if not row.get("item_code"):
            continue

        if not row.get("s_warehouse"):
            continue

        item_code = row.get("original_item") or row.item_code
        required = brand(restrictions.get(item_code))
        if row.get("material_request_item"):
            source = _lineage_brand("Material Request Item", row.material_request_item)
            if source and required and source != required:
                frappe.throw(_("Stock Entry row {0}: Material Request Brand {1} conflicts with Work Order/BOM Brand {2}.").format(
                    row.idx, source, required
                ))
            # A blank Material Request means Any; it must not weaken a
            # specific requirement from the Work Order or BOM.
            required = required or source or ""
        # Required Brand is inherited from the authoritative MR/BOM/WO source.
        # Blank fields may be filled from that source, but a different explicit
        # value is tampering and must be rejected rather than silently replaced.
        declared = brand(row.get("taj_required_brand"))
        if required and declared and declared != required:
            frappe.throw(_("Stock Entry row {0}: Required Brand {1} conflicts with source Required Brand {2}.").format(
                row.idx, declared, required
            ))
        if required:
            row.taj_required_brand = required
        if required and not frappe.get_cached_value("Item", row.item_code, "has_batch_no"):
            frappe.throw(_("Stock Entry row {0}: Item {1} requires Batch tracking for Brand {2}.").format(row.idx, item_code, required))
        batches = _batches(row)
        # We cannot safely validate an automatically chosen bundle before
        # standard Stock Entry has finished constructing it.  Recheck at ledger.
        if required and not batches and (final or doc._action == "submit"):
            frappe.throw(_("Stock Entry row {0}: Choose a Batch matching required Brand {1}.").format(row.idx, required))
        if not batches:
            continue
        for batch_name in batches:
            actual = _brand_from_batch(row.item_code, batch_name)
            if required and actual != required:
                frappe.throw(_("Stock Entry row {0}: Batch {1} has Brand {2}; required Brand is {3}.").format(row.idx, batch_name, actual or _("Unverified"), required))
            if _tracked(row.item_code) and not actual:
                frappe.throw(_("Stock Entry row {0}: Batch {1} is missing its verified actual Brand.").format(row.idx, batch_name))
