// ERPNext - Production Plan
// TAJ Manual Consolidation based on selected rows in sub_assembly_items

// ------------------------------------------------------------
// Helpers
// ------------------------------------------------------------
function taj_lock_standard_subassembly_consolidation(frm) {
  const sysFields = ['combine_sub_items', 'consolidate_sub_assembly_items'];

  sysFields.forEach((fname) => {
    const hasField =
      (frm.doc && Object.prototype.hasOwnProperty.call(frm.doc, fname)) ||
      frm.get_field(fname);

    if (!hasField) return;

    if (frm.doc[fname] !== 0) {
      frm.set_value(fname, 0);
    }

    frm.set_df_property(fname, 'read_only', 1);
    frm.toggle_enable(fname, false);
    frm.get_field(fname)?.$wrapper?.toggleClass('text-muted', true);
  });

  frm.dashboard?.clear_headline?.();
  frm.dashboard?.set_headline?.(
    __("Use TAJ Consolidate to merge only the selected Sub Assembly rows.")
  );
}

function taj_get_selected_sub_assembly_rows(frm) {
  const grid = frm.get_field('sub_assembly_items')?.grid;

  // Preferred way
  if (grid?.get_selected_children) {
    return grid.get_selected_children() || [];
  }

  // Fallback
  const selected = frm.get_selected?.() || {};
  const selected_names = selected.sub_assembly_items || [];

  return (frm.doc.sub_assembly_items || []).filter((row) =>
    selected_names.includes(row.name)
  );
}

function taj_validate_selected_rows(rows) {
  if (!rows || rows.length < 2) {
    frappe.msgprint(__('Please select at least 2 rows from Sub Assembly Items.'));
    return false;
  }

  // schedule_date required for all selected rows
  const rows_without_date = rows.filter((r) => !r.schedule_date);
  if (rows_without_date.length) {
    frappe.msgprint({
      title: __('Cannot Consolidate'),
      indicator: 'red',
      message: __('All selected rows must have a Schedule Date before consolidation.')
    });
    return false;
  }

  const base = rows[0];

  const compare_fields = [
    { fieldname: 'production_item', label: __('Sub Assembly Item Code') },
    { fieldname: 'bom_no',          label: __('BOM No') },
    { fieldname: 'stock_uom',       label: __('Stock UOM') },
    { fieldname: 'fg_warehouse',    label: __('Target Warehouse') }
  ];

  const issues = [];

  rows.slice(1).forEach((row) => {
    const mismatches = compare_fields.filter((f) => {
      return (row[f.fieldname] || '') !== (base[f.fieldname] || '');
    });

    if (mismatches.length) {
      issues.push(
        __('Row {0}: {1}', [
          row.idx || '?',
          mismatches.map((m) => m.label).join(', ')
        ])
      );
    }
  });

  if (issues.length) {
    frappe.msgprint({
      title: __('Cannot Consolidate'),
      indicator: 'red',
      message: __(
        'Selected rows must have identical values for: {0}<br><br>{1}',
        [
          compare_fields.map((f) => f.label).join(', '),
          issues.join('<br>')
        ]
      )
    });
    return false;
  }

  return true;
}

function taj_build_merged_row(rows) {
  const toDate = (value) => frappe.datetime.str_to_obj(value);

  let total_qty = 0;
  let earliest_row = rows[0];

  rows.forEach((row) => {
    total_qty += flt(row.qty);

    if (toDate(row.schedule_date) < toDate(earliest_row.schedule_date)) {
      earliest_row = row;
    }
  });

  // Start from the first selected row and override qty/date
  const merged = Object.assign({}, rows[0]);
  merged.qty = total_qty;
  merged.schedule_date = earliest_row.schedule_date;

  // Remove identity/meta so Frappe creates a fresh child row
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

function taj_rebuild_sub_assembly_table(frm, merged_row, selected_rows) {
  const original_rows = (frm.doc.sub_assembly_items || []).slice();
  const selected_set = new Set(selected_rows);

  const rebuilt_rows = [];
  let inserted_merged_row = false;

  original_rows.forEach((row) => {
    if (selected_set.has(row)) {
      if (!inserted_merged_row) {
        rebuilt_rows.push(Object.assign({}, merged_row));
        inserted_merged_row = true;
      }
      return;
    }

    rebuilt_rows.push(taj_clone_child_row(row));
  });

  frm.clear_table('sub_assembly_items');

  rebuilt_rows.forEach((row) => {
    frm.add_child('sub_assembly_items', row);
  });

  frm.refresh_field('sub_assembly_items');
  frm.dirty();
}

// ------------------------------------------------------------
// Parent Doctype Events
// ------------------------------------------------------------
frappe.ui.form.on('Production Plan', {
  refresh(frm) {
    // Disable ERPNext native consolidation to avoid conflict
    taj_lock_standard_subassembly_consolidation(frm);

    // Do not show custom buttons before saving
    if (frm.is_new()) return;

    // Show Label
    frm.add_custom_button(
      __('Show Label'),
      function () {
        frappe.call({
          method: "taj_core.public.production_plan.generate_stickers.open_production_stickers",
          args: { plan_name: frm.doc.name },
          callback(res) {
            if (res.message) {
              const link = document.createElement('a');
              link.href = res.message;
              link.download = res.message.split('/').pop();
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
            }
          }
        });
      },
      __('Taj')
    );

    // Delete Label
    frm.add_custom_button(
      __('Delete Label'),
      function () {
        frappe.confirm(
          __('Are you sure you want to delete all labels for this Production Plan?'),
          function () {
            frappe.call({
              method: "taj_core.public.production_plan.generate_stickers.delete_production_stickers",
              args: { plan_name: frm.doc.name },
              callback() {
                frappe.msgprint(__('Labels deleted successfully.'));
              }
            });
          }
        );
      },
      __('Taj')
    );
  },

  taj_consolidate(frm) {
    const selected_rows = taj_get_selected_sub_assembly_rows(frm);

    if (!selected_rows.length) {
      frappe.msgprint(__('Please select rows from Sub Assembly Items first.'));
      return;
    }

    if (!taj_validate_selected_rows(selected_rows)) {
      return;
    }

    const merged_row = taj_build_merged_row(selected_rows);
    taj_rebuild_sub_assembly_table(frm, merged_row, selected_rows);

    frappe.show_alert({
      message: __('Selected Sub Assembly rows were consolidated successfully.'),
      indicator: 'green'
    });
  }
});

// ------------------------------------------------------------
// Child Table Events
// ------------------------------------------------------------
frappe.ui.form.on('Production Plan Sub Assembly Item', {
  form_render(frm) {
    taj_lock_standard_subassembly_consolidation(frm);
  }
});

// // -------- Child Table Events --------
// frappe.ui.form.on('Production Plan Sub Assembly Item', {
//   taj_batch_consolidate(frm, cdt, cdn) {
//     taj_apply_consolidation_lock(frm);
//     frm.refresh_field('sub_assembly_items');
//   },
//   // تغييرات أخرى قد تؤثر على المنطق
//   sub_assembly_item_code(frm) { taj_apply_consolidation_lock(frm); },
//   schedule_date(frm) { taj_apply_consolidation_lock(frm); }
// });
