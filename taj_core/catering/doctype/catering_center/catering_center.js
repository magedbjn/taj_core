frappe.ui.form.on("Catering Center", {
  onload: function (frm) {
    set_default_naming_series(frm);
    calculate_buffet_totals(frm);
  },

  refresh: function (frm) {
    calculate_buffet_totals(frm);

    frm.add_custom_button(__("Distribute Person Qty"), function () {
      distribute_person_qty(frm);
    });
  },

  person_qty: function (frm) {
    calculate_buffet_totals(frm);
  },

  before_save: function (frm) {
    calculate_buffet_totals(frm);
  }
});


frappe.ui.form.on("Catering Center Buffet", {
  buffet_add: function (frm) {
    calculate_buffet_totals(frm);
  },

  buffet_remove: function (frm) {
    calculate_buffet_totals(frm);
  },

  person_qty: function (frm) {
    calculate_buffet_totals(frm);
  },

  is_closed: function (frm) {
    calculate_buffet_totals(frm);
  }
});


function set_default_naming_series(frm) {
  if (!frm.is_new()) return;

  if (!frm.doc.naming_series) {
    frm.set_value("naming_series", "CTG-CC-.YY.-.##");
  }
}


function calculate_buffet_totals(frm) {
  let total_buffet_person_qty = 0;

  (frm.doc.buffet || []).forEach(function (row) {
    /*
      إذا تريد تجاهل البوفيهات المغلقة من المجموع، فعّل هذا الشرط:
      if (row.is_closed) return;
    */

    total_buffet_person_qty += Number(row.person_qty || 0);
  });

  const center_person_qty = Number(frm.doc.person_qty || 0);
  const difference = center_person_qty - total_buffet_person_qty;

  frm.set_value("total_buffet_person_qty", total_buffet_person_qty);
  frm.set_value("person_qty_difference", difference);
}


function distribute_person_qty(frm) {
  const total_person_qty = Number(frm.doc.person_qty || 0);
  const rows = frm.doc.buffet || [];

  if (!total_person_qty || total_person_qty <= 0) {
    frappe.msgprint(__("Please enter Person Qty first."));
    return;
  }

  if (!rows.length) {
    frappe.msgprint(__("Please add Buffet rows first."));
    return;
  }

  const active_rows = rows.filter(function (row) {
    return !row.is_closed;
  });

  if (!active_rows.length) {
    frappe.msgprint(__("No active Buffet rows found."));
    return;
  }

  const base_qty = Math.floor(total_person_qty / active_rows.length);
  const remainder = total_person_qty % active_rows.length;

  active_rows.forEach(function (row, index) {
    row.person_qty = base_qty + (index < remainder ? 1 : 0);
  });

  rows.forEach(function (row) {
    if (row.is_closed) {
      row.person_qty = 0;
    }
  });

  frm.refresh_field("buffet");
  calculate_buffet_totals(frm);

  frappe.show_alert({
    message: __("Person Qty distributed successfully."),
    indicator: "green"
  });
}