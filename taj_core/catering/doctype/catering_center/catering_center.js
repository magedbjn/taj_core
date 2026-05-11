frappe.ui.form.on("Catering Center", {
  onload: function (frm) {
    init_catering_center_form(frm);
  },

  refresh: function (frm) {
    init_catering_center_form(frm);
  },

  catering_menu: function (frm) {
    frm.__menu_service_periods = [];

    load_menu_service_periods(frm).then(function () {
      setup_buffet_exception_filters(frm);
      update_exception_grid_options(frm);
      update_all_exception_previews(frm);
    });
  },

  person_qty: function (frm) {
    calculate_buffet_totals(frm);
    update_all_exception_previews(frm);
  },

  before_save: function (frm) {
    calculate_buffet_totals(frm);
    update_all_exception_previews(frm);
    validate_buffet_exceptions_client(frm);
  }
});


frappe.ui.form.on("Catering Center Buffet", {
  buffet: function (frm) {
    refresh_buffet_related(frm);
  },

  buffet_company: function (frm) {
    refresh_buffet_related(frm);
  },

  person_qty: function (frm) {
    refresh_buffet_related(frm);
  },

  is_closed: function (frm) {
    refresh_buffet_related(frm);
  },

  buffet_add: function (frm) {
    refresh_buffet_related(frm);
  },

  buffet_remove: function (frm) {
    refresh_buffet_related(frm);
  }
});


frappe.ui.form.on("Catering Center Buffet Exception", {
  buffet_exception_add: function (frm, cdt, cdn) {
    set_default_exception_values(frm, cdt, cdn);
    update_exception_grid_options(frm);
    update_exception_preview(frm, cdt, cdn);
    toggle_buffet_exception_section(frm);
  },

  buffet_exception_remove: function (frm) {
    update_all_exception_previews(frm);
  },

  service_period: function (frm, cdt, cdn) {
    update_exception_preview(frm, cdt, cdn);
    validate_exception_row_client(frm, cdt, cdn);
  },

  meal_type: function (frm, cdt, cdn) {
    update_exception_preview(frm, cdt, cdn);
    validate_exception_row_client(frm, cdt, cdn);
  },

  apply_to: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (row.exception_type === "Distribution" && row.apply_to !== "Company") {
      frappe.model.set_value(cdt, cdn, "apply_to", "Company");
      return;
    }

    if (row.apply_to === "All Buffets") {
      frappe.model.set_value(cdt, cdn, "buffet", "");
      frappe.model.set_value(cdt, cdn, "buffet_company", "");
    }

    if (row.apply_to === "Buffet") {
      frappe.model.set_value(cdt, cdn, "buffet_company", "");
    }

    update_exception_grid_options(frm);
    update_exception_preview(frm, cdt, cdn);
    validate_exception_row_client(frm, cdt, cdn);
  },

  buffet: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (row.exception_type === "Distribution" && row.apply_to !== "Company") {
      frappe.model.set_value(cdt, cdn, "apply_to", "Company");
    }

    if (row.apply_to === "All Buffets") {
      frappe.model.set_value(cdt, cdn, "buffet", "");
      frappe.model.set_value(cdt, cdn, "buffet_company", "");
      return;
    }

    frappe.model.set_value(cdt, cdn, "buffet_company", "");

    update_exception_grid_options(frm);
    update_exception_preview(frm, cdt, cdn);
    validate_exception_row_client(frm, cdt, cdn);
  },

  buffet_company: function (frm, cdt, cdn) {
    update_exception_preview(frm, cdt, cdn);
    validate_exception_row_client(frm, cdt, cdn);
  },

  exception_type: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    clear_exception_values_by_type(cdt, cdn);

    if (row.exception_type === "Distribution") {
      frappe.model.set_value(cdt, cdn, "apply_to", "Company");

      frappe.show_alert({
        message: __("Distribution will split the final quantity by location. The total may be less than the base quantity."),
        indicator: "blue"
      });
    }

    if (row.exception_type === "Closed") {
      frappe.show_alert({
        message: __("This will close the selected target for this period and meal."),
        indicator: "orange"
      });
    }

    toggle_exception_fields(frm);
    update_exception_grid_options(frm);
    update_exception_preview(frm, cdt, cdn);
    validate_exception_row_client(frm, cdt, cdn);
  },

  location: function (frm, cdt, cdn) {
    update_all_exception_previews(frm);
    validate_exception_row_client(frm, cdt, cdn);
  },

  person_qty: function (frm, cdt, cdn) {
    update_all_exception_previews(frm);
    validate_exception_row_client(frm, cdt, cdn);
  },

  percent: function (frm, cdt, cdn) {
    update_exception_preview(frm, cdt, cdn);
    validate_exception_row_client(frm, cdt, cdn);
  },

  fixed_qty: function (frm, cdt, cdn) {
    update_exception_preview(frm, cdt, cdn);
    validate_exception_row_client(frm, cdt, cdn);
  }
});


