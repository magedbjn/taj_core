"""Brand-aware shortage planning for ERPNext v16 Production Plan.

With no BOM brand requirement, delegates *entirely* to ERPNext.  In the rare
restricted case it replaces rows for the affected Item Codes using batch-
qualified physical stock.  It is deliberately conservative: unreceived POs
are NOT treated as brand-specific physical stock.  Unsupported modes abort,
never silently fall back to non-brand-aware planning.
"""
import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, nowdate, nowtime
from erpnext.manufacturing.doctype.production_plan import production_plan as standard
from erpnext.stock.doctype.batch.batch import get_available_batches
from erpnext.setup.doctype.item_group.item_group import get_item_group_defaults

from .bom import bom_components
from .rules import allocate_requirements, brand
from .setup import batch_brand_field
from .validation import require_tracked_brand


def _plan_demands(doc):
    demands = []
    po_items = doc.get("po_items") or doc.get("items") or []
    for po in po_items:
        if not po.get("item_code"):
            continue
        bom = po.get("bom") or po.get("bom_no")
        planned_qty = flt(po.get("required_qty") or po.get("planned_qty"))
        if planned_qty <= 0:
            continue
        components = (
            bom_components(bom, planned_qty, bool(po.get("include_exploded_items") or doc.get("sub_assembly_items")))
            if bom else [{"item_code": po.get("item_code"), "required_brand": "", "qty": planned_qty, "source_warehouse": ""}]
        )
        for component in components:
            component["main_bom"] = bom or ""
            component["main_item_code"] = po.get("item_code")
            component["sales_order"] = po.get("sales_order")
            component["schedule_date"] = po.get("planned_start_date") or ""
            demands.append(component)
    for sub in doc.get("sub_assembly_items") or []:
        if sub.get("type_of_manufacturing") == "Material Request" and sub.get("production_item"):
            demands.append({
                "item_code": sub.production_item,
                "qty": flt(sub.get("qty") or sub.get("required_qty")),
                "required_brand": "", "source_warehouse": "",
                "main_bom": "", "main_item_code": sub.production_item,
                "sales_order": "", "schedule_date": sub.get("schedule_date") or "",
            })
    return demands


def restricted_items(doc):
    restricted = set()
    for component in _plan_demands(doc):
        if require_tracked_brand(
            component["item_code"], component.get("required_brand"), "Production Plan"
        ):
            restricted.add(component["item_code"])
    return restricted


def _warehouse_for(item_code, component, company, target):
    warehouse = target or component.get("source_warehouse")
    if not warehouse:
        warehouse = frappe.db.get_value("Item Default", {"parent": item_code, "company": company}, "default_warehouse")
    if not warehouse:
        warehouse = get_item_group_defaults(item_code, company).get("default_warehouse")
    if not warehouse:
        frappe.throw(_("Set a warehouse for item {0} before brand-aware planning.").format(item_code))
    return warehouse


def _leaf_warehouses(root, company):
    # Group Warehouse may be used as an *availability scope*, never as MR target.
    row = frappe.db.get_value("Warehouse", root, ["is_group", "company"], as_dict=True)
    if not row or row.company != company:
        frappe.throw(_("Invalid warehouse or company for brand planning: {0}").format(root))
    if not row.is_group:
        return [root]
    from frappe.utils.nestedset import get_descendants_of
    children = get_descendants_of("Warehouse", root)
    return frappe.get_all(
        "Warehouse", filters={"name": ["in", children], "company": company, "is_group": 0}, pluck="name"
    )


def _stock_by_brand(item_code, scope, company):
    item = frappe.get_cached_value("Item", item_code, ["has_batch_no", "is_stock_item"], as_dict=True)
    if not item or not item.has_batch_no or not item.is_stock_item:
        frappe.throw(_("Brand-restricted item {0} must be a batch-tracked stock item.").format(item_code))
    balances = defaultdict(float)
    for wh in _leaf_warehouses(scope, company):
        # Native ERPNext v16 selection already excludes invalid/expired batches
        # according to Stock Settings and existing serial/batch reservations.
        batch_qty = get_available_batches(frappe._dict({
            "item_code": item_code,
            "warehouse": wh,
            "company": company,
            "posting_date": nowdate(),
            "posting_time": nowtime(),
        }))
        if not batch_qty:
            continue
        batch_names = list(batch_qty)
        names_to_brand = dict(frappe.get_all(
            "Batch", filters={"name": ["in", batch_names], "item": item_code},
            fields=["name", batch_brand_field()], as_list=True,
        ))
        for batch_no, qty in batch_qty.items():
            # Legacy batches without a verified brand only count for 'Any'.
            if batch_no not in names_to_brand:
                frappe.throw(_("Batch {0} does not belong to Item {1}.").format(batch_no, item_code))
            balances[brand(names_to_brand[batch_no])] += max(0, flt(qty))
    return balances


