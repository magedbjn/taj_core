frappe.ui.form.on('Purchase Order', {
  refresh(frm) {
    if (!frm.doc || frm.is_new() || !frm.doc.supplier) return;
    if (!Array.isArray(frm.doc.items) || frm.doc.items.length === 0) return;

    frm.add_custom_button(__('Request Qualification Review'), function() {
      const pending = [];
      (frm.doc.items || []).forEach(row => {
        const s = (row.item_status || '').trim();
        if (!s || (s !== 'Approved' && s !== 'Rejected')) {
          if (row.item_code) pending.push(row.item_code);
        }
      });

      if (pending.length === 0) {
        frappe.msgprint(__('All items appear to have a final status (Approved/Rejected).'));
        return;
      }

      frappe.call({
        method: 'taj_core.qc.doctype.supplier_qualification.supplier_qualification.request_items_approval',
        args: {
          supplier: frm.doc.supplier,
          items: pending,
          reference_doctype: frm.doctype,
          reference_name: frm.doc.name,
          note: __('Requested via Purchase Order {0}', [frm.doc.name])
        },
        callback: function(r) {
          if (!r.exc && r.message) {
            const msg = r.message;
            const added = (msg.added || []).join(', ');
            const skipped = (msg.skipped || []).join(', ');
            let html = '';
            if (added) html += `<div><b>${__('Added for review')}:</b> ${frappe.utils.escape_html(added)}</div>`;
            if (skipped) html += `<div><b>${__('Already pending review')}:</b> ${frappe.utils.escape_html(skipped)}</div>`;
            if (!html) html = __('Nothing to add.');

            frappe.msgprint({
              title: __('Qualification Request Submitted'),
              message: html,
              indicator: 'blue'
            });

            setTimeout(() => frm.refresh(), 600);
          }
        }
      });
    }, __('Taj'));
  }
});
