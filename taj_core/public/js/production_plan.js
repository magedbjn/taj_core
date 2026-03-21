// Production Plan
// TAJ manual consolidation + stable internal reference map in taj_sub_assembly_items_split
//
// Final behavior:
// 1) Get Sub Assembly Items => clear taj_sub_assembly_items_split only
// 2) taj_consolidate => add selected rows to split first, then merge, then update references
//
// IMPORTANT:
// - Stable link is now:
//     split.merge_group_id  <->  sub_assembly_items.taj_merge_group_id
// - Do NOT rely on merged_sub_assembly_item as final DB link after save.

function taj_lock_standard_subassembly_consolidation(frm) {
  const sysFields = ["combine_sub_items", "consolidate_sub_assembly_items"];

  sysFields.forEach((fname) => {
    const hasField =
      (frm.doc && Object.prototype.hasOwnProperty.call(frm.doc, fname)) ||
      frm.get_field(fname);

    if (!hasField) return;

    if (frm.doc[fname] !== 0) {
      frm.set_value(fname, 0);
    }

    frm.set_df_property(fname, "read_only", 1);
    frm.toggle_enable(fname, false);
    frm.get_field(fname)?.$wrapper?.toggleClass("text-muted", true);
  });
}

function taj_generate_merge_group_id() {
  return `TAJ-MG-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function taj_get_sub_row_link_key(row) {
  return row.taj_merge_group_id || row.name || "";
}

function taj_get_split_row_link_key(row) {
  return (
    row.merge_group_id ||
    row.merged_sub_assembly_item ||
    row.source_sub_assembly_item ||
    ""
  );
}

function taj_get_selected_sub_assembly_rows(frm) {
  const grid = frm.get_field("sub_assembly_items")?.grid;

  if (grid?.get_selected_children) {
    return grid.get_selected_children() || [];
  }

  const selected = frm.get_selected?.() || {};
  const selected_names = selected.sub_assembly_items || [];

  return (frm.doc.sub_assembly_items || []).filter((row) =>
    selected_names.includes(row.name)
  );
}

function taj_validate_selected_rows(rows) {
  if (!rows || rows.length < 2) {
    frappe.msgprint(__("Please select at least 2 rows from Sub Assembly Items."));
    return false;
  }

  const rows_without_date = rows.filter((r) => !r.schedule_date);
  if (rows_without_date.length) {
    frappe.msgprint({
      title: __("Cannot Consolidate"),
      indicator: "red",
      message: __("All selected rows must have a Schedule Date before consolidation.")
    });
    return false;
  }

  const base = rows[0];

  const compare_fields = [
    { fieldname: "production_item", label: __("Sub Assembly Item Code") },
    { fieldname: "bom_no", label: __("BOM No") },
    { fieldname: "stock_uom", label: __("Stock UOM") },
    { fieldname: "fg_warehouse", label: __("Target Warehouse") },
    { fieldname: "type_of_manufacturing", label: __("Manufacturing Type") }
  ];

  const issues = [];

  rows.slice(1).forEach((row) => {
    const mismatches = compare_fields.filter((f) => {
      return (row[f.fieldname] || "") !== (base[f.fieldname] || "");
    });

    if (mismatches.length) {
      issues.push(
        __("Row {0}: {1}", [
          row.idx || "?",
          mismatches.map((m) => m.label).join(", ")
        ])
      );
    }
  });

  if (issues.length) {
    frappe.msgprint({
      title: __("Cannot Consolidate"),
      indicator: "red",
      message: __("Selected rows contain mismatched items and cannot be consolidated.")
    });
    return false;
  }

  return true;
}

function taj_clone_child_row(row) {
  const copy = Object.assign({}, row);

  delete copy.name;
  delete copy.idx;
  delete copy.owner;
  delete copy.creation;
  delete copy.modified;
  delete copy.modified_by;
  delete copy.parent;
  delete copy.parentfield;
  delete copy.parenttype;
  delete copy.docstatus;
  delete copy.__islocal;

  return copy;
}

function taj_build_merged_row(rows, new_group_id) {
  const toDate = (value) => frappe.datetime.str_to_obj(value);

  let total_qty = 0;
  let earliest_row = rows[0];

  rows.forEach((row) => {
    total_qty += flt(row.qty);

    if (toDate(row.schedule_date) < toDate(earliest_row.schedule_date)) {
      earliest_row = row;
    }
  });

  const merged = Object.assign({}, rows[0]);
  merged.qty = total_qty;
  merged.schedule_date = earliest_row.schedule_date;

  // Stable key for the merged live row
  merged.taj_merge_group_id = new_group_id || "";

  delete merged.name;
  delete merged.idx;
  delete merged.owner;
  delete merged.creation;
  delete merged.modified;
  delete merged.modified_by;
  delete merged.parent;
  delete merged.parentfield;
  delete merged.parenttype;
  delete merged.docstatus;
  delete merged.__islocal;

  return merged;
}

function taj_find_source_assembly_row(frm, subRow) {
  const po_items = frm.doc.po_items || [];
  return po_items.find((r) => r.name === subRow.production_plan_item) || null;
}

function taj_get_selected_group_ids(frm, selected_rows) {
  const split_rows = frm.doc.taj_sub_assembly_items_split || [];
  const selected_keys = new Set(
    (selected_rows || []).map((r) => taj_get_sub_row_link_key(r)).filter(Boolean)
  );
  const group_ids = new Set();

  split_rows.forEach((row) => {
    const split_key = taj_get_split_row_link_key(row);
    if (selected_keys.has(split_key)) {
      group_ids.add(split_key);
    }
  });

  return group_ids;
}

function taj_add_selected_rows_to_split(frm, selected_rows) {
  const split_rows = frm.doc.taj_sub_assembly_items_split || [];

  (selected_rows || []).forEach((subRow) => {
    const sub_row_key = taj_get_sub_row_link_key(subRow);

    const already_exists = split_rows.some((row) => {
      return (
        (row.merge_group_id || "") === sub_row_key ||
        (row.source_sub_assembly_item || "") === (subRow.name || "") ||
        (row.merged_sub_assembly_item || "") === (subRow.name || "")
      );
    });

    if (already_exists) return;

    const source_po = taj_find_source_assembly_row(frm, subRow);
    const current_ref = subRow.name || "";

    frm.add_child("taj_sub_assembly_items_split", {
      source_assembly_item: source_po?.name || subRow.production_plan_item || "",
      source_fg_item_code: source_po?.item_code || "",
      source_fg_bom_no: source_po?.bom_no || "",
      assembly_qty: flt(source_po?.planned_qty || 0),
      planned_start_date: source_po?.planned_start_date || "",
      source_sub_assembly_item: current_ref,
      sub_assembly_item_code: subRow.production_item || "",
      sub_assembly_bom_no: subRow.bom_no || "",
      sub_assembly_qty: flt(subRow.qty || subRow.stock_qty || 0),
      sub_assembly_schedule_date: subRow.schedule_date || "",

      // Informational only - not used as stable DB link
      merged_sub_assembly_item: current_ref,

      // Stable per-current-row key:
      // - for normal row => row.name
      // - for previously merged row => taj_merge_group_id
      merge_group_id: sub_row_key
    });
  });

  frm.refresh_field("taj_sub_assembly_items_split");
  frm.dirty();
}

function taj_rebuild_sub_assembly_table(frm, merged_row, selected_rows) {
  const original_rows = (frm.doc.sub_assembly_items || []).slice();
  const selected_names = new Set((selected_rows || []).map((r) => r.name));

  const rebuilt_specs = [];
  let inserted_merged_row = false;

  original_rows.forEach((row) => {
    if (selected_names.has(row.name)) {
      if (!inserted_merged_row) {
        rebuilt_specs.push({
          row_type: "merged",
          old_name: null,
          row_data: Object.assign({}, merged_row)
        });
        inserted_merged_row = true;
      }
      return;
    }

    rebuilt_specs.push({
      row_type: "existing",
      old_name: row.name,
      row_data: taj_clone_child_row(row)
    });
  });

  frm.clear_table("sub_assembly_items");

  let merged_row_doc = null;
  const old_to_new = {};

  rebuilt_specs.forEach((spec) => {
    const new_row = frm.add_child("sub_assembly_items", spec.row_data);

    if (spec.row_type === "merged") {
      merged_row_doc = new_row;
    } else if (spec.old_name) {
      old_to_new[spec.old_name] = new_row.name;
    }
  });

  frm.refresh_field("sub_assembly_items");
  frm.dirty();

  return { merged_row_doc, old_to_new };
}

function taj_sync_split_after_consolidation(frm, selected_group_ids, new_group_id, old_to_new) {
  const split_rows = frm.doc.taj_sub_assembly_items_split || [];
  if (!split_rows.length) return;

  // Update untouched rows if their current row name changed after rebuild
  split_rows.forEach((row) => {
    const row_group_id = row.merge_group_id || "";
    if (selected_group_ids.has(row_group_id)) return;

    // For rows that still rely on direct row name, update to rebuilt row names
    if (row.merged_sub_assembly_item && old_to_new[row.merged_sub_assembly_item]) {
      const oldRef = row.merged_sub_assembly_item;
      const newRef = old_to_new[oldRef];
      row.merged_sub_assembly_item = newRef;

      if (row.merge_group_id === oldRef) {
        row.merge_group_id = newRef;
      }
    }

    if (row.source_sub_assembly_item && old_to_new[row.source_sub_assembly_item]) {
      const oldRef = row.source_sub_assembly_item;
      const newRef = old_to_new[oldRef];

      // For untouched, never-merged rows, keep source/current ref aligned
      row.source_sub_assembly_item = newRef;

      if (row.merge_group_id === oldRef) {
        row.merge_group_id = newRef;
      }
    }
  });

  // Move selected groups to the new stable merged group
  split_rows.forEach((row) => {
    const row_group_id =
      row.merge_group_id ||
      row.merged_sub_assembly_item ||
      row.source_sub_assembly_item ||
      "";

    if (selected_group_ids.has(row_group_id)) {
      row.merge_group_id = new_group_id;

      // Do not store temporary client-side child row names (new-...)
      row.merged_sub_assembly_item = "";
    }
  });

  frm.refresh_field("taj_sub_assembly_items_split");
  frm.dirty();
}

// function taj_show_selected_merge_sources(frm) {
//   const split_rows = frm.doc.taj_sub_assembly_items_split || [];

//   if (!split_rows.length) {
//     frappe.msgprint({
//       title: __("No References Found"),
//       indicator: "orange",
//       message: __("No data found in taj_sub_assembly_items_split.")
//     });
//     return;
//   }

//   // Get unique Sub Assembly Item Code values
//   const item_codes = [...new Set(
//     split_rows
//       .map((r) => (r.sub_assembly_item_code || "").trim())
//       .filter(Boolean)
//   )].sort();

//   if (!item_codes.length) {
//     frappe.msgprint({
//       title: __("No Items Found"),
//       indicator: "orange",
//       message: __("No Sub Assembly Item Code values were found in taj_sub_assembly_items_split.")
//     });
//     return;
//   }

//   const dialog = new frappe.ui.Dialog({
//     title: __("Show Merge References"),
//     fields: [
//       {
//         fieldtype: "Select",
//         fieldname: "sub_assembly_item_code",
//         label: __("Sub Assembly Item"),
//         options: ["", ...item_codes],
//         reqd: 1,
//         onchange: function () {
//           render_results();
//         }
//       },
//       {
//         fieldtype: "HTML",
//         fieldname: "results_html"
//       }
//     ],
//     primary_action_label: __("Close"),
//     primary_action() {
//       dialog.hide();
//     }
//   });

//   function render_results() {
//     const selected_item = dialog.get_value("sub_assembly_item_code");
//     const wrapper = dialog.get_field("results_html").$wrapper;

//     if (!selected_item) {
//       wrapper.html(`
//         <div class="text-muted" style="padding: 12px;">
//           ${__("Please select a Sub Assembly Item.")}
//         </div>
//       `);
//       return;
//     }

//     const result_rows = split_rows.filter((r) =>
//       (r.sub_assembly_item_code || "").trim() === selected_item
//     );

//     if (!result_rows.length) {
//       wrapper.html(`
//         <div class="text-muted" style="padding: 12px;">
//           ${__("No matching rows found.")}
//         </div>
//       `);
//       return;
//     }

//     const rows_html = result_rows.map((r, i) => `
//       <tr>
//         <td>${i + 1}</td>
//         <td>${frappe.utils.escape_html(r.sub_assembly_item_code || "")}</td>
//         <td style="text-align:right;">${format_number(r.sub_assembly_qty || 0, null, 3)}</td>
//         <td>${frappe.utils.escape_html(r.sub_assembly_schedule_date || "")}</td>
//       </tr>
//     `).join("");

//     wrapper.html(`
//       <div style="max-height: 420px; overflow:auto; margin-top: 10px;">
//         <table class="table table-bordered table-sm">
//           <thead>
//             <tr>
//               <th>#</th>
//               <th>Sub Assembly Item</th>
//               <th>Sub Assembly Qty</th>
//               <th>Sub Assembly Schedule Date</th>
//             </tr>
//           </thead>
//           <tbody>
//             ${rows_html}
//           </tbody>
//         </table>
//       </div>
//     `);
//   }

//   dialog.show();

//   // optional: preselect first item automatically
//   dialog.set_value("sub_assembly_item_code", item_codes[0]);
//   render_results();
// }

// ------------------------------------------------------------
// Parent Doctype Events
// ------------------------------------------------------------
frappe.ui.form.on("Production Plan", {
  refresh(frm) {
    taj_lock_standard_subassembly_consolidation(frm);

    // frm.add_custom_button(__("Show Merge References"), function () {
    //   taj_show_selected_merge_sources(frm);
    // });
  },

  get_sub_assembly_items(frm) {
    // Required final behavior:
    // clear split map only, do NOT run standard fetch
    frm.clear_table("taj_sub_assembly_items_split");
    frm.refresh_field("taj_sub_assembly_items_split");
    frm.dirty();
  },

  taj_consolidate(frm) {
    const selected_rows = taj_get_selected_sub_assembly_rows(frm);

    // if (!selected_rows.length) {
    //   frappe.msgprint(__("Please select rows from Sub Assembly Items first."));
    //   return;
    // }

    if (!taj_validate_selected_rows(selected_rows)) {
      return;
    }

    // 1) Before merge: add selected rows/groups to split if missing
    taj_add_selected_rows_to_split(frm, selected_rows);

    // 2) Read selected groups from split
    const selected_group_ids = taj_get_selected_group_ids(frm, selected_rows);
    if (!selected_group_ids.size) {
      frappe.msgprint(__("No matching split references were found for the selected rows."));
      return;
    }

    // 3) Merge sub_assembly_items using a stable group id
    const new_group_id = taj_generate_merge_group_id();
    const merged_row = taj_build_merged_row(selected_rows, new_group_id);
    const result = taj_rebuild_sub_assembly_table(frm, merged_row, selected_rows);

    if (!result?.merged_row_doc) {
      frappe.msgprint({
        title: __("Consolidation Error"),
        indicator: "red",
        message: __("Unable to determine the merged Sub Assembly row.")
      });
      return;
    }

    // 4) After merge: update split references using stable key
    taj_sync_split_after_consolidation(
      frm,
      selected_group_ids,
      new_group_id,
      result.old_to_new || {}
    );

    frappe.show_alert({
      message: __("Selected Sub Assembly rows were consolidated successfully."),
      indicator: "green"
    });
  }
});

// ------------------------------------------------------------
// Child Table Events
// ------------------------------------------------------------
frappe.ui.form.on("Production Plan Sub Assembly Item", {
  form_render(frm) {
    taj_lock_standard_subassembly_consolidation(frm);
  }
});