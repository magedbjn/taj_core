frappe.ui.form.on('Sensory Feedback', {
    setup(frm) {
        set_trial_query(frm);
    },

    refresh(frm) {
        set_trial_query(frm);
    },

    item(frm) {
        if (frm.doc.trial_document) {
            frm.set_value(
                'trial_document',
                null
            );
        }

        set_trial_query(frm);
    }
});


function set_trial_query(frm) {
    frm.set_query(
        'trial_document',
        () => {
            return {
                filters: {
                    product_proposal: (
                        frm.doc.item
                        || ''
                    )
                }
            };
        }
    );
}
