frappe.ui.form.on("Catering Capacity", {
  refresh: function (frm) {
    frm.add_custom_button(__("Get Items From Catering Menus"), function () {
      get_items_from_catering_menus(frm);
    });
  },

  before_save: function (frm) {
    remove_empty_capacity_rows(frm);
    validate_unique_capacity_items(frm);
    validate_capacity_rows(frm);
  }
});


function get_items_from_catering_menus(frm) {
  frappe.call({
    method:
      "taj_core.catering.doctype.catering_capacity.catering_capacity.get_items_from_active_catering_menus",
    freeze: true,
    freeze_message: __("Getting new items from active Catering Menus..."),
    callback: function (r) {
      if (!r.message || !r.message.length) {
        frappe.msgprint(__("No items found in active Catering Menus."));
        return;
      }

      const existing_keys = {};

      (frm.doc.items || []).forEach(function (row) {
        const key = get_capacity_item_key(row);

        if (key) {
          existing_keys[key] = true;
        }
      });

      let added_count = 0;
      let skipped_count = 0;

      (r.message || []).forEach(function (source_row) {
        const key = get_capacity_item_key(source_row);

        if (!key) return;

        if (existing_keys[key]) {
          skipped_count++;
          return;
        }

        const child = frm.add_child("items");

        child.item_code = source_row.item_code || "";
        child.item_name = source_row.item_name || "";
        child.item_name_arabic = source_row.item_name_arabic || "";

        child.workstation = "";
        child.workstation_load_qty = 0;
        child.capacity_qty = 0;
        child.capacity_uom = "Basket";

        existing_keys[key] = true;
        added_count++;
      });

      frm.refresh_field("items");

      frappe.msgprint(
        __("Added {0} new item(s). Skipped {1} existing item(s).", [
          added_count,
          skipped_count
        ])
      );
    }
  });
}


function get_capacity_item_key(row) {
  if (row.item_code) {
    return "ITEM::" + String(row.item_code).trim();
  }

  if (row.item_name || row.item_name_arabic) {
    return (
      "NEW::" +
      String(row.item_name || "").trim().toLowerCase() +
      "::" +
      String(row.item_name_arabic || "").trim()
    );
  }

  return "";
}


function remove_empty_capacity_rows(frm) {
  if (!frm.doc.items || !frm.doc.items.length) {
    return;
  }

  const original_count = frm.doc.items.length;

  frm.doc.items = frm.doc.items.filter(function (row) {
    return (
      Number(row.workstation_load_qty || 0) > 0 ||
      Number(row.capacity_qty || 0) > 0 ||
      row.workstation ||
      row.capacity_uom
    );
  });

  frm.doc.items.forEach(function (row, index) {
    row.idx = index + 1;
  });

  const removed_count = original_count - frm.doc.items.length;

  if (removed_count > 0) {
    frm.refresh_field("items");

    frappe.show_alert({
      message: __("Removed {0} empty capacity row(s).", [removed_count]),
      indicator: "orange"
    });
  }
}


function validate_unique_capacity_items(frm) {
  const seen = {};

  (frm.doc.items || []).forEach(function (row) {
    const key = get_capacity_item_key(row);

    if (!key) return;

    if (seen[key]) {
      frappe.throw(
        __("Duplicate item in Catering Capacity at row #{0}: {1}", [
          row.idx,
          row.item_name || row.item_name_arabic || row.item_code
        ])
      );
    }

    seen[key] = true;
  });
}


function validate_capacity_rows(frm) {
  (frm.doc.items || []).forEach(function (row) {
    const has_item = row.item_code || row.item_name || row.item_name_arabic;

    if (!has_item) return;

    if (!row.workstation) {
      frappe.throw(__("Row #{0}: Workstation is required.", [row.idx]));
    }

    if (Number(row.workstation_load_qty || 0) <= 0) {
      frappe.throw(__("Row #{0}: Workstation Load Qty must be greater than zero.", [row.idx]));
    }

    if (Number(row.capacity_qty || 0) <= 0) {
      frappe.throw(__("Row #{0}: Capacity Qty must be greater than zero.", [row.idx]));
    }

    if (!row.capacity_uom) {
      frappe.throw(__("Row #{0}: Capacity UOM is required.", [row.idx]));
    }
  });
}