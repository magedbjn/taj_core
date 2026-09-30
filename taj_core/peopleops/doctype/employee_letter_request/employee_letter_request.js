frappe.ui.form.on("Employee Letter Request", {
    setup(frm) {
        frm.set_query("employee", () => has_hr_role() ? {} : { filters: { status: "Active" } });

        frm.set_query("letter_template", () => template_query(frm, true));
        frm.set_query("resolved_template", () => {
            const q = template_query(frm, false);
            if (frm.doc.language_mode) q.filters.language_mode = frm.doc.language_mode;
            return q;
        });

        frm.set_query("signatory", () => signatory_query(frm, false));
        frm.set_query("one_time_signatory", () => signatory_query(frm, true));
        frm.set_query("one_time_fee_salary_component", () => ({ filters: { type: "Deduction", disabled: 0 } }));

        frm.set_query("reissue_of", () => ({
            filters: { employee: frm.doc.employee || "", request_type: frm.doc.request_type || "Standard Letter", docstatus: 1 },
        }));
    },

    refresh(frm) {
        apply_request_ui(frm);

        const is_hr = has_hr_role();
        const expired = is_expired(frm.doc);
        const blocked_after_expiry = expired && frm.doc.expired_document_policy === "Block Employee Print/Download";

        // Drafts are previewed in memory. No PDF/File attachment is created.
        if (is_hr && frm.doc.docstatus === 0 && !frm.is_new()) {
            frm.add_custom_button(__("Preview Letter"), () => preview_letter(frm), __("Processing"));
        }

        // A manually signed/stamped PDF is the authoritative final copy.
        if (frm.doc.docstatus === 1 && frm.doc.final_document_method === "Manual Final PDF Upload" && frm.doc.final_document) {
            if (is_hr || !blocked_after_expiry) {
                frm.add_custom_button(__("Open Signed / Stamped PDF"), () => window.open(frm.doc.final_document, "_blank"));
            }
        }

        if (expired) {
            if (frm.doc.expired_document_policy === "Block Employee Print/Download") {
                frm.dashboard.set_headline_alert(
                    __("This letter expired on {0}. Employee printing/download is blocked; HR retains the historical record.", [frm.doc.valid_until]),
                    "orange"
                );
            } else {
                frm.dashboard.set_headline_alert(
                    __("This letter expired on {0}. Any new system print will be marked EXPIRED / منتهي الصلاحية.", [frm.doc.valid_until]),
                    "orange"
                );
            }
        }

        // System-generated letters do not have a stored final PDF attachment.
        if (frm.fields_dict.final_document) {
            const show_manual_final = frm.doc.final_document_method === "Manual Final PDF Upload" && (is_hr || !blocked_after_expiry);
            frm.set_df_property("final_document", "hidden", !show_manual_final);
        }
    },

    request_type(frm) {
        if (frm.doc.request_type === "Custom Letter") {
            frm.set_value("letter_template", null);
        } else {
            frm.set_value("resolution_mode", null);
            frm.set_value("resolved_template", null);
        }
        apply_request_ui(frm);
    },

    resolution_mode(frm) {
        if (frm.doc.resolution_mode !== "Existing Template") frm.set_value("resolved_template", null);
        apply_request_ui(frm);
    },

    employee(frm) {
        if (!frm.doc.employee) return;
        frappe.db.get_value("Employee", frm.doc.employee, ["company"], (r) => {
            if (!r || !r.company) return;
            ["letter_template", "resolved_template"].forEach((fieldname) => {
                if (!frm.doc[fieldname]) return;
                frappe.db.get_value("Employee Document Template", frm.doc[fieldname], "company", (t) => {
                    if (t && t.company && t.company !== r.company) frm.set_value(fieldname, null);
                });
            });
        });
    },

    before_print(frm) {
        if (frm.doc.docstatus === 0) {
            frappe.msgprint(__("Draft letters are previewed through Processing > Preview Letter. No draft PDF attachment is created."));
            throw new Error("Prevent standard printing of draft");
        }

        if (!has_hr_role() && frm.doc.final_document_method === "Manual Final PDF Upload") {
            frappe.msgprint(__("Use the signed/stamped final PDF for this letter. The system Print Format is not the authoritative signed copy."));
            throw new Error("Prevent system print for manual final PDF");
        }

        if (!has_hr_role() && is_expired(frm.doc) && frm.doc.expired_document_policy === "Block Employee Print/Download") {
            frappe.msgprint(__("This letter has expired. Please request a new valid letter."));
            throw new Error("Prevent expired print");
        }
    },
});


function signatory_query(frm, one_time) {
    return {
        query: "taj_core.peopleops.doctype.employee_letter_signatory.employee_letter_signatory.get_available_signatories",
        filters: {
            company: frm.doc.company || "",
            requires_signature: one_time ? cint(frm.doc.one_time_requires_signature) : cint(frm.doc.requires_signature),
            requires_stamp: one_time ? cint(frm.doc.one_time_requires_stamp) : cint(frm.doc.requires_stamp),
        },
    };
}

function template_query(frm, employee_only) {
    const filters = { company: frm.doc.company || "", is_active: 1 };
    if (employee_only && !has_hr_role()) filters.available_for_employee_request = 1;
    return { filters };
}

function has_hr_role() {
    return frappe.user.has_role("HR User") || frappe.user.has_role("HR Manager") || frappe.user.has_role("System Manager");
}

function is_expired(doc) {
    return Boolean(doc.valid_until && frappe.datetime.get_diff(frappe.datetime.get_today(), doc.valid_until) > 0);
}

function apply_request_ui(frm) {
    const custom = frm.doc.request_type === "Custom Letter";
    frm.set_df_property("language_mode", "read_only", !custom);
    frm.set_df_property("bilingual_layout", "read_only", !custom);

    if (!custom && frm.doc.letter_template) {
        frappe.db.get_value("Employee Document Template", frm.doc.letter_template, ["language_mode", "bilingual_layout"], (r) => {
            if (!r) return;
            if (r.language_mode && frm.doc.language_mode !== r.language_mode) frm.set_value("language_mode", r.language_mode);
            if (r.language_mode === "Bilingual" && frm.doc.bilingual_layout !== r.bilingual_layout) {
                frm.set_value("bilingual_layout", r.bilingual_layout || "Side by Side");
            }
        });
    }
}

function preview_letter(frm) {
    frappe.call({
        method: "taj_core.peopleops.doctype.employee_letter_request.employee_letter_request.get_draft_preview",
        args: { name: frm.doc.name },
        freeze: true,
        freeze_message: __("Preparing preview..."),
        callback(r) {
            const html = r.message && r.message.html;
            if (!html) return;

            const win = window.open("", "_blank");
            if (!win) {
                frappe.msgprint(__("Please allow pop-ups to open the letter preview."));
                return;
            }
            win.document.open();
            win.document.write(html);
            win.document.close();
        },
    });
}
