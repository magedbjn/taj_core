// ===== BOM Client Script =====
// الوصف: 
//   سكريبت لجلب بيانات الأصناف من وثيقة "Product Proposal" إلى وثيقة "BOM"
//   مع الحفاظ على الترتيب الأصلي للأصناف وإجراء تحويلات الوحدات تلقائياً

// المميزات:
//   - جلب الأصناف من Product Proposal بالترتيب الأصلي
//   - التحقق من صلاحية الأصناف (وجود Item Code حقيقي)
//   - تحويل الوحدات تلقائياً (خصوصاً g <-> kg) حسب UOM الصنف في BOM أو Item
//   - إعادة حساب الكميات عند تغيير bom.quantity: new = (pp_item.qty / pp_doc.quantity) * bom.quantity
//   - تخزين بيانات مرجعية مؤقتة في الواجهة (frm._pp_cache) لضمان إعادة الحسابات

// ===== أحداث النموذج =====
frappe.ui.form.on('BOM', {
    // حدث التحميل: إضافة زر الجلب عند إنشاء وثيقة جديدة
    refresh: function(frm) {
        if (frm.is_new()) {
            frm.add_custom_button(__('Fetch from Product Proposal'), function() {
                simpleFetchFromProductProposal(frm);
            });
        }
        // حضّر دالة refetch مهدّأة
        frm._debounced_refetch = debounce(() => {
            if (frm._pp_cache && frm._pp_cache.source_pp) {
                refetchFromProductProposal(frm, frm._pp_cache.source_pp);
            }
        }, 350);
    },

    // حدث تغيير الكمية: إعادة الجلب التلقائي عند تعديل الكمية
    // quantity: function(frm) {
    //     // استخدام الدالة المهدأة لمنع الطلبات المتكررة
    //     if (frm._debounced_refetch) {
    //         frm._debounced_refetch();
    //     } else if (frm._pp_cache && frm._pp_cache.source_pp) {
    //         // إذا لم تكن الدالة المهدأة متاحة، استخدم الاستدعاء المباشر
    //         refetchFromProductProposal(frm, frm._pp_cache.source_pp);
    //     }
    //     // لا تفتح prompt تلقائياً - دع المستخدم يضغط الزر يدوياً للمرة الأولى
    // }
});

// ===== الدوال الرئيسية =====
// --- helper: debounce ---
function debounce(fn, wait) {
    let t;
    return function(...args) {
        clearTimeout(t);
        t = setTimeout(() => fn.apply(this, args), wait);
    };
}

/**
 * جلب البيانات من Product Proposal مع فتح نافذة اختيار
 * @param {Object} frm - كائن النموذج الحالي
 */
function simpleFetchFromProductProposal(frm) {
    // فتح نافذة إدخال اسم Product Proposal
    frappe.prompt([
        {
            fieldname: 'pp_name',
            label: __('Product Proposal Name'),
            fieldtype: 'Link',
            options: 'Product Proposal',
            reqd: 1,
            get_query: function() {
                // تصفية الـ Product Proposal حسب الصنف الرئيسي في BOM والحالة المؤكدة
                return {
                    filters: {
                        item_code: frm.doc.item,
                        docstatus: 1
                    }
                };
            }
        }
    ], function(values) {
        // حفظ اسم الـ PP للاستخدام لاحقاً
        if (!frm._pp_cache) frm._pp_cache = {};
        frm._pp_cache.source_pp = values.pp_name;

        // إظهار شريط التقدم
        frappe.show_progress(__('Fetching Data'), 10, 100, __('Loading Product Proposal...'));

        // جلب بيانات الـ Product Proposal من الخادم
        frappe.call({
            method: 'frappe.client.get',
            args: { doctype: 'Product Proposal', name: values.pp_name },
            callback: function(r) {
                if (r.message) {
                    // التحقق من صلاحية الأصناف قبل المعالجة
                    if (validatePPItems(r.message.pp_items)) {
                        // حفظ الكمية الأساسية للـ PP
                        frm._pp_cache.pp_doc_quantity = r.message.quantity;
                        if (!frm._pp_cache.row_lookup) frm._pp_cache.row_lookup = {};
                        
                        // تحديث شريط التقدم
                        frappe.show_progress(__('Fetching Data'), 50, 100, __('Processing items...'));
                        
                        // معالجة البيانات
                        processProductProposalData(frm, r.message);
                    } else {
                        // إخفاء شريط التقدم في حالة الخطأ
                        frappe.hide_progress();
                        // عرض رسالة خطأ إذا كانت الأصناف غير صالحة
                        frappe.msgprint({
                            title: __('Invalid Data'),
                            message: __('Product Proposal contains items without valid Item Code. Please fix the Product Proposal before fetching data.'),
                            indicator: 'red'
                        });
                    }
                } else {
                    frappe.hide_progress();
                    frappe.msgprint(__('Error loading Product Proposal'));
                }
            },
            error: function() { 
                frappe.hide_progress();
                showPermissionError(); 
            }
        });
    }, __('Enter Product Proposal Name'), __('Fetch Data'));
}

