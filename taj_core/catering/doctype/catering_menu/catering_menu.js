frappe.ui.form.on("Catering Menu", {
  onload: function (frm) {
    ensure_row_ids(frm);
  },

  refresh: function (frm) {
    ensure_row_ids(frm);
  },

  before_save: function (frm) {
    ensure_row_ids(frm);
    auto_link_sub_items(frm);
    validate_catering_menu_items(frm);
  }
});


frappe.ui.form.on("Catering Menu Item", {
  items_add: function (frm, cdt, cdn) {
    setTimeout(function () {
      prepare_new_menu_row(frm, cdt, cdn);
    }, 250);
  },

  item_code: function (frm, cdt, cdn) {
    set_item_details_and_uom(frm, cdt, cdn);
  },

  row_type: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (!row.row_id) {
      frappe.model.set_value(cdt, cdn, "row_id", make_row_id());
    }

    clear_fields_by_row_type(frm, cdt, cdn);

    if (row.row_type === "Sub Item") {
      set_parent_from_previous_item(frm, cdt, cdn);
    } else {
      frappe.model.set_value(cdt, cdn, "parent_row_id", "");
      frappe.model.set_value(cdt, cdn, "parent_row_label", "");
    }

    focus_by_row_type(frm, cdt, cdn);
  },

  service_period: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (row && row.row_type === "Sub Item") {
      set_parent_from_previous_item(frm, cdt, cdn);
    }
  },

  meal_type: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (row && row.row_type === "Sub Item") {
      set_parent_from_previous_item(frm, cdt, cdn);
    }
  }
});


function prepare_new_menu_row(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (!row.row_id) {
    frappe.model.set_value(cdt, cdn, "row_id", make_row_id());
  }

  copy_previous_row_values_force(frm, cdt, cdn);

  setTimeout(function () {
    const updated_row = locals[cdt][cdn];

    if (updated_row && updated_row.row_type === "Sub Item") {
      set_parent_from_previous_item(frm, cdt, cdn);
    }

    focus_by_row_type(frm, cdt, cdn);
  }, 500);
}


function copy_previous_row_values_force(frm, cdt, cdn) {
  const current_row = locals[cdt][cdn];

  if (!current_row) return;

  const previous_row = get_previous_row_by_idx(frm, current_row);

  if (!previous_row) return;

  frappe.model.set_value(cdt, cdn, "service_period", previous_row.service_period || "");
  frappe.model.set_value(cdt, cdn, "meal_type", previous_row.meal_type || "");
  frappe.model.set_value(cdt, cdn, "row_type", previous_row.row_type || "");

  if (previous_row.row_type === "Sub Item") {
    frappe.model.set_value(cdt, cdn, "parent_row_id", previous_row.parent_row_id || "");
    frappe.model.set_value(cdt, cdn, "parent_row_label", previous_row.parent_row_label || "");
  } else {
    frappe.model.set_value(cdt, cdn, "parent_row_id", "");
    frappe.model.set_value(cdt, cdn, "parent_row_label", "");
  }

  frappe.model.set_value(cdt, cdn, "section", "");
  frappe.model.set_value(cdt, cdn, "item_code", "");
  frappe.model.set_value(cdt, cdn, "item_name", "");
  frappe.model.set_value(cdt, cdn, "item_name_arabic", "");
  frappe.model.set_value(cdt, cdn, "new_item_name", "");
  frappe.model.set_value(cdt, cdn, "new_item_name_arabic", "");
  frappe.model.set_value(cdt, cdn, "qty", "");
  frappe.model.set_value(cdt, cdn, "uom", "");

  if (!current_row.is_show_print) {
    frappe.model.set_value(cdt, cdn, "is_show_print", 1);
  }

  frm.refresh_field("items");
}


function get_previous_row_by_idx(frm, current_row) {
  const rows = (frm.doc.items || [])
    .slice()
    .sort(function (a, b) {
      return a.idx - b.idx;
    });

  for (let i = 0; i < rows.length; i++) {
    if (rows[i].name === current_row.name && i > 0) {
      return rows[i - 1];
    }
  }

  return null;
}


// function set_item_details_and_uom(frm, cdt, cdn) {
//   const row = locals[cdt][cdn];

//   if (!row || !row.item_code) {
//     frappe.model.set_value(cdt, cdn, "item_name", "");
//     frappe.model.set_value(cdt, cdn, "item_name_arabic", "");
//     frappe.model.set_value(cdt, cdn, "uom", "");
//     return;
//   }

//   frappe.db.get_value(
//     "Item",
//     row.item_code,
//     ["item_name", "item_name_arabic", "stock_uom"]
//   ).then(function (r) {
//     const values = r.message || {};

