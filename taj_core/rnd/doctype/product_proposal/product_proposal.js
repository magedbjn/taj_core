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
