frappe.ui.form.on("Catering Menu Template", {
  onload(frm) {
    set_default_values(frm);
    set_queries(frm);
  },

  refresh(frm) {
    set_default_values(frm);
    set_queries(frm);
    set_indicators(frm);
  },

  template_name(frm) {
    if (!frm.doc.template_name_arabic && frm.doc.template_name) {
      // لا ننسخ الاسم تلقائياً للعربي، فقط نتركه للمستخدم
    }
  },

  meal_type(frm) {
    set_indicators(frm);
  },

  validate(frm) {
    validate_menu_template(frm);
  }
});


frappe.ui.form.on("Catering Menu Template Item", {
  items_add(frm, cdt, cdn) {
    set_child_defaults(frm, cdt, cdn);
  },

  dish(frm, cdt, cdn) {
    fetch_dish_details(frm, cdt, cdn);
  },

  is_required(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (!cint(row.is_required)) {
      frappe.model.set_value(cdt, cdn, "include_in_calculation", 0);
    }
  },

  include_in_calculation(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (cint(row.include_in_calculation) && !cint(row.is_required)) {
      // مسموح: يمكن أن يكون الصنف غير إلزامي لكنه يدخل في الحساب إذا اختاره المستخدم
    }
  },

  print_in_menu(frm, cdt, cdn) {
    // لا يوجد منطق إلزامي الآن
  }
});


// -----------------------------------------------------------------------------
// Parent Defaults
// -----------------------------------------------------------------------------

function set_default_values(frm) {
  if (frm.doc.is_active === undefined || frm.doc.is_active === null) {
    frm.set_value("is_active", 1);
  }

  (frm.doc.items || []).forEach((row) => {
    if (row.is_required === undefined || row.is_required === null) {
      row.is_required = 1;
    }

    if (row.include_in_calculation === undefined || row.include_in_calculation === null) {
      row.include_in_calculation = 1;
    }

    if (row.print_in_menu === undefined || row.print_in_menu === null) {
      row.print_in_menu = 1;
    }
  });

  frm.refresh_field("items");
}


// -----------------------------------------------------------------------------
// Queries
// -----------------------------------------------------------------------------

function set_queries(frm) {
  frm.set_query("meal_type", () => {
    return {};
  });

  frm.set_query("dish", "items", () => {
    return {
      filters: {
        is_active: 1
      }
    };
  });

  frm.set_query("default_section", "items", () => {
    return {};
  });
}


// -----------------------------------------------------------------------------
// UI Indicators
// -----------------------------------------------------------------------------

function set_indicators(frm) {
  if (!frm.doc.is_active) {
    frm.set_intro(__("This menu template is inactive."), "orange");
    return;
  }

  if (!frm.doc.items || !frm.doc.items.length) {
    frm.set_intro(__("Add dishes to this template."), "blue");
    return;
  }

  frm.set_intro("");
}


// -----------------------------------------------------------------------------
// Child Defaults
// -----------------------------------------------------------------------------

function set_child_defaults(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

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
// Fetch Dish Details
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

    if (!row.default_section && dish.default_section) {
      frappe.model.set_value(cdt, cdn, "default_section", dish.default_section);
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


// -----------------------------------------------------------------------------
// Validation
// -----------------------------------------------------------------------------

function validate_menu_template(frm) {
  if (!frm.doc.template_name) {
    frappe.throw(__("Template Name is required."));
  }

  if (!frm.doc.meal_type) {
    frappe.throw(__("Meal Type is required."));
  }

  if (!frm.doc.items || !frm.doc.items.length) {
    frappe.throw(__("At least one dish is required in the menu template."));
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
      // في حال fetch_from لم يعمل لأي سبب
      frappe.throw(__("Row #{0}: Dish Name was not fetched. Please reselect the Dish.", [row.idx]));
    }
  });
}