frappe.ui.form.on("Checklist Answer", {
    refresh(frm) {
        const grid = frm.get_field("answer").grid;

        grid.cannot_add_rows = true;
        grid.cannot_delete_rows = true;
        frm.refresh_field("answer");

        $(frm.fields_dict.answer.grid.wrapper).find(".grid-add-row").hide();
        $(frm.fields_dict.answer.grid.wrapper).find(".grid-remove-rows").hide();
        $(frm.fields_dict.answer.grid.wrapper).find(".btn-open-row, .grid-duplicate-row").hide();
    }
});

frappe.ui.form.on("Checklist Answer Question", {
    form_render(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        apply_row_select_options(frm, cdt, cdn, row);
        sync_row_answer(frm, cdt, cdn);
    },

    yes_no_answer(frm, cdt, cdn) {
        sync_row_answer(frm, cdt, cdn);
    },

    int_answer(frm, cdt, cdn) {
        sync_row_answer(frm, cdt, cdn);
    },

    float_answer(frm, cdt, cdn) {
        sync_row_answer(frm, cdt, cdn);
    },

    select_answer(frm, cdt, cdn) {
        sync_row_answer(frm, cdt, cdn);
    }
});

function sync_row_answer(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    let value = "";

    if (row.type === "Yes/No") {
        value = row.yes_no_answer || "";
    } else if (row.type === "Int") {
        value = row.int_answer != null ? String(row.int_answer) : "";
    } else if (row.type === "Float") {
        value = row.float_answer != null ? String(row.float_answer) : "";
    } else if (row.type === "Select") {
        value = row.select_answer || "";
    }

    frappe.model.set_value(cdt, cdn, "answer", value);
}

function apply_row_select_options(frm, cdt, cdn, row) {
    if (row.type !== "Select") return;

    const grid_row = frm.fields_dict.answer.grid.grid_rows_by_docname[cdn];
    if (!grid_row || !grid_row.grid_form) return;

    const field = grid_row.grid_form.fields_dict.select_answer;
    if (!field) return;

    field.df.options = "\n" + (row.answer_select_options || "");
    field.refresh();
}