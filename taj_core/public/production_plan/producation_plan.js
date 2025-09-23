frappe.ui.form.on('Production Plan', {
    refresh: function(frm) {
        var me = frm;

        // زر داخل القائمة "Taj Label" لعرض الملصقات
        me.add_custom_button(
            __("Show Label"),
            function() {
                frappe.call({
                    method: "taj_core.public.production_plan.generate_stickers.open_production_stickers",
                    args: { plan_name: me.doc.name },
                    callback: function(r) {
                        if(r.message){
                            window.open(r.message, '_blank');
                        }
                    }
                });
            },
            __("Taj Label")
        );

        // زر لحذف الملصقات (جديد)
        me.add_custom_button(
            __("Delete Label"),
            function() {
                frappe.confirm(
                    __('Are you sure you want to delete all Label for this Production Plan?'),
                    function() {
                        frappe.call({
                            method: "taj_core.public.production_plan.generate_stickers.delete_production_stickers",
                            args: { plan_name: me.doc.name },
                            callback: function(r) {
                                frappe.msgprint(__('Label deleted successfully.'));
                            }
                        });
                    }
                );
            },
            __("Taj Label")
        );
    }
});