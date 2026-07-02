// Product Proposal → Client Script

// -----------------------------------------------------------------------------
// Constants
// -----------------------------------------------------------------------------

// اسم جدول المواد
const PP_CHILD_TABLE = 'pp_items';

// اسم حقل الكمية داخل جدول pp_items
const PP_CHILD_QTY_FIELD = 'qty';

// اسم جدول Trial Cooking
const TRIAL_COOKING_TABLE = 'trial_cooking';

// الصلاحيات المسموح لها بإدخال / تعديل Trial Cooking
const TRIAL_COOKING_ALLOWED_ROLES = [
    'System Manager',
    'RND Manager',
    'RND Trial Cooking User'
];


// -----------------------------------------------------------------------------
// Product Proposal
// -----------------------------------------------------------------------------

frappe.ui.form.on('Product Proposal', {
    onload: function(frm) {
        // حفظ كمية الرأس عند فتح المستند
        frm._old_quantity = flt(frm.doc.quantity || 0);

        // هذه الكمية تعتبر أساس كميات pp_items الحالية
        frm._pp_items_quantity_base = flt(frm.doc.quantity || 0);
    },

    refresh: function(frm) {
        if (frm._old_quantity === undefined) {
            frm._old_quantity = flt(frm.doc.quantity || 0);
        }

        if (frm._pp_items_quantity_base === undefined) {
            frm._pp_items_quantity_base = flt(frm.doc.quantity || 0);
        }

        // منع تعديل اسم المنتج بعد إنشاء Item
        frm.set_df_property('product_name', 'read_only', frm.doc.item_code ? 1 : 0);

        // صلاحيات Trial Cooking من الواجهة
        set_trial_cooking_permission(frm);

        // فلتر Preparation BOM
        set_preparation_bom_filter(frm);

        // إخفاء Duplicate قبل Submit
        hide_duplicate_before_submit(frm);

        // أزرار بعد Submit
        add_submitted_buttons(frm);

        // زر Sync Preparation BOM
        add_sync_preparation_bom_button(frm);
    },

    trial_cooking_add: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        // التاريخ تلقائي = اليوم
        row.posting_date = frappe.datetime.get_today();

        // المستخدم تلقائي = المستخدم الحالي
        row.trial_user = frappe.session.user;

        // Trial Qty لا يتم تعبئته تلقائيًا
        // لأنه يمثل الكمية التي أُنتجت فعليًا بعد الطبخ
        // المستخدم يدخلها بنفسه

        // Holding Time تلقائي = الوقت الحالي
        // المستخدم يستطيع تعديله بعد ذلك
        row.holding_time = frappe.datetime.now_time();

        frm.refresh_field(TRIAL_COOKING_TABLE);
    },

    quantity: function(frm) {
        handle_quantity_change(frm);
    }
});


// -----------------------------------------------------------------------------
// Product Proposal Raw Material
// -----------------------------------------------------------------------------

frappe.ui.form.on('Product Proposal Raw Material', {
    item_code: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        // لا تعمل شيء إذا ما فيه item_code أو لو pre_bom ممتلئ مسبقًا
        if (!row.item_code || row.pre_bom) {
            return;
        }

        // اسحب أحدث bom_no من Preparation Items المطابق لـ item_code
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'Preparation Items',
                fields: ['bom_no'],
                filters: {
                    item_code: row.item_code
                },
                limit_page_length: 1,
                order_by: 'modified desc'
            },
            callback: function(r) {
                const rec = (r.message && r.message[0]) || null;

                if (rec && rec.bom_no) {
                    frappe.model.set_value(cdt, cdn, 'pre_bom', rec.bom_no);
                }
            }
        });
    }
});


// -----------------------------------------------------------------------------
// Helper Functions
// -----------------------------------------------------------------------------

