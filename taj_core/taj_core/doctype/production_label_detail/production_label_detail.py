# taj_core/taj_core/doctype/production_label_detail/production_label_detail.py

import frappe
import math
from frappe.utils import flt
from frappe.model.document import Document
from erpnext.manufacturing.doctype.bom.bom import get_children as get_bom_children
from erpnext.manufacturing.doctype.production_plan.production_plan import get_bin_details


class ProductionLabelDetail(Document):
    pass


def generate_production_label_detail(plan_name, warehouse=None, skip_available=False):
    """Generate production_label_detail for a Production Plan"""
    try:
        plan = frappe.get_doc("Production Plan", plan_name)
        if not plan.po_items:
            frappe.msgprint(f"No items found in production plan {plan_name}")
            return []
            
        sub_assembly_store = []
        bin_details = frappe._dict()

        for row in plan.po_items:
            if not row.bom_no:
                frappe.log_error(f"Missing BOM for item {row.production_item} in plan {plan_name}")
                continue
                
            bom_data = []
            _get_sub_assembly_items(
                [item.production_item for item in sub_assembly_store],
                bin_details,
                row.bom_no,
                bom_data,
                row.planned_qty,
                plan.company,
                warehouse=warehouse,
                skip_available_sub_assembly_item=skip_available
            )
            _set_sub_assembly_items_level(row, bom_data, warehouse)
            sub_assembly_store.extend(bom_data)

        labels = []
        for row in sub_assembly_store:
            try:
                # Skip items with zero quantity
                if not getattr(row, "assembly_items_planned_qty", 0) or not getattr(row, "stock_qty", 0):
                    continue
                    
                bom_doc = frappe.get_cached_doc("BOM", row.assembly_items_bom_no)
                batch_size = 0
                runs = 0

                # Get batch size from operation
                if getattr(bom_doc, "with_operations", 0) and bom_doc.operations:
                    operation_found = False
                    for op in bom_doc.operations:
                        if op.operation == getattr(row, "operation", None):
                            batch_size = op.batch_size or 0
                            operation_found = True
                            break
                    
                    # Fallback: if operation not found, use first operation with batch size
                    if not operation_found and bom_doc.operations:
                        for op in bom_doc.operations:
                            if op.batch_size:
                                batch_size = op.batch_size
                                break

                # Calculate runs only if batch_size is positive
                if batch_size > 0:
                    runs = math.ceil(flt(row.assembly_items_planned_qty) / batch_size)

                labels.append({
                    "assembly_item_code": row.parent_item_code,
                    "assembly_item_name": getattr(row, "parent_item_name", ""),
                    "planned_qty": flt(getattr(row, "assembly_items_planned_qty", 0)),
                    "sub_assembly_item_code": row.production_item,
                    "sub_assembly_item_name": row.item_name,
                    "bom_item_qty": flt(getattr(row, "bom_item_qty", 0)),
                    "bom_no": row.bom_no,
                    "uom": row.uom,
                    "bom_qty": flt(getattr(row, "bom_qty", 0)),
                    "required_qty": flt(row.qty),
                    "operation": getattr(row, "operation", ""),
                    "batch_size": flt(batch_size),
                    "cooking_runs": runs,
                })
            except Exception as e:
                frappe.log_error(f"Error processing row {row.get('production_item', 'unknown')}: {str(e)}")
                continue

        return labels

    except Exception as e:
        frappe.log_error(f"Error generating production labels for plan {plan_name}: {str(e)}")
        frappe.throw(f"Failed to generate production labels: {str(e)}")


def _set_sub_assembly_items_level(row, bom_data, warehouse):
    """Set level and warehouse details for sub-assembly items"""
    is_group = False
    if warehouse:
        is_group = frappe.db.get_value("Warehouse", warehouse, "is_group") or False

    for d in bom_data:
        d.qty = d.stock_qty
        d.production_plan_item = row.name
        d.schedule_date = row.planned_start_date
        d.type_of_manufacturing = "Subcontract" if getattr(d, "is_sub_contracted_item", 0) else "In House"

        if warehouse and not is_group:
            d.fg_warehouse = warehouse


