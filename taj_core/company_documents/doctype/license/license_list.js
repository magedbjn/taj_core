// List View Settings
frappe.listview_settings['License'] = {
    hide_name_column: true,
    add_fields: ["attachment", "status"],
    
    get_indicator: function(doc) {
        if (doc.status === 'Expired') return [__('Expired'), 'red', 'status,=,Expired'];
        if (doc.status === 'Renew') return [__('Renew'), 'orange', 'status,=,Renew'];
        return [__('Active'), 'green', 'status,=,Active'];
    },
    
    button: {
        show: function(doc) {
            const val = (doc.attachment || "").toString().trim();
            return !!val;
        },
        
        get_label: function() {
            return __("Open");
        },
        
        get_description: function() {
            return __("Open Attachment in a new tab");
        },
        
        action: function(doc) {
            let file_url = (doc.attachment || "").toString().trim();
            if (!file_url) {
                frappe.msgprint({
                    title: __('No Attachment'),
                    indicator: 'red',
                    message: __('No attachment found for this license')
                });
                return;
            }
            
            if (file_url.startsWith("/files") || file_url.startsWith("/private/files")) {
                file_url = frappe.utils.get_url(file_url);
            }
            
            window.open(file_url, "_blank")?.focus();
        }
    }
};