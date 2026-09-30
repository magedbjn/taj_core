frappe.ui.form.on("Employee Letter Signatory", {
    setup(frm) {
        frm.set_query("employee", () => ({ filters: { status: "Active" } }));
    },

    refresh(frm) {
        apply_asset_visibility(frm);
    },

    signature_usage(frm) {
        apply_asset_visibility(frm);
    },

    stamp_usage(frm) {
        apply_asset_visibility(frm);
    },
});

function apply_asset_visibility(frm) {
    if (frm.is_new() || !frm.doc.name) {
        frm.toggle_display("signature_image", true);
        frm.toggle_display("stamp_image", true);
        return;
    }

    frappe.call({
        method: "taj_core.peopleops.doctype.employee_letter_signatory.employee_letter_signatory.get_asset_access",
        args: { signatory_name: frm.doc.name },
        callback(r) {
            const access = r.message || {};
            frm.toggle_display("signature_image", Boolean(access.signature));
            frm.toggle_display("stamp_image", Boolean(access.stamp));

            if (!access.signature && access.signature_usage === "Signatory Only") {
                frm.set_df_property("signature_usage", "description", __("Stored signature is private to the User ID linked to this Employee and can only be used when that user issues the letter."));
            }
            if (!access.stamp && access.stamp_usage === "Signatory Only") {
                frm.set_df_property("stamp_usage", "description", __("Stored stamp is restricted to the User ID linked to this Employee."));
            }
        },
    });
}