/**
 * إعادة جلب البيانات تلقائياً عند تغيير الكمية
 * @param {Object} frm - كائن النموذج الحالي
 * @param {string} pp_name - اسم وثيقة Product Proposal
 */
function refetchFromProductProposal(frm, pp_name) {
    // منع إعادة التنفيذ المتكرر لتجنب الحلقات
    if (frm._pp_is_refreshing) return;
    frm._pp_is_refreshing = true;

    // إظهار شريط التقدم
    frappe.show_progress(__('Refreshing'), 10, 100, __('Updating quantities...'));

    frappe.call({
        method: 'frappe.client.get',
        args: { doctype: 'Product Proposal', name: pp_name },
        callback: function(r) {
            try {
                if (r.message) {
                    // تحديث شريط التقدم
                    frappe.show_progress(__('Refreshing'), 50, 100, __('Processing items...'));

                    // معالجة البيانات مع تطبيق نفس المنطق
                    processProductProposalData(frm, r.message);
                    
                    // تحديث كمية الـ PP الأساسية في الكاش
                    if (!frm._pp_cache) frm._pp_cache = {};
                    frm._pp_cache.pp_doc_quantity = r.message.quantity;
                } else {
                    frappe.msgprint(__('Error loading Product Proposal'));
                }
            } finally {
                frm._pp_is_refreshing = false;
                // إخفاء شريط التقدم بعد الانتهاء
                setTimeout(() => frappe.hide_progress(), 500);
            }
        },
        error: function() {
            frm._pp_is_refreshing = false;
            // إخفاء شريط التقدم في حالة الخطأ
            frappe.hide_progress();
            showPermissionError();
        }
    });
}

/**
 * التحقق من صلاحية أصناف الـ Product Proposal
 * @param {Array} pp_items - مصفوفة أصناف الـ Product Proposal
 * @returns {boolean} - true إذا كانت جميع الأصناف صالحة
 */
function validatePPItems(pp_items) {
    // التحقق من وجود أصناف
    if (!pp_items || pp_items.length === 0) {
        frappe.msgprint({
            title: __('No Items'),
            message: __('Product Proposal does not contain any items.'),
            indicator: 'orange'
        });
        return false;
    }

    // البحث عن الأصناف غير الصالحة
    let invalidItems = [];
    for (let i = 0; i < pp_items.length; i++) {
        const pp_item = pp_items[i];
        // الصنف غير صالح إذا كان item_code فارغاً أو يساوي item_name
        if (!pp_item.item_code || pp_item.item_code.trim() === '' || pp_item.item_code === pp_item.item_name) {
            invalidItems.push({
                index: i + 1,
                item_name: pp_item.item_name || 'Unnamed Item',
                item_code: pp_item.item_code || 'Empty'
            });
        }
    }

    // إذا وجدت أصناف غير صالحة، عرض رسالة الخطأ
    if (invalidItems.length > 0) {
        let errorMessage = __('The following items have invalid Item Code:') + '<ul>';
        invalidItems.forEach(invalidItem => {
            errorMessage += `<li>Row ${invalidItem.index}: "${invalidItem.item_name}" (Item Code: "${invalidItem.item_code}")</li>`;
        });
        errorMessage += '</ul>' + __('Please fix these items in the Product Proposal before fetching data.');

        frappe.msgprint({
            title: __('Invalid Items Found'),
            message: errorMessage,
            indicator: 'red'
        });
        return false;
    }
    return true;
}