function set_preparation_bom_filter(frm) {
    if (!frm.fields_dict['pp_items']) {
        return;
    }

    const grid = frm.fields_dict['pp_items'].grid;

    if (!grid || !grid.get_field('pre_bom')) {
        return;
    }

    grid.get_field('pre_bom').get_query = function(doc, cdt, cdn) {
        return {
            filters: [
                ['BOM', 'name', 'like', 'BOM-PRE-%']
            ]
        };
    };
}


function hide_duplicate_before_submit(frm) {
    if (frm.doc.docstatus === 1) {
        return;
    }

    const label = __('Duplicate');

    setTimeout(() => {
        frm.page.menu
            .find(`[data-label="${encodeURIComponent(label)}"]`)
            .parent()
            .addClass('hidden');
    }, 300);
}


function add_submitted_buttons(frm) {
    if (frm.doc.docstatus !== 1) {
        return;
    }

    // زر New Version
    frm.add_custom_button(__('New Version'), function() {
        let new_pp = frappe.model.copy_doc(frm.doc);

        // لا تنسخ Trial Cooking إلى النسخة الجديدة
        new_pp.trial_cooking = [];

        frappe.set_route('Form', frm.doctype, new_pp.name);
    });

    // زر Create Item
    add_create_item_button(frm);
}


function add_create_item_button(frm) {
    if (frm.doc.item_code) {
        return;
    }

    const group = __('Create');

    frm.add_custom_button(__('Item'), async () => {
        try {
            if (frm.is_dirty()) {
                await frm.save();
            }

            const r = await frm.call({
                doc: frm.doc,
                method: 'create_item'
            });

            if (!r || !r.message) {
                return;
            }

            // إذا يوجد Item بنفس الاسم
            if (r.message.exists) {
                const code = r.message.item_code;

                const question = __(
                    'An Item with the same name already exists ({0}). Do you want to use this Item Code?',
                    [code]
                );

                frappe.confirm(
                    question,
                    async () => {
                        await frm.call({
                            doc: frm.doc,
                            method: 'link_existing_item',
                            args: {
                                item_code: code
                            }
                        });

                        await frm.reload_doc();

                        frappe.show_alert({
                            message: __('Linked to existing Item: {0}', [code]),
                            indicator: 'green'
                        });
                    },
                    () => {
                        frappe.show_alert({
                            message: __('Cancelled — no changes made.'),
                            indicator: 'yellow'
                        });
                    }
                );

                return;
            }

            // إنشاء Item جديد
            if (r.message.item_code) {
                await frm.set_value('item_code', r.message.item_code);
                await frm.save();
                await frm.reload_doc();

                frappe.show_alert({
                    message: __('Item created: {0}', [r.message.item_code]),
                    indicator: 'green'
                });
            }

        } catch (err) {
            const msg = err && err.message
                ? err.message
                : __('Failed to create/link Item.');

            frappe.msgprint(msg);

            frappe.show_alert({
                message: __('Failed to create/link Item. See console for details.'),
                indicator: 'red'
            });
        }
    }, group);
}


function add_sync_preparation_bom_button(frm) {
    if (frm.is_new()) {
        return;
    }

    if (!(frm.doc.pp_items || []).length) {
        return;
    }

    const prep_group = __('Preparation');

    frm.add_custom_button(__('Sync Preparation BOM'), async () => {
        try {
            const r = await frm.call({
                doc: frm.doc,
                method: 'sync_preparation_bom',
            });

            if (!r || !r.message) {
                frappe.show_alert({
                    message: __('No changes were made.'),
                    indicator: 'yellow'
                });
                return;
            }

            const { updated, missing_items } = r.message;

            if (updated) {
                frappe.show_alert({
                    message: __('Updated Preparation BOM for {0} row(s).', [updated]),
                    indicator: 'green',
                });
            } else {
                frappe.show_alert({
                    message: __('No rows required update.'),
                    indicator: 'yellow',
                });
            }

            if (missing_items && missing_items.length) {
                frappe.msgprint({
                    title: __('Missing Preparation Items'),
                    message: __(
                        'No Preparation Items were found for the following Item Codes: {0}',
                        [missing_items.join(', ')]
                    ),
                    indicator: 'orange',
                });
            }

            await frm.reload_doc();

        } catch (err) {
            frappe.msgprint(__('Failed to sync Preparation BOM. See console for details.'));
        }
    }, prep_group);
}


