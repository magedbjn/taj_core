frappe.ui.form.on("Employee Document Template", {
    setup(frm) {
        frm.set_query("default_signatory", () => ({
            filters: { company: frm.doc.company || "", is_active: 1 },
        }));

        frm.set_query("employee_fee_salary_component", () => ({
            filters: { type: "Deduction", disabled: 0 },
        }));
    },

    refresh(frm) {
        render_variable_reference(frm);
        render_arabic_content_help(frm);
    },

    company(frm) {
        if (frm.doc.default_signatory) frm.set_value("default_signatory", null);
    },

    content_mode(frm) {
        render_variable_reference(frm);
        render_arabic_content_help(frm);
    },

    language_mode(frm) {
        render_arabic_content_help(frm);
    },
});


function render_arabic_content_help(frm) {
    const field = frm.get_field("arabic_content_help");
    if (!field || !field.$wrapper) return;

    if (frm.doc.language_mode === "English Only") {
        field.$wrapper.empty();
        return;
    }

    const section_note = frm.doc.content_mode === "Sections"
        ? `<br>${__("For section-based templates, use Insert AR to copy the token, then paste it into the required Arabic section.")}`
        : "";

    field.$wrapper.html(`
        <div class="alert alert-info" style="margin:6px 0 12px;">
            <strong>كتابة المحتوى العربي والمتغيرات</strong><br>
            استخدم <strong>Insert AR</strong> من قائمة Variables بدل كتابة صيغة Jinja يدويًا كلما أمكن.<br>
            مثال الاسم: <code>{{ employee_name_arabic or employee_name }}</code><br>
            مثال الجنسية المترجمة: <code>{{ _(nationality, lang=&quot;ar&quot;, context=&quot;Nationality&quot;) }}</code>
            ${section_note}
        </div>
    `);
}

function render_variable_reference(frm) {
    const field = frm.get_field("variables_reference");
    if (!field || !field.$wrapper) return;

    frappe.call({
        method: "taj_core.peopleops.doctype.employee_document_template.employee_document_template.get_available_variables",
        callback(r) {
            const data = r.message || {};
            const items = [...(data.variables || []), ...(data.salary_components || [])];
            const rows = items.map((item, idx) => `
                <tr>
                    <td style="width:18%">${frappe.utils.escape_html(item.category || "")}</td>
                    <td>${frappe.utils.escape_html(item.description || "")}</td>
                    <td style="width:26%; white-space:nowrap">
                        <button class="btn btn-xs btn-default taj-insert-var" data-idx="${idx}" data-lang="en">${__("Insert EN")}</button>
                        <button class="btn btn-xs btn-default taj-insert-var" data-idx="${idx}" data-lang="ar">${__("Insert AR")}</button>
                        <button class="btn btn-xs btn-default taj-copy-var" data-idx="${idx}">${__("Copy")}</button>
                    </td>
                </tr>
            `).join("");

            field.$wrapper.html(`
                <div class="small text-muted" style="margin-bottom:8px">
                    ${__("Choose a variable and insert it into the letter. Arabic insertion uses Frappe standard translation for translatable values when available.")}
                    ${frm.doc.content_mode === "Sections" ? `<br>${__("For section-based contracts, Copy the variable then paste it in the required section editor.")}` : ""}
                </div>
                <div style="max-height:420px; overflow:auto; border:1px solid var(--border-color); border-radius:6px;">
                    <table class="table table-bordered" style="margin:0">
                        <thead><tr><th>${__("Group")}</th><th>${__("Variable")}</th><th>${__("Insert")}</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `);

            field.$wrapper.find(".taj-insert-var").on("click", function () {
                const item = items[Number($(this).attr("data-idx"))];
                const lang = $(this).attr("data-lang");
                const token = lang === "ar" ? (item.token_ar || item.token) : (item.token_en || item.token);
                insert_variable(frm, token, lang);
            });
            field.$wrapper.find(".taj-copy-var").on("click", function () {
                const item = items[Number($(this).attr("data-idx"))];
                copy_variable(item.token);
            });
        },
    });
}

function insert_variable(frm, token, language) {
    if (frm.doc.content_mode === "Sections") {
        copy_variable(token);
        frappe.show_alert({ message: __("Variable copied. Paste it inside the required document section."), indicator: "blue" });
        return;
    }

    const fieldname = language === "ar" ? "template_text_arabic" : "template_text_english";
    const control = frm.get_field(fieldname);
    if (!control || !control.quill) {
        copy_variable(token);
        frappe.show_alert({ message: __("Variable copied to clipboard."), indicator: "blue" });
        return;
    }

    const range = control.quill.getSelection(true) || { index: control.quill.getLength() - 1, length: 0 };
    control.quill.insertText(range.index, token, "user");
    control.quill.setSelection(range.index + token.length, 0, "silent");
    control.quill.focus();
}

function copy_variable(token) {
    if (frappe.utils && frappe.utils.copy_to_clipboard) {
        frappe.utils.copy_to_clipboard(token);
        return;
    }
    if (navigator.clipboard) navigator.clipboard.writeText(token);
}
