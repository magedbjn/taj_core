frappe.ui.form.on("Catering Dish", {
  onload(frm) {
    set_default_values(frm);
  },

  refresh(frm) {
    set_default_values(frm);
    set_queries(frm);
    update_recipe_basis_labels(frm);
    toggle_fields(frm);
    set_field_labels(frm);

    if (frm.is_new()) {
      frm.set_intro(__("Save the dish first to enable Calculation Preview."), "blue");
    }
  },

  dish_type(frm) {
    apply_dish_type_defaults(frm);
    clear_fields_by_dish_type(frm);
    toggle_fields(frm);
  },

  supply_mode(frm) {
    toggle_fields(frm);
  },

  item_code(frm) {
    set_item_details(frm);
  },

  recipe_basis_qty(frm) {
    calculate_stock_qty_per_person(frm);
  },

  default_uom(frm) {
    calculate_stock_qty_per_person(frm);
  },

  output_planning_method(frm) {
    clear_fields_by_output_planning_method(frm);
    update_recipe_basis_labels(frm);
    toggle_fields(frm);
  },

  output_rounding_method(frm) {
    toggle_fields(frm);
  },

  receiving_display_method(frm) {
    toggle_fields(frm);
  },

  show_output_qty_difference(frm) {
    toggle_fields(frm);
  },

  show_output_coverage_difference(frm) {
    toggle_fields(frm);
  },

  include_in_purchase(frm) {
    toggle_fields(frm);
  },

  include_in_production(frm) {
    toggle_fields(frm);
  },

  allow_partial_output_qty(frm) {
    if (!cint(frm.doc.allow_partial_output_qty)) {
      frm.set_value("run_partial_output", 0);
    }

    toggle_fields(frm);
  },

  default_workstation(frm) {
    set_workstation_defaults(frm);
    toggle_fields(frm);
  },

  workstation_load_qty(frm) {
    toggle_fields(frm);
  },

  workstation_load_uom(frm) {
    toggle_fields(frm);
  },

  workstation_calculation_method(frm) {
    toggle_fields(frm);
  },

  validate(frm) {
    validate_catering_dish(frm);
  }
});


frappe.ui.form.on("Catering Dish Material", {
  materials_add(frm, cdt, cdn) {
    set_material_row_defaults(frm, cdt, cdn);
  },

  material_item(frm, cdt, cdn) {
    set_material_item_details(frm, cdt, cdn);
  },

  material__calculation_base(frm, cdt, cdn) {
    clear_material_fields_by_calculation_base(frm, cdt, cdn);
    frm.refresh_field("materials");
  },

  qty_per_person(frm, cdt, cdn) {
    frm.refresh_field("materials");
  },

  qty_per_output(frm, cdt, cdn) {
    frm.refresh_field("materials");
  },

  include_in_purchase(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (!cint(row.include_in_purchase)) {
      frappe.model.set_value(cdt, cdn, "receiving_mode", "No Receiving");
      frappe.model.set_value(cdt, cdn, "receiving_capacity_qty", 0);
      frappe.model.set_value(cdt, cdn, "receiving_capacity_uom", "");
      frappe.model.set_value(cdt, cdn, "use_full_receiving_qty", 0);
      frappe.model.set_value(cdt, cdn, "is_scaling_driver", 0);
    }

    frm.refresh_field("materials");
  },

  include_in_production(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (!cint(row.include_in_production)) {
      frappe.model.set_value(cdt, cdn, "workstation", "");
      frappe.model.set_value(cdt, cdn, "operation", "");
    }

    frm.refresh_field("materials");
  },

  receiving_mode(frm, cdt, cdn) {
    clear_material_fields_by_receiving_mode(frm, cdt, cdn);
    frm.refresh_field("materials");
  },

  receiving_capacity_qty(frm, cdt, cdn) {
    frm.refresh_field("materials");
  },

  receiving_capacity_uom(frm, cdt, cdn) {
    frm.refresh_field("materials");
  },

  receiving_rounding_method(frm, cdt, cdn) {
    frm.refresh_field("materials");
  },

  is_scaling_driver(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (cint(row.is_scaling_driver)) {
      frappe.model.set_value(cdt, cdn, "use_full_receiving_qty", 1);
      ensure_single_scaling_driver(frm, cdt, cdn);
    }
  },

  use_full_receiving_qty(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (!cint(row.use_full_receiving_qty) && cint(row.is_scaling_driver)) {
      frappe.model.set_value(cdt, cdn, "is_scaling_driver", 0);
    }
  }
});


