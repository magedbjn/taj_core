// frappe.ui.form.on('Purchase Order', {
// 	refresh(frm) {
// 		frm.add_custom_button(
// 			__('Taj Production Plan'),
// 			function () {
// 				erpnext.utils.map_current_doc({
// 					method: 'taj_core.api.production_plan.make_purchase_order_from_production_plan',
// 					source_doctype: 'Production Plan',
// 					target: frm,
// 					setters: {
// 						company: frm.doc.company
// 					},
// 					get_query_filters: {
// 						docstatus: 1,
// 						company: frm.doc.company
// 					},
// 					allow_child_item_selection: true,
// 					child_fieldname: 'mr_items',  // ✅ اسم الحقل الفرعي في DocType
// 					child_columns: ['item_code', 'item_name', 'quantity']
// 				});
// 			},
// 			__('Get Items From')
// 		);
// 	}
// });

frappe.ui.form.on('Material Request', {
    refresh: function (frm) {
        // ✅ الزر الأول: Collect Similar Items
        if (!frm.doc.__islocal && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Collect Similar Items'), function () {
                frappe.call({
                    method: 'taj_core.custom.material_request.collect_similar_items',
                    args: {
                        docname: frm.doc.name
                    },
                    callback: function(r) {
                        if(!r.exc) {
                            // Update the items table without full reload
                            if (r.message && r.message.items) {
                                frm.doc.items = r.message.items;
                                frm.refresh_field('items');
                            }
                            
                            frappe.show_alert({
                                message: __('Similar items collected successfully'), 
                                indicator: 'green'
                            });
                        }
                    }
                });
            }, __('Taj'));
        }

        // ✅ الزر الثاني: Taj Production Plan
        frm.add_custom_button(
            __('Taj Production Plan'),
            function () {
                if (!frm.doc.company) {
                    frappe.msgprint(__('Please select company first'));
                    return;
                }
                
                var from_date = frappe.datetime.add_months(frappe.datetime.get_today(), -5);
                var to_date = frappe.datetime.get_today();

                erpnext.utils.map_current_doc({
                    method: 'taj_core.custom.production_plan.make_material_request_from_production_plan',
                    source_doctype: 'Production Plan',
                    target: frm,
                    setters: { company: frm.doc.company },
                    get_query_filters: {
                        docstatus: 1,
                        company: frm.doc.company,
                        posting_date: ['between', [from_date, to_date]]
                    },
                    args: { material_request_type: 'Purchase' },
                    allow_child_item_selection: true,
                    child_fieldname: 'mr_items',
                    child_columns: [
                        'item_code', 'item_name', 'quantity', 
                        'material_request_type', 'schedule_date'
                    ]
                });
            },
            __('Taj') // نفس مجموعة الأزرار
        );
    }
});
