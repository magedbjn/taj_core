// license.js
frappe.ui.form.on('License', {
    license_english: function(frm) {
        if (!frm.doc.license_english) return;
        
        frappe.db.get_value('License Type', frm.doc.license_english, ['no_expiry', 'type_arabic']).then((r) => {
            if (!r.message) return;
            
            const data = r.message;
            
            // Update Arabic name if available and different
            if (data.type_arabic && frm.doc.license_arabic !== data.type_arabic) {
                frm.set_value('license_arabic', data.type_arabic);
            }
            
            // Handle expiry date fields based on no_expiry
            const noExpiry = !!data.no_expiry;
            frm.toggle_reqd('expiry_date', !noExpiry);
            frm.set_df_property('expiry_date', 'read_only', noExpiry);
            frm.toggle_display('expiry_date', !noExpiry);
            
            if (noExpiry) {
                frm.set_value('expiry_date', null);
                frm.set_value('status', 'Active');
            } else {
                // Trigger status update when expiry date changes
                frm.trigger('update_status');
            }
        });
    },
    
    expiry_date: function(frm) {
        if (frm.doc.expiry_date) {
            frm.trigger('update_status');
        }
    },
    
    update_status: function(frm) {
        // معاينة سريعة فقط — بدون حفظ
        if (!(frm.doc.license_english && frm.doc.expiry_date)) return;

        frappe.db.get_value('License Type', frm.doc.license_english, ['renew']).then(r => {
            const renew = (r.message && parseInt(r.message.renew, 10)) || 0;
            const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
            const expiry = frappe.datetime.str_to_obj(frm.doc.expiry_date);
            const diff = frappe.datetime.get_day_diff(expiry, today);

            let status = 'Active';
            if (diff < 0) status = 'Expired';
            else if (diff >= 0 && diff <= renew) status = 'Renew';

            // اعرضها فقط على الفورم، لا تحفظ
            frm.set_value('status', status);
            frm.refresh_field('status');
        });
    }
});