frappe.ui.form.on("Catering Center", {
  onload: function (frm) {
    set_default_naming_series(frm);
  },
});


frappe.ui.form.on("Catering Center Buffet", {
  
});


function set_default_naming_series(frm) {
  if (!frm.is_new()) return;

  if (!frm.doc.naming_series) {
    frm.set_value("naming_series", "CTG-CC-.YY.-.##");
  }
}