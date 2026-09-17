frappe.ui.form.on("Checklist Question Template", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("New Schedule"), () => {
                frappe.new_doc("Checklist Schedule", { template: frm.doc.name });
            }, __("Schedule"));

            frm.add_custom_button(__("View Schedules"), () => {
                frappe.set_route("List", "Checklist Schedule", { template: frm.doc.name });
            }, __("Schedule"));
        }
    }
});
