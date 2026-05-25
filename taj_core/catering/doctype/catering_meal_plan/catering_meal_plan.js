frappe.ui.form.on("Catering Meal Plan", {
  onload(frm) {
    set_default_values(frm);
    set_queries(frm);
  },

  refresh(frm) {
    set_default_values(frm);
    set_queries(frm);
    set_indicators(frm);
    add_custom_buttons(frm);
  },

  plan_date(frm) {
    set_indicators(frm);
  },

  meal_type(frm) {
    set_template_filter(frm);
    clear_template_if_meal_type_changed(frm);
  },

  menu_template(frm) {
    fetch_template_details(frm);
  },

  person_qty(frm) {
    set_final_person_qty(frm);
    update_items_person_qty(frm);
  },

  actual_person_qty(frm) {
    set_final_person_qty(frm);
    update_items_person_qty(frm);
  },

  final_person_qty(frm) {
    update_items_person_qty(frm);
  },

  validate(frm) {
    validate_meal_plan(frm);
  }
});


frappe.ui.form.on("Catering Meal Plan Item", {
  items_add(frm, cdt, cdn) {
    set_child_defaults(frm, cdt, cdn);
  },

  dish(frm, cdt, cdn) {
    fetch_dish_details(frm, cdt, cdn);
  },

  person_qty(frm, cdt, cdn) {
    // لاحقًا عند إضافة الحسابات، هذا الحقل سيؤثر على حساب الصنف
  },

  include_in_calculation(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (!cint(row.include_in_calculation)) {
      // لاحقًا يمكن إخفاء الحسابات أو تصفيرها
    }
  },

  print_in_menu(frm, cdt, cdn) {
    // خاص بالطباعة لاحقًا
  }
});


// -----------------------------------------------------------------------------
// Parent Defaults
// -----------------------------------------------------------------------------

function set_default_values(frm) {
  if (!frm.doc.plan_date) {
    frm.set_value("plan_date", frappe.datetime.get_today());
  }

  if (!frm.doc.status) {
    frm.set_value("status", "Draft");
  }

  if (frm.doc.person_qty === undefined || frm.doc.person_qty === null) {
    frm.set_value("person_qty", 0);
  }

  if (frm.doc.actual_person_qty === undefined || frm.doc.actual_person_qty === null) {
    frm.set_value("actual_person_qty", 0);
  }

  set_final_person_qty(frm);
}


function set_final_person_qty(frm) {
  const actual_person_qty = flt(frm.doc.actual_person_qty || 0);
  const person_qty = flt(frm.doc.person_qty || 0);

  if (actual_person_qty > 0) {
    frm.set_value("final_person_qty", actual_person_qty);
  } else {
    frm.set_value("final_person_qty", person_qty);
  }
}


// -----------------------------------------------------------------------------
// Queries
// -----------------------------------------------------------------------------

function set_queries(frm) {
  frm.set_query("meal_type", () => {
    return {};
  });

  frm.set_query("menu_template", () => {
    if (frm.doc.meal_type) {
      return {
        filters: {
          is_active: 1,
          meal_type: frm.doc.meal_type
        }
      };
    }

    return {
      filters: {
        is_active: 1
      }
    };
  });

  frm.set_query("dish", "items", () => {
    return {
      filters: {
        is_active: 1
      }
    };
  });

  frm.set_query("section", "items", () => {
    return {};
  });
}


function set_template_filter(frm) {
  frm.set_query("menu_template", () => {
    if (frm.doc.meal_type) {
      return {
        filters: {
          is_active: 1,
          meal_type: frm.doc.meal_type
        }
      };
    }

    return {
      filters: {
        is_active: 1
      }
    };
  });
}


// -----------------------------------------------------------------------------
// UI
// -----------------------------------------------------------------------------

function set_indicators(frm) {
  if (!frm.doc.menu_template) {
    frm.set_intro(__("Select a Menu Template, then generate items."), "blue");
    return;
  }

  if (!frm.doc.items || !frm.doc.items.length) {
    frm.set_intro(__("Click Generate Items From Template to load dishes."), "blue");
    return;
  }

  if (frm.doc.status === "Generated") {
    frm.set_intro(__("Items have been generated from the selected template."), "green");
    return;
  }

  frm.set_intro("");
}