function init_catering_center_form(frm) {
  calculate_buffet_totals(frm);
  toggle_buffet_exception_section(frm);

  load_menu_service_periods(frm).then(function () {
    setup_buffet_exception_filters(frm);
    update_exception_grid_options(frm);
    update_all_exception_previews(frm);
  });
}


function refresh_buffet_related(frm) {
  calculate_buffet_totals(frm);
  toggle_buffet_exception_section(frm);
  setup_buffet_exception_filters(frm);
  update_exception_grid_options(frm);
  update_all_exception_previews(frm);
}


function toggle_buffet_exception_section(frm) {
  const has_buffet_rows = (frm.doc.buffet || []).length > 0;

  frm.toggle_display("section_break_suqf", has_buffet_rows);
  frm.toggle_display("buffet_exception", has_buffet_rows);

  if (!has_buffet_rows && (frm.doc.buffet_exception || []).length > 0) {
    frm.clear_table("buffet_exception");
    frm.refresh_field("buffet_exception");
    frm.dirty();
  }
}


function set_default_exception_values(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (!row.apply_to) {
    frappe.model.set_value(cdt, cdn, "apply_to", "Company");
  }

  if (!row.exception_type) {
    frappe.model.set_value(cdt, cdn, "exception_type", "Closed");
  }
}


function setup_buffet_exception_filters(frm) {
  if (!frm.fields_dict.buffet_exception) return;

  frm.set_query("service_period", "buffet_exception", function () {
    const periods = frm.__menu_service_periods || [];

    if (!periods.length) {
      return {};
    }

    return {
      filters: {
        name: ["in", periods]
      }
    };
  });

  frm.set_query("buffet_company", "buffet_exception", function (doc, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return {};

    if (row.apply_to !== "Company") return {};

    if (!row.buffet) {
      frappe.show_alert({
        message: __("Please select Buffet first."),
        indicator: "orange"
      });

      return {};
    }

    const companies = get_open_companies_for_buffet(frm, row.buffet);

    if (!companies.length) {
      frappe.show_alert({
        message: __("No open companies found for the selected Buffet."),
        indicator: "orange"
      });

      return {};
    }

    return {
      filters: {
        name: ["in", companies]
      }
    };
  });
}


function update_exception_grid_options(frm) {
  if (!frm.fields_dict.buffet_exception) return;

  const grid = frm.fields_dict.buffet_exception.grid;

  grid.update_docfield_property(
    "buffet",
    "options",
    [""] .concat(get_open_buffets(frm)).join("\n")
  );

  grid.update_docfield_property(
    "meal_type",
    "options",
    ["", "Breakfast", "Lunch", "Dinner"].join("\n")
  );

  grid.update_docfield_property(
    "apply_to",
    "options",
    ["", "All Buffets", "Buffet", "Company"].join("\n")
  );

  grid.update_docfield_property(
    "exception_type",
    "options",
    ["", "Distribution", "Percent", "Fixed Qty", "Closed"].join("\n")
  );

  grid.update_docfield_property(
    "location",
    "options",
    ["", "Mina", "Arafat"].join("\n")
  );

  toggle_exception_fields(frm);
  refresh_invalid_exception_rows(frm);
  frm.refresh_field("buffet_exception");
}


function toggle_exception_fields(frm) {
  if (!frm.fields_dict.buffet_exception) return;

  const grid = frm.fields_dict.buffet_exception.grid;

  grid.update_docfield_property(
    "buffet",
    "depends_on",
    "eval:doc.apply_to=='Buffet' || doc.apply_to=='Company' || doc.exception_type=='Distribution'"
  );

  grid.update_docfield_property(
    "buffet_company",
    "depends_on",
    "eval:doc.apply_to=='Company' || doc.exception_type=='Distribution'"
  );

  grid.update_docfield_property(
    "location",
    "depends_on",
    "eval:doc.exception_type=='Distribution'"
  );

  grid.update_docfield_property(
    "person_qty",
    "depends_on",
    "eval:doc.exception_type=='Distribution'"
  );

  grid.update_docfield_property(
    "percent",
    "depends_on",
    "eval:doc.exception_type=='Percent'"
  );

  grid.update_docfield_property(
    "fixed_qty",
    "depends_on",
    "eval:doc.exception_type=='Fixed Qty'"
  );
}