// -----------------------------------------------------------------------------
// Defaults
// -----------------------------------------------------------------------------

function set_default_values(frm) {
  if (frm.doc.is_active === undefined || frm.doc.is_active === null) {
    frm.set_value("is_active", 1);
  }

  if (!frm.doc.test_person_qty) {
    frm.set_value("test_person_qty", 100);
  }

  if (!frm.doc.output_planning_method) {
    frm.set_value("output_planning_method", "Manual");
  }

  if (!frm.doc.output_rounding_method) {
    frm.set_value("output_rounding_method", "Round Up");
  }

  if (!frm.doc.receiving_display_method) {
    frm.set_value("receiving_display_method", "Required Qty");
  }

  if (frm.doc.show_output_coverage_difference === undefined || frm.doc.show_output_coverage_difference === null) {
    frm.set_value("show_output_coverage_difference", 1);
  }

  if (frm.doc.show_output_qty_difference === undefined || frm.doc.show_output_qty_difference === null) {
    frm.set_value("show_output_qty_difference", 0);
  }
}


// -----------------------------------------------------------------------------
// Queries / Labels
// -----------------------------------------------------------------------------

function set_queries(frm) {
  frm.set_query("item_code", () => {
    return {
      filters: {
        disabled: 0
      }
    };
  });

  frm.set_query("default_workstation", () => {
    return {};
  });

  frm.set_query("workstation_load_uom", () => {
    return {};
  });

  frm.set_query("output_container_uom", () => {
    return {};
  });

  frm.set_query("output_container_capacity_uom", () => {
    return {};
  });

  frm.set_query("default_uom", () => {
    return {};
  });
}


function set_field_labels(frm) {
  frm.set_df_property("default_workstation", "label", "Equipment / Workstation");
  frm.set_df_property("workstation_calculation_method", "label", "Run Calculation Base");
  frm.set_df_property("workstation_load_qty", "label", "Run Load Qty");
  frm.set_df_property("workstation_load_uom", "label", "Run Load UOM");

  frm.set_df_property(
    "section_break_insg",
    "label",
    "Field Equipment / Run Information"
  );
}


// -----------------------------------------------------------------------------
// Toggle
// -----------------------------------------------------------------------------

