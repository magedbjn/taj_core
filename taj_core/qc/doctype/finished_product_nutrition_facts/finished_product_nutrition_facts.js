frappe.ui.form.on('Finished Product Nutrition Facts', {
    setup(frm) {
        frm.set_query('item_code', () => ({
            filters: { is_sales_item: 1, item_group: 'Finished Goods', disabled: 0 }
        }));
        frm.set_query('item_code', 'additional_items', () => ({
            filters: {
                is_sales_item: 1,
                item_group: 'Finished Goods',
                disabled: 0,
                has_variants: 0
            }
        }));
    },
    refresh(frm) {
        frm.__fpls_previous_item = frm.doc.item_code || '';
        update_additional_items_visibility(frm, false);
    },
    item_code(frm) {
        update_additional_items_visibility(frm, true);
    }
});

async function update_additional_items_visibility(frm, changed) {
    const item_code = frm.doc.item_code;
    const show = (visible) => {
        frm.toggle_display('independent_items_section', visible);
        frm.toggle_display('additional_items', visible);
    };
    if (!item_code) {
        show(false);
        frm.__fpls_previous_item = '';
        return;
    }

    try {
        const response = await frappe.db.get_value('Item', item_code, 'has_variants');
        if (frm.doc.item_code !== item_code) return;
        const is_template = Number(response.message?.has_variants || 0) === 1;
        show(!is_template);

        // Never silently erase linked Items, including on switches to a template.
        if (is_template && (frm.doc.additional_items || []).length) {
            if (changed && !frm.__fpls_link_prompt_open) {
                frm.__fpls_link_prompt_open = true;
                frappe.confirm(
                    __('The selected Item has variants. Remove the existing Additional Items?'),
                    () => {
                        frm.clear_table('additional_items');
                        frm.refresh_field('additional_items');
                        frm.__fpls_previous_item = item_code;
                        frm.__fpls_link_prompt_open = false;
                    },
                    () => {
                        frm.__fpls_link_prompt_open = false;
                        frm.set_value('item_code', frm.__fpls_previous_item || '');
                    }
                );
            }
        } else {
            frm.__fpls_previous_item = item_code;
        }
    } catch (error) {
        // If the lookup fails, rely on server validation and avoid guessing.
        show(false);
    }
}