function refresh_invalid_exception_rows(frm) {
  let changed = false;

  const open_buffets = get_open_buffets(frm);
  const periods = frm.__menu_service_periods || [];

  (frm.doc.buffet_exception || []).forEach(function (row) {
    if (row.exception_type === "Distribution") {
      if (row.apply_to !== "Company") {
        row.apply_to = "Company";
        changed = true;
      }

      if (Number(row.percent || 0) !== 0) {
        row.percent = 0;
        changed = true;
      }

      if (Number(row.fixed_qty || 0) !== 0) {
        row.fixed_qty = 0;
        changed = true;
      }
    }

    if (row.exception_type !== "Distribution") {
      if (row.location) {
        row.location = "";
        changed = true;
      }

      if (Number(row.person_qty || 0) !== 0) {
        row.person_qty = 0;
        changed = true;
      }
    }

    if (row.apply_to === "All Buffets") {
      if (row.buffet) {
        row.buffet = "";
        changed = true;
      }

      if (row.buffet_company) {
        row.buffet_company = "";
        changed = true;
      }
    }

    if (row.apply_to === "Buffet" && row.buffet_company) {
      row.buffet_company = "";
      changed = true;
    }

    if (row.apply_to !== "All Buffets") {
      if (row.buffet && !open_buffets.includes(row.buffet)) {
        row.buffet = "";
        row.buffet_company = "";
        changed = true;
      }
    }

    if (row.apply_to === "Company" && row.buffet && row.buffet_company) {
      const companies = get_open_companies_for_buffet(frm, row.buffet);

      if (!companies.includes(row.buffet_company)) {
        row.buffet_company = "";
        changed = true;
      }
    }

    if (periods.length && row.service_period && !periods.includes(row.service_period)) {
      row.service_period = "";
      changed = true;
    }

    if (row.exception_type === "Closed") {
      if (Number(row.percent || 0) !== 0) {
        row.percent = 0;
        changed = true;
      }

      if (Number(row.fixed_qty || 0) !== 0) {
        row.fixed_qty = 0;
        changed = true;
      }
    }

    if (row.exception_type === "Percent") {
      if (Number(row.fixed_qty || 0) !== 0) {
        row.fixed_qty = 0;
        changed = true;
      }
    }

    if (row.exception_type === "Fixed Qty") {
      if (Number(row.percent || 0) !== 0) {
        row.percent = 0;
        changed = true;
      }
    }
  });

  if (changed) {
    frm.refresh_field("buffet_exception");
    frm.dirty();
  }
}


function update_all_exception_previews(frm) {
  (frm.doc.buffet_exception || []).forEach(function (row) {
    update_exception_preview(frm, row.doctype, row.name);
  });

  frm.refresh_field("buffet_exception");
}


