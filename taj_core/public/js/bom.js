// ===== BOM Client Script (Optimized) =====
// الهدف:
// - Fetch من Product Proposal إلى BOM (كل الأصناف) مع الحفاظ على الترتيب
// - تسريع الأداء عبر Batch Fetch (بدون استعلام لكل صف)
// - تحويل الوحدات (g/kg/mg فقط) + خيار تحويل دائم
// - تحسين تجربة المستخدم (Confirm قبل مسح items)
// - تحسين قابلية الصيانة (ربط حقول الوزن بشكل ديناميكي)

// -------------------------------
// 1) Events
// -------------------------------
(() => {
  const WEIGHT_FIELDS = [
    'taj_liquid_weight', 'taj_solid_weight_1', 'taj_solid_weight_2',
    'taj_liquid_under_weight', 'taj_solid_under_weight_1', 'taj_solid_under_weight_2',
    'taj_liquid_over_weight', 'taj_solid_over_weight_1', 'taj_solid_over_weight_2'
  ];

  // تسجيل الأحداث ديناميكيًا (طريقة موثوقة)
  const weightHandlers = Object.fromEntries(
    WEIGHT_FIELDS.map(f => [f, frm => calculate_totals(frm)])
  );

  frappe.ui.form.on('BOM', {
    refresh(frm) {
      if (frm.is_new()) {
        frm.add_custom_button(__('Fetch from Product Proposal'), () => simpleFetchFromProductProposal(frm));
      }
      frm._debounced_refetch = debounce(() => {
        if (frm._pp_cache?.source_pp) refetchFromProductProposal(frm, frm._pp_cache.source_pp);
      }, 350);
    },

    validate(frm) {
      calculate_totals(frm);
    },

    ...weightHandlers
  });
})();

// -------------------------------
// 2) Totals
// -------------------------------
function calculate_totals(frm) {
  const total_weight =
    (frm.doc.taj_liquid_weight || 0) +
    (frm.doc.taj_solid_weight_1 || 0) +
    (frm.doc.taj_solid_weight_2 || 0);

  const total_under =
    (frm.doc.taj_liquid_under_weight || 0) +
    (frm.doc.taj_solid_under_weight_1 || 0) +
    (frm.doc.taj_solid_under_weight_2 || 0);

  const total_over =
    (frm.doc.taj_liquid_over_weight || 0) +
    (frm.doc.taj_solid_over_weight_1 || 0) +
    (frm.doc.taj_solid_over_weight_2 || 0);

  frm.set_value("taj_total_weight", total_weight);
  frm.set_value("taj_total_under_weight_", total_under);
  frm.set_value("taj_total_over_weight", total_over);
}

// -------------------------------
// 3) Helpers
// -------------------------------
function debounce(fn, wait) {
  let t;
  return function (...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), wait);
  };
}

function flt(n) {
  const x = parseFloat(n);
  return isNaN(x) ? 0 : x;
}

function showPermissionError() {
  frappe.msgprint({
    title: __('Permission Error'),
    message: __(
      'You do not have permission to access some resources. ' +
      'Please contact your system administrator to ensure you have permissions for: ' +
      'Product Proposal, BOM, and Item'
    ),
    indicator: 'red'
  });
}

// Batch fetch Items (stock_uom, item_name)
async function fetchItemsData(itemCodes) {
  const uniq = [...new Set((itemCodes || []).filter(Boolean))];
  if (!uniq.length) return {};

  const r = await frappe.call({
    method: 'frappe.client.get_list',
    args: {
      doctype: 'Item',
      filters: { name: ['in', uniq] },
      fields: ['name', 'stock_uom', 'item_name'],
      limit_page_length: uniq.length
    }
  });

  const out = {};
  (r.message || []).forEach(it => { out[it.name] = it; });
  return out;
}

// Batch fetch BOMs (item, uom) for pre_bom
async function fetchBOMData(bomNames) {
  const uniq = [...new Set((bomNames || []).filter(Boolean))];
  if (!uniq.length) return {};

  const r = await frappe.call({
    method: 'frappe.client.get_list',
    args: {
      doctype: 'BOM',
      filters: { name: ['in', uniq] },
      fields: ['name', 'item', 'uom'],
      limit_page_length: uniq.length
    }
  });

  const out = {};
  (r.message || []).forEach(b => { out[b.name] = b; });
  return out;
}

