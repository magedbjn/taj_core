"""Brand-aware Work Order Pick Lists for Frappe/ERPNext v16.

Frappe's extend_doctype_class hook adds this mixin without overriding ERPNext's
Pick List controller.  Every stock lookup, reservation adjustment and UOM
split uses ERPNext's native functions.  A blank BOM required Brand delegates
completely to the native Pick List behavior.
"""

import frappe
from frappe import _
from frappe.utils import flt

from .rules import brand
from .setup import batch_brand_field
from .validation import _batches, _brand_from_batch, _work_order_brand_requirements, enabled


def requirements_for_pick_list(pick_list):
    """Return (work_order, {item_code: required_brand}) for WO picking."""
    if not enabled():
        return None, {}
    # Check the Work Order link even if a caller tampers with Purpose.
    if not pick_list.get("work_order"):
        return None, {}
    work_order = frappe.get_doc("Work Order", pick_list.work_order)
    # Do not reread a possibly changed BOM for an already-approved WO.
    return work_order, _work_order_brand_requirements(work_order.name)


def validate_pick_list(doc, method=None):
    """Reject wrong physical batches on save, submit, and update-after-submit.

    This is a *server-side* rule, not a read-only UI field or client script.
    No batch selection is allowed to silently bypass the source Work Order BOM.
    """
    work_order, requirements = requirements_for_pick_list(doc)
    if not work_order:
        return
    for row in doc.get("locations") or []:
        expected = brand(requirements.get(row.item_code))
        provided = brand(row.get("taj_required_brand"))
        if provided and provided != expected:
            frappe.throw(_("Pick List row {0}: Required Brand must match the Work Order BOM.").format(row.idx))
        row.taj_required_brand = expected
        if not expected:
            continue
        batch_names = _batches(row)
        quantity = max(flt(row.get("stock_qty")), flt(row.get("picked_qty")))
        if quantity > 0 and not batch_names:
            frappe.throw(_("Pick List row {0}: Select a Batch with required Brand {1} for Item {2}.").format(
                row.idx, expected, row.item_code
            ))
        for batch_no in batch_names:
            actual = _brand_from_batch(row.item_code, batch_no)
            if actual != expected:
                frappe.throw(_("Pick List row {0}: Batch {1} has Brand {2}; required Brand is {3}.").format(
                    row.idx, batch_no, actual or _("Unverified"), expected
                ))


def _warehouse_descendants(name):
    if not name:
        return []
    from frappe.utils.nestedset import get_descendants_of

    # Preserve the source warehouse itself, including ordinary leaf warehouses.
    return [name, *(get_descendants_of("Warehouse", name) or [])]


def _allowed_warehouses(pick_list, work_order, item_code):
    """Use the same parent/Work Order source warehouse priorities as core."""
    parent = pick_list.get("parent_warehouse")
    if not parent:
        parent = frappe.db.get_value(
            "Warehouse",
            {"company": pick_list.company, "parent_warehouse": ["IS", "NOT SET"], "is_group": 1},
        )
    base = _warehouse_descendants(parent)
    source = next((
        row.source_warehouse
        for row in work_order.get("required_items") or []
        if row.item_code == item_code and row.source_warehouse
    ), None)
    priority = _warehouse_descendants(source)
    # `[]` means native company-wide search when ERPNext has no root warehouse.
    allowed = list(dict.fromkeys(priority + base))
    return allowed, priority


def _brand_stock_locations(pick_list, work_order, item_code, required_brand, picked_details, quantity):
    """Available native batch locations, restricted by verified physical Brand."""
    from erpnext.stock.doctype.pick_list.pick_list import (
        filter_locations_by_picked_materials,
        get_available_item_locations_for_batched_item,
        get_available_item_locations_for_serial_and_batched_item,
    )

    warehouses, priority = _allowed_warehouses(pick_list, work_order, item_code)
    is_serialized = frappe.get_cached_value("Item", item_code, "has_serial_no")
    if is_serialized:
        locations = get_available_item_locations_for_serial_and_batched_item(
            item_code, warehouses, quantity, pick_list.company,
            consider_rejected_warehouses=bool(pick_list.get("consider_rejected_warehouses")),
        )
    else:
        locations = get_available_item_locations_for_batched_item(
            item_code, warehouses, pick_list.company,
            consider_rejected_warehouses=bool(pick_list.get("consider_rejected_warehouses")),
        )

    names = list({r.batch_no for r in locations if r.get("batch_no")})
    if names:
        physical_field = batch_brand_field()
        batch_values = frappe.get_all(
            "Batch", filters={"name": ["in", names], "item": item_code},
            fields=["name", physical_field], limit_page_length=len(names),
        )
        allowed_batches = {
            entry.name for entry in batch_values
            if brand(entry.get(physical_field)) == required_brand
        }
        locations = [r for r in locations if r.batch_no in allowed_batches]
    else:
        locations = []
    if picked_details:
        locations = filter_locations_by_picked_materials(locations, picked_details)

    if priority:
        high = [r for r in locations if r.warehouse in priority]
        low = [r for r in locations if r.warehouse not in priority]
        locations = high + low
    return locations


