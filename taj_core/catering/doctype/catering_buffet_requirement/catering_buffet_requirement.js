frappe.ui.form.on("Catering Buffet Requirement", {
  // onload: function (frm) {
  //   calculate_total_person_qty(frm);
  // },

  // refresh: function (frm) {
  //   add_catering_action_buttons(frm);
  //   calculate_total_person_qty(frm);
  // },

  // before_save: function (frm) {
  //   calculate_total_person_qty(frm);
  // },
  
  refresh: function (frm) {
    add_catering_action_buttons(frm);
  },

  get_buffet_plan: function (frm) {
    show_service_plan_dialog(frm);
  },

  get_filtered_requirements: function (frm) {
    do_get_filtered_requirements(frm);
  },

  get_buffet_requirements: function (frm) {
    do_get_filtered_requirements(frm);
  },

  filter_service_period: function (frm) {
    show_filter_summary(frm);
  },

  filter_meal_type: function (frm) {
    show_filter_summary(frm);
  },

  filter_catering_center: function (frm) {
    show_filter_summary(frm);
  },

  filter_buffet: function (frm) {
    show_filter_summary(frm);
  }
});


// frappe.ui.form.on("Catering Buffet Requirement Buffet", {
//   person_qty: function (frm) {
//     calculate_total_person_qty(frm);
//   },

//   is_closed: function (frm) {
//     calculate_total_person_qty(frm);
//   },

//   buffets_add: function (frm) {
//     calculate_total_person_qty(frm);
//   },

//   buffets_remove: function (frm) {
//     calculate_total_person_qty(frm);
//   }
// });


function add_catering_action_buttons(frm) {
  const service_plan_group = __("Service Plan");
  const requirements_group = __("Requirements");

  frm.add_custom_button(__("Get Service Plan"), function () {
    show_service_plan_dialog(frm);
  }, service_plan_group);

  frm.add_custom_button(__("Clear Service Plan"), function () {
    clear_service_plan(frm);
  }, service_plan_group);

  frm.add_custom_button(__("Get Filtered Requirements"), function () {
    do_get_filtered_requirements(frm);
  }, requirements_group);

  frm.add_custom_button(__("Get All Requirements"), function () {
    clear_requirement_filters(frm);
    do_get_filtered_requirements(frm);
  }, requirements_group);

  frm.add_custom_button(__("Clear Items"), function () {
    clear_items(frm);
  }, requirements_group);

  if (frm.page && frm.page.set_inner_btn_group_as_primary) {
    frm.page.set_inner_btn_group_as_primary(service_plan_group);
  }
}


function get_current_year() {
  const today = frappe.datetime.get_today();
  return today ? today.substring(0, 4) : String(new Date().getFullYear());
}


function show_service_plan_dialog(frm) {
  const current_year = get_current_year();

  const dialog = new frappe.ui.Dialog({
    title: __("Get Service Plan"),
    size: "large",
    fields: [
      {
        fieldname: "catering_year",
        fieldtype: "Data",
        label: __("Year"),
        default: current_year,
        read_only: 1
      },
      {
        fieldname: "section_break_centers",
        fieldtype: "Section Break",
        label: __("Catering Centers")
      },
      {
        fieldname: "centers_html",
        fieldtype: "HTML"
      }
    ],
    primary_action_label: __("Get Service Plan"),
    primary_action: function () {
      const selected_centers = get_selected_centers_from_dialog(dialog);

      if (!selected_centers.length) {
        frappe.msgprint(__("Please select at least one Catering Center."));
        return;
      }

      dialog.hide();

      do_get_buffet_plan(frm, {
        catering_year: current_year,
        catering_centers: selected_centers
      });
    }
  });

  dialog.show();

  load_centers_into_dialog(dialog, current_year);
}


