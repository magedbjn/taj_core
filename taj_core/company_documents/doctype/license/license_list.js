frappe.listview_settings['License'] = {
  hide_name_column: true,
  add_fields: ["attachment", "status"],

  get_indicator(doc) {
    if (doc.status === 'Expired') return [__('Expired'), 'red', 'status,=,Expired'];
    if (doc.status === 'Renew')   return [__('Renew'), 'orange', 'status,=,Renew'];
    return [__('Active'), 'green', 'status,=,Active'];
  },

  button: {
    show(doc) {
      const val = ((doc.attachment || '') + '').trim();
      return !!val;
    },
    get_label() {
      return __("Open");
    },
    get_description(doc) {
      return __("Open Attachment in a new tab");
    },
    action(doc) {
      try {
        let raw = ((doc.attachment || '') + '').trim();
        if (!raw) {
          frappe.msgprint({ 
            title: __('No Attachment'), 
            indicator: 'red', 
            message: __('No attachment found for this license') 
          });
          return;
        }

        // معالجة الملف
        frappe.call({
          method: 'frappe.client.get_value',
          args: {
            doctype: 'File',
            filters: { name: raw },
            fieldname: ['file_url']
          },
          callback: function(r) {
            if (r.message && r.message.file_url) {
              raw = r.message.file_url;
            }
            openFile(raw);
          }
        }).then(() => {
          // إذا لم يكن ملف، حاول فتح الرابط مباشرة
          if (raw.includes('/')) {
            openFile(raw);
          }
        });

        function openFile(url) {
          // تحويل المسار النسبي إلى مسار كامل
          if (url.startsWith('/')) {
            url = frappe.utils.get_url(url);
          }

          // فتح في نافذة جديدة
          window.open(url, '_blank', 'noopener,noreferrer');
        }

      } catch (err) {
        console.error('Error opening attachment:', err);
        frappe.msgprint({
          title: __('Open Failed'),
          indicator: 'red',
          message: __('Could not open the attachment. Please check the file URL or permissions.')
        });
      }
    }
  }
};