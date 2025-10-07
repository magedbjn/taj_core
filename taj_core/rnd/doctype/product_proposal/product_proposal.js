frappe.ui.form.on('Product Proposal', {
    refresh(frm) {
        if (!frm.is_new() && !frm.doc.docstatus == 0) {
                frm.add_custom_button(__("New Version"), function () {
                    let new_pp = frappe.model.copy_doc(frm.doc);
                    frappe.set_route("Form", frm.doctype, new_pp.name);
                });
        };
    },
});