def _ensure_projection_can_be_attributed(item_code, scope, company):
    """Fail closed on unresolved Bin commitments; they have no proven Brand.

    Native Projected Qty includes open orders and reservations. We cannot
    safely assign them to an actual Batch Brand before physical verification.
    """
    meta = frappe.get_meta("Bin")
    commitment_names = (
        "ordered_qty", "requested_qty", "planned_qty", "reserved_qty",
        "reserved_qty_for_production", "reserved_qty_for_sub_contract",
        "reserved_qty_for_subcontracting", "reserved_qty_for_production_plan",
        "indented_qty",
    )
    relevant = [name for name in commitment_names if meta.has_field(name)]
    cols = ["actual_qty", "projected_qty", *relevant]
    for wh in _leaf_warehouses(scope, company):
        balance = frappe.db.get_value(
            "Bin", {"item_code": item_code, "warehouse": wh}, cols, as_dict=True
        )
        if not balance:
            continue
        unresolved = [name for name in relevant if abs(flt(balance.get(name))) > 0.000001]
        if abs(flt(balance.get("projected_qty")) - flt(balance.get("actual_qty"))) > 0.000001:
            unresolved.append("projected_qty")
        if unresolved:
            frappe.throw(_(
                "Cannot calculate Brand-specific Projected Qty for Item {0} in Warehouse {1}: "
                "open orders/reservations are not attributable to verified Batches ({2}). "
                "Review the outstanding documents; do not create duplicate purchasing requests."
            ).format(item_code, wh, ", ".join(sorted(set(unresolved)))))