//     frappe.model.set_value(cdt, cdn, "item_name", values.item_name || "");
//     frappe.model.set_value(cdt, cdn, "item_name_arabic", values.item_name_arabic || "");

//     if (values.stock_uom) {
//       frappe.model.set_value(cdt, cdn, "uom", values.stock_uom);
//     }
//   });
// }

function set_item_details_and_uom(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row || !row.item_code) {
    frappe.model.set_value(cdt, cdn, "item_name", "");
    frappe.model.set_value(cdt, cdn, "item_name_arabic", "");
    frappe.model.set_value(cdt, cdn, "qty", "");
    frappe.model.set_value(cdt, cdn, "uom", "");
    return;
  }

  frappe.db.get_value(
    "Item",
    row.item_code,
    ["item_name", "item_name_arabic", "stock_uom"]
  ).then(function (r) {
    const item = r.message || {};

    frappe.model.set_value(cdt, cdn, "item_name", item.item_name || "");
    frappe.model.set_value(cdt, cdn, "item_name_arabic", item.item_name_arabic || "");

    if (item.stock_uom) {
      frappe.model.set_value(cdt, cdn, "uom", item.stock_uom);
    }

    return frappe.db.get_value(
      "Catering Items",
      {
        item_code: row.item_code
      },
      ["qty", "uom"]
    );
  }).then(function (r) {
    const catering_item = r.message || {};

    if (catering_item.qty) {
      frappe.model.set_value(cdt, cdn, "qty", catering_item.qty);
    }

    if (catering_item.uom) {
      frappe.model.set_value(cdt, cdn, "uom", catering_item.uom);
    }
  });
}

function clear_fields_by_row_type(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (row.row_type === "Section") {
    frappe.model.set_value(cdt, cdn, "item_code", "");
    frappe.model.set_value(cdt, cdn, "item_name", "");
    frappe.model.set_value(cdt, cdn, "item_name_arabic", "");
    frappe.model.set_value(cdt, cdn, "new_item_name", "");
    frappe.model.set_value(cdt, cdn, "new_item_name_arabic", "");
    frappe.model.set_value(cdt, cdn, "qty", "");
    frappe.model.set_value(cdt, cdn, "uom", "");
    frappe.model.set_value(cdt, cdn, "parent_row_id", "");
    frappe.model.set_value(cdt, cdn, "parent_row_label", "");
  }

  if (row.row_type === "Item" || row.row_type === "Sub Item") {
    frappe.model.set_value(cdt, cdn, "section", "");
    frappe.model.set_value(cdt, cdn, "new_item_name", "");
    frappe.model.set_value(cdt, cdn, "new_item_name_arabic", "");
  }

  if (row.row_type === "New Item") {
    frappe.model.set_value(cdt, cdn, "section", "");
    frappe.model.set_value(cdt, cdn, "item_code", "");
    frappe.model.set_value(cdt, cdn, "item_name", "");
    frappe.model.set_value(cdt, cdn, "item_name_arabic", "");
  }
}


function make_row_id() {
  return (
    "ROW-" +
    Math.random().toString(36).substring(2, 10).toUpperCase() +
    "-" +
    Date.now().toString(36).toUpperCase()
  );
}


function ensure_row_ids(frm) {
  let changed = false;

  (frm.doc.items || []).forEach(function (row) {
    if (!row.row_id) {
      row.row_id = make_row_id();
      changed = true;
    }

    if (row.is_show_print === undefined || row.is_show_print === null) {
      row.is_show_print = 1;
      changed = true;
    }
  });

  if (changed) {
    frm.refresh_field("items");
    frm.dirty();
  }
}


function set_parent_from_previous_item(frm, cdt, cdn) {
  const current_row = locals[cdt][cdn];

  if (!current_row) return;

  let parent_row = null;

  const previous_rows = (frm.doc.items || [])
    .filter(function (row) {
      return row.idx < current_row.idx;
    })
    .sort(function (a, b) {
      return b.idx - a.idx;
    });

  for (let i = 0; i < previous_rows.length; i++) {
    const row = previous_rows[i];

    const same_period = row.service_period === current_row.service_period;
    const same_meal = row.meal_type === current_row.meal_type;
    const is_parent_type = row.row_type === "Item" || row.row_type === "New Item";

    if (same_period && same_meal && is_parent_type) {
      parent_row = row;
      break;
    }

    if (same_period && same_meal && row.row_type === "Section") {
      break;
    }
  }

  if (parent_row) {
    if (!parent_row.row_id) {
      parent_row.row_id = make_row_id();
    }

    frappe.model.set_value(cdt, cdn, "parent_row_id", parent_row.row_id);
    frappe.model.set_value(cdt, cdn, "parent_row_label", get_parent_row_label(parent_row));

    frm.refresh_field("items");
  }
}


