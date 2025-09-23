frappe.ui.form.on('Material Request', {
    refresh: function (frm) {
        if (!frm.doc.__islocal && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Collect Similar Items'), function () {
                frappe.call({
                    method: 'taj_core.custom.material_request.collect_similar_items',
                    args: {
                        docname: frm.doc.name
                    },
                    callback: function(r) {
                        if(!r.exc) {
                            frappe.show_alert({message: __('Similar items collected'), indicator: 'green'});
                            frm.reload_doc();
                        }
                    }
                });
            }, __('Taj'));
        }
    }
});