frappe.ui.form.on('Product Proposal', {
    refresh(frm) {
        frm.fields_dict['pp_items'].grid.get_field('pre_bom').get_query = function(doc, cdt, cdn) {
            return {
                filters: [
                    ['BOM', 'name', 'like', 'BOM-PRE-%']
                ]
            };
        };

        if (frm.doc.docstatus !== 1) {
            const label = __('Duplicate');
            frm.page.menu.find(`[data-label="${encodeURIComponent(label)}"]`).parent().addClass('hidden');
        }

        if (frm.doc.docstatus === 1) {
               
            // New Version
            frm.add_custom_button(__("New Version"), function () {
                let new_pp = frappe.model.copy_doc(frm.doc);
                frappe.set_route("Form", frm.doctype, new_pp.name);
            });

            const group = __('Create');
            if (!frm.doc.item_code) {
                frm.add_custom_button(__('Item'), async () => {
                    if (frm.is_dirty()) {
                        await frm.save();
                    }
                    frm.call('create_item')
                        .then((r) => {
                            if (r && r.message && r.message.item_code) {
                                frm.set_value('item_code', r.message.item_code);
                                frappe.show_alert({
                                    message: __('Item created: {0}', [r.message.item_code]),
                                    indicator: 'green'
                                });
                                frm.reload_doc();
                            }
                        })
                        .catch(() => {
                            frappe.msgprint(__('Failed to create Item. See console for details.'));
                        });
                }, group);
            }
        }
    }
});