/**
 * معالجة بيانات الـ Product Proposal وتحويلها إلى BOM items
 * @param {Object} frm - كائن النموذج الحالي
 * @param {Object} pp_doc - وثيقة الـ Product Proposal
 */
async function processProductProposalData(frm, pp_doc) {
    try {
        // حساب نسبة التحويل بين كميتي BOM و PP
        const bom_qty = flt(frm.doc.quantity);
        const pp_qty  = flt(pp_doc.quantity || 1);
        // إذا كانت كمية BOM أكبر من كمية PP، استخدم النسبة، وإلا استخدم 1
        const ratio = (bom_qty > pp_qty) ? (bom_qty / pp_qty) : 1;

        // مسح الجدول الحالي للأصناف
        frm.clear_table('items');

        // التحقق من الأصناف قبل المعالجة
        if (!validatePPItems(pp_doc.pp_items)) {
            frappe.hide_progress();
            return;
        }

        const totalItems = pp_doc.pp_items.length;
        
        // معالجة كل صنف في الـ Product Proposal
        for (let i = 0; i < totalItems; i++) {
            const pp_item = pp_doc.pp_items[i];
            
            // تحديث شريط التقدم
            const progress = 50 + Math.floor((i / totalItems) * 40);
            frappe.show_progress(__('Processing'), progress, 100, 
                __('Processing item {0} of {1}', [i + 1, totalItems]));
            
            // تخطي الأصناف بدون item_code صالح
            if (!pp_item.item_code || pp_item.item_code.trim() === '') {
                frappe.msgprint({
                    title: __('Processing Error'),
                    message: __('Skipping item without valid Item Code at row {0}', [i + 1]),
                    indicator: 'orange'
                });
                continue;
            }
            
            // معالجة الصنف مع تحويل الوحدات
            await processItemWithConversion(frm, pp_item, ratio, i, pp_doc.quantity);
        }

        // تحديث واجهة الجدول
        frm.refresh_field('items');

        // تحديث البيانات المرجعية في الكاش
        if (!frm._pp_cache) frm._pp_cache = {};
        if (!frm._pp_cache.row_lookup) frm._pp_cache.row_lookup = {};
        frm._pp_cache.pp_doc_quantity = pp_doc.quantity;
        
        // حفظ بيانات كل صف للاستخدام في إعادة الحساب
        (frm.doc.items || []).forEach(row => {
            const key = `${row.item_code}::${row.idx}`;
            frm._pp_cache.row_lookup[key] = {
                pp_qty: row.__pp_qty,   // الكمية الأصلية من PP
                pp_uom: row.__pp_uom    // الوحدة الأصلية من PP
            };
        });

        // إكمال شريط التقدم
        frappe.show_progress(__('Complete'), 100, 100, __('Finalizing...'));

        // عرض رسالة نجاح
        frappe.show_alert({
            message: __('Data fetched from {0} with original order preserved', [pp_doc.name]),
            indicator: 'green'
        });

        // إخفاء شريط التقدم بعد تأخير بسيط
        setTimeout(() => frappe.hide_progress(), 1000);

    } catch (error) {
        console.error('Error processing data:', error);
        frappe.hide_progress();
        frappe.msgprint(__('Error processing data: {0}', [error.message]));
    }
}

/**
 * معالجة صنف مع تحويل الوحدات إذا لزم الأمر
 * @param {Object} frm - كائن النموذج الحالي
 * @param {Object} pp_item - بيانات الصنف من الـ PP
 * @param {number} ratio - نسبة التحويل بين BOM و PP
 * @param {number} index - الفهرس الحالي للصنف
 * @param {number} pp_quantity - الكمية الأساسية للـ PP
 * @returns {Promise} - وعد بإكمال المعالجة
 */
