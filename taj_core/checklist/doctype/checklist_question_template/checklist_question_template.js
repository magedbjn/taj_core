frappe.ui.form.on("Checklist Question Template", {
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Create Checklist Answer"), async () => {
                const r = await frappe.call({
                    method: "taj_core.checklist.api.create_checklist_answer",
                    args: { template_name: frm.doc.name },
                    freeze: true,
                    freeze_message: __("Creating Checklist Answer...")
                });

                const message = r.message || {};
                if (message.name) {
                    frappe.show_alert({
                        message: message.notice || __("Checklist Answer created successfully."),
                        indicator: message.reused_existing ? "orange" : "green"
                    });

                    if (message.reused_existing && message.open_reference) {
                        frappe.msgprint({
                            title: __("Open Checklist Reused"),
                            indicator: "orange",
                            message: __(
                                "An open checklist already exists for this template without answers. The same document was reused for the new cycle.<br><br><strong>Document:</strong> {0}<br><strong>Date:</strong> {1}",
                                [message.open_reference.name || "-", message.open_reference.posting_date || "-"]
                            )
                        });
                    }

                    frappe.set_route("Form", "Checklist Answer", message.name);
                }
            });
        }
    }
});
