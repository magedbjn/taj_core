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
                try {
                if (frm.is_dirty()) {
                    await frm.save();
                }

                const r = await frm.call({ doc: frm.doc, method: 'create_item' });
                if (!r || !r.message) return;

                // Existing item with the same name
                if (r.message.exists) {
                    const code = r.message.item_code;
                    const question = __('An Item with the same name already exists ({0}). Do you want to use this Item Code?', [code]);

                    frappe.confirm(
                    question,
                    async () => {
                        // YES: persist on the server to avoid client-side save issues
                        await frm.call({
                        doc: frm.doc,
                        method: 'link_existing_item',
                        args: { item_code: code }
                        });

                        await frm.reload_doc();
                        frappe.show_alert({ message: __('Linked to existing Item: {0}', [code]), indicator: 'green' });
                    },
                    () => {
                        // NO: do nothing
                        frappe.show_alert({ message: __('Cancelled — no changes made.'), indicator: 'yellow' });
                    }
                    );
                    return;
                }

                // Newly created item
                if (r.message.item_code) {
                    await frm.set_value('item_code', r.message.item_code);
                    await frm.save();
                    await frm.reload_doc();
                    frappe.show_alert({ message: __('Item created: {0}', [r.message.item_code]), indicator: 'green' });
                }
                } catch (err) {
                const msg = (err && err.message) ? err.message : __('Failed to create/link Item.');
                frappe.msgprint(msg);
                frappe.show_alert({ message: __('Failed to create/link Item. See console for details.'), indicator: 'red' });
                // console.error(err);
                }
            }, group);
            }
        }
    }
});