frappe.ui.form.on('Preparation Items', {
  refresh(frm) {
    // 1) item_code: اسم الصنف يبدأ بـ RAW-
    frm.set_query('item_code', function() {
      return {
        filters: [
          ['Item', 'item_code', 'like', 'RAW-%'],
          ['Item', 'disabled', '=', 0],
        ]
      };
    });

    frm.set_query('preparation_item', function() {
      return {
        filters: {
          item_group: 'Preparation'
        }
      };
    });

    // 3) bom_no: يساوي preparation_item (BOM.item = preparation_item)
    frm.set_query('bom_no', function() {
      const pre = frm.doc.preparation_item || '';
      return {
        filters: {
          item: pre,
          is_active: 1,   
          docstatus: 1,
          is_default: 1,   
        }
      };
    });
  },

  // تحسين تجربة الاستخدام: تفريغ bom_no عند تغيير preparation_item
  preparation_item(frm) {
    frm.set_value('bom_no', null);
  },

  // تحقّق (اختياري): تأكد أن bom_no المختار يعود لنفس preparation_item
  validate(frm) {
    if (frm.doc.bom_no && frm.doc.preparation_item) {
      frappe.db.get_value('BOM', frm.doc.bom_no, 'item').then(r => {
        const bom_item = r && r.message && r.message.item;
        if (bom_item && bom_item !== frm.doc.preparation_item) {
          frappe.msgprint(__('The selected BOM does not belong to the chosen preparation item.'));
          frappe.validated = false;
        }
      });
    }
  }
});
