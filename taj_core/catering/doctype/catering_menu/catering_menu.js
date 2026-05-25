frappe.ui.form.on("Catering Menu", {
  refresh: function (frm) {
    frm.add_custom_button(__("Generate Items"), function () {
      frm.call({
        method: "generate_items_button",
        doc: frm.doc,
        freeze: true,
        freeze_message: __("Generating menu items..."),
        callback: function () {
          frm.reload_doc();
          frappe.show_alert({
            message: __("Menu items generated successfully."),
            indicator: "green"
          });
        }
      });
    });
  },
  
});


frappe.ui.form.on("Catering Menu Dish Line", {
  dish: function (frm, cdt, cdn) {
    validate_dish_or_package(frm, cdt, cdn);
    mark_generated_items_not_updated(frm);
  },

  meal_package: function (frm, cdt, cdn) {
    validate_dish_or_package(frm, cdt, cdn);
    mark_generated_items_not_updated(frm);
  },

  service_period: function (frm) {
    mark_generated_items_not_updated(frm);
  },

  meal_type: function (frm) {
    mark_generated_items_not_updated(frm);
  },

  qty_per_person: function (frm) {
    mark_generated_items_not_updated(frm);
  },

  uom: function (frm) {
    mark_generated_items_not_updated(frm);
  },

  show_in_menu_print: function (frm) {
    mark_generated_items_not_updated(frm);
  },

  include_in_purchase: function (frm) {
    mark_generated_items_not_updated(frm);
  },

  include_in_production: function (frm) {
    mark_generated_items_not_updated(frm);
  }
});


function validate_dish_or_package(frm, cdt, cdn) {
  const row = locals[cdt][cdn];

  if (!row) return;

  if (row.dish && row.meal_package) {
    frappe.model.set_value(cdt, cdn, "meal_package", "");
    frappe.msgprint(__("Select either Dish or Meal Package, not both."));
  }
}


function mark_generated_items_not_updated(frm) {
  if (frm.doc.generated_items_updated) {
    frm.set_value("generated_items_updated", 0);
  }
}