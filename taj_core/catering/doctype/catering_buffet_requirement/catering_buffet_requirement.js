frappe.ui.form.on("Catering Buffet Requirement", {
  onload: function (frm) {
    calculate_total_person_qty(frm);
  },

  refresh: function (frm) {
    frm.add_custom_button(__("Get Buffet Plan"), function () {
      do_get_buffet_plan(frm);
    });

    frm.add_custom_button(__("Get Filtered Requirements"), function () {
      do_get_filtered_requirements(frm);
    });

    frm.add_custom_button(__("Get All Requirements"), function () {
      clear_requirement_filters(frm);
      do_get_filtered_requirements(frm);
    });

    calculate_total_person_qty(frm);
  },

  before_save: function (frm) {
    calculate_total_person_qty(frm);
  },

  // إذا عندك Button Field اسمه get_buffet_plan
  get_buffet_plan: function (frm) {
    do_get_buffet_plan(frm);
  },

  // إذا عندك Button Field اسمه get_filtered_requirements
  get_filtered_requirements: function (frm) {
    do_get_filtered_requirements(frm);
  },

  // إذا عندك Button Field اسمه get_buffet_requirements
  get_buffet_requirements: function (frm) {
    do_get_filtered_requirements(frm);
  }
});


frappe.ui.form.on("Catering Buffet Requirement Buffet", {
  person_qty: function (frm, cdt, cdn) {
    calculate_total_person_qty(frm);
  },

  is_closed: function (frm, cdt, cdn) {
    calculate_total_person_qty(frm);
  }
});


function calculate_total_person_qty(frm) {
  let total_person_qty = 0;

  (frm.doc.buffets || []).forEach(function (row) {
    if (!row.is_closed) {
      total_person_qty += Number(row.person_qty || 0);
    }
  });

  frm.set_value("total_person_qty", total_person_qty);
}


function do_get_buffet_plan(frm) {
  frappe.call({
    method:
      "taj_core.catering.doctype.catering_buffet_requirement.catering_buffet_requirement.get_buffet_plan",
    freeze: true,
    freeze_message: __("Getting buffet plan..."),
    callback: function (r) {
      if (!r.message) {
        frappe.msgprint(__("No response from server."));
        return;
      }

      if (!r.message.length) {
        frappe.msgprint(__("No buffet plan found. Please check Catering Centers and Menus."));
        return;
      }

      const existing_map = get_existing_buffet_map(frm);

      frm.clear_table("buffets");

      (r.message || []).forEach(function (source_row) {
        const key = get_buffet_key(source_row);
        const existing = existing_map[key] || {};

        const child = frm.add_child("buffets");

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
            : source_row.person_qty || 0;

        child.is_closed =
          existing.is_closed !== undefined && existing.is_closed !== null
            ? existing.is_closed
            : source_row.is_closed || 0;
      });

      frm.refresh_field("buffets");
      calculate_total_person_qty(frm);

      frappe.msgprint(
        __("Buffet plan updated. Rows generated: {0}", [r.message.length])
      );
    },
    error: function () {
      frappe.msgprint(__("Error while getting buffet plan. Please check server logs."));
    }
  });
}


function do_get_filtered_requirements(frm) {
  if (!frm.doc.buffets || !frm.doc.buffets.length) {
    frappe.msgprint(__("Please click Get Buffet Plan first. Buffets table is empty."));
    return;
  }

  const filtered_buffets = get_filtered_buffets(frm);

  if (!filtered_buffets.length) {
    frappe.msgprint({
      title: __("No Matching Buffets"),
      message: __(
        "No rows matched the selected filters.<br><br>Service Period: {0}<br>Meal Type: {1}<br>Buffet: {2}",
        [
          frm.doc.filter_service_period || "All",
          frm.doc.filter_meal_type || "All",
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
    freeze_message: __("Calculating filtered requirements..."),
    callback: function (r) {
      if (!r.message) {
        frappe.msgprint(__("No response from server."));
        return;
      }

      const returned_items = r.message.items || [];

      frm.clear_table("items");

      if (!returned_items.length) {
        frm.set_value("total_person_qty", r.message.total_person_qty || 0);
        frm.refresh_field("items");

        frappe.msgprint({
          title: __("No Items Generated"),
          message: __(
            "Matched Buffet Rows: {0}<br>Total Person Qty: {1}<br><br>No items were generated. Check Catering Menu rows for the selected Service Period and Meal Type.",
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

      frm.set_value("total_person_qty", r.message.total_person_qty || 0);
      frm.refresh_field("items");

      frappe.msgprint({
        title: __("Filtered Requirements Generated"),
        message: __(
          "Matched Buffet Rows: {0}<br>Generated Item Rows: {1}<br>Total Person Qty: {2}",
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
  const filter_buffet = frm.doc.filter_buffet || "";

  return (frm.doc.buffets || [])
    .filter(function (row) {
      if (filter_service_period && row.service_period !== filter_service_period) {
        return false;
      }

      if (filter_meal_type && row.meal_type !== filter_meal_type) {
        return false;
      }

      if (filter_buffet && row.buffet !== filter_buffet) {
        return false;
      }

      return true;
    })
    .map(function (row) {
      return {
        service_period: row.service_period || "",
        meal_type: row.meal_type || "",
        catering_center: row.catering_center || "",
        center_name: row.center_name || "",
        catering_menu: row.catering_menu || "",
        buffet: row.buffet || "",
        buffet_company: row.buffet_company || "",
        person_qty: row.person_qty || 0,
        is_closed: row.is_closed || 0
      };
    });
}


function clear_requirement_filters(frm) {
  frm.set_value("filter_service_period", "");
  frm.set_value("filter_meal_type", "");
  frm.set_value("filter_buffet", "");
}


function get_existing_buffet_map(frm) {
  const existing_map = {};

  (frm.doc.buffets || []).forEach(function (row) {
    const key = get_buffet_key(row);

    if (key) {
      existing_map[key] = {
        person_qty: row.person_qty,
        is_closed: row.is_closed
      };
    }
  });

  return existing_map;
}


function get_buffet_key(row) {
  return [
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