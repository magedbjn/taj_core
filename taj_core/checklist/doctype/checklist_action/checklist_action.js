frappe.ui.form.on("Checklist Action", {
    refresh(frm) {
        if (frm.is_new()) return;

        if (["Open", "Waiting"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Start Action"), async () => {
                await frm.call("start_action");
                await frm.reload_doc();
            });
        }

        if (!["Closed", "Pending Verification"].includes(frm.doc.status)) {
            frm.add_custom_button(__("Set Waiting"), () => {
                frappe.prompt(
                    [
                        {
                            fieldname: "reason",
                            fieldtype: "Small Text",
                            label: __("Waiting Reason"),
                            reqd: 1,
                        },
                    ],
                    async (values) => {
                        await frm.call("set_waiting", { reason: values.reason });
                        await frm.reload_doc();
                    },
                    __("Set Waiting")
                );
            });

            frm.add_custom_button(__("Submit Resolution"), async () => {
                if (!String(frm.doc.resolution_details || "").trim()) {
                    frappe.msgprint(__("Enter What Was Done before submitting the resolution."));
                    frm.scroll_to_field("resolution_details");
                    return;
                }
                if (frm.is_dirty()) await frm.save();
                await frm.call("submit_resolution", {
                    resolution_details: frm.doc.resolution_details,
                });
                await frm.reload_doc();
            });
        }

        if (frm.doc.status === "Pending Verification") {
            frm.add_custom_button(__("Verify Resolution"), async () => {
                await frm.call("verify_resolution", { accepted: 1 });
                await frm.reload_doc();
            });

            frm.add_custom_button(__("Reject Resolution"), () => {
                frappe.prompt(
                    [
                        {
                            fieldname: "note",
                            fieldtype: "Small Text",
                            label: __("Verification Note"),
                            reqd: 1,
                        },
                    ],
                    async (values) => {
                        await frm.call("verify_resolution", {
                            accepted: 0,
                            note: values.note,
                        });
                        await frm.reload_doc();
                    },
                    __("Reject Resolution")
                );
            });
        }
    },
});