function toggle_fields(frm) {
  const method = frm.doc.output_planning_method || "Manual";
  const dish_type = frm.doc.dish_type || "";

  const is_display_only = dish_type === "Display Only";
  const is_prepared = dish_type === "Prepared Dish";

  frm.toggle_display("item_and_supply_setup_section", !!dish_type && !is_display_only);
  frm.toggle_display("supply_mode", !!dish_type && !is_display_only);

  frm.toggle_display("item_code", cint(frm.doc.requires_item_code));
  frm.toggle_display("item_name", !!frm.doc.item_code);
  frm.toggle_display("item_name_arabic", !!frm.doc.item_code);

  frm.toggle_display("preparation_method", false);

  frm.toggle_display("materials_tab", is_prepared);
  frm.toggle_display("materials", is_prepared);

  frm.toggle_display("production_tab", !!dish_type && !is_display_only);
  frm.toggle_display("cooking__heating_settings_section", !!dish_type && !is_display_only);
  frm.toggle_display("section_break_insg", !!dish_type && !is_display_only);

  frm.toggle_display("default_workstation", !!dish_type && !is_display_only);
  frm.toggle_display("default_temperature", !!dish_type && !is_display_only);
  frm.toggle_display("default_duration_minutes", !!dish_type && !is_display_only);
  frm.toggle_display("holding_temperature", !!dish_type && !is_display_only);
  frm.toggle_display("holding_duration_minutes", !!dish_type && !is_display_only);

  frm.toggle_display("workstation_calculation_method", !!dish_type && !is_display_only);
  frm.toggle_display("workstation_load_qty", !!dish_type && !is_display_only);
  frm.toggle_display("workstation_load_uom", !!dish_type && !is_display_only);

  frm.toggle_display("production_output_section", !!dish_type && !is_display_only);
  frm.toggle_display("output_planning_method", !!dish_type && !is_display_only);

  frm.toggle_display("recipe_basis_qty", needs_recipe_basis_qty(method));
  frm.toggle_display("default_uom", needs_default_uom(method));

  frm.toggle_display("output_container_uom", method !== "Manual");

  frm.toggle_display(
    "output_container_capacity_qty",
    ["Dish Qty Per Person", "Sum Output Materials"].includes(method)
  );

  frm.toggle_display(
    "output_container_capacity_uom",
    ["Dish Qty Per Person", "Sum Output Materials"].includes(method)
  );

  frm.toggle_display("output_rounding_method", method !== "Manual");

  frm.toggle_display(
    "allow_partial_output_qty",
    ["Dish Qty Per Person", "Sum Output Materials"].includes(method)
  );

  frm.toggle_display(
    "run_partial_output",
    ["Dish Qty Per Person", "Sum Output Materials"].includes(method) && cint(frm.doc.allow_partial_output_qty)
  );

  frm.toggle_display(
    "show_output_coverage_difference",
    method === "Covers Persons"
  );

  frm.toggle_display(
    "show_output_qty_difference",
    ["Dish Qty Per Person", "Output Driver Material", "Sum Output Materials", "Covers Persons"].includes(method)
  );

  frm.toggle_display(
    "receiving_display_method",
    ["Dish Qty Per Person", "Covers Persons", "Per Buffet"].includes(method)
  );

  frm.toggle_display("stock_uom", !!frm.doc.item_code);
  frm.toggle_display(
    "uom_conversion_factor",
    !!frm.doc.stock_uom && !!frm.doc.default_uom && frm.doc.stock_uom !== frm.doc.default_uom
  );

  frm.toggle_display(
    "stock_qty_per_person",
    !!frm.doc.stock_uom && !!frm.doc.default_uom && frm.doc.stock_uom !== frm.doc.default_uom
  );

  frm.refresh_fields();
}


function needs_recipe_basis_qty(method) {
  return [
    "Dish Qty Per Person",
    "Covers Persons",
    "Output Driver Material",
    "Sum Output Materials"
  ].includes(method);
}


function needs_default_uom(method) {
  return [
    "Dish Qty Per Person",
    "Covers Persons",
    "Output Driver Material",
    "Sum Output Materials"
  ].includes(method);
}


// -----------------------------------------------------------------------------
// Dish Type
// -----------------------------------------------------------------------------

function apply_dish_type_defaults(frm) {
  if (!frm.doc.dish_type) return;

  frappe.db.get_value(
    "Catering Dish Type",
    frm.doc.dish_type,
    [
      "requires_item_code",
      "requires_recipe",
      "include_in_purchase",
      "include_in_production",
      "show_in_menu_print"
    ]
  ).then((r) => {
    const values = r.message || {};

    frm.set_value("requires_item_code", values.requires_item_code || 0);
    frm.set_value("requires_recipe", values.requires_recipe || 0);
    frm.set_value("include_in_purchase", values.include_in_purchase || 0);
    frm.set_value("include_in_production", values.include_in_production || 0);
    frm.set_value("show_in_menu_print", values.show_in_menu_print || 0);

    toggle_fields(frm);
  });
}


