frappe.ui.form.on('Product Proposal Trial', {
    setup(frm) {
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
        }

        set_trial_snapshot_read_only(frm);

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


function set_trial_snapshot_read_only(frm) {
    const frozen = (
        !frm.is_new()
        && frm.doc.status
        && frm.doc.status !== 'Draft'
    );

    const fields = [
        'trial_title',
        'planned_cooking_qty',
        'actual_produced_qty',
        'pouch_size',
        'holding_time',
        'remark',
        'items'
    ];

    fields.forEach(fieldname => {
        frm.set_df_property(
            fieldname,
            'read_only',
            frozen ? 1 : 0
        );
    });
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
