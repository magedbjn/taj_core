frappe.ui.form.on('Product Proposal', {
    refresh: function(frm) {
        frm.set_df_property('product_name', 'read_only', frm.doc.item_code ? 1 : 0);
        // if (frm.doc.item_code) {
        //     frm.set_df_property('product_name', 'read_only', 1);
        // } else {
        //     frm.set_df_property('product_name', 'read_only', 0);
        // }

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

        // زر Sync Preparation BOM يظهر إذا السند محفوظ (مش جديد) وفيه صفوف pp_items
        if (!frm.is_new() && (frm.doc.pp_items || []).length) {
            const prep_group = __('Preparation');

            frm.add_custom_button(__('Sync Preparation BOM'), async () => {
                try {
                    const r = await frm.call({
                        doc: frm.doc,
                        method: 'sync_preparation_bom',
                    });

                    if (!r || !r.message) {
                        frappe.show_alert({ message: __('No changes were made.'), indicator: 'yellow' });
                        return;
                    }

                    const { updated, total, missing_items } = r.message;

                    if (updated) {
                        frappe.show_alert({
                            message: __('Updated Preparation BOM for {0} row(s).', [updated]),
                            indicator: 'green',
                        });
                    } else {
                        frappe.show_alert({
                            message: __('No rows required update.'), 
                            indicator: 'yellow',
                        });
                    }

                    if (missing_items && missing_items.length) {
                        frappe.msgprint({
                            title: __('Missing Preparation Items'),
                            message: __(
                                'No Preparation Items were found for the following Item Codes: {0}',
                                [missing_items.join(', ')]
                            ),
                            indicator: 'orange',
                        });
                    }

                    // حدّث الفورم عشان تشوف pre_bom بعد التحديث
                    await frm.reload_doc();
                } catch (err) {
                    frappe.msgprint(__('Failed to sync Preparation BOM. See console for details.'));
                    // console.error(err);
                }
            }, prep_group);
        }
    }
});

// Product Proposal → Client Script
frappe.ui.form.on('Product Proposal Raw Material', {
  item_code(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    // لا تعمل شيء إذا ما فيه item_code أو لو pre_bom ممتلئ مسبقًا
    if (!row.item_code || row.pre_bom) return;

    // اسحب أحدث bom_no من Preparation Items المطابق لـ item_code
    frappe.call({
      method: 'frappe.client.get_list',
      args: {
        doctype: 'Preparation Items',
        fields: ['bom_no'],
        filters: { item_code: row.item_code },
        limit_page_length: 1,
        order_by: 'modified desc'
      },
      callback: (r) => {
        const rec = (r.message && r.message[0]) || null;
        if (rec && rec.bom_no) {
          // إن كان اسم الحقل في الجدول هو pre_bom
          frappe.model.set_value(cdt, cdn, 'pre_bom', rec.bom_no);

          // لو اسم الحقل عندك هو bom_no بدل pre_bom، استخدم السطر التالي:
          // frappe.model.set_value(cdt, cdn, 'bom_no', rec.bom_no);
        }
      }
    });
  }
});
