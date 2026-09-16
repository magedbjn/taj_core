function set_raw_material_item_query(frm, table_fieldname) {
    frm.set_query('item_code', table_fieldname, () => ({
        query: 'taj_core.rnd.item_queries.raw_material_item_query'
    }));
}


function is_trial_frozen(frm) {
    const frozen_statuses = ['Completed', 'Approved', 'Rejected'];
    return !frm.is_new() && frozen_statuses.includes(frm.doc.status);
}


function is_trial_formula_locked(frm) {
    return (
        is_trial_frozen(frm)
        || Boolean(frm.doc.formula_approved)
    );
}


function show_trial_formula_lock_intro(frm) {
    if (
        frm.doc.formula_approved
        && !is_trial_frozen(frm)
    ) {
        frm.set_intro(
            __(
                'Formula Locked — Formula quantities are approved. ' +
                'Cooking Runs and actual trial quantities can still be recorded.'
            ),
            'green'
        );
    }
}


frappe.ui.form.on('Product Proposal Trial', {
    setup(frm) {
        set_raw_material_item_query(frm, 'items');
        frappe.require(
            '/assets/taj_core/js/item_uom.js',
            () => {
                if (
                    window.taj_core
                    && taj_core.item_uom
                    && taj_core.item_uom.setup_grid
                ) {
                    taj_core.item_uom.setup_grid(
                        frm,
                        'items'
                    );
                }
            }
        );

        frm.set_query('based_on_trial', () => {
            return {
                filters: {
                    product_proposal: frm.doc.product_proposal || ''
                }
            };
        });
    },

    refresh(frm) {
        if (frm.doc.product_proposal) {
            frm.add_custom_button(
                __('Product Proposal'),
                () => {
                    frappe.set_route(
                        'Form',
                        'Product Proposal',
                        frm.doc.product_proposal
                    );
                }
            );
        }

        if (!frm.is_new() && frm.doc.product_proposal) {
            frm.add_custom_button(
                __('Sensory Rating Form'),
                () => open_sensory_rating_form(frm),
                __('Sensory')
            );

            frm.add_custom_button(
                __('Print Trial Label'),
                () => print_trial_label(frm),
                __('Print')
            );

            frm.add_custom_button(
                __('Print Cooking Sheet'),
                () => print_trial_cooking_sheet(frm),
                __('Print')
            );
        }

        set_trial_snapshot_read_only(frm);
        lock_solid_liquid_grid(frm);
        show_trial_formula_lock_intro(frm);

        if (
            !frm.is_new()
            && !is_trial_frozen(frm)
            && !frm.doc.formula_approved
        ) {
            frm.add_custom_button(
                __('Approve Formula Quantities'),
                () => approve_trial_formula(frm),
                __('Formula')
            );
        }

        if (
            !frm.is_new()
            && frm.doc.status === 'Approved'
            && frm.doc.is_final_trial
        ) {
            frm.add_custom_button(
                __('Update Product Proposal Formula'),
                () => replace_product_proposal_formula(frm),
                __('Formula')
            );
        }

        if (
            !frm.is_new()
            && frm.doc.status === 'Draft'
        ) {
            frm.add_custom_button(
                __('Refresh Costs'),
                () => refresh_trial_costs(frm),
                __('Costing')
            );
        }
    }
});



frappe.ui.form.on('Product Proposal Trial Item', {
    async item_code(frm, cdt, cdn) {
        if (
            window.taj_core
            && taj_core.item_uom
            && taj_core.item_uom.apply_item_default
        ) {
            await taj_core.item_uom.apply_item_default(
                frm,
                cdt,
                cdn
            );
        } else {
            frappe.require(
                '/assets/taj_core/js/item_uom.js',
                () => {
                    if (
                        window.taj_core
                        && taj_core.item_uom
                        && taj_core.item_uom.apply_item_default
                    ) {
                        taj_core.item_uom.apply_item_default(
                            frm,
                            cdt,
                            cdn
                        );
                    }
                }
            );
        }
    }
});


frappe.ui.form.on('Product Proposal Trial Run', {
    cooking_runs_add(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        row.run_date = frappe.datetime.get_today();
        frm.refresh_field('cooking_runs');
        set_trial_snapshot_read_only(frm);
        lock_solid_liquid_grid(frm);
    },

    cooking_runs_remove(frm) {
        set_trial_snapshot_read_only(frm);
        lock_solid_liquid_grid(frm);
    }
});


function lock_solid_liquid_grid(frm) {
    const field = frm.fields_dict.solid_liquid;

    if (!field || !field.grid) {
        return;
    }

    const frozen = is_trial_frozen(frm);
    const formula_locked = is_trial_formula_locked(frm);
    const formula_fields = [
        'component_type',
        'component_name',
        'size',
        'weight',
        'salt',
        'brix',
        'ph',
        'viscosity',
        'spindel_type',
        'rpm',
        'temperature'
    ];

    field.grid.cannot_add_rows = formula_locked;
    field.grid.cannot_delete_rows = formula_locked;

    formula_fields.forEach(fieldname => {
        field.grid.update_docfield_property(
            fieldname,
            'read_only',
            formula_locked ? 1 : 0
        );
    });

    field.grid.update_docfield_property(
        'total_weight_cook',
        'read_only',
        formula_locked ? 1 : 0
    );

    setTimeout(() => {
        if (!field.grid.wrapper) {
            return;
        }
        field.grid.wrapper.find('.grid-add-row').toggle(!formula_locked);
        field.grid.wrapper.find('.grid-remove-rows').toggle(!formula_locked);
        field.grid.wrapper.find('.grid-delete-row').toggle(!formula_locked);
    }, 100);
}


