// TAJ_NUTRITION_AUTO_V2 - one Nutrition Facts button per relevant form.
// Source and output are validated again by the Frappe server before printing.
(() => {
    const METHOD = 'taj_core.qc.nutrition_label_service.get_approved_nutrition_print_target';

    function register(doctype, getCode) {
        frappe.ui.form.on(doctype, {
            refresh(frm) {
                if (frm.is_new()) return;
                const itemCode = getCode(frm);
                if (!itemCode) return;
                frm.add_custom_button('Nutrition Facts Ar', async () => {
                    const currentCode = getCode(frm);
                    if (!currentCode) {
                        frappe.msgprint(__('Select an Item first.'));
                        return;
                    }
                    const response = await frappe.call({
                        method: METHOD,
                        args: { item_code: currentCode },
                        freeze: false,
                    });
                    const target = response.message;
                    if (!target || !target.name) return;
                    const query = new URLSearchParams({
                        doctype: target.doctype,
                        name: target.name,
                        format: target.format,
                        taj_print_item: target.item_code,
                        pdf_generator: 'chrome',
                        no_letterhead: '1',
                        language: 'ar',
                    });
                    window.open('/api/method/frappe.utils.print_format.download_pdf?' + query.toString(), '_blank', 'noopener');
                }, __('Taj'));
            },
        });
    }

    register('Item', frm => frm.doc.name);
    register('BOM', frm => frm.doc.item);
    register('Job Card', frm => frm.doc.production_item);
})();