// -------------------------------
// 4) Validate PP Items
// -------------------------------
function validatePPItems(pp_items) {
  if (!pp_items || pp_items.length === 0) {
    frappe.msgprint({
      title: __('No Items'),
      message: __('Product Proposal does not contain any items.'),
      indicator: 'orange'
    });
    return false;
  }

  const invalid = [];
  for (let i = 0; i < pp_items.length; i++) {
    const code = (pp_items[i].item_code || '').toString().trim();
    if (!code) {
      invalid.push({
        index: i + 1,
        item_name: pp_items[i].item_name || 'Unnamed Item',
        item_code: pp_items[i].item_code || 'Empty'
      });
    }
    // (اختياري) منع الكمية الصفرية/السالبة:
    if (flt(pp_items[i].qty) <= 0) {
      invalid.push({
        index: i + 1,
        item_name: pp_items[i].item_name || 'Unnamed Item',
        item_code: pp_items[i].item_code || 'Empty',
        qty: pp_items[i].qty
      });
    }
  }

  if (invalid.length) {
    let msg = __('Invalid rows found:') + '<ul>';
    invalid.forEach(x => {
      msg += `<li>Row ${x.index}: "${x.item_name}" (Item: "${x.item_code}", Qty: "${x.qty ?? ''}")</li>`;
    });
    msg += '</ul>';

    frappe.msgprint({
      title: __('Invalid Items Found'),
      message: msg,
      indicator: 'red'
    });
    return false;
  }

  return true;
}

// -------------------------------
// 5) Fetch flow
// -------------------------------
async function simpleFetchFromProductProposal(frm) {
  // تحذير قبل استبدال items
  const proceed = () => open_pp_dialog_and_fetch(frm);

  if (frm.doc.items && frm.doc.items.length > 0) {
    frappe.confirm(
      __('This will replace all existing items. Continue?'),
      () => proceed(),
      () => null
    );
  } else {
    proceed();
  }
}

function open_pp_dialog_and_fetch(frm) {
  const d = new frappe.ui.Dialog({
    title: __('Enter Product Proposal Name'),
    fields: [
      {
        fieldname: 'pp_name',
        label: __('Product Proposal Name'),
        fieldtype: 'Link',
        options: 'Product Proposal',
        reqd: 1,
        get_query() {
          return {
            filters: { item_code: frm.doc.item, docstatus: 1 }
          };
        }
      }
    ],
    primary_action_label: __('Fetch Data'),
    primary_action: async () => {
      const values = d.get_values();
      if (!values) return;

      // اقفل الزر أثناء التنفيذ
      d.get_primary_btn().prop('disabled', true);

      try {
        if (!frm._pp_cache) frm._pp_cache = {};
        frm._pp_cache.source_pp = values.pp_name;

        frappe.show_progress(__('Fetching Data'), 10, 100, __('Loading Product Proposal...'));

        const r = await frappe.call({
          method: 'frappe.client.get',
          args: { doctype: 'Product Proposal', name: values.pp_name }
        });

        if (!r.message) {
          frappe.hide_progress();
          frappe.msgprint(__('Error loading Product Proposal'));
          d.get_primary_btn().prop('disabled', false);
          return;
        }

        const pp_doc = r.message;

        if (!validatePPItems(pp_doc.pp_items)) {
          frappe.hide_progress();
          d.get_primary_btn().prop('disabled', false);
          return;
        }

        frm._pp_cache.pp_doc_quantity = pp_doc.quantity;

        frappe.show_progress(__('Fetching Data'), 35, 100, __('Preparing data...'));
        await processProductProposalDataOptimized(frm, pp_doc);

        // ✅ بعد النجاح: اقفل النافذة تلقائيًا
        d.hide();

      } catch (e) {
        console.error(e);
        frappe.hide_progress();
        showPermissionError();
        d.get_primary_btn().prop('disabled', false);
      }
    }
  });

  d.show();
}


