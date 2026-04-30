frappe.ui.form.on("Catering Capacity", {
  refresh: function (frm) {
    frm.add_custom_button(__("Get Items From Catering Menus"), function () {
      get_items_from_catering_menus(frm);
    });
  },

  before_save: function (frm) {
    remove_zero_capacity_rows(frm);
    validate_unique_capacity_items(frm);
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

      const table_fieldname = "items";
      const existing_keys = {};

      (frm.doc[table_fieldname] || []).forEach(function (row) {
        const key = get_capacity_item_key(row);
        if (key) {
          existing_keys[key] = true;
        }
      });

      let added_count = 0;
      let skipped_count = 0;

      r.message.forEach(function (source_row) {
        const key = get_capacity_item_key(source_row);

        if (!key) {
          return;
        }

        if (existing_keys[key]) {
          skipped_count++;
          return;
        }

        const child = frm.add_child(table_fieldname);

        child.item = source_row.item || "";
        child.item_name = source_row.item_name || "";
        child.item_name_arabic = source_row.item_name_arabic || "";

        child.workstation = "";
        child.capacity_person_qty = 0;
        child.capacity_qty = 0;
        child.capacity_uom = "Basket";

        existing_keys[key] = true;
        added_count++;
      });

      frm.refresh_field(table_fieldname);

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
  if (row.item) {
    return "ITEM::" + String(row.item).trim();
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


function remove_zero_capacity_rows(frm) {
  if (!frm.doc.items || !frm.doc.items.length) {
    return;
  }

  const original_count = frm.doc.items.length;

  frm.doc.items = frm.doc.items.filter(function (row) {
    return (
      Number(row.capacity_person_qty || 0) > 0 &&
      Number(row.capacity_qty || 0) > 0
    );
  });

  frm.doc.items.forEach(function (row, index) {
    row.idx = index + 1;
  });

  const removed_count = original_count - frm.doc.items.length;

  if (removed_count > 0) {
    frm.refresh_field("items");

    frappe.show_alert({
      message: __("Removed {0} row(s) with empty capacity.", [removed_count]),
      indicator: "orange"
    });
  }
}


function validate_unique_capacity_items(frm) {
  const seen = {};

  (frm.doc.items || []).forEach(function (row) {
    const key = get_capacity_item_key(row);

    if (!key) {
      return;
    }

    if (seen[key]) {
      frappe.throw(
        __("Duplicate item in Catering Capacity at row #{0}: {1}", [
          row.idx,
          row.item_name || row.item_name_arabic || row.item
        ])
      );
    }

    seen[key] = true;
  });
}