function clear_fields_by_dish_type(frm) {
  const dish_type = frm.doc.dish_type;

  if (!dish_type) return;

  if (["Finished Product", "Direct Item", "Disposable Item"].includes(dish_type)) {
    frm.clear_table("materials");
    frm.refresh_field("materials");

    if (
      !frm.doc.output_planning_method
      || ["Output Driver Material", "Sum Output Materials"].includes(frm.doc.output_planning_method)
    ) {
      frm.set_value("output_planning_method", "Dish Qty Per Person");
    }
  }

  if (dish_type === "Prepared Dish") {
    frm.set_value("item_code", "");
    frm.set_value("item_name", "");
    frm.set_value("item_name_arabic", "");
    frm.set_value("stock_uom", "");
    frm.set_value("uom_conversion_factor", 0);
    frm.set_value("stock_qty_per_person", 0);

    if (!frm.doc.output_planning_method || frm.doc.output_planning_method === "Dish Qty Per Person") {
      frm.set_value("output_planning_method", "Output Driver Material");
    }
  }

  if (dish_type === "Display Only") {
    frm.set_value("item_code", "");
    frm.set_value("item_name", "");
    frm.set_value("item_name_arabic", "");
    frm.set_value("supply_mode", "");
    frm.set_value("preparation_method", "");

    frm.set_value("recipe_basis_qty", 0);
    frm.set_value("default_uom", "");
    frm.set_value("stock_uom", "");
    frm.set_value("uom_conversion_factor", 0);
    frm.set_value("stock_qty_per_person", 0);

    frm.set_value("include_in_purchase", 0);
    frm.set_value("include_in_production", 0);

    frm.set_value("default_workstation", "");
    frm.set_value("workstation_calculation_method", "");
    frm.set_value("workstation_load_qty", 0);
    frm.set_value("workstation_load_uom", "");

    frm.set_value("output_planning_method", "Manual");
    frm.set_value("output_container_uom", "");
    frm.set_value("output_container_capacity_qty", 0);
    frm.set_value("output_container_capacity_uom", "");

    frm.clear_table("materials");
    frm.refresh_field("materials");
  }
}


// -----------------------------------------------------------------------------
// Item Details
// -----------------------------------------------------------------------------

function set_item_details(frm) {
  if (!frm.doc.item_code) {
    frm.set_value("item_name", "");
    frm.set_value("item_name_arabic", "");
    frm.set_value("stock_uom", "");
    frm.set_value("uom_conversion_factor", 0);
    frm.set_value("stock_qty_per_person", 0);
    return;
  }

  frappe.db.get_value(
    "Item",
    frm.doc.item_code,
    ["item_name", "item_name_arabic", "stock_uom"]
  ).then((r) => {
    const item = r.message || {};

    frm.set_value("item_name", item.item_name || "");
    frm.set_value("item_name_arabic", item.item_name_arabic || "");
    frm.set_value("stock_uom", item.stock_uom || "");

    if (!frm.doc.default_uom && item.stock_uom) {
      frm.set_value("default_uom", item.stock_uom);
    }

    calculate_stock_qty_per_person(frm);
  });
}


function calculate_stock_qty_per_person(frm) {
  if (!frm.doc.item_code || !frm.doc.default_uom || !frm.doc.stock_uom) return;

  if (frm.doc.default_uom === frm.doc.stock_uom) {
    frm.set_value("uom_conversion_factor", 1);
    frm.set_value("stock_qty_per_person", flt(frm.doc.recipe_basis_qty || 0));
    return;
  }

  frappe.call({
    method: "erpnext.stock.get_item_details.get_conversion_factor",
    args: {
      item_code: frm.doc.item_code,
      uom: frm.doc.default_uom
    },
    callback(r) {
      const factor = r.message && r.message.conversion_factor
        ? flt(r.message.conversion_factor)
        : 0;

      frm.set_value("uom_conversion_factor", factor);

      const stock_qty = flt(frm.doc.recipe_basis_qty || 0) * factor;
      frm.set_value("stock_qty_per_person", stock_qty);
    }
  });
}


// -----------------------------------------------------------------------------
// Output Planning Cleanup
// -----------------------------------------------------------------------------