def _rebuild_restricted_locations(doc, work_order, requirements, templates):
    """Recalculate only as-yet-unpicked restricted rows using native stock APIs.

    This runs AFTER core set_item_locations; no global monkeypatching and no
    copied ERPNext controller methods.  Picked rows are retained and counted
    against availability by the native Pick List reservation calculation.
    """
    from erpnext.stock.doctype.pick_list.pick_list import get_items_with_location_and_quantity

    restricted = {code: brand(value) for code, value in requirements.items() if brand(value)}
    if not restricted or not templates:
        return
    relevant = [t for t in templates if t.get("item_code") in restricted]
    if not relevant:
        return

    # Native method sees current picked rows (but not unpicked auto-suggestions)
    # and reservations in other Pick Lists, including their Serial/Batch Bundles.
    picked = doc.get_picked_items_details([frappe._dict(t) for t in relevant])
    by_item = {}
    for template in relevant:
        code = template["item_code"]
        if code not in by_item:
            total_qty = sum(
                flt(t.get("stock_qty")) or flt(t.get("qty")) * flt(t.get("conversion_factor") or 1)
                for t in relevant if t["item_code"] == code
            )
            by_item[code] = _brand_stock_locations(
                doc, work_order, code, restricted[code], picked.get(code, {}), total_qty
            )

    new_rows = []
    for template in relevant:
        code = template["item_code"]
        target = flt(template.get("stock_qty")) or flt(template.get("qty")) * flt(template.get("conversion_factor") or 1)
        if target <= 0:
            continue
        fields = frappe._dict(dict(template))
        fields.stock_qty = target
        fields.picked_qty = 0
        remaining_stock = {code: by_item[code]}
        selected = get_items_with_location_and_quantity(
            fields, remaining_stock, doc.docstatus
        )
        # get_items_with_location_and_quantity records the remainder in the
        # mapping, which may be a *new* list after a partial batch allocation.
        by_item[code] = remaining_stock.get(code) or []
        used = sum(flt(x.get("stock_qty")) for x in selected)
        if used + 1e-5 < target:
            frappe.throw(_("Pick List: Not enough unreserved Batch stock of required Brand {0} for Item {1}. Needed {2}, available {3}. Do not use a different Brand.").format(
                restricted[code], code, target, used
            ))
        for location in selected:
            row = dict(template)
            row.update(location)
            row.pop("name", None)
            row.pop("idx", None)
            row.pop("parent", None)
            row.pop("parenttype", None)
            row.pop("parentfield", None)
            row["picked_qty"] = 0
            row["serial_and_batch_bundle"] = None
            row["taj_required_brand"] = restricted[code]
            new_rows.append(row)

    # Mutate the table only after every restricted row can be safely assigned.
    for row in list(doc.get("locations") or []):
        if row.item_code in restricted and not flt(row.get("picked_qty")):
            doc.remove(row)
    for row in new_rows:
        doc.append("locations", row)


class BrandAwarePickList:
    """v16 extend_doctype_class mixin; super() always runs ERPNext's method."""

    @frappe.whitelist(methods=["POST"])
    def set_item_locations(self, save=False):
        work_order, requirements = requirements_for_pick_list(self)
        relevant = {code for code, value in requirements.items() if brand(value)}
        templates = [
            dict(row.as_dict()) for row in self.get("locations") or []
            if row.item_code in relevant and not flt(row.get("picked_qty"))
        ]
        # Avoid duplicating ERPNext's warehouse, reservation, UOM and picking
        # logic. Frappe v16 extension resolves super() to the native controller.
        response = super().set_item_locations(save=False)
        if work_order and templates:
            _rebuild_restricted_locations(self, work_order, requirements, templates)
            validate_pick_list(self)
        if save:
            self.save()
        return response
