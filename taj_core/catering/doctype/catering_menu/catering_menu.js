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
  },

  items_add: function (frm, cdt, cdn) {
    setTimeout(function () {
      const row = locals[cdt][cdn];

      if (!row) return;

      if (!row.row_id) {
        frappe.model.set_value(cdt, cdn, "row_id", make_row_id());
      }

      copy_previous_row_values(frm, cdt, cdn);

      if (row.row_type === "Sub Item") {
        set_parent_from_previous_item(frm, cdt, cdn);
      }
    }, 100);
  }
});


frappe.ui.form.on("Catering Menu Item", {
  item_code: function (frm, cdt, cdn) {
    set_item_details_and_uom(frm, cdt, cdn);
  },

  row_type: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    if (!row) return;

    if (!row.row_id) {
      frappe.model.set_value(cdt, cdn, "row_id", make_row_id());
    }

    if (row.row_type === "Sub Item") {
      set_parent_from_previous_item(frm, cdt, cdn);
    } else {
      frappe.model.set_value(cdt, cdn, "parent_row_id", "");
      frappe.model.set_value(cdt, cdn, "parent_row_label", "");
    }
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


function set_item_details_and_uom(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row || !row.item_code) {
    frappe.model.set_value(cdt, cdn, "item_name", "");
    frappe.model.set_value(cdt, cdn, "item_name_arabic", "");
    frappe.model.set_value(cdt, cdn, "uom", "");
    return;
  }

  frappe.db.get_value(
    "Item",
    row.item_code,
    ["item_name", "item_name_arabic", "stock_uom"],
    function (r) {
      if (!r) return;

      frappe.model.set_value(cdt, cdn, "item_name", r.item_name || "");
      frappe.model.set_value(cdt, cdn, "item_name_arabic", r.item_name_arabic || "");

      if (r.stock_uom) {
        frappe.model.set_value(cdt, cdn, "uom", r.stock_uom);
      }
    }
  );
}


function copy_previous_row_values(frm, cdt, cdn) {
  const current_row = locals[cdt][cdn];

  if (!current_row || !frm.doc.items || frm.doc.items.length <= 1) {
    return;
  }

  const previous_row = frm.doc.items.find(function (row) {
    return row.idx === current_row.idx - 1;
  });

  if (!previous_row) return;

  const fields_to_copy = [
    "service_period",
    "meal_type",
    "row_type"
  ];

  fields_to_copy.forEach(function (fieldname) {
    if (previous_row[fieldname]) {
      frappe.model.set_value(cdt, cdn, fieldname, previous_row[fieldname]);
    }
  });

  // إذا السطر السابق Sub Item، السطر الجديد يكون تابع لنفس الأب
  if (previous_row.row_type === "Sub Item") {
    frappe.model.set_value(cdt, cdn, "parent_row_id", previous_row.parent_row_id || "");
    frappe.model.set_value(cdt, cdn, "parent_row_label", previous_row.parent_row_label || "");
  }

  // لا تنسخ بيانات الصنف نفسه
  frappe.model.set_value(cdt, cdn, "item_code", "");
  frappe.model.set_value(cdt, cdn, "item_name", "");
  frappe.model.set_value(cdt, cdn, "item_name_arabic", "");
  frappe.model.set_value(cdt, cdn, "new_item_name", "");
  frappe.model.set_value(cdt, cdn, "new_item_name_arabic", "");
  frappe.model.set_value(cdt, cdn, "qty", "");
  frappe.model.set_value(cdt, cdn, "uom", "");

  frm.refresh_field("items");
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