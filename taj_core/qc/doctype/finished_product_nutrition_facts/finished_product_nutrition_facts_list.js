frappe.listview_settings['Finished Product Nutrition Facts'] = {
    add_fields: ['docstatus'],
    get_indicator(doc) {
        return doc.docstatus === 1 ? [__('Approved'), 'green', 'docstatus,=,1']
            : doc.docstatus === 2 ? [__('Cancelled'), 'red', 'docstatus,=,2']
            : [__('Draft'), 'orange', 'docstatus,=,0'];
    }
};
