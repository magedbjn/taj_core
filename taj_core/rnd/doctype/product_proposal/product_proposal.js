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

        // Independent Trial snapshots
        set_trial_document_filters(frm);
        add_trial_management_buttons(frm);

        // Customer Samples
        set_customer_sample_filter(frm);

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


frappe.ui.form.on('Product Proposal Sample', {
    evaluation_link(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.evaluation_token) {
            frappe.msgprint(
                __('Save the Product Proposal first to generate the evaluation link.')
            );
            return;
        }

        const url = [
            window.location.origin,
            '/sensory-rating?sample=',
            encodeURIComponent(row.evaluation_token)
        ].join('');

        window.open(url, '_blank', 'noopener');
    }
});


// -----------------------------------------------------------------------------
// Helper Functions
// -----------------------------------------------------------------------------

function set_customer_sample_filter(frm) {
    if (!frm.fields_dict.customer_samples) {
        return;
    }

    const grid = frm.fields_dict.customer_samples.grid;
    const trial_field = grid && grid.get_field('trial_document');

    if (!trial_field) {
        return;
    }

    trial_field.get_query = function() {
        return {
            filters: {
                product_proposal: frm.doc.name || ''
            }
        };
    };
}


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

// -----------------------------------------------------------------------------
// Independent Trial Documents
// -----------------------------------------------------------------------------

function set_trial_document_filters(frm) {
    if (!frm.doc.name || frm.is_new()) {
        return;
    }

    frm.set_query(
        'trial_document',
        'trial_cooking',
        () => {
            return {
                filters: {
                    product_proposal: frm.doc.name
                }
            };
        }
    );

    frm.set_query(
        'trial_document',
        'pp_sensory_evaluation',
        () => {
            return {
                filters: {
                    product_proposal: frm.doc.name
                }
            };
        }
    );
}


function add_trial_management_buttons(frm) {
    if (
        frm.is_new()
        || frm.doc.docstatus === 2
    ) {
        return;
    }

    const group = __('Trial Cooking');

    if (user_can_edit_trial_cooking()) {
        frm.add_custom_button(
            __('New Trial'),
            () => create_new_trial(frm),
            group
        );
    }

    frm.add_custom_button(
        __('View Trials'),
        () => {
            frappe.route_options = {
                product_proposal: frm.doc.name
            };

            frappe.set_route(
                'List',
                'Product Proposal Trial'
            );
        },
        group
    );

    frm.add_custom_button(
        __('Compare Trials'),
        () => compare_product_trials(frm),
        group
    );
}


function create_new_trial(frm) {
    const dialog = new frappe.ui.Dialog({
        fields: [
            {
                fieldname: 'source_label',
                fieldtype: 'Select',
                label: __('Copy Items From'),
                options: [
                    'Previous Trial',
                    'Current Product Proposal Items',
                    'Empty Trial'
                ].join('\n'),
                default: 'Previous Trial',
                reqd: 1
            },
            {
                fieldname: 'planned_cooking_qty',
                fieldtype: 'Int',
                label: __('Planned Cooking Qty'),
                reqd: 1
            }
        ],
        title: __('New Trial Cooking'),
        primary_action_label: __('Create'),
        primary_action: async values => {
            dialog.hide();

            const source_map = {
                'Previous Trial': 'previous',
                'Current Product Proposal Items': 'proposal',
                'Empty Trial': 'empty'
            };

            const source = (
                source_map[values.source_label]
                || 'previous'
            );

            const response = await frappe.call({
                method: [
                    'taj_core.rnd.doctype.',
                    'product_proposal_trial.',
                    'product_proposal_trial.',
                    'create_trial'
                ].join(''),
                args: {
                    product_proposal: frm.doc.name,
                    source: source,
                    planned_cooking_qty: values.planned_cooking_qty
                },
                freeze: true,
                freeze_message: __('Creating Trial...')
            });

            if (
                !response.message
                || !response.message.name
            ) {
                return;
            }

            const cost_summary = (
                response.message.cost_summary
                || {}
            );

            let creation_message = __(
                'Trial {0} created with {1} Items.',
                [
                    response.message.trial_no,
                    response.message.items
                ]
            );

            if (cost_summary.missing_conversion) {
                creation_message += ' ' + __(
                    '{0} item(s) were excluded from costing because no UOM conversion to Stock UOM was found.',
                    [cost_summary.missing_conversion]
                );
            }

            frappe.show_alert(
                {
                    message: creation_message,
                    indicator: (
                        cost_summary.missing_conversion
                        ? 'orange'
                        : 'green'
                    )
                },
                7
            );

            frappe.set_route(
                'Form',
                'Product Proposal Trial',
                response.message.name
            );
        }
    });

    dialog.show();
}


