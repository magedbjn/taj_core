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

        def consolidation_key(item):
            """Only merge Material Request rows that are operationally compatible."""
            return (
                item.item_code or "",
                item.warehouse or "",
                item.from_warehouse or "",
                item.uom or "",
                flt(item.conversion_factor or 0),
                str(item.schedule_date or ""),
            )

        # Collect data for compatible item rows.
        for idx, item in enumerate(doc.items):
            key = consolidation_key(item)

            if key not in first_occurrence_index:
                first_occurrence_index[key] = idx
                total_stock_qty[key] = 0
                total_qty[key] = 0
                item_count[key] = 0

            total_stock_qty[key] += flt(item.stock_qty)
            total_qty[key] += flt(item.qty)
            item_count[key] += 1

            # Keep the first occurrence of each compatible group.
            if idx != first_occurrence_index[key]:
                items_to_delete.append(item)

        # Delete duplicate compatible rows.
        for item in reversed(items_to_delete):
            doc.remove(item)

        # Update the surviving row without changing its UOM,
        # conversion factor, warehouse, or schedule date.
        for item in doc.items:
            key = consolidation_key(item)

            if item_count[key] > 1:
                item.qty = total_qty[key]
                item.stock_qty = total_stock_qty[key]

                # Update rate if applicable.
                if hasattr(item, "rate"):
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