async function refetchFromProductProposal(frm, pp_name) {
  if (frm._pp_is_refreshing) return;
  frm._pp_is_refreshing = true;

  frappe.show_progress(__('Refreshing'), 10, 100, __('Updating quantities...'));

  try {
    const r = await frappe.call({
      method: 'frappe.client.get',
      args: { doctype: 'Product Proposal', name: pp_name }
    });

    if (!r.message) {
      frappe.msgprint(__('Error loading Product Proposal'));
      return;
    }

    const pp_doc = r.message;

    frappe.show_progress(__('Refreshing'), 35, 100, __('Preparing data...'));
    await processProductProposalDataOptimized(frm, pp_doc);

    if (!frm._pp_cache) frm._pp_cache = {};
    frm._pp_cache.pp_doc_quantity = pp_doc.quantity;

  } catch (e) {
    showPermissionError();
    console.error(e);
  } finally {
    frm._pp_is_refreshing = false;
    setTimeout(() => frappe.hide_progress(), 500);
  }
}

// -------------------------------
// 6) Optimized processing (Batch Fetch + single refresh)
// -------------------------------
async function processProductProposalDataOptimized(frm, pp_doc) {
  try {
    const bom_qty = flt(frm.doc.quantity);
    const pp_qty  = flt(pp_doc.quantity || 1);
    const ratio   = (bom_qty > 0 && pp_qty > 0) ? (bom_qty / pp_qty) : 1;

    // دائمًا نحول الوحدة بعد النقل (حسب طلبك)
    const SHOULD_CONVERT_UNITS = true;

    // اجمع الأكواد و pre_bom للـ batch fetch
    const pp_items = pp_doc.pp_items || [];
    const preBoms = pp_items.map(x => x.pre_bom).filter(Boolean);
    const itemCodes = pp_items.map(x => x.item_code).filter(Boolean);

    // جلب البيانات مرة واحدة
    frappe.show_progress(__('Fetching Data'), 45, 100, __('Fetching Items/BOMs in batch...'));
    const [itemsMap, bomsMap] = await Promise.all([
      fetchItemsData(itemCodes),
      fetchBOMData(preBoms)
    ]);

    // امسح الجدول مرة واحدة
    frm.clear_table('items');

    const total = pp_items.length;

    for (let i = 0; i < total; i++) {
      const pp_item = pp_items[i];

      const progress = 50 + Math.floor((i / Math.max(total, 1)) * 40);
      frappe.show_progress(__('Processing'), progress, 100, __('Processing item {0} of {1}', [i + 1, total]));

      const code = (pp_item.item_code || '').toString().trim();
      if (!code) continue;

      // resolve item_code + target_uom
      let resolved_item_code = code;
      let original_uom = pp_item.uom;
      let uom = pp_item.uom;
      let target_uom = pp_item.uom;
      let conversion_rate = 1;

      // 1) لو pre_bom -> خذ item و uom من BOM
      if (pp_item.pre_bom && bomsMap[pp_item.pre_bom]) {
        const b = bomsMap[pp_item.pre_bom];
        if (b.item) resolved_item_code = b.item;

        if (SHOULD_CONVERT_UNITS && b.uom) {
          target_uom = b.uom;
        }
      } else if (SHOULD_CONVERT_UNITS) {
        // 2) بدون pre_bom -> خذ stock_uom من item
        const it = itemsMap[resolved_item_code];
        if (it?.stock_uom) target_uom = it.stock_uom;
      }

      // qty base
      let final_qty = flt(pp_item.qty) * ratio;

      // conversion (g/kg/mg فقط)
      if (SHOULD_CONVERT_UNITS && target_uom && target_uom !== uom) {
        conversion_rate = getConversionRate(original_uom, target_uom, resolved_item_code);
        final_qty = flt(pp_item.qty) * conversion_rate * ratio;
        uom = target_uom;
      }

      await addBOMItemWithConversion(
        frm,
        pp_item,
        resolved_item_code,
        uom,
        final_qty,
        original_uom,
        conversion_rate,
        target_uom,
        i,
        SHOULD_CONVERT_UNITS
      );
    }

    // refresh مرة واحدة فقط
    frm.refresh_field('items');

    // cache
    if (!frm._pp_cache) frm._pp_cache = {};
    frm._pp_cache.pp_doc_quantity = pp_doc.quantity;
    frm._pp_cache.row_lookup = {};

    (frm.doc.items || []).forEach(row => {
      const key = `${row.item_code}::${row.idx}`;
      frm._pp_cache.row_lookup[key] = { pp_qty: row.__pp_qty, pp_uom: row.__pp_uom };
    });

    frappe.show_progress(__('Complete'), 100, 100, __('Finalizing...'));
    frappe.show_alert({ message: __('Data fetched from {0}', [pp_doc.name]), indicator: 'green' });
    setTimeout(() => frappe.hide_progress(), 700);

  } catch (error) {
    console.error(error);
    frappe.hide_progress();
    frappe.msgprint(__('Error processing data: {0}', [error.message || error]));
  }
}