function compare_product_trials(frm) {
    const get_query = () => {
        return {
            filters: {
                product_proposal: frm.doc.name
            }
        };
    };

    frappe.prompt(
        [
            {
                fieldname: 'first_trial',
                fieldtype: 'Link',
                options: 'Product Proposal Trial',
                label: __('First Trial'),
                reqd: 1,
                get_query: get_query
            },
            {
                fieldname: 'second_trial',
                fieldtype: 'Link',
                options: 'Product Proposal Trial',
                label: __('Second Trial'),
                reqd: 1,
                get_query: get_query
            }
        ],
        async values => {
            if (
                values.first_trial
                === values.second_trial
            ) {
                frappe.msgprint(
                    __('Please select two different Trials.')
                );
                return;
            }

            const response = await frappe.call({
                method: [
                    'taj_core.rnd.doctype.',
                    'product_proposal_trial.',
                    'product_proposal_trial.',
                    'compare_trials'
                ].join(''),
                args: {
                    first_trial: values.first_trial,
                    second_trial: values.second_trial
                },
                freeze: true,
                freeze_message: __('Comparing Trials...')
            });

            if (!response.message) {
                return;
            }

            show_trial_comparison(
                response.message
            );
        },
        __('Compare Trials'),
        __('Compare')
    );
}


function trial_escape(value) {
    if (
        value === null
        || value === undefined
        || value === ''
    ) {
        return '-';
    }

    return frappe.utils.escape_html(
        String(value)
    );
}


function sensory_status_text(summary) {
    const counts = (
        summary.final_status_counts
        || {}
    );

    const values = Object.entries(counts)
        .map(([status, count]) => {
            return (
                `${trial_escape(status)} (${count})`
            );
        });

    return values.length
        ? values.join(', ')
        : '-';
}


function sensory_summary_row(label, trial) {
    const sensory = (
        trial.sensory
        || {}
    );

    return `
        <tr>
            <td><strong>${trial_escape(label)}</strong></td>
            <td>${trial_escape(trial.name)}</td>
            <td>${trial_escape(sensory.count || 0)}</td>
            <td>${trial_escape(sensory.appearance)}</td>
            <td>${trial_escape(sensory.texture)}</td>
            <td>${trial_escape(sensory.taste)}</td>
            <td>${sensory_status_text(sensory)}</td>
        </tr>
    `;
}


function show_trial_comparison(data) {
    const detail_rows = [];

    (data.changes || []).forEach(row => {
        if (row.change_type === 'Added') {
            detail_rows.push(`
                <tr>
                    <td>${trial_escape(row.item_code)}</td>
                    <td>${__('Added')}</td>
                    <td>${__('Qty')}</td>
                    <td>-</td>
                    <td>${trial_escape(row.new_qty)}</td>
                </tr>
            `);
            return;
        }

        if (row.change_type === 'Removed') {
            detail_rows.push(`
                <tr>
                    <td>${trial_escape(row.item_code)}</td>
                    <td>${__('Removed')}</td>
                    <td>${__('Qty')}</td>
                    <td>${trial_escape(row.old_qty)}</td>
                    <td>-</td>
                </tr>
            `);
            return;
        }

        (row.changes || []).forEach(change => {
            detail_rows.push(`
                <tr>
                    <td>${trial_escape(row.item_code)}</td>
                    <td>${__('Changed')}</td>
                    <td>${trial_escape(change.label)}</td>
                    <td>${trial_escape(change.old)}</td>
                    <td>${trial_escape(change.new)}</td>
                </tr>
            `);
        });
    });

    if (!detail_rows.length) {
        detail_rows.push(`
            <tr>
                <td colspan="5" class="text-muted text-center">
                    ${__('No formulation differences found.')}
                </td>
            </tr>
        `);
    }

    const html = `
        <div class="mb-4">
            <strong>${__('Product Proposal')}:</strong>
            ${trial_escape(data.product_proposal)}
        </div>

        <div class="mb-4">
            <strong>${trial_escape(data.first.name)}</strong>
            &nbsp;→&nbsp;
            <strong>${trial_escape(data.second.name)}</strong>
        </div>

        <h5>${__('Formulation Changes')}</h5>

        <table class="table table-bordered table-sm">
            <thead>
                <tr>
                    <th>${__('Item')}</th>
                    <th>${__('Change')}</th>
                    <th>${__('Field')}</th>
                    <th>${__('From')}</th>
                    <th>${__('To')}</th>
                </tr>
            </thead>
            <tbody>
                ${detail_rows.join('')}
            </tbody>
        </table>

        <p class="text-muted">
            ${__('Unchanged lines')}:
            ${trial_escape(data.unchanged_count || 0)}
        </p>

        <h5>${__('Sensory Evaluation')}</h5>

        <table class="table table-bordered table-sm">
            <thead>
                <tr>
                    <th>${__('Trial')}</th>
                    <th>${__('Document')}</th>
                    <th>${__('Evaluations')}</th>
                    <th>${__('Appearance')}</th>
                    <th>${__('Texture')}</th>
                    <th>${__('Taste')}</th>
                    <th>${__('Decision')}</th>
                </tr>
            </thead>
            <tbody>
                ${sensory_summary_row(
                    __('First'),
                    data.first
                )}
                ${sensory_summary_row(
                    __('Second'),
                    data.second
                )}
            </tbody>
        </table>
    `;

    frappe.msgprint({
        title: __('Trial Comparison'),
        message: html,
        wide: true
    });
}