function update_exception_preview(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (row.exception_type === "Distribution") {
    update_distribution_preview(frm, cdt, cdn);
    return;
  }

  const base_qty = get_exception_base_qty(frm, row);
  let effective_qty = base_qty;
  let reduction_qty = 0;
  let summary = "";

  if (!row.service_period || !row.meal_type || !row.apply_to || !row.exception_type) {
    set_child_value(cdt, cdn, "base_qty", Math.round(base_qty || 0));
    set_child_value(cdt, cdn, "reduction_qty", 0);
    set_child_value(cdt, cdn, "effective_qty", Math.round(base_qty || 0));
    set_child_value(cdt, cdn, "impact_summary", "");
    return;
  }

  if (row.apply_to !== "All Buffets" && !row.buffet) {
    set_child_value(cdt, cdn, "base_qty", 0);
    set_child_value(cdt, cdn, "reduction_qty", 0);
    set_child_value(cdt, cdn, "effective_qty", 0);
    set_child_value(cdt, cdn, "impact_summary", "");
    return;
  }

  if (row.apply_to === "Company" && !row.buffet_company) {
    set_child_value(cdt, cdn, "base_qty", 0);
    set_child_value(cdt, cdn, "reduction_qty", 0);
    set_child_value(cdt, cdn, "effective_qty", 0);
    set_child_value(cdt, cdn, "impact_summary", "");
    return;
  }

  let target = "";

  if (row.apply_to === "All Buffets") {
    target = "All Buffets";
  } else if (row.apply_to === "Buffet") {
    target = row.buffet || "";
  } else if (row.apply_to === "Company") {
    target = `${row.buffet_company || "Company"} in ${row.buffet || ""}`;
  }

  if (row.exception_type === "Closed") {
    effective_qty = 0;
    reduction_qty = base_qty;

    summary = `${row.service_period} ${row.meal_type}: ${target} will be closed. Final Qty: 0.`;
  }

  else if (row.exception_type === "Percent") {
    const percent = Number(row.percent || 0);

    effective_qty = base_qty * (1 - percent / 100);
    reduction_qty = base_qty - effective_qty;

    summary = `${row.service_period} ${row.meal_type}: ${target} will be reduced by ${percent}%. Final Qty: ${Math.round(effective_qty)}.`;
  }

  else if (row.exception_type === "Fixed Qty") {
    const fixed_qty = Number(row.fixed_qty || 0);

    effective_qty = fixed_qty;
    reduction_qty = base_qty - fixed_qty;

    summary = `${row.service_period} ${row.meal_type}: ${target} will use fixed qty ${Math.round(fixed_qty)}.`;
  }

  if (effective_qty < 0) effective_qty = 0;
  if (reduction_qty < 0) reduction_qty = 0;

  set_child_value(cdt, cdn, "base_qty", Math.round(base_qty));
  set_child_value(cdt, cdn, "reduction_qty", Math.round(reduction_qty));
  set_child_value(cdt, cdn, "effective_qty", Math.round(effective_qty));
  set_child_value(cdt, cdn, "impact_summary", summary);
}


function update_distribution_preview(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (!row.service_period || !row.meal_type || !row.buffet || !row.buffet_company) {
    set_child_value(cdt, cdn, "base_qty", 0);
    set_child_value(cdt, cdn, "reduction_qty", 0);
    set_child_value(cdt, cdn, "effective_qty", 0);
    set_child_value(cdt, cdn, "impact_summary", "");
    return;
  }

  const base_qty = get_base_buffet_company_qty(frm, row.buffet, row.buffet_company);
  const total_distribution_qty = get_distribution_total_qty(frm, row);
  const reduction_qty = Math.max(base_qty - total_distribution_qty, 0);
  const breakdown = get_distribution_breakdown(frm, row);

  let summary = "";

  if (!row.location || Number(row.person_qty || 0) <= 0) {
    summary = `${row.service_period} ${row.meal_type}: Distribution is incomplete.`;
  } else {
    summary = `${row.service_period} ${row.meal_type}: ${row.buffet_company} in ${row.buffet} distributed ${Math.round(total_distribution_qty)} of ${Math.round(base_qty)}. ${row.location}: ${Math.round(Number(row.person_qty || 0))}.`;

    if (breakdown) {
      summary += ` Breakdown: ${breakdown}.`;
    }

    summary += ` Difference: ${Math.round(reduction_qty)}.`;
  }

  if (total_distribution_qty > base_qty && base_qty > 0) {
    summary += ` Warning: distributed qty exceeds base qty.`;
  }

  set_child_value(cdt, cdn, "base_qty", Math.round(base_qty));
  set_child_value(cdt, cdn, "reduction_qty", Math.round(reduction_qty));
  set_child_value(cdt, cdn, "effective_qty", Math.round(total_distribution_qty));
  set_child_value(cdt, cdn, "impact_summary", summary);
}


function set_child_value(cdt, cdn, fieldname, value) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (row[fieldname] !== value) {
    frappe.model.set_value(cdt, cdn, fieldname, value);
  }
}


function get_open_buffets(frm) {
  const buffets = [];

  (frm.doc.buffet || []).forEach(function (row) {
    if (
      row.buffet &&
      !row.is_closed &&
      Number(row.person_qty || 0) > 0
    ) {
      if (!buffets.includes(row.buffet)) {
        buffets.push(row.buffet);
      }
    }
  });

  return buffets;
}