// -------------------------------
// 7) Add row (await set_value item_code) + custom fields copy
// -------------------------------
async function addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, did_convert) {
  const row = frm.add_child('items');

  // مهم: انتظر set_value(item_code) عشان النظام يملأ defaults
  await frappe.model.set_value(row.doctype, row.name, 'item_code', item_code);

  await frappe.model.set_value(row.doctype, row.name, 'qty', flt(final_qty));
  await frappe.model.set_value(row.doctype, row.name, 'uom', uom);
  await frappe.model.set_value(row.doctype, row.name, 'description', pp_item.item_name || row.description);

  // ✅ الحقول المخصصة من PP -> BOM Item
  await frappe.model.set_value(row.doctype, row.name, 'taj_procees_type', pp_item.procees_type || null);
  await frappe.model.set_value(row.doctype, row.name, 'taj_cooking_type', pp_item.cooking_type || null);
  await frappe.model.set_value(row.doctype, row.name, 'taj_temperature', pp_item.temperature || null);
  await frappe.model.set_value(row.doctype, row.name, 'taj_duration', pp_item.duration || null);
  await frappe.model.set_value(row.doctype, row.name, 'taj_notes', pp_item.notes || null);

  // لو rate mandatory وما تعبى
  if (row.rate === undefined || row.rate === null) {
    await frappe.model.set_value(row.doctype, row.name, 'rate', 0);
  }

  // metadata
  row.__pp_qty = flt(pp_item.qty || 0);
  row.__pp_uom = original_uom || uom;
  row.__pp_index = index + 1;
  row.__converted_to = target_uom;
  row.__conversion_rate = conversion_rate;
  row.__did_convert = !!did_convert;

  return row;
}

// -------------------------------
// 8) Conversion rates (g/kg/mg only; avoid L↔kg without density)
// -------------------------------
function getConversionRate(from_uom, to_uom, item_code) {
    const norm = (x) => (x || '').toString().trim().toLowerCase();

    const aliases = {
        // weight
        'g': 'g', 'gram': 'g', 'grams': 'g', 'جرام': 'g',
        'kg': 'kg', 'kilogram': 'kg', 'kilograms': 'kg', 'كيلوجرام': 'kg',

        // volume
        'ml': 'ml', 'milliliter': 'ml', 'millilitre': 'ml', 'مليلتر': 'ml',
        'l': 'l', 'liter': 'l', 'litre': 'l', 'لتر': 'l'
    };

    const f = aliases[norm(from_uom)] || norm(from_uom);
    const t = aliases[norm(to_uom)] || norm(to_uom);

    if (f === t) return 1;

    // gram ⇄ milliliter
    if (f === 'g' && t === 'ml') return 1;
    if (f === 'ml' && t === 'g') return 1;

    // kilogram ⇄ liter
    if (f === 'kg' && t === 'l') return 1;
    if (f === 'l' && t === 'kg') return 1;

    // gram ⇄ liter
    if (f === 'g' && t === 'l') return 1 / 1000;
    if (f === 'l' && t === 'g') return 1000;

    // kilogram ⇄ milliliter
    if (f === 'kg' && t === 'ml') return 1000;
    if (f === 'ml' && t === 'kg') return 1 / 1000;

    // gram ⇄ kilogram
    if (f === 'g' && t === 'kg') return 1 / 1000;
    if (f === 'kg' && t === 'g') return 1000;

    return 1;
}