function add_custom_buttons(frm) {
  if (frm.is_new()) {
    return;
  }

  frm.add_custom_button(__("Generate Items From Template"), () => {
    generate_items_from_template(frm);
  }, __("Actions"));

  frm.add_custom_button(__("Refresh Dish Details"), () => {
    refresh_all_dish_details(frm);
  }, __("Actions"));
}


// -----------------------------------------------------------------------------
// Template
// -----------------------------------------------------------------------------

function clear_template_if_meal_type_changed(frm) {
  if (!frm.doc.menu_template || !frm.doc.meal_type) return;

  frappe.db.get_value(
    "Catering Menu Template",
    frm.doc.menu_template,
    ["meal_type"]
  ).then((r) => {
    const template = r.message || {};

    if (template.meal_type && template.meal_type !== frm.doc.meal_type) {
      frm.set_value("menu_template", "");
      frm.clear_table("items");
      frm.refresh_field("items");
      frappe.msgprint({
        title: __("Template Cleared"),
        message: __("Menu Template was cleared because Meal Type changed."),
        indicator: "orange"
      });
    }
  });
}


function fetch_template_details(frm) {
  if (!frm.doc.menu_template) return;

  frappe.db.get_value(
    "Catering Menu Template",
    frm.doc.menu_template,
    ["meal_type", "is_active"]
  ).then((r) => {
    const template = r.message || {};

    if (!template) return;

    if (!cint(template.is_active)) {
      frappe.msgprint({
        title: __("Inactive Template"),
        message: __("The selected Menu Template is inactive."),
        indicator: "orange"
      });
    }

    if (template.meal_type && !frm.doc.meal_type) {
      frm.set_value("meal_type", template.meal_type);
    }

    if (template.meal_type && frm.doc.meal_type && template.meal_type !== frm.doc.meal_type) {
      frappe.msgprint({
        title: __("Meal Type Mismatch"),
        message: __("Selected template meal type does not match Meal Plan meal type."),
        indicator: "red"
      });
    }
  });
}


function generate_items_from_template(frm) {
  if (!frm.doc.menu_template) {
    frappe.msgprint({
      title: __("Missing Template"),
      message: __("Please select Menu Template first."),
      indicator: "red"
    });
    return;
  }

  if (flt(frm.doc.final_person_qty || 0) <= 0) {
    frappe.msgprint({
      title: __("Missing Person Qty"),
      message: __("Please enter Person Qty or Actual Person Qty first."),
      indicator: "red"
    });
    return;
  }

  frappe.confirm(
    __("This will replace current items with template items. Continue?"),
    () => {
      frm.call({
        doc: frm.doc,
        method: "generate_items_from_template",
        freeze: true,
        freeze_message: __("Generating items from template..."),
        callback(r) {
          if (!r.exc) {
            const result = r.message || {};
            frm.refresh_field("items");
            frm.set_value("status", result.status || "Generated");

            frappe.msgprint({
              title: __("Items Generated"),
              message: __("Generated {0} item(s) using Final Person Qty {1}.", [
                result.items_count || 0,
                result.final_person_qty || frm.doc.final_person_qty
              ]),
              indicator: "green"
            });
          }
        }
      });
    }
  );
}


// -----------------------------------------------------------------------------
// Child Defaults
// -----------------------------------------------------------------------------

function set_child_defaults(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (!row.person_qty || flt(row.person_qty) <= 0) {
    frappe.model.set_value(cdt, cdn, "person_qty", frm.doc.final_person_qty || frm.doc.person_qty || 0);
  }

  if (row.is_required === undefined || row.is_required === null) {
    frappe.model.set_value(cdt, cdn, "is_required", 1);
  }

  if (row.include_in_calculation === undefined || row.include_in_calculation === null) {
    frappe.model.set_value(cdt, cdn, "include_in_calculation", 1);
  }

  if (row.print_in_menu === undefined || row.print_in_menu === null) {
    frappe.model.set_value(cdt, cdn, "print_in_menu", 1);
  }
}


// -----------------------------------------------------------------------------
// Dish Details
// -----------------------------------------------------------------------------