function get_parent_row_label(row) {
  let item_label = "";

  if (row.row_type === "New Item") {
    item_label = row.new_item_name_arabic || row.new_item_name || "";
  } else if (row.row_type === "Item") {
    item_label = row.item_name_arabic || row.item_name || row.item_code || "";
  }

  return [
    row.service_period || "",
    row.meal_type || "",
    item_label
  ].filter(Boolean).join(" / ");
}


function auto_link_sub_items(frm) {
  (frm.doc.items || []).forEach(function (row) {
    if (row.row_type === "Sub Item" && !row.parent_row_id) {
      set_parent_from_previous_item(frm, row.doctype, row.name);
    }
  });
}


function focus_by_row_type(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  let fieldname = "";

  if (row.row_type === "Section") {
    fieldname = "section";
  } else if (row.row_type === "Item" || row.row_type === "Sub Item") {
    fieldname = "item_code";
  } else if (row.row_type === "New Item") {
    fieldname = "new_item_name";
  }

  if (!fieldname) return;

  focus_child_table_field(frm, "items", cdn, fieldname);
}


function focus_child_table_field(frm, table_fieldname, cdn, fieldname) {
  setTimeout(function () {
    const grid = frm.fields_dict[table_fieldname] && frm.fields_dict[table_fieldname].grid;

    if (!grid) return;

    const grid_row = grid.grid_rows_by_docname[cdn];

    if (!grid_row) return;

    if (grid_row.refresh) {
      grid_row.refresh();
    }

    setTimeout(function () {
      let focused = false;

      if (
        grid_row.columns &&
        grid_row.columns[fieldname] &&
        grid_row.columns[fieldname].field &&
        grid_row.columns[fieldname].field.$input
      ) {
        const $input = grid_row.columns[fieldname].field.$input;

        if ($input && $input.length) {
          $input.focus();

          if ($input.select) {
            $input.select();
          }

          focused = true;
        }
      }

      if (focused) return;

      if (grid_row.row) {
        const $cell = grid_row.row.find('[data-fieldname="' + fieldname + '"]');
        const $input = $cell.find("input:visible, textarea:visible, select:visible").first();

        if ($input && $input.length) {
          $input.focus();

          if ($input.select) {
            $input.select();
          }

          focused = true;
        }
      }

      if (focused) return;

      if (grid_row.toggle_view) {
        grid_row.toggle_view(true);

        setTimeout(function () {
          if (
            grid_row.grid_form &&
            grid_row.grid_form.fields_dict &&
            grid_row.grid_form.fields_dict[fieldname]
          ) {
            const field = grid_row.grid_form.fields_dict[fieldname];

            if (field.$input && field.$input.length) {
              field.$input.focus();

              if (field.$input.select) {
                field.$input.select();
              }
            }
          }
        }, 200);
      }
    }, 200);
  }, 250);
}


function validate_catering_menu_items(frm) {
  (frm.doc.items || []).forEach(function (row) {
    if (!row.service_period) {
      frappe.throw(__("Row #{0}: Service Period is required.", [row.idx]));
    }

    if (!row.meal_type) {
      frappe.throw(__("Row #{0}: Meal Type is required.", [row.idx]));
    }

    if (!row.row_type) {
      frappe.throw(__("Row #{0}: Row Type is required.", [row.idx]));
    }

    if (row.row_type === "Section" && !row.section) {
      frappe.throw(__("Row #{0}: Section is required.", [row.idx]));
    }

    if ((row.row_type === "Item" || row.row_type === "Sub Item") && !row.item_code) {
      frappe.throw(__("Row #{0}: Item Code is required for {1}.", [row.idx, row.row_type]));
    }

    if (row.row_type === "New Item") {
      if (!row.new_item_name || !row.new_item_name_arabic) {
        frappe.throw(__("Row #{0}: New Item Name and New Item Name Arabic are required.", [row.idx]));
      }
    }

    if (row.row_type !== "Section") {
      if (!row.qty) {
        frappe.throw(__("Row #{0}: QTY is required.", [row.idx]));
      }

      if (!row.uom) {
        frappe.throw(__("Row #{0}: UOM is required.", [row.idx]));
      }
    }

    if (row.row_type === "Sub Item" && !row.parent_row_id) {
      frappe.throw(__("Row #{0}: Sub Item must be linked to a parent Item or New Item.", [row.idx]));
    }
  });
}