function set_trial_snapshot_read_only(frm) {
    const frozen = is_trial_frozen(frm);

    frm.set_df_property(
        'planned_cooking_qty',
        'read_only',
        !frm.is_new() ? 1 : 0
    );

    const fields = [
        'trial_title',
        'actual_produced_qty',
        'pouch_size',
        'holding_time',
        'remark'
    ];

    fields.forEach(fieldname => {
        frm.set_df_property(
            fieldname,
            'read_only',
            frozen ? 1 : 0
        );
    });

    const formula_locked = is_trial_formula_locked(frm);
    frm.set_df_property('items', 'read_only', formula_locked ? 1 : 0);
}

async function approve_trial_formula(frm) {
    if (frm.is_dirty()) {
        await frm.save();
    }

    frappe.confirm(
        __(
            'Approve the current formula quantities? ' +
            'Items and formulation quantities will be locked afterwards.'
        ),
        async () => {
            await frm.call('approve_formula');
            await frm.reload_doc();
            frappe.show_alert({
                message: __('Formula quantities approved.'),
                indicator: 'green'
            });
        }
    );
}


async function replace_product_proposal_formula(frm) {
    frappe.confirm(
        __(
            'Replace all Raw Materials and Solid / Liquid rows in ' +
            'Product Proposal {0}, and set Quantity from the latest ' +
            'Run Produced Qty?',
            [frm.doc.product_proposal]
        ),
        async () => {
            const response = await frm.call(
                'replace_product_proposal_formula'
            );
            const result = response.message || {};

            frappe.show_alert({
                message: __(
                    '{0} material(s) and {1} Solid / Liquid row(s) replaced. ' +
                    'Quantity set to {2} from Run {3}.',
                    [
                        result.items_replaced || 0,
                        result.solid_liquid_replaced || 0,
                        result.quantity || 0,
                        result.run_no || 0
                    ]
                ),
                indicator: 'green'
            });
        }
    );
}


async function refresh_trial_costs(frm) {
    const response = await frappe.call({
        method: [
            'taj_core.rnd.doctype.',
            'product_proposal_trial.',
            'product_proposal_trial.',
            'refresh_trial_costs'
        ].join(''),
        args: {
            trial_name: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Refreshing Costs...')
    });

    const summary = (
        response.message
        || {}
    );

    await frm.reload_doc();

    show_cost_summary_alert(summary);
}


function show_cost_summary_alert(summary) {
    const messages = [];

    if (summary.costed) {
        messages.push(
            __(
                'Cost calculated for {0} item(s).',
                [summary.costed]
            )
        );
    }

    if (summary.missing_conversion) {
        messages.push(
            __(
                '{0} item(s) ignored because no UOM conversion to Stock UOM was found.',
                [summary.missing_conversion]
            )
        );
    }

    if (summary.missing_cost) {
        messages.push(
            __(
                '{0} item(s) have no available cost.',
                [summary.missing_cost]
            )
        );
    }

    if (summary.missing_item) {
        messages.push(
            __(
                '{0} item(s) could not be found.',
                [summary.missing_item]
            )
        );
    }

    if (!messages.length) {
        messages.push(
            __('No costs were updated.')
        );
    }

    frappe.show_alert(
        {
            message: messages.join(' '),
            indicator: (
                summary.missing_conversion
                || summary.missing_cost
                || summary.missing_item
            )
                ? 'orange'
                : 'green'
        },
        7
    );
}


function open_sensory_rating_form(frm) {
    const query = new URLSearchParams({
        item: frm.doc.product_proposal,
        trial_document: frm.doc.name
    });

    window.open(
        `/sensory-rating?${query.toString()}`,
        '_blank',
        'noopener'
    );
}


async function print_trial_cooking_sheet(frm) {
    if (frm.is_dirty()) {
        await frm.save();
    }

    const runs = frm.doc.cooking_runs || [];

    if (!runs.length) {
        frappe.msgprint(__('Add a Trial Cooking Run before printing a Cooking Sheet.'));
        return;
    }

    const options = runs.map(row => String(row.run_no));

    const dialog = new frappe.ui.Dialog({
        title: __('Print Cooking Sheet'),
        fields: [
            {
                fieldname: 'run_no',
                fieldtype: 'Select',
                label: __('Cooking Run'),
                options: options.join('\n'),
                default: options[options.length - 1],
                reqd: 1
            }
        ],
        primary_action_label: __('Print'),
        primary_action: async values => {
            dialog.hide();
            const print_window = window.open('', '_blank');

            if (!print_window) {
                frappe.msgprint(__('Please allow pop-ups to print the Cooking Sheet.'));
                return;
            }

            const response = await frappe.call({
                method: [
                    'taj_core.rnd.doctype.',
                    'product_proposal_trial.',
                    'product_proposal_trial.',
                    'get_trial_run_cooking_sheet_html'
                ].join(''),
                args: {
                    trial_name: frm.doc.name,
                    run_no: values.run_no
                },
                freeze: true,
                freeze_message: __('Preparing Cooking Sheet...')
            });

            const html = response.message && response.message.html;
            if (!html) {
                print_window.close();
                return;
            }

            print_window.document.open();
            print_window.document.write(html);
            print_window.document.close();
            print_window.focus();
            setTimeout(() => print_window.print(), 250);
        }
    });

    dialog.show();
}


function print_trial_label(frm) {
    const query = new URLSearchParams({
        doctype: frm.doctype,
        name: frm.doc.name,
        trigger_print: '1',
        format: 'Product Proposal Trial Label 6x4',
        no_letterhead: '1'
    });

    window.open(
        `/printview?${query.toString()}`,
        '_blank',
        'noopener'
    );
}