function processItemWithConversion(frm, pp_item, ratio, index, pp_quantity) {
    return new Promise((resolve) => {
        let item_code = pp_item.item_code;
        let uom = pp_item.uom; // الوحدة الأصلية من الـ PP
        let final_qty = flt(pp_item.qty) * ratio;
        let original_uom = pp_item.uom;
        let target_uom = pp_item.uom;
        let conversion_rate = 1;

        // تحديد إذا كان يجب تحويل الوحدات (فقط إذا كانت كمية BOM أكبر من PP)
        const shouldConvertUnits = flt(frm.doc.quantity) > flt(pp_quantity);

        // إذا كان الصنف مرتبطاً بـ BOM سابقة
        if (pp_item.pre_bom) {
            // جلب بيانات الـ BOM السابقة لتحديد الوحدة المستهدفة
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'BOM',
                    filters: { name: pp_item.pre_bom },
                    fieldname: ['item', 'uom']
                },
                callback: function(r) {
                    if (r.message) {
                        if (r.message.item) item_code = r.message.item;
                        // إذا كان يجب التحويل، استخدم وحدة الـ BOM السابقة
                        if (r.message.uom && shouldConvertUnits) {
                            target_uom = r.message.uom;
                            conversion_rate = getConversionRate(original_uom, target_uom, item_code);
                            final_qty = flt(pp_item.qty) * conversion_rate * ratio;
                            uom = target_uom;
                        }
                    }
                    // إضافة الصنف إلى الجدول
                    addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                    resolve();
                },
                error: function() {
                    // في حالة الخطأ، إضافة الصنف بدون تحويل
                    addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                    resolve();
                }
            });
        } else {
            // إذا لم يكن مرتبطاً بـ BOM سابقة
            if (shouldConvertUnits) {
                // جلب وحدة التخزين الافتراضية للصنف
                frappe.call({
                    method: 'frappe.client.get_value',
                    args: {
                        doctype: 'Item',
                        filters: { name: item_code },
                        fieldname: ['stock_uom']
                    },
                    callback: function(r) {
                        if (r.message && r.message.stock_uom) {
                            target_uom = r.message.stock_uom;
                            // إذا اختلفت الوحدة، حساب معدل التحويل
                            if (target_uom && target_uom !== uom) {
                                const rate = getConversionRate(original_uom, target_uom, item_code);
                                if (rate > 0) {
                                    conversion_rate = rate;
                                    final_qty = flt(pp_item.qty) * conversion_rate * ratio;
                                    uom = target_uom;
                                }
                            }
                        }
                        addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                        resolve();
                    },
                    error: function() {
                        addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                        resolve();
                    }
                });
            } else {
                // إذا لم يكن يجب تحويل الوحدات، أضف الصنف كما هو
                addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                resolve();
            }
        }
    });
}

/**
 * إضافة صنف إلى جدول BOM items مع حفظ البيانات المرجعية
 * @param {Object} frm - كائن النموذج الحالي
 * @param {Object} pp_item - بيانات الصنف من الـ PP
 * @param {string} item_code - كود الصنف النهائي
 * @param {string} uom - الوحدة النهائية
 * @param {number} final_qty - الكمية النهائية
 * @param {string} original_uom - الوحدة الأصلية من الـ PP
 * @param {number} conversion_rate - معدل التحويل
 * @param {string} target_uom - الوحدة المستهدفة
 * @param {number} index - الفهرس الحالي
 * @param {boolean} did_convert - هل تم تحويل الوحدات
 */
function addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, did_convert) {
    // إضافة صف جديد إلى الجدول
    const row = frm.add_child('items');

    // مهم: استخدم set_value عشان يشغّل سكربتات ERPNext الافتراضية لحقل item_code
    frappe.model.set_value(row.doctype, row.name, 'item_code', item_code).then(() => {
        // بعد ما يخلّص جلب بيانات الصنف نضبط باقي الحقول الأساسية
        frappe.model.set_value(row.doctype, row.name, 'qty', flt(final_qty));
        frappe.model.set_value(row.doctype, row.name, 'uom', uom);
        frappe.model.set_value(row.doctype, row.name, 'stock_uom', uom);
        frappe.model.set_value(row.doctype, row.name, 'description', pp_item.item_name || row.description);

        // ✅ نسخ الحقول المخصصة من PP Item إلى BOM Item
        // BOM Item taj.procees_type = PP Item procees_type
        frappe.model.set_value(row.doctype, row.name, 'taj_procees_type', pp_item.procees_type || null);

        // BOM Item taj.cooking_type = PP Item cooking_type
        frappe.model.set_value(row.doctype, row.name, 'taj_cooking_type', pp_item.cooking_type || null);

        // BOM Item taj.temperature = PP Item temperature
        frappe.model.set_value(row.doctype, row.name, 'taj_temperature', pp_item.temperature || null);

        // BOM Item taj.duration = PP Item duration
        frappe.model.set_value(row.doctype, row.name, 'taj_duration', pp_item.duration || null);

        // BOM Item taj.notes = PP Item notes
        frappe.model.set_value(row.doctype, row.name, 'taj_notes', pp_item.notes || null);

        // لو بعد كل شي الـ rate ما تعبّى (وهو mandatory)، حطّ 0 كقيمة افتراضية
        const current_rate = row.rate;
        if (!current_rate && current_rate !== 0) {
            frappe.model.set_value(row.doctype, row.name, 'rate', 0);
        }

        // حفظ البيانات المرجعية للجلسة (تبقى مثل ما هي)
        row.__pp_qty = flt(pp_item.qty || 0);     // الكمية الأصلية للـ PP
        row.__pp_uom = original_uom || uom;       // UOM الأصلية للـ PP
        row.__pp_index = index + 1;               // الفهرس الأصلي
        row.__converted_to = target_uom;          // الوحدة المحول إليها
        row.__conversion_rate = conversion_rate;  // معدل التحويل
        row.__did_convert = !!did_convert;        // هل تم التحويل

        // تحديث الجدول في الواجهة
        frm.refresh_field('items');
    });
}


