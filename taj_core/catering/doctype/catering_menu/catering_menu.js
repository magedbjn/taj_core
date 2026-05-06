frappe.ui.form.on("Catering Menu", {
  onload: function (frm) {
    ensure_new_item_row_ids(frm);
  },

  refresh: function (frm) {
    ensure_new_item_row_ids(frm);
  },

  before_save: function (frm) {
    ensure_new_item_row_ids(frm);
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

  row_type: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    clear_fields_by_row_type(frm, cdt, cdn);

    if (row.row_type === "New Item") {
      ensure_row_id_for_new_item(frm, cdt, cdn);
      frappe.model.set_value(cdt, cdn, "parent_row_id", "");
      frappe.model.set_value(cdt, cdn, "parent_row_label", "");
    }

    if (row.row_type === "Sub Item") {
      frappe.model.set_value(cdt, cdn, "row_id", "");
      set_parent_from_previous_row(frm, cdt, cdn);
    }

    if (row.row_type === "Item" || row.row_type === "Section") {
      frappe.model.set_value(cdt, cdn, "row_id", "");
      frappe.model.set_value(cdt, cdn, "parent_row_id", "");
      frappe.model.set_value(cdt, cdn, "parent_row_label", "");
    }

    focus_by_row_type(frm, cdt, cdn);
  },

  parent_row_id: function (frm, cdt, cdn) {
    update_parent_label_from_parent_id(frm, cdt, cdn);
  },

  service_period: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (row.row_type === "Sub Item" && !row.parent_row_id) {
      set_parent_from_previous_row(frm, cdt, cdn);
    }

    if (row.row_type === "Sub Item" && row.parent_row_id) {
      update_parent_label_from_parent_id(frm, cdt, cdn);
    }
  },

  meal_type: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (row.row_type === "Sub Item" && !row.parent_row_id) {
      set_parent_from_previous_row(frm, cdt, cdn);
    }

    if (row.row_type === "Sub Item" && row.parent_row_id) {
      update_parent_label_from_parent_id(frm, cdt, cdn);
    }
  },

  item_code: function (frm, cdt, cdn) {
    set_item_details_and_uom(frm, cdt, cdn);
  }
});


function prepare_new_menu_row(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  const previous_row = get_previous_row_by_idx(frm, row);

  if (previous_row) {
    frappe.model.set_value(cdt, cdn, "service_period", previous_row.service_period || "");
    frappe.model.set_value(cdt, cdn, "meal_type", previous_row.meal_type || "");

    if (previous_row.row_type === "New Item") {
      frappe.model.set_value(cdt, cdn, "row_type", "Sub Item");

      ensure_row_id_for_existing_new_item(frm, previous_row);

      frappe.model.set_value(cdt, cdn, "parent_row_id", previous_row.row_id || "");
      frappe.model.set_value(cdt, cdn, "parent_row_label", get_new_item_label(previous_row));
    } else if (previous_row.row_type === "Sub Item") {
      frappe.model.set_value(cdt, cdn, "row_type", "Sub Item");
      frappe.model.set_value(cdt, cdn, "parent_row_id", previous_row.parent_row_id || "");
      frappe.model.set_value(cdt, cdn, "parent_row_label", previous_row.parent_row_label || "");
    } else {
      frappe.model.set_value(cdt, cdn, "row_type", previous_row.row_type || "Item");
      frappe.model.set_value(cdt, cdn, "parent_row_id", "");
      frappe.model.set_value(cdt, cdn, "parent_row_label", "");
    }
  }

  clear_value_fields_for_new_row(frm, cdt, cdn);

  if (!row.is_show_print) {
    frappe.model.set_value(cdt, cdn, "is_show_print", 1);
  }

  setTimeout(function () {
    const updated_row = locals[cdt][cdn];

    if (updated_row && updated_row.row_type === "New Item") {
      ensure_row_id_for_new_item(frm, cdt, cdn);
    }

    if (updated_row && updated_row.row_type === "Sub Item" && !updated_row.parent_row_id) {
      set_parent_from_previous_row(frm, cdt, cdn);
    }

    focus_by_row_type(frm, cdt, cdn);
  }, 400);
}


function clear_value_fields_for_new_row(frm, cdt, cdn) {
  frappe.model.set_value(cdt, cdn, "section", "");
  frappe.model.set_value(cdt, cdn, "item_code", "");
  frappe.model.set_value(cdt, cdn, "item_name", "");
  frappe.model.set_value(cdt, cdn, "item_name_arabic", "");
  frappe.model.set_value(cdt, cdn, "new_item_name", "");
  frappe.model.set_value(cdt, cdn, "new_item_name_arabic", "");
  frappe.model.set_value(cdt, cdn, "qty", "");
  frappe.model.set_value(cdt, cdn, "uom", "");

  frm.refresh_field("items");
}


function get_previous_row_by_idx(frm, current_row) {
  const rows = (frm.doc.items || [])
    .slice()
    .sort(function (a, b) {
      return (a.idx || 0) - (b.idx || 0);
    });

  for (let i = 0; i < rows.length; i++) {
    if (rows[i].name === current_row.name && i > 0) {
      return rows[i - 1];
    }
  }

  return null;
}


