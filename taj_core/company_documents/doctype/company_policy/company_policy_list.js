frappe.listview_settings['Company Policy'] = {
    hide_name_column: true,
    add_fields: ["attachment"],
    button: {
        show(doc) {
            return !!(doc.attachment && doc.attachment.trim());
        },
        get_label() {
            return __("📄 Open");
        },
        get_description() {
            return __("Open the policy attachment in a new tab");
        },
        action(doc) {
            if (doc.attachment && doc.attachment.trim() !== "") {
                let file_url = doc.attachment;

                // إذا الرابط يبدأ بـ /files فقط، ضيف الدومين
                if (file_url.startsWith("/files")) {
                    file_url = frappe.utils.get_url(file_url);
                }

                window.open(file_url, "_blank").focus();
            } else {
                frappe.msgprint({
                    title: __('No Attachment'),
                    indicator: 'red',
                    message: __('No attachment found for this policy')
                });
            }
        }
    }
};
