frappe.ui.form.on("Job Card", {
    refresh(frm) {
        if (!frm.doc.work_order || frm.is_new()) return;

        frm.add_custom_button(__("Preparation Label"), function () {
            frappe.call({
                method: "taj_core.taj_manufacturing.api.preparation_labels.render_preparation_labels_from_job_card",
                args: {
                    job_card: frm.doc.name
                },
                freeze: true,
                freeze_message: __("Generating Prep Tags..."),
                callback: function (r) {
                    const html = r.message && r.message.html;

                    if (!html) {
                        frappe.msgprint(__("No labels were generated."));
                        return;
                    }

                    const printWindow = window.open("", "_blank");

                    if (!printWindow) {
                        frappe.msgprint(__("Popup blocked. Please allow popups and try again."));
                        return;
                    }

                    printWindow.document.open();
                    printWindow.document.write(html);
                    printWindow.document.close();

                    printWindow.focus();

                    printWindow.onafterprint = function () {
                        printWindow.close();
                    };

                    setTimeout(() => {
                        printWindow.print();
                    }, 300);
                }
            });
        }, __("Print"));
    }
});