function get_open_companies_for_buffet(frm, buffet) {
  const companies = [];

  if (!buffet) return companies;

  (frm.doc.buffet || []).forEach(function (row) {
    if (
      row.buffet === buffet &&
      row.buffet_company &&
      !row.is_closed &&
      Number(row.person_qty || 0) > 0
    ) {
      if (!companies.includes(row.buffet_company)) {
        companies.push(row.buffet_company);
      }
    }
  });

  return companies;
}


function get_base_buffet_qty(frm, buffet) {
  let total = 0;

  (frm.doc.buffet || []).forEach(function (row) {
    if (
      row.buffet === buffet &&
      !row.is_closed &&
      Number(row.person_qty || 0) > 0
    ) {
      total += Number(row.person_qty || 0);
    }
  });

  return total;
}


function get_base_all_buffets_qty(frm) {
  let total = 0;

  (frm.doc.buffet || []).forEach(function (row) {
    if (
      row.buffet &&
      !row.is_closed &&
      Number(row.person_qty || 0) > 0
    ) {
      total += Number(row.person_qty || 0);
    }
  });

  return total;
}


function get_base_buffet_company_qty(frm, buffet, company) {
  let total = 0;

  (frm.doc.buffet || []).forEach(function (row) {
    if (
      row.buffet === buffet &&
      row.buffet_company === company &&
      !row.is_closed &&
      Number(row.person_qty || 0) > 0
    ) {
      total += Number(row.person_qty || 0);
    }
  });

  return total;
}


function get_exception_base_qty(frm, row) {
  if (!row) return 0;

  if (row.apply_to === "All Buffets") {
    return get_base_all_buffets_qty(frm);
  }

  if (row.apply_to === "Buffet") {
    return get_base_buffet_qty(frm, row.buffet);
  }

  if (row.apply_to === "Company") {
    return get_base_buffet_company_qty(frm, row.buffet, row.buffet_company);
  }

  return 0;
}


function is_same_distribution_group(a, b) {
  return (
    a &&
    b &&
    a.exception_type === "Distribution" &&
    b.exception_type === "Distribution" &&
    a.service_period === b.service_period &&
    a.meal_type === b.meal_type &&
    a.buffet === b.buffet &&
    a.buffet_company === b.buffet_company
  );
}


function get_distribution_total_qty(frm, target_row) {
  let total = 0;

  if (!target_row) return total;

  (frm.doc.buffet_exception || []).forEach(function (row) {
    if (is_same_distribution_group(row, target_row)) {
      total += Number(row.person_qty || 0);
    }
  });

  return total;
}


function get_distribution_breakdown(frm, target_row) {
  const map = {};

  if (!target_row) return "";

  (frm.doc.buffet_exception || []).forEach(function (row) {
    if (!is_same_distribution_group(row, target_row)) return;
    if (!row.location) return;

    map[row.location] = (map[row.location] || 0) + Number(row.person_qty || 0);
  });

  const parts = [];

  ["Mina", "Arafat"].forEach(function (location) {
    if (map[location]) {
      parts.push(`${location}: ${Math.round(map[location])}`);
    }
  });

  Object.keys(map).forEach(function (location) {
    if (!["Mina", "Arafat"].includes(location)) {
      parts.push(`${location}: ${Math.round(map[location])}`);
    }
  });

  return parts.join(", ");
}


