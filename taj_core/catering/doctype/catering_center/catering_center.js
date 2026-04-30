frappe.ui.form.on("Catering Center", {
  onload: function (frm) {
    set_default_naming_series(frm);
    calculate_qty_difference(frm);
  },

  refresh: function (frm) {
    calculate_qty_difference(frm);
  },

  person_qty: function (frm) {
    calculate_qty_difference(frm);
  },

  before_save: function (frm) {
    calculate_qty_difference(frm);
  }
});


frappe.ui.form.on("Catering Center Buffet", {
  buffet_add: function (frm) {
    calculate_qty_difference(frm);
  },

  buffet_remove: function (frm) {
    calculate_qty_difference(frm);
  },

  person_qty: function (frm) {
    calculate_qty_difference(frm);
  },

  qty: function (frm) {
    calculate_qty_difference(frm);
  },

  is_closed: function (frm) {
    calculate_qty_difference(frm);
  }
});


function set_default_naming_series(frm) {
  if (!frm.is_new()) return;

  if (!frm.doc.naming_series) {
    frm.set_value("naming_series", "CTG-CC-.YY.-.##");
  }
}


function calculate_qty_difference(frm) {
  let total_buffet_person_qty = 0;

  (frm.doc.buffet || []).forEach(function (row) {
    const is_closed = row.is_closed || row.close || 0;

    if (!is_closed) {
      total_buffet_person_qty += Number(row.person_qty || row.qty || 0);
    }
  });

  const center_person_qty = Number(frm.doc.person_qty || 0);
  const difference = center_person_qty - total_buffet_person_qty;

  frm.set_value("qty_difference", difference);
}