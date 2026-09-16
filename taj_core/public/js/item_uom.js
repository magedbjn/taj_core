frappe.provide('taj_core.item_uom');


taj_core.item_uom.setup_grid = function(
    frm,
    table_fieldname,
    options = {}
) {
    const item_field = options.item_field || 'item_code';
    const uom_field = options.uom_field || 'uom';

    const table = frm.fields_dict[table_fieldname];

    if (!table || !table.grid) {
        return;
    }

    const field = table.grid.get_field(uom_field);

    if (!field) {
        return;
    }

    field.get_query = function(doc, cdt, cdn) {
        const row = locals[cdt] && locals[cdt][cdn];

        return {
            query: 'taj_core.services.item_uom.item_uom_query',
            filters: {
                item_code: (
                    row
                    && row[item_field]
                ) || ''
            }
        };
    };
};


taj_core.item_uom.apply_item_default = async function(
    frm,
    cdt,
    cdn,
    options = {}
) {
    const item_field = options.item_field || 'item_code';
    const uom_field = options.uom_field || 'uom';

    const row = locals[cdt] && locals[cdt][cdn];

    if (!row) {
        return;
    }

    const item_code = row[item_field] || '';

    if (!item_code) {
        if (row[uom_field]) {
            await frappe.model.set_value(
                cdt,
                cdn,
                uom_field,
                ''
            );
        }

        return;
    }

    const response = await frappe.call({
        method: 'taj_core.services.item_uom.get_item_uom_options',
        args: {
            item_code: item_code
        }
    });

    // Protect against an older async request overwriting a newer Item.
    const current_row = locals[cdt] && locals[cdt][cdn];

    if (
        !current_row
        || current_row[item_field] !== item_code
    ) {
        return;
    }

    const result = response.message || {};
    const stock_uom = result.stock_uom || '';

    if (
        stock_uom
        && current_row[uom_field] !== stock_uom
    ) {
        await frappe.model.set_value(
            cdt,
            cdn,
            uom_field,
            stock_uom
        );
    }
};