function validate_exception_row_client(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (row.exception_type === "Distribution") {
    if (row.apply_to !== "Company") {
      frappe.model.set_value(cdt, cdn, "apply_to", "Company");
      frappe.show_alert({
        message: __("Distribution must apply to Company."),
        indicator: "orange"
      });
      return;
    }

    if (Number(row.percent || 0) !== 0) {
      frappe.model.set_value(cdt, cdn, "percent", 0);
    }

    if (Number(row.fixed_qty || 0) !== 0) {
      frappe.model.set_value(cdt, cdn, "fixed_qty", 0);
    }

    if (Number(row.person_qty || 0) < 0) {
      frappe.model.set_value(cdt, cdn, "person_qty", 0);
      frappe.msgprint(__("Person Qty cannot be negative."));
      return;
    }

    const base_qty = get_base_buffet_company_qty(frm, row.buffet, row.buffet_company);
    const total_distribution_qty = get_distribution_total_qty(frm, row);

    if (base_qty > 0 && total_distribution_qty > base_qty) {
      frappe.show_alert({
        message: __("Distribution total cannot exceed base qty {0}.", [base_qty]),
        indicator: "red"
      });
    }

    return;
  }

  if (row.location) {
    frappe.model.set_value(cdt, cdn, "location", "");
  }

  if (Number(row.person_qty || 0) !== 0) {
    frappe.model.set_value(cdt, cdn, "person_qty", 0);
  }

  if (row.apply_to === "All Buffets") {
    if (row.buffet) {
      frappe.model.set_value(cdt, cdn, "buffet", "");
    }

    if (row.buffet_company) {
      frappe.model.set_value(cdt, cdn, "buffet_company", "");
    }
  }

  if (row.apply_to === "Buffet" && row.buffet_company) {
    frappe.model.set_value(cdt, cdn, "buffet_company", "");
  }

  if (row.apply_to !== "All Buffets" && !row.buffet) return;

  const open_buffets = get_open_buffets(frm);

  if (row.apply_to !== "All Buffets") {
    if (!open_buffets.includes(row.buffet)) {
      frappe.model.set_value(cdt, cdn, "buffet", "");
      frappe.model.set_value(cdt, cdn, "buffet_company", "");

      frappe.msgprint(__("This Buffet is closed or not available in the base Buffet table."));
      return;
    }
  }

  if (row.apply_to === "Company") {
    const companies = get_open_companies_for_buffet(frm, row.buffet);

    if (row.buffet_company && !companies.includes(row.buffet_company)) {
      frappe.model.set_value(cdt, cdn, "buffet_company", "");

      frappe.msgprint(__("This Company is not available for the selected open Buffet."));
      return;
    }
  }

  if (row.exception_type === "Percent") {
    const percent = Number(row.percent || 0);

    if (percent < 0 || percent > 100) {
      frappe.model.set_value(cdt, cdn, "percent", 0);

      frappe.msgprint(__("Percent must be between 0 and 100."));
      return;
    }
  }

  if (row.exception_type === "Fixed Qty") {
    const fixed_qty = Number(row.fixed_qty || 0);
    const base_qty = get_exception_base_qty(frm, row);

    if (fixed_qty < 0) {
      frappe.model.set_value(cdt, cdn, "fixed_qty", 0);

      frappe.msgprint(__("Fixed Qty cannot be negative."));
      return;
    }

    if (base_qty && fixed_qty > base_qty) {
      frappe.model.set_value(cdt, cdn, "fixed_qty", base_qty);

      frappe.msgprint(__("Fixed Qty cannot be greater than base qty {0}.", [base_qty]));
      return;
    }
  }
}


function validate_buffet_exceptions_client(frm) {
  const buffet_rows = frm.doc.buffet || [];
  const exception_rows = frm.doc.buffet_exception || [];

  if (!exception_rows.length) return;

  if (!buffet_rows.length) {
    frappe.throw(__("Please add Buffet rows before adding Buffet Exceptions."));
  }

  const seen_standard = {};
  const seen_distribution = {};
  const distribution_groups = {};
  const standard_rules = [];
  const open_buffets = get_open_buffets(frm);

  exception_rows.forEach(function (row) {
    if (!row.service_period) {
      frappe.throw(__("Exception Row #{0}: Service Period is required.", [row.idx]));
    }

    if (!row.meal_type) {
      frappe.throw(__("Exception Row #{0}: Meal Type is required.", [row.idx]));
    }

    if (!row.apply_to) {
      frappe.throw(__("Exception Row #{0}: Apply To is required.", [row.idx]));
    }

    if (!["All Buffets", "Buffet", "Company"].includes(row.apply_to)) {
      frappe.throw(__("Exception Row #{0}: Invalid Apply To.", [row.idx]));
    }

    if (!row.exception_type) {
      frappe.throw(__("Exception Row #{0}: Exception Type is required.", [row.idx]));
    }

    if (!["Distribution", "Percent", "Fixed Qty", "Closed"].includes(row.exception_type)) {
      frappe.throw(__("Exception Row #{0}: Invalid Exception Type.", [row.idx]));
    }

    if (row.exception_type === "Distribution") {
      validate_distribution_row_client(frm, row, open_buffets, seen_distribution, distribution_groups);
      return;
    }

    validate_standard_exception_row_client(frm, row, open_buffets, seen_standard, standard_rules);
  });

  validate_distribution_conflicts_client(distribution_groups, standard_rules);
  validate_distribution_totals_client(frm, distribution_groups);
}