function handle_quantity_change(frm) {
    const old_qty = flt(frm._old_quantity || 0);
    const new_qty = flt(frm.doc.quantity || 0);

    // لا تعمل شيء إذا لا يوجد تغيير
    if (old_qty === new_qty) {
        return;
    }

    const rows = frm.doc[PP_CHILD_TABLE] || [];

    // إذا لا توجد مواد، فقط حدّث الكمية القديمة
    if (!rows.length) {
        frm._old_quantity = new_qty;
        frm._pp_items_quantity_base = new_qty;
        return;
    }

    // إذا الكمية الجديدة صفر، لا نعدل المواد
    if (!new_qty) {
        frm._old_quantity = new_qty;

        frappe.show_alert({
            message: __('Quantity is zero. Raw Materials quantities were not changed.'),
            indicator: 'yellow'
        });

        return;
    }

    // الأساس الذي تم بناء كميات pp_items عليه
    const base_qty = flt(frm._pp_items_quantity_base || old_qty || 0);

    if (!base_qty) {
        frm._old_quantity = new_qty;
        frm._pp_items_quantity_base = new_qty;
        return;
    }

    frappe.confirm(
        __(
            'Quantity changed from {0} to {1}. Do you want to update quantities in Raw Materials table?',
            [old_qty, new_qty]
        ),

        // Yes
        () => {
            const ratio = new_qty / base_qty;

            rows.forEach(row => {
                const current_child_qty = flt(row[PP_CHILD_QTY_FIELD] || 0);

                frappe.model.set_value(
                    row.doctype,
                    row.name,
                    PP_CHILD_QTY_FIELD,
                    current_child_qty * ratio
                );
            });

            frm.refresh_field(PP_CHILD_TABLE);

            // بعد التعديل، تصبح الكمية الجديدة هي الأساس
            frm._old_quantity = new_qty;
            frm._pp_items_quantity_base = new_qty;

            frappe.show_alert({
                message: __('Raw Materials quantities updated.'),
                indicator: 'green'
            });
        },

        // No
        () => {
            // لا نغير pp_items
            // لكن نحدث old_quantity حتى لا تظهر الرسالة مرة أخرى لنفس التغيير
            frm._old_quantity = new_qty;

            // مهم: لا نغير frm._pp_items_quantity_base
            // لأن كميات pp_items ما زالت مبنية على الكمية القديمة

            frappe.show_alert({
                message: __('Raw Materials quantities were not changed.'),
                indicator: 'yellow'
            });
        }
    );
}


function user_can_edit_trial_cooking() {
    return TRIAL_COOKING_ALLOWED_ROLES.some(role => frappe.user.has_role(role));
}


function set_trial_cooking_permission(frm) {
    if (!frm.fields_dict[TRIAL_COOKING_TABLE]) {
        return;
    }

    const allowed = user_can_edit_trial_cooking();

    // منع التعديل من الواجهة لغير المصرح لهم
    frm.set_df_property(TRIAL_COOKING_TABLE, 'read_only', allowed ? 0 : 1);

    const grid = frm.fields_dict[TRIAL_COOKING_TABLE].grid;

    if (!grid) {
        return;
    }

    grid.cannot_add_rows = !allowed;
    grid.cannot_delete_rows = !allowed;

    // إخفاء أزرار الإضافة والحذف قدر الإمكان
    setTimeout(() => {
        if (!grid.wrapper) {
            return;
        }

        grid.wrapper.find('.grid-add-row').toggle(allowed);
        grid.wrapper.find('.grid-remove-rows').toggle(allowed);
        grid.wrapper.find('.grid-delete-row').toggle(allowed);
        grid.wrapper.find('.grid-row-check').toggle(allowed);
    }, 300);
}