/**
 * حساب معدل التحويل بين الوحدات
 * @param {string} from_uom - الوحدة المصدر
 * @param {string} to_uom - الوحدة المستهدفة
 * @param {string} item_code - كود الصنف (غير مستخدم حالياً)
 * @returns {number} - معدل التحويل
 */
function getConversionRate(from_uom, to_uom, item_code) {
    // تطبيع أسماء الوحدات (تحويل إلى أحرف صغيرة وإزالة المسافات)
    const norm = (x) => (x || '').toString().trim().toLowerCase();

    // قاموس المرادفات للوحدات - تمت إضافة مرادفات اللتر
    const aliases = {
        'g': 'g', 'gram': 'g', 'grams': 'g', 'جرام': 'g',
        'kg': 'kg', 'kilogram': 'kg', 'kilograms': 'kg', 'كيلوجرام': 'kg',
        'mg': 'mg', 'milligram': 'mg', 'milligrams': 'mg',
        'l': 'l', 'litre': 'l', 'liter': 'l', 'لتر': 'l', 'liters': 'l', 'litres': 'l',
        'unit': 'unit', 'pcs': 'unit', 'piece': 'unit', 'each': 'unit'
    };

    // الحصول على الأسماء المعيارية للوحدات
    const f = aliases[norm(from_uom)] || norm(from_uom);
    const t = aliases[norm(to_uom)] || norm(to_uom);

    // التحويلات القياسية الشائعة - تمت إضافة تحويلات اللتر
    if (f === t) return 1;
    
    // تحويلات الجرام
    if (f === 'g' && t === 'kg') return 1 / 1000.0;
    if (f === 'kg' && t === 'g') return 1000.0;
    if (f === 'mg' && t === 'g') return 1 / 1000.0;
    if (f === 'g' && t === 'mg') return 1000.0;
    if (f === 'mg' && t === 'kg') return 1 / 1_000_000.0;
    if (f === 'kg' && t === 'mg') return 1_000_000.0;
    
    // تحويلات اللتر مع افتراض أن 1 لتر = 1 كجم = 1000 جرام
    if (f === 'l' && t === 'kg') return 1.0;           // 1 لتر = 1 كجم
    if (f === 'kg' && t === 'l') return 1.0;           // 1 كجم = 1 لتر
    if (f === 'l' && t === 'g') return 1000.0;         // 1 لتر = 1000 جرام
    if (f === 'g' && t === 'l') return 1 / 1000.0;     // 1 جرام = 0.001 لتر
    if (f === 'l' && t === 'mg') return 1_000_000.0;   // 1 لتر = 1,000,000 مليجرام
    if (f === 'mg' && t === 'l') return 1 / 1_000_000.0; // 1 مليجرام = 0.000001 لتر

    // إذا لم يتم التعرف على التحويل، ارجع 1 كقيمة افتراضية
    return 1;
}

/**
 * عرض رسالة خطأ في الصلاحيات
 */
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

// ===== دوال مساعدة =====

/**
 * تحويل القيمة إلى رقم عشري
 * @param {any} n - القيمة المدخلة
 * @returns {number} - القيمة الرقمية
 */
function flt(n) {
    const x = parseFloat(n);
    return isNaN(x) ? 0 : x;
}