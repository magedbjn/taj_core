import frappe

def update_item_batch_no(doc, method=None):
    if doc.is_new() and doc.item_group:
        item_group_has_batch = frappe.db.get_value(
            "Item Group", 
            doc.item_group, 
            "taj_has_batch_no"
        )
        
        if item_group_has_batch:
            doc.has_batch_no = 1
            doc.has_expiry_date = 1