function load_centers_into_dialog(dialog, catering_year) {
  const wrapper = dialog.fields_dict.centers_html.$wrapper;

  wrapper.html(
    '<div class="text-muted" style="padding: 12px;">' +
      __("Loading Catering Centers...") +
    '</div>'
  );

  frappe.call({
    method:
      "taj_core.catering.doctype.catering_buffet_requirement.catering_buffet_requirement.get_catering_centers_for_year",
    args: {
      catering_year: catering_year
    },
    freeze: true,
    freeze_message: __("Loading Catering Centers..."),
    callback: function (r) {
      const centers = r.message || [];

      if (!centers.length) {
        wrapper.html(
          '<div class="alert alert-warning">' +
            __("No Catering Centers found for year {0}.", [catering_year]) +
          '</div>'
        );
        return;
      }

      render_centers_selection(wrapper, centers);
    },
    error: function () {
      wrapper.html(
        '<div class="alert alert-danger">' +
          __("Error while loading Catering Centers.") +
        '</div>'
      );
    }
  });
}


function render_centers_selection(wrapper, centers) {
  let html = "";

  html += '<div style="margin-bottom: 10px; display: flex; gap: 8px; align-items: center;">';
  html += '  <input type="text" class="form-control center-search-input" placeholder="' + __("Search Center...") + '" style="max-width: 320px;">';
  html += '  <button type="button" class="btn btn-xs btn-default select-all-centers">' + __("Select All") + '</button>';
  html += '  <button type="button" class="btn btn-xs btn-default clear-all-centers">' + __("Clear") + '</button>';
  html += '</div>';

  html += '<div class="center-list-wrapper" style="max-height: 420px; overflow: auto; border: 1px solid #d1d8dd; border-radius: 6px;">';

  html += '<table class="table table-bordered table-sm" style="margin: 0;">';
  html += '  <thead>';
  html += '    <tr>';
  html += '      <th style="width: 40px; text-align:center;"></th>';
  html += '      <th>' + __("Center") + '</th>';
  html += '      <th style="width: 140px;">' + __("Menu") + '</th>';
  html += '      <th style="width: 110px; text-align:right;">' + __("Person Qty") + '</th>';
  html += '      <th style="width: 110px;">' + __("Posting Date") + '</th>';
  html += '    </tr>';
  html += '  </thead>';
  html += '  <tbody>';

  centers.forEach(function (center) {
    const search_text = [
      center.name || "",
      center.center_name || "",
      center.catering_menu || ""
    ].join(" ").toLowerCase();

    html += '<tr class="center-row" data-search="' + frappe.utils.escape_html(search_text) + '">';
    html += '  <td class="text-center">';
    html += '    <input type="checkbox" class="center-checkbox" value="' + frappe.utils.escape_html(center.name || "") + '">';
    html += '  </td>';
    html += '  <td>';
    html += '    <strong>' + frappe.utils.escape_html(center.center_name || center.name || "") + '</strong>';
    html += '    <div class="text-muted" style="font-size: 11px;">' + frappe.utils.escape_html(center.name || "") + '</div>';
    html += '  </td>';
    html += '  <td>' + frappe.utils.escape_html(center.catering_menu || "") + '</td>';
    html += '  <td style="text-align:right;">' + Number(center.person_qty || 0) + '</td>';
    html += '  <td>' + frappe.utils.escape_html(center.posting_date || "") + '</td>';
    html += '</tr>';
  });

  html += '  </tbody>';
  html += '</table>';
  html += '</div>';

  wrapper.html(html);

  wrapper.find(".center-search-input").on("input", function () {
    const query = String($(this).val() || "").toLowerCase();

    wrapper.find(".center-row").each(function () {
      const row = $(this);
      const search_text = row.attr("data-search") || "";

      if (!query || search_text.indexOf(query) !== -1) {
        row.show();
      } else {
        row.hide();
      }
    });
  });

  wrapper.find(".select-all-centers").on("click", function () {
    wrapper.find(".center-row:visible .center-checkbox").prop("checked", true);
  });

  wrapper.find(".clear-all-centers").on("click", function () {
    wrapper.find(".center-checkbox").prop("checked", false);
  });
}