function validate_distribution_row_client(frm, row, open_buffets, seen_distribution, distribution_groups) {
  if (row.apply_to !== "Company") {
    frappe.throw(__("Exception Row #{0}: Distribution must apply to Company.", [row.idx]));
  }

  if (!row.buffet) {
    frappe.throw(__("Exception Row #{0}: Buffet is required for Distribution.", [row.idx]));
  }

  if (!open_buffets.includes(row.buffet)) {
    frappe.throw(__("Exception Row #{0}: Buffet is closed or not available.", [row.idx]));
  }

  if (!row.buffet_company) {
    frappe.throw(__("Exception Row #{0}: Buffet Company is required for Distribution.", [row.idx]));
  }

  const companies = get_open_companies_for_buffet(frm, row.buffet);

  if (!companies.includes(row.buffet_company)) {
    frappe.throw(__("Exception Row #{0}: Buffet Company is not available for this Buffet.", [row.idx]));
  }

  if (!row.location) {
    frappe.throw(__("Exception Row #{0}: Location is required for Distribution.", [row.idx]));
  }

  if (!["Mina", "Arafat"].includes(row.location)) {
    frappe.throw(__("Exception Row #{0}: Invalid Location.", [row.idx]));
  }

  const person_qty = Number(row.person_qty || 0);

  if (person_qty <= 0) {
    frappe.throw(__("Exception Row #{0}: Person Qty must be greater than zero for Distribution.", [row.idx]));
  }

  const duplicate_key = [
    row.service_period || "",
    row.meal_type || "",
    row.buffet || "",
    row.buffet_company || "",
    row.location || ""
  ].join("||");

  if (seen_distribution[duplicate_key]) {
    frappe.throw(__("Exception Row #{0}: Duplicate Distribution row for the same Location is not allowed.", [row.idx]));
  }

  seen_distribution[duplicate_key] = true;

  const group_key = [
    row.service_period || "",
    row.meal_type || "",
    row.buffet || "",
    row.buffet_company || ""
  ].join("||");

  if (!distribution_groups[group_key]) {
    distribution_groups[group_key] = {
      service_period: row.service_period,
      meal_type: row.meal_type,
      buffet: row.buffet,
      buffet_company: row.buffet_company,
      total: 0,
      rows: []
    };
  }

  distribution_groups[group_key].total += person_qty;
  distribution_groups[group_key].rows.push(row);
}


function validate_standard_exception_row_client(frm, row, open_buffets, seen_standard, standard_rules) {
  if (row.apply_to !== "All Buffets") {
    if (!row.buffet) {
      frappe.throw(__("Exception Row #{0}: Buffet is required.", [row.idx]));
    }

    if (!open_buffets.includes(row.buffet)) {
      frappe.throw(__("Exception Row #{0}: Buffet is closed or not available.", [row.idx]));
    }
  }

  if (row.apply_to === "Company") {
    if (!row.buffet_company) {
      frappe.throw(__("Exception Row #{0}: Buffet Company is required.", [row.idx]));
    }

    const companies = get_open_companies_for_buffet(frm, row.buffet);

    if (!companies.includes(row.buffet_company)) {
      frappe.throw(__("Exception Row #{0}: Buffet Company is not available for this Buffet.", [row.idx]));
    }
  }

  const duplicate_key = [
    row.service_period || "",
    row.meal_type || "",
    row.apply_to || "",
    row.apply_to === "All Buffets" ? "" : row.buffet || "",
    row.apply_to === "Company" ? row.buffet_company || "" : ""
  ].join("||");

  if (seen_standard[duplicate_key]) {
    frappe.throw(__("Exception Row #{0}: Duplicate exception is not allowed.", [row.idx]));
  }

  seen_standard[duplicate_key] = true;

  if (row.exception_type === "Percent") {
    const percent = Number(row.percent || 0);

    if (percent <= 0 || percent > 100) {
      frappe.throw(__("Exception Row #{0}: Percent must be greater than 0 and less than or equal to 100.", [row.idx]));
    }
  }

  if (row.exception_type === "Fixed Qty") {
    const fixed_qty = Number(row.fixed_qty || 0);
    const base_qty = get_exception_base_qty(frm, row);

    if (fixed_qty < 0) {
      frappe.throw(__("Exception Row #{0}: Fixed Qty cannot be negative.", [row.idx]));
    }

    if (fixed_qty > base_qty) {
      frappe.throw(__("Exception Row #{0}: Fixed Qty cannot be greater than base qty {1}.", [row.idx, base_qty]));
    }
  }

  standard_rules.push({
    service_period: row.service_period,
    meal_type: row.meal_type,
    apply_to: row.apply_to,
    buffet: row.buffet || "",
    buffet_company: row.buffet_company || "",
    row_idx: row.idx
  });
}


