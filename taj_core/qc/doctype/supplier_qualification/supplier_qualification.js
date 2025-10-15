// في supplier_qualification.js - إضافة منع التكرار
frappe.ui.form.on('Supplier Approved Item', {
    item(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);
        if (!row.item) return;

        // التحقق من التكرار
        const existingItems = new Set();
        (frm.doc.sq_items || []).forEach(item_row => {
            if (item_row.name !== row.name && item_row.item) {
                existingItems.add(item_row.item);
            }
        });

        if (existingItems.has(row.item)) {
            frappe.msgprint(__('Item {0} is already added to the table. Duplicates are not allowed.', [row.item]));
            frappe.model.set_value(cdt, cdn, 'item', '');
            frm.refresh_field('sq_items');
        }
    }
});

// تحديث apply_state_ui لمنع التكرار
function apply_state_ui(frm) {
    const status = frm.doc.approval_status || '';
    const show_items = (status === 'Partially Approved');

    frm.toggle_display('approved_item_tab', show_items);
    frm.toggle_display('sq_items', show_items);

    if (frm.fields_dict.sq_items) {
        frm.fields_dict.sq_items.grid.wrapper.toggleClass('hidden', !show_items);
        frm.fields_dict.sq_items.grid.cannot_add_rows = !show_items;
        frm.fields_dict.sq_items.grid.cannot_delete_rows = !show_items;
        
        // إزالة التكرارات تلقائياً
        if (frm.doc.sq_items && frm.doc.sq_items.length > 0) {
            const seen = new Set();
            const uniqueItems = [];
            frm.doc.sq_items.forEach(row => {
                if (row.item && !seen.has(row.item)) {
                    seen.add(row.item);
                    uniqueItems.push(row);
                }
            });
            if (uniqueItems.length !== frm.doc.sq_items.length) {
                frm.doc.sq_items = uniqueItems;
                frm.refresh_field('sq_items');
            }
        }
        
        frm.fields_dict.sq_items.refresh();
    }

    if (!show_items && Array.isArray(frm.doc.sq_items) && frm.doc.sq_items.length) {
        frm.clear_table('sq_items');
        frm.refresh_field('sq_items');
    }

    frm.set_df_property('sq_items', 'hidden', !show_items);
    frm.set_df_property('approved_item_tab', 'hidden', !show_items);
}