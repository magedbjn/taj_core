frappe.ui.form.on("Mock Recall", {
  setup(frm) {
    frm.set_query("item_code", () => ({
      query:"taj_core.qc.doctype.mock_recall.mock_recall.item_query",
      filters:{scenario_type:frm.doc.scenario_type}
    }));
    frm.set_query("batch_no", () => ({filters:{item:frm.doc.item_code || "__NO_MATCH__"}}));
  },
  item_code(frm) { return frm.set_value("batch_no", null); },
  scenario_type(frm) {
    if (frm.doc.status === "Draft") return frm.set_value({item_code:null, batch_no:null});
  },
  refresh(frm) {
    frm.__taj_mock_recall_buttons_revision = "buttons-fix-20261109-v1";
    const qualityGroup = __("Quality Actions", null, "Mock Recall UI");
    ["Run Mock Recall Trace", "Verify Evidence", "Start Quality Review", "Finalize Review"].forEach(label => {
      frm.remove_custom_button(__(label));
      frm.remove_custom_button(__(label), qualityGroup);
    });
    frm.set_intro("");
    const open = ["Traced", "Under Review"].includes(frm.doc.status);
    ["company", "item_code", "batch_no", "scenario_type"].forEach(field => frm.set_df_property(field, "read_only", frm.doc.status !== "Draft"));
    ["quantity_verified", "customers_verified", "genealogy_verified", "coverage_notes", "exceptions"].forEach(field => frm.set_df_property(field, "read_only", !open));
    frm.set_df_property("review_notes", "read_only", 1);
    frm.toggle_display("batch_no", Boolean(frm.doc.item_code));
    frm.set_df_property("scenario_type", "options", !frm.is_new() && frm.doc.scenario_type === "Packaging Material" ? "Finished Product\nRaw Material\nPreparation\nPackaging Material" : "Finished Product\nRaw Material\nPreparation");
    if (frm.doc.status === "Closed") { frm.disable_save(); return; }
    if (frm.is_new()) return;
    const canAct = frm.get_perm(0, "write") && ["QC User", "Quality Manager", "System Manager"].some(role => frappe.user.has_role(role));
    if (!canAct) return;
    const action = async (method, args={}) => {
      if (frm.is_dirty()) await frm.save();
      await frappe.call({method:"taj_core.qc.doctype.mock_recall.mock_recall." + method,
        args:{name:frm.doc.name, ...args}, freeze:true, freeze_message:__("Processing mock recall...")});
      await frm.reload_doc();
    };
    frm.add_custom_button(__("Run Mock Recall Trace"), () => {
      frappe.confirm(__("Re-running replaces this snapshot and resets all verification and review notes. Continue?"), () => action("run_mock_recall"));
    }).addClass("btn-primary");
    if (open && Number(frm.doc.evidence_version || 0) === 2) {
      frm.add_custom_button(__("Verify Evidence"), () => {
        const dialog = new frappe.ui.Dialog({title:__("Verify Evidence"), fields:[
          {fieldname:"table_field", fieldtype:"Select", label:__("Evidence Table"), options:[{label:__("Traceability Evidence"), value:"trace_rows"}, {label:__("Customer Distribution"), value:"distribution_rows"}], reqd:1,
            onchange() {
              dialog.set_df_property("row_name", "options", (frm.doc[dialog.get_value("table_field")] || []).map(row => ({label:`${row.idx}: ${row.item_code || ""} / ${row.batch_no || ""} / ${row.reference_name || row.voucher_no || ""}`, value:row.name})));
              dialog.set_value("row_name", null);
            }},
          {fieldname:"row_name", fieldtype:"Select", label:__("Evidence Row"), options:[], reqd:1},
          {fieldname:"verification", fieldtype:"Select", label:__("Verification"), options:"Verified\nDiscrepancy\nUnverified", reqd:1},
          {fieldname:"notes", fieldtype:"Small Text", label:__("Source-check Notes"), reqd:1}
        ], primary_action_label:__("Record Verification"), async primary_action(values) {
          await action("verify_evidence", values); dialog.hide();
        }});
        dialog.show(); dialog.set_value("table_field", "trace_rows");
        dialog.fields_dict.table_field.df.onchange();
      }, qualityGroup);
    }
    if (frm.doc.status === "Traced") frm.add_custom_button(__("Start Quality Review"), () => action("start_review"), qualityGroup);
    if (open && (frappe.user.has_role("Quality Manager") || frappe.user.has_role("System Manager"))) {
      frm.add_custom_button(__("Finalize Review"), () => {
        const dialog = new frappe.ui.Dialog({title:__("Quality Review"), fields:[
          {fieldname:"decision", fieldtype:"Select", label:__("Assessment"), options:"Failed\nPassed", reqd:1},
          {fieldname:"notes", fieldtype:"Small Text", label:__("Review Notes"), reqd:1}
        ], primary_action_label:__("Close Simulation"), async primary_action(values) {
          await action("submit_mock_review", values); dialog.hide();
        }}); dialog.show();
      }, qualityGroup);
    }
  }
});