function get_selected_centers_from_dialog(dialog) {
  const selected = [];

  dialog.fields_dict.centers_html.$wrapper
    .find(".center-checkbox:checked")
    .each(function () {
      const value = $(this).val();

      if (value) {
        selected.push(value);
      }
    });

  return selected;
}


// function calculate_total_person_qty(frm) {
//   /*
//     Total Person Qty يحسب عدد المركز مرة واحدة فقط.
//     لا يجمع Service Period ولا Meal Type ولا Buffet.
//   */

//   const center_map = {};

//   (frm.doc.buffets || []).forEach(function (row) {
//     if (row.is_closed) return;

//     if (row.catering_center) {
//       center_map[row.catering_center] = true;
//     }
//   });

//   const centers = Object.keys(center_map);

//   if (!centers.length) {
//     frm.set_value("total_person_qty", 0);
//     return;
//   }

//   const request_id = Date.now();
//   frm.__total_person_qty_request_id = request_id;

//   let total = 0;
//   let completed = 0;

//   centers.forEach(function (center_name) {
//     frappe.db.get_value("Catering Center", center_name, "person_qty")
//       .then(function (r) {
//         if (frm.__total_person_qty_request_id !== request_id) return;

//         const value = r.message ? Number(r.message.person_qty || 0) : 0;
//         total += value;
//       })
//       .finally(function () {
//         if (frm.__total_person_qty_request_id !== request_id) return;

//         completed++;

//         if (completed === centers.length) {
//           frm.set_value("total_person_qty", total);
//         }
//       });
//   });
// }


function do_get_buffet_plan(frm, opts) {
  opts = opts || {};

  frappe.call({
    method:
      "taj_core.catering.doctype.catering_buffet_requirement.catering_buffet_requirement.get_buffet_plan",
    args: {
      catering_year: opts.catering_year || get_current_year(),
      catering_centers: JSON.stringify(opts.catering_centers || [])
    },
    freeze: true,
    freeze_message: __("Getting service plan..."),
    callback: function (r) {
      if (!r.message) {
        frappe.msgprint(__("No response from server."));
        return;
      }

      const rows = Array.isArray(r.message) ? r.message : (r.message.rows || []);
      const total_person_qty = Array.isArray(r.message)
        ? 0
        : Number(r.message.total_person_qty || 0);

      if (!rows.length) {
        frappe.msgprint(__("No service plan found for selected Catering Centers."));
        return;
      }

      const existing_map = get_existing_service_plan_map(frm);

      frm.clear_table("buffets");

      rows.forEach(function (source_row) {
        const key = get_service_plan_key(source_row);
        const existing = existing_map[key] || {};

        const child = frm.add_child("buffets");

        set_child_value(child, "plan_type", source_row.plan_type || "");

        child.service_period = source_row.service_period || "";
        child.meal_type = source_row.meal_type || "";
        child.catering_center = source_row.catering_center || "";
        child.center_name = source_row.center_name || "";
        child.catering_menu = source_row.catering_menu || "";
        child.buffet = source_row.buffet || "";
        child.buffet_company = source_row.buffet_company || "";

        child.person_qty =
          existing.person_qty !== undefined && existing.person_qty !== null
            ? existing.person_qty
            : Number(source_row.person_qty || 0);

        child.is_closed =
          existing.is_closed !== undefined && existing.is_closed !== null
            ? existing.is_closed
            : Number(source_row.is_closed || 0);
      });

      frm.set_value("total_person_qty", total_person_qty);
      frm.refresh_field("buffets");
      frm.dirty();

      frappe.show_alert({
        message: __("Service Plan updated."),
        indicator: "green"
      });
    },
    error: function () {
      frappe.msgprint(__("Error while getting service plan. Please check server logs."));
    }
  });
}