def _generate_brand_rows(doc, demand, affected):
    if doc.get("include_safety_stock"):
        frappe.throw(_("Brand-aware planning with Include Safety Stock is not yet supported. Disable it or plan these items separately."))
    scopes = {}
    grouped = defaultdict(float)
    for comp in demand:
        code = comp["item_code"]
        if code not in affected:
            continue
        item = frappe.get_cached_value(
            "Item", code,
            ["item_name", "stock_uom", "purchase_uom", "min_order_qty", "safety_stock", "default_material_request_type", "is_sub_contracted_item"],
            as_dict=True,
        )
        if item.is_sub_contracted_item:
            frappe.throw(_("Restricted brand planning is not supported for subcontracted item {0}.").format(code))
        if item.default_material_request_type == "Material Transfer":
            frappe.throw(_("Brand-specific Material Transfer requests require verified Batch source allocation; use a validated Pick List / Stock Entry until implemented."))
        target = _warehouse_for(code, comp, doc.company, doc.get("for_warehouse"))
        if frappe.db.get_value("Warehouse", target, "is_group"):
            frappe.throw(_("Select a leaf warehouse for purchase of Item {0}.").format(code))
        scope = doc.get("raw_material_group_warehouse") or target
        scope_key = (code, scope)
        scopes[scope_key] = item
        # Preserve BOM and sales-order identity; never merge A with B or with Any.
        key = (
            code, scope, target, brand(comp.get("required_brand")), comp.get("sales_order") or "",
            comp.get("main_bom") or "", comp.get("main_item_code") or "",
        )
        grouped[key] += flt(comp["qty"])

    requirements = []
    for key, qty in grouped.items():
        code, scope, target, required_brand, sales_order, main_bom, main_code = key
        requirements.append({
            "item_code": code, "warehouse": scope, "target_warehouse": target, "required_brand": required_brand,
            "sales_order": sales_order, "main_bom": main_bom, "main_item_code": main_code,
            "qty": qty,
        })
    requirements.sort(key=lambda row: (
        row["item_code"], row["warehouse"], row["target_warehouse"], row["sales_order"], row["main_bom"], row["required_brand"]
    ))
    available = {}
    # v16's "Consider Projected Qty" defaults to true. With it OFF, follow
    # ERPNext and request the full BOM qty, ignoring inventory entirely.
    # With it ON, count verified physical Batch balances only after proving
    # no unattributable projected commitments exist for these items.
    if doc.get("ignore_existing_ordered_qty"):
        for code, scope in scopes:
            _ensure_projection_can_be_attributed(code, scope, doc.company)
            for actual_brand, quantity in _stock_by_brand(code, scope, doc.company).items():
                available[(code, scope, actual_brand)] = quantity

    allocated = allocate_requirements(requirements, available)
    results = []
    for row in allocated:
        if row["shortage_qty"] <= 1e-9:
            continue
        code, scope = row["item_code"], row["warehouse"]
        item = scopes[(code, scope)]
        stock_qty = flt(row["shortage_qty"])
        uom = item.purchase_uom or item.stock_uom
        conversion = standard.get_uom_conversion_factor(code, uom)
        if not conversion or conversion <= 0:
            frappe.throw(_("Invalid purchase UOM conversion for {0}").format(code))
        min_order_qty = flt(item.min_order_qty) if doc.get("consider_minimum_order_qty") else 0
        qty = standard._quantity_in_purchase_uom(stock_qty, conversion, min_order_qty)
        if flt(qty) <= 0:
            continue
        planned = flt(row["qty"])
        value = {
            "item_code": code,
            "item_name": item.item_name,
            "quantity": qty,
            "conversion_factor": conversion,
            "required_bom_qty": planned,
            "stock_uom": item.stock_uom,
            "warehouse": row["target_warehouse"],
            "actual_qty": flt(row["available_qty"]),
            # Not a projected Bin quantity: this conservative planner counts
            # only eligible on-hand batch stock, not unknown-brand incoming POs.
            "projected_qty": flt(row["available_qty"]),
            "ordered_qty": 0,
            "reserved_qty_for_production": 0,
            "safety_stock": 0,
            "min_order_qty": flt(item.min_order_qty),
            "material_request_type": item.default_material_request_type or "Purchase",
            "sales_order": row["sales_order"],
            "uom": uom,
            "main_item_code": row["main_item_code"],
            "from_bom": row["main_bom"],
            "taj_required_brand": row["required_brand"],
            "taj_available_brand_qty": flt(row["available_qty"]),
        }
        results.append(value)
    return results


@frappe.whitelist()
def get_items_for_material_requests(doc, warehouses=None, get_parent_warehouse_data=None):
    # Preserve ERPNext v16's permission boundary before any custom BOM/stock
    # inspection. The standard function performs the same check again when
    # delegated to below.
    frappe.has_permission("Production Plan", "read", throw=True)

    # The standard whitelisted API receives a JSON document from the browser,
    # whereas Production Plan.validate calls us with a Document object.
    # Normalize both to a plain mapping before running ERPNext's native logic.
    if isinstance(doc, str):
        payload = json.loads(doc)
    elif isinstance(doc, dict):
        # frappe._dict is a dict; its missing attributes resolve to None,
        # so hasattr(doc, "as_dict") is not a safe Document type check.
        payload = doc
    elif callable(getattr(doc, "as_dict", None)):
        payload = doc.as_dict()
    else:
        payload = doc
    document = frappe._dict(payload)
    demand = _plan_demands(document)
    affected = set()
    for component in demand:
        if require_tracked_brand(
            component["item_code"], component.get("required_brand"), "Production Plan"
        ):
            affected.add(component["item_code"])
    if not affected:
        return standard.get_items_for_material_requests(payload, warehouses, get_parent_warehouse_data)
    if warehouses:
        frappe.throw(_("Stock transfer and CSV inventory availability using restricted brands must be planned with batch-specific quantities; standard Item-only aggregation is disabled."))
    standard_rows = standard.get_items_for_material_requests(payload, warehouses, get_parent_warehouse_data)
    clean = [r for r in standard_rows if r.get("item_code") not in affected]
    return clean + _generate_brand_rows(document, demand, affected)
