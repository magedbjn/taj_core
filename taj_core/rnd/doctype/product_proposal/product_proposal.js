frappe.ui.form.on('Product Proposal', {
    pp_solid_liquid_add: function(frm, cdt, cdn) {
        let child = locals[cdt][cdn];

        // عداد لكل نوع
        let solid_count = 0;
        let liquid_count = 0;

        frm.doc.pp_solid_liquid.forEach(c => {
            if(c.component_type === 'Solid') solid_count++;
            if(c.component_type === 'Liquid') liquid_count++;
        });

        if(child.component_type === 'Solid') {
            child.component_no = 'Solid ' + solid_count;
        } else if(child.component_type === 'Liquid') {
            child.component_no = 'Liquid ' + liquid_count;
        }

        refresh_field('pp_solid_liquid');
    }
});