function do_get_filtered_requirements(frm) {
  if (!frm.doc.buffets || !frm.doc.buffets.length) {
    frappe.msgprint(__("Please click Get Service Plan first. Service Plan table is empty."));
    return;
  }

  const filtered_buffets = get_filtered_buffets(frm);

  if (!filtered_buffets.length) {
    frappe.msgprint({
      title: __("No Matching Service Plan Rows"),
      message: __(
        "No rows matched the selected filters.<br><br>Service Period: {0}<br>Meal Type: {1}<br>Center: {2}<br>Buffet: {3}",
        [
          frm.doc.filter_service_period || "All",
          frm.doc.filter_meal_type || "All",
          frm.doc.filter_catering_center || "All",
          frm.doc.filter_buffet || "All"
        ]
      ),
      indicator: "orange"
    });
    return;
  }

  frappe.call({
    method:
      "taj_core.catering.doctype.catering_buffet_requirement.catering_buffet_requirement.get_buffet_requirements",
    args: {
      buffets: JSON.stringify(filtered_buffets)
    },
    freeze: true,
    freeze_message: __("Calculating requirements..."),
    callback: function (r) {
      if (!r.message) {
        frappe.msgprint(__("No response from server."));
        return;
      }

      const returned_items = r.message.items || [];

      frm.clear_table("items");

      if (!returned_items.length) {
        frm.set_value("total_person_qty", Number(r.message.total_person_qty || 0));
        frm.refresh_field("items");

        frappe.msgprint({
          title: __("No Items Generated"),
          message: __(
            "Matched Service Plan Rows: {0}<br>Total Person Qty: {1}<br><br>No items were generated. Check Catering Menu rows for the selected Service Period and Meal Type.",
            [
              filtered_buffets.length,
              r.message.total_person_qty || 0
            ]
          ),
          indicator: "orange"
        });

        return;
      }

      returned_items.forEach(function (source_row) {
        const child = frm.add_child("items");

        set_child_value(child, "plan_type", source_row.plan_type);

        set_child_value(child, "catering_center", source_row.catering_center);
        set_child_value(child, "center_name", source_row.center_name);
        set_child_value(child, "catering_menu", source_row.catering_menu);

        set_child_value(child, "buffet", source_row.buffet);
        set_child_value(child, "buffet_company", source_row.buffet_company);
        set_child_value(child, "person_qty", source_row.person_qty);
        set_child_value(child, "menu_person_qty", source_row.menu_person_qty);
        set_child_value(child, "person_ratio", source_row.person_ratio);

        set_child_value(child, "service_period", source_row.service_period);
        set_child_value(child, "meal_type", source_row.meal_type);
        set_child_value(child, "section", source_row.section);
        set_child_value(child, "row_type", source_row.row_type);

        set_child_value(child, "source_row_id", source_row.source_row_id);
        set_child_value(child, "parent_row_id", source_row.parent_row_id);
        set_child_value(child, "parent_menu_item", source_row.parent_menu_item);
        set_child_value(child, "parent_menu_item_arabic", source_row.parent_menu_item_arabic);

        set_child_value(child, "item_code", source_row.item_code);
        set_child_value(child, "item_name", source_row.item_name);
        set_child_value(child, "item_name_arabic", source_row.item_name_arabic);
        set_child_value(child, "base_item_qty", source_row.base_item_qty);
        set_child_value(child, "required_item_qty", source_row.required_item_qty);
        set_child_value(child, "uom", source_row.uom);

        set_child_value(child, "is_closed", source_row.is_closed);

        set_child_value(child, "workstation", source_row.workstation);
        set_child_value(child, "workstation_load_qty", source_row.workstation_load_qty);
        set_child_value(child, "cooking_runs", source_row.cooking_runs);
        set_child_value(child, "capacity_qty", source_row.capacity_qty);
        set_child_value(child, "capacity_uom", source_row.capacity_uom);
        set_child_value(child, "required_capacity_qty", source_row.required_capacity_qty);
        set_child_value(child, "extra_person_qty", source_row.extra_person_qty);
      });

      frm.set_value("total_person_qty", Number(r.message.total_person_qty || 0));
      frm.refresh_field("items");

      frappe.msgprint({
        title: __("Requirements Generated"),
        message: __(
          "Matched Service Plan Rows: {0}<br>Generated Item Rows: {1}<br>Total Person Qty: {2}",
          [
            filtered_buffets.length,
            returned_items.length,
            r.message.total_person_qty || 0
          ]
        ),
        indicator: "green"
      });
    },
    error: function () {
      frappe.msgprint(__("Error while calculating requirements. Please check server logs."));
    }
  });
}


