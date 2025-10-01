import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def collect_similar_items(docname):
    """
    Collect similar items in Material Request by summing quantities
    and removing duplicates while preserving the first occurrence.
    """
    try:
        # Validate document exists and is in draft state
        doc = frappe.get_doc("Material Request", docname)
        
        if doc.docstatus != 0:
            frappe.throw(_("This operation can only be performed on draft documents"))
        
        if not doc.items:
            frappe.msgprint(_("No items found in this Material Request"))
            return doc.as_dict()

        total_stock_qty = {}
        total_qty = {}
        item_count = {}
        items_to_delete = []
        first_occurrence_index = {}

        # Collect data for all items
        for idx, item in enumerate(doc.items):
            item_code = item.item_code
            
            # Initialize if first time seeing this item
            if item_code not in first_occurrence_index:
                first_occurrence_index[item_code] = idx
                total_stock_qty[item_code] = 0
                total_qty[item_code] = 0
                item_count[item_code] = 0
            
            # Sum quantities
            total_stock_qty[item_code] += flt(item.stock_qty)
            total_qty[item_code] += flt(item.qty)
            item_count[item_code] += 1

            # Mark for deletion if duplicate (keep first occurrence)
            if idx != first_occurrence_index[item_code]:
                items_to_delete.append(item)

        # Delete duplicate items (reverse to avoid index issues)
        for item in reversed(items_to_delete):
            doc.remove(item)

        # Update remaining items
        for item in doc.items:
            item_code = item.item_code
            
            if item_count[item_code] > 1:
                # For duplicated items, update quantities and reset to stock UOM
                stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
                
                item.uom = stock_uom
                item.conversion_factor = 1.0
                item.qty = total_qty[item_code]
                item.stock_qty = total_stock_qty[item_code]
                
                # Update rate if applicable
                if hasattr(item, 'rate'):
                    # You can add custom rate calculation logic here
                    pass

        # Save the document to apply changes
        doc.save()
        
        # Add summary message
        if items_to_delete:
            frappe.msgprint(_(
                "Successfully consolidated {0} duplicate item(s) into {1} unique item(s). Document has been saved."
            ).format(len(items_to_delete), len(doc.items)))
        else:
            frappe.msgprint(_("No duplicate items found to consolidate"))

        return doc.as_dict()

    except Exception as e:
        frappe.log_error(f"Error in collect_similar_items: {str(e)}")
        frappe.throw(_("Failed to collect similar items: {0}").format(str(e)))