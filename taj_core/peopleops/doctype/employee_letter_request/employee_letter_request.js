frappe.ui.form.on('Employee Letter Request', {
  before_print(frm) {
    if (frm.doc.docstatus === 0) {
      frappe.msgprint(__('لا يمكن طباعة المسودة. يرجى اعتماد المستند أولاً.'));
      throw new Error('Prevent printing draft');
    }
  }
});