function clear_fields_by_output_planning_method(frm) {
  const method = frm.doc.output_planning_method || "Manual";

  if (method === "Covers Persons") {
    frm.set_value("output_container_capacity_qty", 0);
    frm.set_value("output_container_capacity_uom", "");
    
    if (!frm.doc.default_uom) {
      frm.set_value("default_uom", "Person");
    }

    if (!frm.doc.output_rounding_method) {
      frm.set_value("output_rounding_method", "Round Up");
    }
  }

  if (method === "Output Driver Material") {
    frm.set_value("output_container_capacity_qty", 0);
    frm.set_value("output_container_capacity_uom", "");
    frm.set_value("receiving_display_method", "Required Qty");

    if (!frm.doc.default_uom) {
      frm.set_value("default_uom", "Person");
    }

    if (!frm.doc.recipe_basis_qty) {
      frm.set_value("recipe_basis_qty", 1);
    }

    if (!frm.doc.output_rounding_method) {
      frm.set_value("output_rounding_method", "Round Up");
    }
  }

  if (method === "Per Buffet") {
    frm.set_value("output_container_capacity_qty", 0);
    frm.set_value("output_container_capacity_uom", "");
    frm.set_value("allow_partial_output_qty", 0);
    frm.set_value("run_partial_output", 0);
    frm.set_value("recipe_basis_qty", 0);
    frm.set_value("default_uom", "");
    
    if (!frm.doc.output_rounding_method) {
      frm.set_value("output_rounding_method", "No Rounding");
    }
  }

  if (method === "Manual") {
    frm.set_value("recipe_basis_qty", 0);
    frm.set_value("default_uom", "");
    frm.set_value("output_container_uom", "");
    frm.set_value("output_container_capacity_qty", 0);
    frm.set_value("output_container_capacity_uom", "");
    frm.set_value("allow_partial_output_qty", 0);
    frm.set_value("run_partial_output", 0);
    frm.set_value("show_output_qty_difference", 0);
  }

  if (["Dish Qty Per Person", "Sum Output Materials"].includes(method)) {
    if (!frm.doc.output_rounding_method) {
      frm.set_value("output_rounding_method", "Round Up");
    }
  }
}


// -----------------------------------------------------------------------------
// Workstation Defaults
// -----------------------------------------------------------------------------
// Workstation is informational only.
// Run load stays in Catering Dish and is used only for print/report calculation.

function set_workstation_defaults(frm) {
  if (!frm.doc.default_workstation) return;

  frappe.db.get_value(
    "Catering Workstation",
    frm.doc.default_workstation,
    [
      "default_unit_capacity_qty",
      "default_unit_capacity_uom",
      "default_temperature",
      "default_duration_minutes"
    ]
  ).then((r) => {
    const ws = r.message || {};

    if (ws.default_unit_capacity_qty && !frm.doc.workstation_load_qty) {
      frm.set_value("workstation_load_qty", ws.default_unit_capacity_qty);
    }

    if (ws.default_unit_capacity_uom && !frm.doc.workstation_load_uom) {
      frm.set_value("workstation_load_uom", ws.default_unit_capacity_uom);
    }

    if (ws.default_temperature) {
      frm.set_value("default_temperature", ws.default_temperature);
    }

    if (ws.default_duration_minutes) {
      frm.set_value("default_duration_minutes", ws.default_duration_minutes);
    }
  });
}


// -----------------------------------------------------------------------------
// Materials
// -----------------------------------------------------------------------------

function set_material_row_defaults(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (!row.material__calculation_base) {
    frappe.model.set_value(cdt, cdn, "material__calculation_base", "Per Person");
  }

  if (!row.receiving_mode) {
    frappe.model.set_value(cdt, cdn, "receiving_mode", "Single Unit");
  }

  if (!row.receiving_rounding_method) {
    frappe.model.set_value(cdt, cdn, "receiving_rounding_method", "Round Up");
  }

  if (row.include_in_purchase === undefined || row.include_in_purchase === null) {
    frappe.model.set_value(cdt, cdn, "include_in_purchase", 1);
  }

  if (row.include_in_production === undefined || row.include_in_production === null) {
    frappe.model.set_value(cdt, cdn, "include_in_production", 1);
  }

  if (row.include_in_output_qty === undefined || row.include_in_output_qty === null) {
    frappe.model.set_value(cdt, cdn, "include_in_output_qty", 0);
  }

  if (row.follow_scaling_driver === undefined || row.follow_scaling_driver === null) {
    frappe.model.set_value(cdt, cdn, "follow_scaling_driver", 1);
  }
}