function make_row_id() {
  return (
    "ROW-" +
    Math.random().toString(36).substring(2, 10).toUpperCase() +
    "-" +
    Date.now().toString(36).toUpperCase()
  );
}


function ensure_row_id_for_new_item(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (row.row_type !== "New Item") return;

  if (!row.row_id) {
    frappe.model.set_value(cdt, cdn, "row_id", make_row_id());
  }
}


function ensure_row_id_for_existing_new_item(frm, row) {
  if (!row) return;

  if (row.row_type !== "New Item") return;

  if (!row.row_id) {
    row.row_id = make_row_id();
    frm.refresh_field("items");
    frm.dirty();
  }
}


function ensure_new_item_row_ids(frm) {
  let changed = false;

  (frm.doc.items || []).forEach(function (row) {
    if (row.row_type === "New Item" && !row.row_id) {
      row.row_id = make_row_id();
      changed = true;
    }

    if (row.row_type !== "New Item" && row.row_id) {
      row.row_id = "";
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
    frappe.model.set_value(cdt, cdn, "qty", "");
    frappe.model.set_value(cdt, cdn, "uom", "");
  }
}


function set_parent_from_previous_row(frm, cdt, cdn) {
  const current_row = locals[cdt][cdn];

  if (!current_row) return;

  const previous_row = get_previous_row_by_idx(frm, current_row);

  if (!previous_row) return;

  if (previous_row.row_type === "New Item") {
    ensure_row_id_for_existing_new_item(frm, previous_row);

    frappe.model.set_value(cdt, cdn, "parent_row_id", previous_row.row_id || "");
    frappe.model.set_value(cdt, cdn, "parent_row_label", get_new_item_label(previous_row));

    return;
  }

  if (previous_row.row_type === "Sub Item" && previous_row.parent_row_id) {
    frappe.model.set_value(cdt, cdn, "parent_row_id", previous_row.parent_row_id || "");
    frappe.model.set_value(cdt, cdn, "parent_row_label", previous_row.parent_row_label || "");

    return;
  }

  if (current_row.parent_row_id) {
    update_parent_label_from_parent_id(frm, cdt, cdn);
  }
}


function get_new_item_map(frm) {
  const map = {};

  (frm.doc.items || []).forEach(function (row) {
    if (row.row_type === "New Item" && row.row_id) {
      map[row.row_id] = row;
    }
  });

  return map;
}


function get_new_item_label(row) {
  if (!row) return "";

  return (
    row.new_item_name_arabic ||
    row.new_item_name ||
    row.row_id ||
    ""
  );
}


function update_parent_label_from_parent_id(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row || row.row_type !== "Sub Item") return;

  if (!row.parent_row_id) {
    frappe.model.set_value(cdt, cdn, "parent_row_label", "");
    return;
  }

  const parent_map = get_new_item_map(frm);
  const parent = parent_map[row.parent_row_id];

  if (!parent) {
    frappe.model.set_value(cdt, cdn, "parent_row_label", "");
    return;
  }

  frappe.model.set_value(cdt, cdn, "parent_row_label", get_new_item_label(parent));
}


function auto_link_sub_items(frm) {
  (frm.doc.items || []).forEach(function (row) {
    if (row.row_type !== "Sub Item") return;

    if (!row.parent_row_id) {
      set_parent_from_previous_row(frm, row.doctype, row.name);
    } else {
      update_parent_label_from_parent_id(frm, row.doctype, row.name);
    }
  });
}


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


function validate_catering_menu_items(frm) {
  const parent_map = get_new_item_map(frm);

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

    if (row.row_type === "Section") {
      if (!row.section) {
        frappe.throw(__("Row #{0}: Section is required.", [row.idx]));
      }
    }

    if (row.row_type === "New Item") {
      if (!row.row_id) {
        frappe.throw(__("Row #{0}: Row ID is required for New Item.", [row.idx]));
      }

      if (!row.new_item_name && !row.new_item_name_arabic) {
        frappe.throw(__("Row #{0}: New Item Name or New Item Name Arabic is required.", [row.idx]));
      }
    }

    if (row.row_type === "Item" || row.row_type === "Sub Item") {
      if (!row.item_code) {
        frappe.throw(__("Row #{0}: Item Code is required for {1}.", [row.idx, row.row_type]));
      }

      if (!row.qty) {
        frappe.throw(__("Row #{0}: QTY is required for {1}.", [row.idx, row.row_type]));
      }

      if (!row.uom) {
        frappe.throw(__("Row #{0}: UOM is required for {1}.", [row.idx, row.row_type]));
      }
    }

    if (row.row_type === "Sub Item") {
      if (!row.parent_row_id) {
        frappe.throw(__("Row #{0}: Sub Item must be linked to a New Item using Parent Row ID.", [row.idx]));
      }

      const parent = parent_map[row.parent_row_id];

      if (!parent) {
        frappe.throw(__("Row #{0}: Parent Row ID is not linked to a valid New Item.", [row.idx]));
      }

      if (row.service_period !== parent.service_period) {
        frappe.throw(__("Row #{0}: Sub Item Service Period must match the linked New Item.", [row.idx]));
      }

      if (row.meal_type !== parent.meal_type) {
        frappe.throw(__("Row #{0}: Sub Item Meal Type must match the linked New Item.", [row.idx]));
      }
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