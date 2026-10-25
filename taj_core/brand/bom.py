"""BOM-source restrictions.  No mutation of ERPNext core or submitted BOMs."""
import frappe
from frappe import _
from frappe.utils import flt

from .rules import MixedBrandRequirementError, brand, unique_brand_requirements


def _bom_rows(name):
    return frappe.get_all(
        "BOM Item", filters={"parent": name, "parenttype": "BOM"},
        fields=["name", "idx", "item_code", "stock_qty", "source_warehouse", "is_phantom_item", "is_sub_assembly_item", "taj_required_brand"],
        order_by="idx asc",
    )


def bom_components(bom_name, fg_qty, expand=False, path=None):
    """Return raw BOM demand at stock UOM, keeping source brand per row.

    Mirrors v16's BOM direct-item expansion, including default-BOM subassemblies
    when the plan or Work Order enables multi-level expansion.  It deliberately
    does not try to expand alternative item substitutions or subcontracted flows.
    """
    path = tuple(path or ())
    if bom_name in path:
        frappe.throw(_("Circular BOM hierarchy: {0}").format(bom_name))
    bom = frappe.get_cached_doc("BOM", bom_name)
    bom_qty = flt(bom.quantity)
    if bom_qty <= 0:
        frappe.throw(_("BOM {0} has invalid quantity").format(bom_name))
    results = []
    for item in _bom_rows(bom_name):
        if item.is_sub_assembly_item:
            continue  # matches ERPNext v16 BOM direct/subitems query
        if not item.item_code:
            continue
        qty = flt(item.stock_qty) * flt(fg_qty) / bom_qty
        item_data = frappe.get_cached_value(
            "Item", item.item_code, ["default_bom", "is_sub_contracted_item"], as_dict=True
        )
        nested_bom = item_data.default_bom
        if item.is_phantom_item and not nested_bom:
            frappe.throw(_("Phantom BOM row {0} has no default subassembly BOM.").format(item.name))
        nested = bool(item.is_phantom_item or expand and nested_bom)
        if nested and nested_bom:
            results.extend(bom_components(nested_bom, qty, expand, path + (bom_name,)))
        else:
            results.append({
                "item_code": item.item_code,
                "required_brand": brand(item.taj_required_brand),
                "qty": qty,
                "bom": bom_name,
                "bom_item": item.name,
                "source_warehouse": item.source_warehouse,
            })
    return results


def bom_brand_map(bom_name, multi_level=False):
    rows = bom_components(bom_name, 1, expand=bool(multi_level))
    try:
        return unique_brand_requirements(rows)
    except MixedBrandRequirementError as exc:
        frappe.throw(_(
            "Mixed Brand requirements for Item {0}. "
            "Split the BOM or use separate Work Orders for mixed requirements."
        ).format(exc.item_code))


def validate_bom_item_restrictions(doc):
    for row in doc.get("items") or []:
        required = brand(row.get("taj_required_brand"))
        if not required:
            continue
        data = frappe.get_cached_value("Item", row.item_code, ["is_stock_item", "has_batch_no"], as_dict=True)
        if not data or not data.is_stock_item or not data.has_batch_no:
            frappe.throw(_("BOM row {0}: Item {1} requires batch tracking before a specific brand can be required.").format(row.idx, row.item_code))