function set_material_item_details(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row || !row.material_item) return;

  frappe.db.get_value(
    "Item",
    row.material_item,
    ["stock_uom"]
  ).then((r) => {
    const item = r.message || {};

    if (!row.uom && item.stock_uom) {
      frappe.model.set_value(cdt, cdn, "uom", item.stock_uom);
    }
  });
}


function clear_material_fields_by_calculation_base(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  const base = row.material__calculation_base || "Per Person";

  if (base === "Per Person") {
    frappe.model.set_value(cdt, cdn, "qty_per_output", 0);
  }

  if (base === "Per Output") {
    frappe.model.set_value(cdt, cdn, "qty_per_person", 0);
    frappe.model.set_value(cdt, cdn, "include_in_output_qty", 0);
  }

  if (base === "Output Driver") {
    frappe.model.set_value(cdt, cdn, "include_in_output_qty", 0);
  }

  if (base === "Manual") {
    frappe.model.set_value(cdt, cdn, "qty_per_person", 0);
    frappe.model.set_value(cdt, cdn, "qty_per_output", 0);
    frappe.model.set_value(cdt, cdn, "include_in_output_qty", 0);
  }
}


function clear_material_fields_by_receiving_mode(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  const mode = row.receiving_mode || "Single Unit";

  if (mode !== "Unit Breakdown") {
    frappe.model.set_value(cdt, cdn, "base_receiving_uom", "");
    frappe.model.set_value(cdt, cdn, "small_pack_qty", 0);
    frappe.model.set_value(cdt, cdn, "small_pack_uom", "");
    frappe.model.set_value(cdt, cdn, "large_pack_qty", 0);
    frappe.model.set_value(cdt, cdn, "large_pack_uom", "");
  }

  if (mode !== "Small Qty Rule") {
    frappe.model.set_value(cdt, cdn, "small_qty_threshold_percent", 0);
    frappe.model.set_value(cdt, cdn, "small_qty_uom", "");
  }

  if (mode === "No Receiving") {
    frappe.model.set_value(cdt, cdn, "receiving_capacity_qty", 0);
    frappe.model.set_value(cdt, cdn, "receiving_capacity_uom", "");
    frappe.model.set_value(cdt, cdn, "receiving_rounding_method", "No Rounding");
    frappe.model.set_value(cdt, cdn, "use_full_receiving_qty", 0);
    frappe.model.set_value(cdt, cdn, "is_scaling_driver", 0);
  }

  if (["Single Unit", "Unit Breakdown", "Small Qty Rule"].includes(mode)) {
    if (!row.receiving_rounding_method || row.receiving_rounding_method === "No Rounding") {
      frappe.model.set_value(cdt, cdn, "receiving_rounding_method", "Round Up");
    }
  }
}


function ensure_single_scaling_driver(frm, cdt, cdn) {
  const current = locals[cdt][cdn];

  if (!current || !cint(current.is_scaling_driver)) return;

  (frm.doc.materials || []).forEach((row) => {
    if (row.name !== current.name && cint(row.is_scaling_driver)) {
      frappe.model.set_value(row.doctype, row.name, "is_scaling_driver", 0);
    }
  });

  frm.refresh_field("materials");
}


// -----------------------------------------------------------------------------
// Validation
// -----------------------------------------------------------------------------

function validate_catering_dish(frm) {
  validate_required_fields(frm);
  validate_output_planning(frm);
  validate_material_rows(frm);
  validate_workstation_run_setup(frm);
}


function validate_required_fields(frm) {
  if (!frm.doc.dish_name) {
    frappe.throw(__("Dish Name is required."));
  }

  if (!frm.doc.dish_type) {
    frappe.throw(__("Dish Type is required."));
  }

  if (!frm.doc.default_section) {
    frappe.throw(__("Default Section is required."));
  }

  if (frm.doc.dish_type !== "Display Only" && !frm.doc.supply_mode) {
    frappe.throw(__("Supply Mode is required."));
  }

  if (cint(frm.doc.requires_item_code) && !frm.doc.item_code) {
    frappe.throw(__("Item Code is required for this Dish Type."));
  }

  if (cint(frm.doc.requires_recipe) && !(frm.doc.materials || []).length) {
    frappe.throw(__("Materials are required for this Dish Type."));
  }
}


