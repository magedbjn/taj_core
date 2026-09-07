// ===== BOM Client Script (Optimized) =====
// الهدف:
// - Fetch من Product Proposal إلى BOM (كل الأصناف) مع الحفاظ على الترتيب
// - تسريع الأداء عبر Batch Fetch (بدون استعلام لكل صف)
// - تحويل الوحدات باستخدام إعدادات ERPNext الفعلية فقط
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
      if (frm.doc.docstatus !== 0) return;

      const hasTrialSource = Boolean(
        frm.doc.taj_product_proposal &&
        frm.doc.taj_product_proposal_trial
      );

      frm.add_custom_button(
        hasTrialSource
          ? __('Refresh from Trial')
          : __('Fetch from Product Proposal'),
        () => simpleFetchFromProductProposal(frm),
        __('Trial Source')
      );
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
  frm.set_value("taj_total_under_weight", total_under);
  frm.set_value("taj_total_over_weight", total_over);
}

// -------------------------------
// 3) Helpers
// -------------------------------
function flt(n) {
  const x = parseFloat(n);
  return isNaN(x) ? 0 : x;
}

function confirmReplaceBOMItems(frm) {
  if (!(frm.doc.items || []).length) {
    return Promise.resolve(true);
  }

  return new Promise(resolve => {
    frappe.confirm(
      __(
        'Fetching the Trial will replace the current BOM Items. Continue?'
      ),
      () => resolve(true),
      () => resolve(false)
    );
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

async function fetchUomConversionFactors(conversions) {
  if (!conversions.length) return {};

  const r = await frappe.call({
    method:
      'taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial.get_bom_uom_conversion_factors',
    args: {
      conversions: JSON.stringify(conversions)
    }
  });

  const out = {};
  (r.message || []).forEach(row => {
    out[row.key] = row;
  });
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
function simpleFetchFromProductProposal(frm) {
  const pp_name =
    frm.doc.taj_product_proposal ||
    frm._pp_cache?.source_pp;

  const trial_name =
    frm.doc.taj_product_proposal_trial ||
    frm._pp_cache?.source_trial;

  if (pp_name && trial_name) {
    refetchFromProductProposal(
      frm,
      pp_name,
      trial_name
    );
    return;
  }

  open_pp_dialog_and_fetch(frm);
}

async function fetchTrialSnapshotForBOM(
  pp_name,
  trial_name = null
) {
  const r = await frappe.call({
    method:
      'taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial.get_bom_trial_snapshot',
    args: {
      product_proposal: pp_name,
      trial_name: trial_name || null
    }
  });

  if (!r.message) {
    throw new Error(
      __('Unable to load Product Proposal Trial')
    );
  }

  return r.message;
}

function open_pp_dialog_and_fetch(frm) {
  const d = new frappe.ui.Dialog({
    title: __('Fetch Approved Final Trial'),
    fields: [
      {
        fieldname: 'pp_name',
        label: __('Product Proposal'),
        fieldtype: 'Link',
        options: 'Product Proposal',
        reqd: 1,
        default:
          frm.doc.taj_product_proposal || '',
        get_query() {
          return {
            filters: {
              item_code: frm.doc.item,
              docstatus: 1
            }
          };
        }
      }
    ],
    primary_action_label: __('Fetch Final Trial'),
    primary_action: async () => {
      const values = d.get_values();
      if (!values) return;

      d.get_primary_btn().prop(
        'disabled',
        true
      );

      try {
        frappe.show_progress(
          __('Fetching Data'),
          10,
          100,
          __('Loading Final Trial...')
        );

        const snapshot =
          await fetchTrialSnapshotForBOM(
            values.pp_name
          );

        if (
          !validatePPItems(snapshot.items)
        ) {
          frappe.hide_progress();
          d.get_primary_btn().prop(
            'disabled',
            false
          );
          return;
        }

        if (!(await confirmReplaceBOMItems(frm))) {
          frappe.hide_progress();
          d.get_primary_btn().prop(
            'disabled',
            false
          );
          return;
        }

        const source_doc = {
          name: snapshot.trial_name,
          source_label:
            `${snapshot.product_proposal} / ` +
            `${snapshot.trial_name}`,
          quantity: snapshot.quantity,
          pp_items: snapshot.items
        };

        frappe.show_progress(
          __('Fetching Data'),
          35,
          100,
          __(
            'Preparing Trial formulation...'
          )
        );

        await processProductProposalDataOptimized(
          frm,
          source_doc
        );

        await frm.set_value(
          'taj_product_proposal',
          snapshot.product_proposal
        );

        await frm.set_value(
          'taj_product_proposal_trial',
          snapshot.trial_name
        );

        if (!frm._pp_cache) {
          frm._pp_cache = {};
        }

        frm._pp_cache.source_pp =
          snapshot.product_proposal;

        frm._pp_cache.source_trial =
          snapshot.trial_name;

        frm._pp_cache.pp_doc_quantity =
          snapshot.quantity;

        frappe.show_alert(
          {
            message: __(
              'BOM formulation loaded from Final Trial {0}',
              [snapshot.trial_name]
            ),
            indicator: 'green'
          },
          7
        );

        d.hide();

      } catch (e) {
        console.error(e);
        frappe.hide_progress();

        d.get_primary_btn().prop(
          'disabled',
          false
        );
      }
    }
  });

  d.show();
}

async function refetchFromProductProposal(
  frm,
  pp_name,
  trial_name
) {
  if (frm._pp_is_refreshing) return;

  frm._pp_is_refreshing = true;

  frappe.show_progress(
    __('Refreshing'),
    10,
    100,
    __('Reloading Trial formulation...')
  );

  try {
    const snapshot =
      await fetchTrialSnapshotForBOM(
        pp_name,
        trial_name
      );

    if (
      !validatePPItems(snapshot.items)
    ) {
      return;
    }

    if (!(await confirmReplaceBOMItems(frm))) {
      return;
    }

    const source_doc = {
      name: snapshot.trial_name,
      source_label:
        `${snapshot.product_proposal} / ` +
        `${snapshot.trial_name}`,
      quantity: snapshot.quantity,
      pp_items: snapshot.items
    };

    frappe.show_progress(
      __('Refreshing'),
      35,
      100,
      __('Preparing Trial formulation...')
    );

    await processProductProposalDataOptimized(
      frm,
      source_doc
    );

    await frm.set_value(
      'taj_product_proposal',
      snapshot.product_proposal
    );

    await frm.set_value(
      'taj_product_proposal_trial',
      snapshot.trial_name
    );

    if (!frm._pp_cache) {
      frm._pp_cache = {};
    }

    frm._pp_cache.source_pp =
      snapshot.product_proposal;

    frm._pp_cache.source_trial =
      snapshot.trial_name;

    frm._pp_cache.pp_doc_quantity =
      snapshot.quantity;

  } catch (e) {
    console.error(e);

  } finally {
    frm._pp_is_refreshing = false;

    setTimeout(
      () => frappe.hide_progress(),
      500
    );
  }
}

async function processProductProposalDataOptimized(frm, pp_doc) {
  try {
    const bom_qty = flt(frm.doc.quantity);
    const pp_qty = flt(pp_doc.quantity || 1);
    const ratio =
      (bom_qty > 0 && pp_qty > 0)
        ? (bom_qty / pp_qty)
        : 1;

    const pp_items = pp_doc.pp_items || [];
    const preBoms = pp_items
      .map(row => row.pre_bom)
      .filter(Boolean);
    const itemCodes = pp_items
      .map(row => row.item_code)
      .filter(Boolean);

    frappe.show_progress(
      __('Fetching Data'),
      45,
      100,
      __('Fetching Items/BOMs in batch...')
    );

    const [itemsMap, bomsMap] = await Promise.all([
      fetchItemsData(itemCodes),
      fetchBOMData(preBoms)
    ]);

    // Resolve the target Item/UOM first. Do not clear the BOM table until
    // every required conversion has been validated by ERPNext data.
    const preparedRows = pp_items.map((pp_item, index) => {
      const code = (pp_item.item_code || '')
        .toString()
        .trim();

      if (!code) return null;

      let resolved_item_code = code;
      const original_uom = pp_item.uom;
      let target_uom = original_uom;

      if (
        pp_item.pre_bom &&
        bomsMap[pp_item.pre_bom]
      ) {
        const sourceBom = bomsMap[pp_item.pre_bom];

        if (sourceBom.item) {
          resolved_item_code = sourceBom.item;
        }

        if (sourceBom.uom) {
          target_uom = sourceBom.uom;
        }
      } else {
        const item = itemsMap[resolved_item_code];
        if (item?.stock_uom) {
          target_uom = item.stock_uom;
        }
      }

      return {
        key: index,
        index,
        pp_item,
        resolved_item_code,
        original_uom,
        target_uom
      };
    }).filter(Boolean);

    const conversionRequests = preparedRows
      .filter(row => (
        row.original_uom &&
        row.target_uom &&
        row.original_uom !== row.target_uom
      ))
      .map(row => ({
        key: row.key,
        item_code: row.resolved_item_code,
        from_uom: row.original_uom,
        to_uom: row.target_uom
      }));

    frappe.show_progress(
      __('Fetching Data'),
      48,
      100,
      __('Validating UOM conversions...')
    );

    const conversionMap =
      await fetchUomConversionFactors(
        conversionRequests
      );

    const missingConversions = conversionRequests
      .filter(request => (
        conversionMap[request.key]?.status !== 'OK' ||
        flt(conversionMap[request.key]?.factor) <= 0
      ));

    if (missingConversions.length) {
      const rows = missingConversions
        .map(request => (
          `${request.key + 1}: ${request.item_code} ` +
          `(${request.from_uom} -> ${request.to_uom})`
        ))
        .join(', ');

      throw new Error(
        __(
          'Missing configured UOM conversion for: {0}. ' +
          'Configure the Item/UOM conversion before fetching the Trial.',
          [rows]
        )
      );
    }

    frm.clear_table('items');

    const total = preparedRows.length;

    for (let i = 0; i < total; i++) {
      const prepared = preparedRows[i];
      const pp_item = prepared.pp_item;

      const progress =
        50 + Math.floor(
          (i / Math.max(total, 1)) * 40
        );

      frappe.show_progress(
        __('Processing'),
        progress,
        100,
        __('Processing item {0} of {1}', [
          i + 1,
          total
        ])
      );

      const didConvert = Boolean(
        prepared.original_uom &&
        prepared.target_uom &&
        prepared.original_uom !==
          prepared.target_uom
      );

      const conversionRate = didConvert
        ? flt(
          conversionMap[prepared.key]?.factor
        )
        : 1;

      const finalQty =
        flt(pp_item.qty) *
        conversionRate *
        ratio;

      await addBOMItemWithConversion(
        frm,
        pp_item,
        prepared.resolved_item_code,
        prepared.target_uom ||
          prepared.original_uom,
        finalQty,
        prepared.original_uom,
        conversionRate,
        prepared.target_uom,
        prepared.index,
        didConvert
      );
    }

    frm.refresh_field('items');

    if (!frm._pp_cache) frm._pp_cache = {};
    frm._pp_cache.pp_doc_quantity = pp_doc.quantity;
    frm._pp_cache.row_lookup = {};

    (frm.doc.items || []).forEach(row => {
      const key = `${row.item_code}::${row.idx}`;
      frm._pp_cache.row_lookup[key] = {
        pp_qty: row.__pp_qty,
        pp_uom: row.__pp_uom
      };
    });

    frappe.show_progress(
      __('Complete'),
      100,
      100,
      __('Finalizing...')
    );
    frappe.show_alert({
      message: __('Data fetched from {0}', [
        pp_doc.source_label || pp_doc.name
      ]),
      indicator: 'green'
    });
    setTimeout(() => frappe.hide_progress(), 700);
  } catch (error) {
    console.error(error);
    frappe.hide_progress();
    frappe.msgprint(
      __('Error processing data: {0}', [
        error.message || error
      ])
    );
    throw error;
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
  await frappe.model.set_value(row.doctype, row.name, 'taj_process_type', pp_item.procees_type || null);
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