def _get_sub_assembly_items(sub_items, bin_details, bom_no, bom_data, qty_to_produce, company,
                           warehouse=None, indent=0, skip_available_sub_assembly_item=False):
    """Recursively get sub-assembly items from BOM with precise operation matching"""
    try:
        if not bom_no:
            return
            
        data = get_bom_children(parent=bom_no)
        if not data:
            return

        # Prefetch BOM Item rows for precise operation matching
        bom_items = frappe.get_all(
            "BOM Item",
            fields=["name", "item_code", "operation", "idx", "stock_qty", "qty"],
            filters={"parent": bom_no},
            order_by="idx",
        )
        
        # Create a mapping for quick lookup by item_code and idx
        bom_item_map = {}
        for item in bom_items:
            bom_item_map[(item.item_code, item.idx)] = item

        parent_code = frappe.get_cached_value("BOM", bom_no, "item")
        parent_name = frappe.get_cached_value("BOM", bom_no, "item_name")

        for i, d in enumerate(data):
            if not d.expandable:
                continue

            stock_qty = (flt(d.stock_qty) / flt(d.parent_bom_qty)) * flt(qty_to_produce)
            required_qty = stock_qty

            # Skip zero quantity items
            if stock_qty <= 0:
                continue

            # Handle available stock checking
            if skip_available_sub_assembly_item and d.item_code not in sub_items:
                bin_details.setdefault(d.item_code, get_bin_details(d, company, for_warehouse=warehouse))
                for b in bin_details[d.item_code]:
                    b.original_projected_qty = b.projected_qty
                    if b.original_projected_qty > 0:
                        if b.original_projected_qty >= stock_qty:
                            b.original_projected_qty -= stock_qty
                            stock_qty = 0
                            break
                        else:
                            stock_qty -= b.original_projected_qty
                            sub_items.append(d.item_code)
            elif warehouse:
                bin_details.setdefault(d.item_code, get_bin_details(d, company, for_warehouse=warehouse))

            # Determine operation - try multiple strategies
            operation = getattr(d, "operation", None)
            
            if not operation:
                # Strategy 1: Match by index if available
                if i < len(bom_items) and bom_items[i].item_code == d.item_code:
                    operation = bom_items[i].operation
                
                # Strategy 2: Lookup in bom_item_map
                if not operation:
                    for idx in range(1, len(bom_items) + 1):
                        bom_item = bom_item_map.get((d.item_code, idx))
                        if bom_item and bom_item.operation:
                            operation = bom_item.operation
                            break
                
                # Strategy 3: Fallback to database lookup
                if not operation:
                    operation = frappe.db.get_value(
                        "BOM Item", 
                        {"parent": bom_no, "item_code": d.item_code}, 
                        "operation"
                    ) or ""

            # Create item dictionary
            item_dict = frappe._dict({
                "actual_qty": bin_details[d.item_code][0].get("actual_qty", 0) if bin_details.get(d.item_code) else 0,
                "parent_item_code": parent_code,
                "parent_item_name": parent_name,
                "description": d.description,
                "production_item": d.item_code,
                "item_name": d.item_name,
                "stock_uom": d.stock_uom,
                "uom": d.stock_uom,
                "bom_no": d.value,
                "is_sub_contracted_item": d.is_sub_contracted_item,
                "bom_level": indent,
                "indent": indent,
                "stock_qty": stock_qty,
                "required_qty": required_qty,
                "projected_qty": bin_details[d.item_code][0].get("projected_qty", 0) if bin_details.get(d.item_code) else 0,
                "operation": operation or "",
                "assembly_items_bom_no": bom_no,
                "assembly_items_planned_qty": qty_to_produce,
                "bom_qty": d.parent_bom_qty,
                "bom_item_qty": d.stock_qty,
            })

            bom_data.append(item_dict)

            # Recursive call for nested BOMs
            if d.value:
                _get_sub_assembly_items(
                    sub_items, bin_details, d.value, bom_data, stock_qty,
                    company, warehouse, indent + 1,
                    skip_available_sub_assembly_item=skip_available_sub_assembly_item
                )

    except Exception as e:
        frappe.log_error(f"Error in _get_sub_assembly_items for BOM {bom_no}: {str(e)}")
        raise


def fill_production_label_detail(doc, method):
    """Hook function to fill production label details"""
    try:
        # Clear existing labels
        doc.set("production_label_detail", [])
        
        # Generate new labels
        labels = generate_production_label_detail(
            plan_name=doc.name,
            warehouse=getattr(doc, "sub_assembly_warehouse", None),
            skip_available=getattr(doc, "skip_available_sub_assembly_item", False)
        )

        # Append labels to document
        for label in labels:
            doc.append("production_label_detail", label)
            
        # # Show success message
        # if labels:
        #     frappe.msgprint(f"Generated {len(labels)} production labels successfully")
        # else:
        #     frappe.msgprint("No production labels generated")

    except Exception as e:
        frappe.log_error(f"Error filling production label details for {doc.name}: {str(e)}")
        frappe.throw(f"Failed to generate production labels: {str(e)}")


# Optional: Add a button to manually regenerate labels
def regenerate_production_labels(doc, method):
    """Manual regeneration of production labels"""
    fill_production_label_detail(doc, method)