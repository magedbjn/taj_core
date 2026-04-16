frappe.ui.form.on("Work Order", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Prepare Raw Materials"), function () {
            const selected = ((frm.get_selected() || {}).required_items || []);

            open_preparation_labels_print({
                work_order: frm.doc.name,
                selected_rows: selected,
                label_mode: "raw"
            });
        }, __("Print"));

        frm.add_custom_button(__("Prepare for Cooking"), function () {
            open_preparation_labels_print({
                work_order: frm.doc.name,
                label_mode: "cooking"
            });
        }, __("Print"));
    }
});


function open_preparation_labels_print(args) {
    const printWindow = window.open("", "_blank");

    if (!printWindow) {
        frappe.msgprint(__("Popup was blocked by the browser"));
        return;
    }

    printWindow.document.open();
    printWindow.document.write("<html><body style='font-family:Arial;padding:20px;'>Loading...</body></html>");
    printWindow.document.close();

    frappe.call({
        method: "taj_core.taj_manufacturing.api.preparation_labels.render_preparation_labels_html",
        args: args,
        freeze: true,
        callback: function (r) {
            const html = r.message && r.message.html;

            if (!html) {
                printWindow.close();
                frappe.msgprint(__("Unable to render label HTML"));
                return;
            }

            printWindow.document.open();
            printWindow.document.write(html);
            printWindow.document.close();
            printWindow.focus();

            printWindow.onafterprint = function () {
                printWindow.close();
            };

            setTimeout(function () {
                printWindow.print();
            }, 300);
        },
        error: function (r) {
            let msg = __("Server error while rendering labels");

            if (r && r._server_messages) {
                try {
                    const messages = JSON.parse(r._server_messages);
                    if (messages && messages.length) {
                        msg = messages.join("<br>");
                    }
                } catch (e) {}
            }

            printWindow.document.open();
            printWindow.document.write(`
                <html>
                    <body style="font-family:Arial;padding:20px;">
                        <h3>Steamer Labels Error</h3>
                        <div>${msg}</div>
                    </body>
                </html>
            `);
            printWindow.document.close();
        }
    });
}