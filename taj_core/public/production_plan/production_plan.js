// DocType: Production Plan

// -------- Helpers --------
function taj_apply_consolidation_lock(frm) {
  const hasDays = !!(frm.doc.taj_days_consolidate && String(frm.doc.taj_days_consolidate).trim() !== '');
  const hasBatchAnywhere = (frm.doc.sub_assembly_items || []).some(
    r => !!(r.taj_batch_consolidate && String(r.taj_batch_consolidate).trim() !== '')
  );

  const mustDisable = hasDays || hasBatchAnywhere;

  // غطِّ كلا الاسمين الممكنين
  const sysFields = ['combine_sub_items', 'consolidate_sub_assembly_items'];

  sysFields.forEach(fname => {
    const hasField = (frm.doc && Object.prototype.hasOwnProperty.call(frm.doc, fname)) || frm.get_field(fname);
    if (!hasField) return;

    if (mustDisable) {
      if (frm.doc[fname] !== 0) frm.set_value(fname, 0);
      frm.set_df_property(fname, 'read_only', 1);
      frm.toggle_enable(fname, false);
      frm.get_field(fname)?.$wrapper?.toggleClass('text-muted', true);
    } else {
      // إن أردتها دومًا معطّلة، احذف هذا الفرع
      frm.set_df_property(fname, 'read_only', 0);
      frm.toggle_enable(fname, true);
      frm.get_field(fname)?.$wrapper?.toggleClass('text-muted', false);
    }
  });

  // تلميح بسيط
  frm.dashboard?.clear_headline?.();
  if (mustDisable) {
    frm.dashboard?.set_headline?.(__("Global 'combine similar items' is disabled because TAJ consolidation is active."));
  }
}

