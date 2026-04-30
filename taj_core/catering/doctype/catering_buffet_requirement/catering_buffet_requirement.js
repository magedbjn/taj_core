frappe.ui.form.on("Catering Buffet Requirement", {
  onload: function (frm) {
    set_default_naming_series(frm);
  },

  refresh: function (frm) {
    frm.add_custom_button(__("Get Buffet Requirements"), function () {
      get_buffet_requirements(frm);
    });
  }
});


function set_default_naming_series(frm) {
  if (!frm.is_new()) return;

  if (!frm.doc.naming_series) {
    frm.set_value("naming_series", "CTG-BR-.YY.-.##");
  }
}


function get_buffet_requirements(frm) {
  frappe.call({
    method:
      "taj_core.catering.doctype.catering_buffet_requirement.catering_buffet_requirement.get_buffet_requirements",
    freeze: true,
    freeze_message: __("Calculating buffet requirements..."),
    callback: function (r) {
      if (!r.message) {
        return;
      }

      frm.clear_table("items");

      (r.message.items || []).forEach(function (source_row) {
        let child = frm.add_child("items");

        child.catering_center = source_row.catering_center;
        child.center_name = source_row.center_name;
        child.catering_menu = source_row.catering_menu;

        child.buffet = source_row.buffet;
        child.buffet_company = source_row.buffet_company;
        child.person_qty = source_row.person_qty;
        child.menu_person_qty = source_row.menu_person_qty;
        child.person_ratio = source_row.person_ratio;

        child.service_period = source_row.service_period || source_row.service_period;
        child.service_period = source_row.service_period;
        child.meal_type = source_row.meal_type;
        child.section = source_row.section;
        child.row_type = source_row.row_type;

        child.source_row_id = source_row.source_row_id;
        child.parent_row_id = source_row.parent_row_id;
        child.parent_menu_item = source_row.parent_menu_item;
        child.parent_menu_item_arabic = source_row.parent_menu_item_arabic;

        child.item_code = source_row.item_code;
        child.item_name = source_row.item_name;
        child.item_name_arabic = source_row.item_name_arabic;
        child.base_item_qty = source_row.base_item_qty;
        child.required_item_qty = source_row.required_item_qty;
        child.uom = source_row.uom;

        child.close = source_row.close || source_row.is_closed || 0;
        child.is_closed = source_row.is_closed || source_row.close || 0;

        child.workstation = source_row.workstation;
        child.capacity_person_qty = source_row.capacity_person_qty;
        child.cooking_runs = source_row.cooking_runs;
        child.capacity_qty = source_row.capacity_qty;
        child.capacity_uom = source_row.capacity_uom;
        child.required_capacity_qty = source_row.required_capacity_qty;
        child.extra_person_qty = source_row.extra_person_qty;
      });

      frm.set_value("total_person_qty", r.message.total_person_qty || 0);

      frm.refresh_field("items");

      frappe.msgprint(__("Buffet requirements calculated successfully."));
    }
  });
}