// maintenance_contract.js
frappe.ui.form.on('Maintenance Contract', {
  refresh(frm) {
    if (frm.doc.contract_status === 'Completed' && !frm.is_new()) {
      frm.set_read_only();
      // خله يقدر يطبع/يصدر فقط
      frm.disable_save();
    }
  }
});