function fetch_dish_details(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row || !row.dish) {
    clear_dish_details(cdt, cdn);
    return;
  }

  frappe.db.get_value(
    "Catering Dish",
    row.dish,
    [
      "dish_name",
      "dish_name_arabic",
      "dish_type",
      "supply_mode",
      "default_section",
      "is_active",
      "show_in_menu_print"
    ]
  ).then((r) => {
    const dish = r.message || {};

    if (!dish) {
      clear_dish_details(cdt, cdn);
      return;
    }

    if (!cint(dish.is_active)) {
      frappe.msgprint({
        title: __("Inactive Dish"),
        message: __("The selected dish is inactive."),
        indicator: "orange"
      });
    }

    frappe.model.set_value(cdt, cdn, "dish_name", dish.dish_name || "");
    frappe.model.set_value(cdt, cdn, "dish_name_arabic", dish.dish_name_arabic || "");
    frappe.model.set_value(cdt, cdn, "dish_type", dish.dish_type || "");
    frappe.model.set_value(cdt, cdn, "supply_mode", dish.supply_mode || "");

    if (!row.section && dish.default_section) {
      frappe.model.set_value(cdt, cdn, "section", dish.default_section);
    }

    if (dish.show_in_menu_print !== undefined && dish.show_in_menu_print !== null) {
      frappe.model.set_value(cdt, cdn, "print_in_menu", cint(dish.show_in_menu_print));
    }

    frm.refresh_field("items");
  });
}


function clear_dish_details(cdt, cdn) {
  frappe.model.set_value(cdt, cdn, "dish_name", "");
  frappe.model.set_value(cdt, cdn, "dish_name_arabic", "");
  frappe.model.set_value(cdt, cdn, "dish_type", "");
  frappe.model.set_value(cdt, cdn, "supply_mode", "");
}


function refresh_all_dish_details(frm) {
  const rows = frm.doc.items || [];

  if (!rows.length) {
    frappe.msgprint(__("No items to refresh."));
    return;
  }

  rows.forEach((row) => {
    if (row.dish) {
      fetch_dish_details(frm, row.doctype, row.name);
    }
  });

  frappe.show_alert({
    message: __("Dish details refreshed."),
    indicator: "green"
  });
}


// -----------------------------------------------------------------------------
// Person Qty
// -----------------------------------------------------------------------------

function update_items_person_qty(frm) {
  const final_person_qty = flt(frm.doc.final_person_qty || 0);

  if (!frm.doc.items || !frm.doc.items.length) return;

  (frm.doc.items || []).forEach((row) => {
    if (!row.person_qty || flt(row.person_qty) <= 0) {
      row.person_qty = final_person_qty;
    }
  });

  frm.refresh_field("items");
}


// -----------------------------------------------------------------------------
// Validation
// -----------------------------------------------------------------------------

function validate_meal_plan(frm) {
  if (!frm.doc.plan_date) {
    frappe.throw(__("Plan Date is required."));
  }

  if (!frm.doc.meal_type) {
    frappe.throw(__("Meal Type is required."));
  }

  if (!frm.doc.menu_template) {
    frappe.throw(__("Menu Template is required."));
  }

  if (flt(frm.doc.person_qty || 0) <= 0 && flt(frm.doc.actual_person_qty || 0) <= 0) {
    frappe.throw(__("Person Qty or Actual Person Qty is required."));
  }

  validate_duplicate_dishes(frm);
  validate_child_rows(frm);
}


function validate_duplicate_dishes(frm) {
  const seen = {};

  (frm.doc.items || []).forEach((row) => {
    if (!row.dish) return;

    if (seen[row.dish]) {
      frappe.throw(__("Dish {0} is duplicated in rows #{1} and #{2}.", [
        row.dish,
        seen[row.dish],
        row.idx
      ]));
    }

    seen[row.dish] = row.idx;
  });
}


function validate_child_rows(frm) {
  (frm.doc.items || []).forEach((row) => {
    if (!row.dish) {
      frappe.throw(__("Row #{0}: Dish is required.", [row.idx]));
    }

    if (!row.dish_name) {
      frappe.throw(__("Row #{0}: Dish Name was not fetched. Please reselect the Dish.", [row.idx]));
    }

    if (flt(row.person_qty || 0) <= 0) {
      frappe.throw(__("Row #{0}: Person Qty is required.", [row.idx]));
    }
  });
}