function sensory_api(method) {
    return [
        'taj_core.rnd.web_form.sensory_rating.sensory_rating.',
        method
    ].join('');
}


function set_trial_options(rows, selected_trial, selected_label) {
    const options = [
        { label: '', value: '' },
        ...(rows || []).map(row => ({
            label: [
                row.product_name || row.product_proposal,
                row.trial_title || row.name
            ].filter(Boolean).join(' — '),
            value: row.name
        }))
    ];

    if (
        selected_trial
        && !options.some(option => option.value === selected_trial)
    ) {
        options.unshift({
            label: selected_label || selected_trial,
            value: selected_trial
        });
    }

    frappe.web_form.set_df_property('trial_document', 'options', options);
}


async function set_trial_context(trial_document) {
    if (!trial_document) {
        frappe.web_form.set_value('item', '');
        return;
    }

    const response = await frappe.call({
        method: sensory_api('get_trial_evaluation_context'),
        args: { trial_document }
    });

    const context = response.message || {};
    frappe.web_form.set_value('item', context.product_proposal || '');
}


async function load_general_trials(selected_trial) {
    const response = await frappe.call({
        method: sensory_api('get_active_sensory_trials'),
        args: { txt: '' }
    });

    set_trial_options(response.message || [], selected_trial);
}


async function load_sample_context(sample_token) {
    const response = await frappe.call({
        method: sensory_api('resolve_sample_evaluation_context'),
        args: { sample_token }
    });

    const context = response.message || {};
    set_trial_options(
        [],
        context.trial_document,
        [context.product_name, context.trial_title]
            .filter(Boolean)
            .join(' — ')
    );
    frappe.web_form.set_value('sample_token', sample_token);
    frappe.web_form.set_value('customer', context.customer || '');
    frappe.web_form.set_value('trial_document', context.trial_document || '');
    frappe.web_form.set_value('item', context.product_proposal || '');
    frappe.web_form.set_df_property('trial_document', 'read_only', 1);
    frappe.web_form.set_df_property('your_name', 'reqd', 0);
    frappe.web_form.set_df_property('your_name', 'hidden', 1);
}


frappe.web_form.after_load = async () => {
    const params = new URLSearchParams(window.location.search);
    const sample_token = params.get('sample');
    const direct_trial = params.get('trial_document');

    if (sample_token) {
        await load_sample_context(sample_token);
        return;
    }

    await load_general_trials(direct_trial);

    if (direct_trial) {
        await frappe.web_form.set_value('trial_document', direct_trial);
        await set_trial_context(direct_trial);
    }
};


frappe.web_form.on('trial_document', async (field, value) => {
    const sample_token = frappe.web_form.get_value('sample_token');

    if (sample_token) {
        return;
    }

    await set_trial_context(value);
});