function get_filtered_buffets(frm) {
  const filter_service_period = frm.doc.filter_service_period || "";
  const filter_meal_type = frm.doc.filter_meal_type || "";
  const filter_catering_center = frm.doc.filter_catering_center || "";
  const filter_buffet = frm.doc.filter_buffet || "";

  return (frm.doc.buffets || [])
    .filter(function (row) {
      if (filter_service_period && row.service_period !== filter_service_period) {
        return false;
      }

      if (filter_meal_type && row.meal_type !== filter_meal_type) {
        return false;
      }

      if (filter_catering_center && row.catering_center !== filter_catering_center) {
        return false;
      }

      if (filter_buffet && row.buffet !== filter_buffet) {
        return false;
      }

      return true;
    })
    .map(function (row) {
      return {
        plan_type: row.plan_type || "",

        service_period: row.service_period || "",
        meal_type: row.meal_type || "",
        catering_center: row.catering_center || "",
        center_name: row.center_name || "",
        catering_menu: row.catering_menu || "",
        buffet: row.buffet || "",
        buffet_company: row.buffet_company || "",
        person_qty: Number(row.person_qty || 0),
        is_closed: Number(row.is_closed || 0)
      };
    });
}


function clear_requirement_filters(frm) {
  if (frappe.meta.has_field(frm.doctype, "filter_service_period")) {
    frm.set_value("filter_service_period", "");
  }

  if (frappe.meta.has_field(frm.doctype, "filter_meal_type")) {
    frm.set_value("filter_meal_type", "");
  }

  if (frappe.meta.has_field(frm.doctype, "filter_catering_center")) {
    frm.set_value("filter_catering_center", "");
  }

  if (frappe.meta.has_field(frm.doctype, "filter_buffet")) {
    frm.set_value("filter_buffet", "");
  }
}


function clear_items(frm) {
  frappe.confirm(__("Clear all generated Items?"), function () {
    frm.clear_table("items");
    frm.refresh_field("items");

    frm.dirty();

    frappe.show_alert({
      message: __("Items cleared."),
      indicator: "orange"
    });
  });
}


function clear_service_plan(frm) {
  frappe.confirm(__("Clear Service Plan and Items?"), function () {
    frm.clear_table("buffets");
    frm.clear_table("items");
    frm.set_value("total_person_qty", 0);
    frm.refresh_field("buffets");
    frm.refresh_field("items");

    frappe.show_alert({
      message: __("Service Plan and Items cleared."),
      indicator: "orange"
    });
  });
}


function get_existing_service_plan_map(frm) {
  const existing_map = {};

  (frm.doc.buffets || []).forEach(function (row) {
    const key = get_service_plan_key(row);

    if (key) {
      existing_map[key] = {
        person_qty: row.person_qty,
        is_closed: row.is_closed
      };
    }
  });

  return existing_map;
}


function get_service_plan_key(row) {
  return [
    row.plan_type || "",
    row.service_period || "",
    row.meal_type || "",
    row.catering_center || "",
    row.buffet || "",
    row.buffet_company || ""
  ].join("||");
}


function set_child_value(child, fieldname, value) {
  if (frappe.meta.has_field(child.doctype, fieldname)) {
    child[fieldname] = value;
  }
}


function show_filter_summary(frm) {
  const parts = [];

  parts.push(__("Service Period: {0}", [frm.doc.filter_service_period || "All"]));
  parts.push(__("Meal Type: {0}", [frm.doc.filter_meal_type || "All"]));
  parts.push(__("Center: {0}", [frm.doc.filter_catering_center || "All"]));
  parts.push(__("Buffet: {0}", [frm.doc.filter_buffet || "All"]));

  frm.dashboard.clear_headline();
  frm.dashboard.set_headline(parts.join(" | "));
}