function validate_output_planning(frm) {
  const method = frm.doc.output_planning_method || "Manual";

  if (method === "Manual") return;

  if (!frm.doc.output_container_uom) {
    frappe.throw(__("Output Container UOM is required."));
  }

  if (method === "Dish Qty Per Person") {
    if (flt(frm.doc.recipe_basis_qty || 0) <= 0 || !frm.doc.default_uom) {
      frappe.throw(__("Default Recipe Basis Qty and UOM are required for Dish Qty Per Person."));
    }

    if (flt(frm.doc.output_container_capacity_qty || 0) <= 0 || !frm.doc.output_container_capacity_uom) {
      frappe.throw(__("Output Container Capacity Qty and UOM are required for Dish Qty Per Person."));
    }
  }

  if (method === "Covers Persons") {
    if (flt(frm.doc.recipe_basis_qty || 0) <= 0 || frm.doc.default_uom !== "Person") {
      frappe.throw(__("For Covers Persons, Default Recipe Basis Qty must be greater than 0 and UOM must be Person."));
    }
  }

  if (method === "Output Driver Material") {
    const drivers = (frm.doc.materials || []).filter((row) => row.material__calculation_base === "Output Driver");

    if (!drivers.length) {
      frappe.throw(__("One material must be marked as Output Driver."));
    }

    if (drivers.length > 1) {
      frappe.throw(__("Only one material can be marked as Output Driver."));
    }
  }

  if (method === "Sum Output Materials") {
    const output_rows = (frm.doc.materials || []).filter((row) => cint(row.include_in_output_qty || 0));

    if (!output_rows.length) {
      frappe.throw(__("At least one material must be marked Include in Output Qty."));
    }

    if (flt(frm.doc.output_container_capacity_qty || 0) <= 0 || !frm.doc.output_container_capacity_uom) {
      frappe.throw(__("Output Container Capacity Qty and UOM are required for Sum Output Materials."));
    }
  }
}


function validate_material_rows(frm) {
  (frm.doc.materials || []).forEach((row) => {
    if (!row.material_item) return;

    const base = row.material__calculation_base || "Per Person";

    if (base !== "Manual" && !row.uom) {
      frappe.throw(__("Row #{0}: UOM is required.", [row.idx]));
    }

    if (base === "Per Person" && flt(row.qty_per_person || 0) <= 0) {
      frappe.throw(__("Row #{0}: Qty For Recipe Basis is required for Per Person material.", [row.idx]));
    }

    if (base === "Per Output" && flt(row.qty_per_output || 0) <= 0) {
      frappe.throw(__("Row #{0}: Qty Per Output is required for Per Output material.", [row.idx]));
    }

    if (base === "Output Driver") {
      if (flt(row.qty_per_person || 0) <= 0) {
        frappe.throw(__("Row #{0}: Qty For Recipe Basis is required for Output Driver material.", [row.idx]));
      }

      if (flt(row.qty_per_output || 0) <= 0) {
        frappe.throw(__("Row #{0}: Qty Per Output is required for Output Driver material.", [row.idx]));
      }
    }

    if (cint(row.include_in_purchase || 0) && (row.receiving_mode || "Single Unit") !== "No Receiving") {
      validate_receiving_row(row);
    }
  });
}