// -------- Parent Doctype Events --------
// ---------------- TAJ Consolidation (Button Action) ----------------
// ---------------- TAJ Consolidation (Sequential, by schedule_date) ----------------
// ---------------- TAJ Consolidation (Days window OR Batch-only) ----------------
frappe.ui.form.on('Production Plan', {
   refresh(frm) {
    // ابقِ منطق القفل مفعّلًا عند كل تحديث
    taj_apply_consolidation_lock(frm);

    // وصف الحقل (اختياري)
    const f = frm.get_field('taj_days_consolidate');
    if (f) {
      f.df.description = __('Combine identical sub-assembly items within the selected number of days.');
      f.refresh();
    }

    // لا تُظهر الأزرار قبل حفظ المستند
    if (frm.is_new()) return;

    // Show Label
    frm.add_custom_button(
      __('Show Label'),
      function () {
        frappe.call({
          method: "taj_core.public.production_plan.generate_stickers.open_production_stickers",
          args: { plan_name: frm.doc.name },
          callback(res) {
            if (res.message) {
              const link = document.createElement('a');
              link.href = res.message;
              link.download = res.message.split('/').pop();
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
            }
          }
        });
      },
      __('Taj') // مجموعة الأزرار
    );

    // Delete Label
    frm.add_custom_button(
      __('Delete Label'),
      function () {
        frappe.confirm(
          __('Are you sure you want to delete all labels for this Production Plan?'),
          function () {
            frappe.call({
              method: "taj_core.public.production_plan.generate_stickers.delete_production_stickers",
              args: { plan_name: frm.doc.name },
              callback() {
                frappe.msgprint(__('Labels deleted successfully.'));
              }
            });
          }
        );
      },
      __('Taj') // نفس المجموعة
    );
  },
  
  taj_consolidate(frm) {
    const days_window = cint(frm.doc.taj_days_consolidate) || 0;
    const rows = (frm.doc.sub_assembly_items || []).slice();

    if (!rows.length) {
      frappe.msgprint(__('No Sub Assembly Items to consolidate.'));
      return;
    }

    const hasAnyBatch = rows.some(r => (r.taj_batch_consolidate || '').trim() !== '');

    // 0) لا أيام ولا باتش → لا يوجد ما نفعله
    if (!days_window && !hasAnyBatch) {
      frappe.msgprint(__('Choose "Days Consolidate" or set "Batch Consolidate" on rows.'));
      return;
    }

    // Helper: parse date
    const toDate = (s) => s ? frappe.datetime.str_to_obj(s) : null;

    // A) وضع "تجميع حسب الـBatch فقط" عند عدم اختيار أيام
    if (!days_window && hasAnyBatch) {
      const grouped = {};
      const keepAsIs = []; // صفوف بلا Batch تبقى كما هي

      rows.forEach(r => {
        const batch = (r.taj_batch_consolidate || '').trim();
        if (!batch) { keepAsIs.push(r); return; }

        const item = r.production_item;
        const bom  = r.bom_no || ''; // احذف من المفتاح إن لا تريد التمييز حسب BOM
        const key  = [item, bom, batch].join('||');

        if (!grouped[key]) {
          grouped[key] = { base: Object.assign({}, r), total: flt(r.qty) || 0.0, earliest: toDate(r.schedule_date) || null };
        } else {
          grouped[key].total += (flt(r.qty) || 0.0);
          const d = toDate(r.schedule_date);
          if (d && (!grouped[key].earliest || d < grouped[key].earliest)) grouped[key].earliest = d;
        }
      });

      frm.clear_table('sub_assembly_items');
      keepAsIs.forEach(r => frm.add_child('sub_assembly_items', r));

      Object.keys(grouped).forEach(k => {
        const g = grouped[k];
        const out = Object.assign({}, g.base);
        out.qty = g.total;
        out.schedule_date = g.earliest ? frappe.datetime.obj_to_str(g.earliest) : g.base.schedule_date;
        delete out.name;
        frm.add_child('sub_assembly_items', out);
      });

      frm.refresh_field('sub_assembly_items');
      frappe.show_alert({ message: __('Consolidated by batch only.'), indicator: 'green' });
      taj_apply_consolidation_lock(frm);
      return;
    }

    // B) وضع "تجميع متتابع حسب الأيام" (كما فعلنا سابقًا)
    const buckets = {};
    rows.forEach(r => {
      const item = r.production_item;
      const bom  = r.bom_no || '';
      const batch = (r.taj_batch_consolidate || '').trim();
      const key = [item, bom, batch].join('||');
      (buckets[key] ||= []).push(r);
    });

    const new_rows = [];
    const outside_noDate = [];

    Object.keys(buckets).forEach(key => {
      const list = buckets[key].slice();
      const noDate = list.filter(r => !r.schedule_date);
      noDate.forEach(r => outside_noDate.push(r));

      const dated = list.filter(r => !!r.schedule_date)
                        .sort((a,b) => toDate(a.schedule_date) - toDate(b.schedule_date));

      let anchor = null;
      let acc = null;
      const dayms = 24*60*60*1000;

      const flush = () => {
        if (!acc) return;
        const out = Object.assign({}, acc.base);
        out.qty = acc.sum;
        out.schedule_date = frappe.datetime.obj_to_str(acc.anchor);
        delete out.name;
        new_rows.push(out);
        anchor = null; acc = null;
      };

      dated.forEach(r => {
        const d = toDate(r.schedule_date);
        if (!anchor) {
          anchor = d;
          acc = { base: Object.assign({}, r), sum: flt(r.qty) || 0.0, anchor: d };
        } else {
          const diff_days = Math.floor((d - anchor)/dayms);
          if (diff_days < days_window) {
            acc.sum += (flt(r.qty) || 0.0);
          } else {
            flush();
            anchor = d;
            acc = { base: Object.assign({}, r), sum: flt(r.qty) || 0.0, anchor: d };
          }
        }
      });
      flush();
    });

    frm.clear_table('sub_assembly_items');
    outside_noDate.forEach(r => frm.add_child('sub_assembly_items', r));
    new_rows.forEach(r => frm.add_child('sub_assembly_items', r));
    frm.refresh_field('sub_assembly_items');
    frappe.show_alert({ message: __('Consolidated sequentially by days and batch.'), indicator: 'green' });
    taj_apply_consolidation_lock(frm);
  }
});


// -------- Child Table Events --------
frappe.ui.form.on('Production Plan Sub Assembly Item', {
  taj_batch_consolidate(frm, cdt, cdn) {
    taj_apply_consolidation_lock(frm);
    frm.refresh_field('sub_assembly_items');
  },
  // تغييرات أخرى قد تؤثر على المنطق
  sub_assembly_item_code(frm) { taj_apply_consolidation_lock(frm); },
  schedule_date(frm) { taj_apply_consolidation_lock(frm); }
});
