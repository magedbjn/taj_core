import frappe

def execute():
    """
    Cleanup patch for Intern Sales Order doctype removal
    """
    
    frappe.db.sql("DELETE FROM `tabDocField` WHERE `parent` = 'Intern Sales Order'")
    print("✓ Cleaned tabDocField")
    
    frappe.db.sql("DELETE FROM `tabSeries` WHERE `name` LIKE 'Intern Sales Order%'")
    print("✓ Cleaned tabSeries")
    
    # 4. Commit changes
    frappe.db.commit()
    
    # 5. Clear cache
    frappe.clear_cache()
    
    print("✅ Cleanup completed successfully!")