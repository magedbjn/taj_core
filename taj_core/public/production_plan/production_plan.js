frappe.ui.form.on('Production Plan', {
    refresh: function(frm) {
        var me = frm;

        // زر لعرض الملصقات وتحميلها مباشرة
        me.add_custom_button(
            __("Show Label"),
            function() {
                frappe.call({
                    method: "taj_core.public.production_plan.generate_stickers.open_production_stickers",
                    args: { plan_name: me.doc.name },
                    callback: function(res) {
                        if (res.message) {
                            // تحميل الملف مباشرة
                            var link = document.createElement('a');
                            link.href = res.message;
                            link.download = res.message.split('/').pop();
                            document.body.appendChild(link);
                            link.click();
                            document.body.removeChild(link);
                        }
                    }
                });
            },
            __("Taj")
        );

        // زر لحذف الملصقات يدويًا
        me.add_custom_button(
            __("Delete Label"),
            function() {
                frappe.confirm(
                    __('Are you sure you want to delete all labels for this Production Plan?'),
                    function() {
                        frappe.call({
                            method: "taj_core.public.production_plan.generate_stickers.delete_production_stickers",
                            args: { plan_name: me.doc.name },
                            callback: function(r) {
                                frappe.msgprint(__('Labels deleted successfully.'));
                            }
                        });
                    }
                );
            },
            __("Taj")
        );

    }
});

