frappe.ui.form.on('Product Development', {
  onload(frm) {
    apply_type_behavior(frm);
    setup_queries(frm);
    enforce_only_select(frm);
  },

  refresh(frm) {
    apply_type_behavior(frm);
    setup_queries(frm);
    enforce_only_select(frm);
  },

  type(frm) {
    if (frm.doc.type !== frm._lastType) {
      clear_related_fields(frm);
      frm._lastType = frm.doc.type;
    }
    apply_type_behavior(frm);
    setup_queries(frm);
  },

  async item_code(frm) {
    if (!frm.doc.item_code) {
      frm.set_value('version', '');
      frm.set_value('item_name', '');
      return;
    }
    frm.set_value('version', '');

    try {
      if (frm.doc.type === 'Product Proposal') {
        const { message } = await frappe.db.get_value('Product Proposal', frm.doc.item_code, 'product_name');
        if (message?.product_name) frm.set_value('item_name', message.product_name);
      } else if (frm.doc.type === 'BOM') {
        const { message } = await frappe.db.get_value('Item', frm.doc.item_code, 'item_name');
        if (message?.item_name) frm.set_value('item_name', message.item_name);
      }
    } catch (err) {
      console.error('Error fetching item details:', err);
    } finally {
      setup_version_query(frm);
    }
  },

  validate(frm) {
    // تأكيد إعداد حقول الهدف لـ Dynamic Link قبل الحفظ
    if (!frm.doc.link_target_doctype || !frm.doc.version_target_doctype) {
      frappe.throw(__('Internal doctype targets are not set. Please choose Type again.'));
    }
  }
});

function apply_type_behavior(frm) {
  const t = frm.doc.type || '';
  const isBOM = t === 'BOM';
  const isPP  = t === 'Product Proposal';

  if (isBOM) {
    // اضبط الدوكتايب الهدف للـ Dynamic Link
    frm.set_value('link_target_doctype', 'Item');
    frm.set_value('version_target_doctype', 'BOM');

    frm.set_df_property('item_code', 'label', __('Item Code'));
    frm.set_df_property('version',   'label', __('BOM Version'));

  } else if (isPP) {
    frm.set_value('link_target_doctype', 'Product Proposal');
    frm.set_value('version_target_doctype', 'Product Proposal');

    frm.set_df_property('item_code', 'label', __('Product Name'));
    frm.set_df_property('version',   'label', __('Proposal Version'));
  }

  // فحصٌ ودي (اختياري) لضمان صحة تعريف Dynamic Link
  ['item_code','version'].forEach(f => {
    const df = frm.fields_dict[f]?.df;
    const optField = df?.options; // اسم الحقل الحامل للدوكتايب
    const ref = frm.fields_dict[optField]?.df;
    if (df?.fieldtype === 'Dynamic Link' && !(ref?.fieldtype === 'Link' && ref?.options === 'DocType')) {
      console.warn(`Dynamic Link '${f}' must point to a Link field whose options='DocType'. Check field: ${optField}`);
    }
  });
}

function setup_queries(frm) {
  setup_item_code_query(frm);
  setup_version_query(frm);
}

function setup_item_code_query(frm) {
  if (!frm.doc.type) return;

  if (frm.doc.type === 'BOM') {
    // Item حيث Finished Goods & disabled=0
    frm.set_query('item_code', () => ({
      filters: { item_group: 'Finished Goods', disabled: 0 }
    }));

  } else if (frm.doc.type === 'Product Proposal') {
    // product_name بدون تكرار
    frm.set_query('item_code', () => ({
      query: 'taj_core.rnd.doctype.product_development.product_development.product_name_distinct_query'
    }));
  }
}

function setup_version_query(frm) {
  if (!frm.doc.type) return;

  if (frm.doc.type === 'BOM') {
    frm.set_query('version', () => {
      const filters = { is_active: 1 };
      if (frm.doc.item_code) filters.item = frm.doc.item_code;
      return { filters };
    });

  } else if (frm.doc.type === 'Product Proposal') {
    frm.set_query('version', () => {
      const filters = {};
      if (frm.doc.item_name) filters.product_name = frm.doc.item_name;
      return {
        query: 'taj_core.rnd.doctype.product_development.product_development.proposal_versions_query',
        filters
      };
    });
  }
}

function clear_related_fields(frm) {
  ['item_code', 'version', 'item_name'].forEach(f => frm.set_value(f, ''));
}

function enforce_only_select(frm) {
  ['item_code', 'version'].forEach(f => {
    const field = frm.get_field(f);
    if (field && typeof field.set_only_select === 'function') {
      field.set_only_select(true); // يمنع الإدخال اليدوي قدر الإمكان
    }
  });
}