function validate_distribution_conflicts_client(distribution_groups, standard_rules) {
  Object.keys(distribution_groups).forEach(function (group_key) {
    const group = distribution_groups[group_key];

    standard_rules.forEach(function (rule) {
      if (rule.service_period !== group.service_period) return;
      if (rule.meal_type !== group.meal_type) return;

      if (rule.apply_to === "All Buffets") {
        frappe.throw(
          __("Distribution for {0} / {1} conflicts with an All Buffets exception.", [
            group.service_period,
            group.meal_type
          ])
        );
      }

      if (rule.apply_to === "Buffet" && rule.buffet === group.buffet) {
        frappe.throw(
          __("Distribution for {0} / {1} / {2} conflicts with a Buffet exception.", [
            group.service_period,
            group.meal_type,
            group.buffet
          ])
        );
      }

      if (
        rule.apply_to === "Company" &&
        rule.buffet === group.buffet &&
        rule.buffet_company === group.buffet_company
      ) {
        frappe.throw(
          __("Distribution for {0} / {1} / {2} / {3} conflicts with another exception.", [
            group.service_period,
            group.meal_type,
            group.buffet,
            group.buffet_company
          ])
        );
      }
    });
  });
}


function validate_distribution_totals_client(frm, distribution_groups) {
  Object.keys(distribution_groups).forEach(function (group_key) {
    const group = distribution_groups[group_key];
    const base_qty = get_base_buffet_company_qty(frm, group.buffet, group.buffet_company);

    if (group.total > base_qty) {
      frappe.throw(
        __("Distribution for {0} / {1} / {2} / {3} cannot exceed base qty {4}. Current distributed qty is {5}.", [
          group.service_period,
          group.meal_type,
          group.buffet,
          group.buffet_company,
          base_qty,
          group.total
        ])
      );
    }
  });
}


function clear_exception_values_by_type(cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (row.exception_type === "Distribution") {
    frappe.model.set_value(cdt, cdn, "apply_to", "Company");
    frappe.model.set_value(cdt, cdn, "percent", 0);
    frappe.model.set_value(cdt, cdn, "fixed_qty", 0);
  }

  if (row.exception_type === "Closed") {
    frappe.model.set_value(cdt, cdn, "percent", 0);
    frappe.model.set_value(cdt, cdn, "fixed_qty", 0);
    frappe.model.set_value(cdt, cdn, "location", "");
    frappe.model.set_value(cdt, cdn, "person_qty", 0);
  }

  if (row.exception_type === "Percent") {
    frappe.model.set_value(cdt, cdn, "fixed_qty", 0);
    frappe.model.set_value(cdt, cdn, "location", "");
    frappe.model.set_value(cdt, cdn, "person_qty", 0);
  }

  if (row.exception_type === "Fixed Qty") {
    frappe.model.set_value(cdt, cdn, "percent", 0);
    frappe.model.set_value(cdt, cdn, "location", "");
    frappe.model.set_value(cdt, cdn, "person_qty", 0);
  }
}


function calculate_buffet_totals(frm) {
  let total = 0;

  (frm.doc.buffet || []).forEach(function (row) {
    if (!row.is_closed) {
      total += Number(row.person_qty || 0);
    }
  });

  frm.set_value("total_buffet_person_qty", total);

  const center_qty = Number(frm.doc.person_qty || 0);
  frm.set_value("person_qty_difference", center_qty - total);
}


function load_menu_service_periods(frm) {
  if (!frm.doc.catering_menu) {
    frm.__menu_service_periods = [];
    return Promise.resolve([]);
  }

  return frappe.db.get_doc("Catering Menu", frm.doc.catering_menu).then(function (menu_doc) {
    const periods = [];

    (menu_doc.items || []).forEach(function (row) {
      if (row.service_period && !periods.includes(row.service_period)) {
        periods.push(row.service_period);
      }
    });

    frm.__menu_service_periods = periods;

    return periods;
  }).catch(function () {
    frm.__menu_service_periods = [];
    return [];
  });
}