function validate_receiving_row(row) {
  const mode = row.receiving_mode || "Single Unit";

  if (mode === "Single Unit") {
    if (flt(row.receiving_capacity_qty || 0) <= 0 || !row.receiving_capacity_uom) {
      frappe.throw(__("Row #{0}: Receiving Capacity Qty and UOM are required.", [row.idx]));
    }
  }

  if (mode === "Unit Breakdown") {
    if (flt(row.large_pack_qty || 0) <= 0 || !row.large_pack_uom) {
      frappe.throw(__("Row #{0}: Large Pack Qty and UOM are required for Unit Breakdown.", [row.idx]));
    }

    if (flt(row.small_pack_qty || 0) <= 0 || !row.small_pack_uom) {
      frappe.throw(__("Row #{0}: Small Pack Qty and UOM are required for Unit Breakdown.", [row.idx]));
    }
  }

  if (mode === "Small Qty Rule") {
    if (flt(row.receiving_capacity_qty || 0) <= 0 || !row.receiving_capacity_uom) {
      frappe.throw(__("Row #{0}: Receiving Capacity Qty and UOM are required for Small Qty Rule.", [row.idx]));
    }

    if (flt(row.small_qty_threshold_percent || 0) <= 0 || !row.small_qty_uom) {
      frappe.throw(__("Row #{0}: Small Qty Threshold Percent and Small Qty UOM are required for Small Qty Rule.", [row.idx]));
    }
  }
}


function validate_workstation_run_setup(frm) {
  if (!frm.doc.default_workstation && !frm.doc.workstation_calculation_method && flt(frm.doc.workstation_load_qty || 0) <= 0) {
    return;
  }

  if (flt(frm.doc.workstation_load_qty || 0) > 0 && !frm.doc.workstation_load_uom) {
    frappe.throw(__("Run Load UOM is required when Run Load Qty is entered."));
  }

  if (frm.doc.workstation_load_uom && flt(frm.doc.workstation_load_qty || 0) <= 0) {
    frappe.throw(__("Run Load Qty is required when Run Load UOM is entered."));
  }

  if (flt(frm.doc.workstation_load_qty || 0) > 0 && !frm.doc.workstation_calculation_method) {
    frappe.throw(__("Run Calculation Base is required when Run Load Qty is entered."));
  }
}

function update_recipe_basis_labels(frm) {
  const method = frm.doc.output_planning_method || "Manual";

  let qty_label = "Default Recipe Basis Qty";
  let qty_description = "Base quantity used by the selected output planning method.";
  let uom_label = "Default Recipe Basis UOM";
  let uom_description = "UOM for the recipe basis quantity.";

  if (method === "Dish Qty Per Person") {
    qty_label = "Qty Per Person";
    qty_description = "Quantity required per one person. Example: 1.2 Pouch per person.";
    uom_label = "Qty Per Person UOM";
    uom_description = "UOM of the quantity required per person.";
  }

  else if (method === "Covers Persons") {
    qty_label = "Persons Covered Per Output";
    qty_description = "Number of persons covered by one output container. Example: 30 persons per Chafing Dish.";
    uom_label = "Coverage UOM";
    uom_description = "Usually Person.";
  }

  else if (method === "Output Driver Material") {
    qty_label = "Recipe Basis Multiplier";
    qty_description = "Multiplier used with material Qty For Recipe Basis to calculate Qty Per Person. Usually 1 Person.";
    uom_label = "Recipe Basis UOM";
    uom_description = "Usually Person.";
  }

  else if (method === "Sum Output Materials") {
    qty_label = "Recipe Basis Multiplier";
    qty_description = "Multiplier used with included output materials to calculate output base quantity. Usually 1 Person.";
    uom_label = "Recipe Basis UOM";
    uom_description = "Usually Person.";
  }

  else if (method === "Per Buffet") {
    qty_label = "Not Used";
    qty_description = "Not used for Per Buffet. Output Qty is calculated from Default Buffet Qty.";
    uom_label = "Not Used";
    uom_description = "Not used for Per Buffet.";
  }

  else if (method === "Manual") {
    qty_label = "Not Used";
    qty_description = "Not used for Manual planning.";
    uom_label = "Not Used";
    uom_description = "Not used for Manual planning.";
  }

  frm.set_df_property("recipe_basis_qty", "label", qty_label);
  frm.set_df_property("recipe_basis_qty", "description", qty_description);

  frm.set_df_property("default_uom", "label", uom_label);
  frm.set_df_property("default_uom", "description", uom_description);

  frm.refresh_field("recipe_basis_qty");
  frm.refresh_field("default_uom");
}