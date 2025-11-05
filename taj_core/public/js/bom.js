frappe.ui.form.on('BOM', {
    refresh: function(frm) {
        if (frm.is_new()) {
            // إضافة زر جلب البيانات من Product Proposal
            frm.add_custom_button(__('Fetch from Product Proposal'), function() {
                simpleFetchFromProductProposal(frm);
            });
        }
    }
});

function simpleFetchFromProductProposal(frm) {
    // طلب من المستخدم إدخال اسم Product Proposal يدوياً
    frappe.prompt([
        {
            fieldname: 'pp_name',
            label: __('Product Proposal Name'),
            fieldtype: 'Link',
            options: 'Product Proposal',
            reqd: 1,
            get_query: function() {
                return {
                    filters: {
                        item_code: frm.doc.item,
                        docstatus: 1
                    }
                };
            }
        }
    ], function(values) {
        // جلب بيانات Product Proposal المحدد
        frappe.call({
            method: 'frappe.client.get',
            args: {
                doctype: 'Product Proposal',
                name: values.pp_name
            },
            callback: function(r) {
                if (r.message) {
                    // التحقق من صحة البيانات قبل المعالجة
                    if (validatePPItems(r.message.pp_items)) {
                        processProductProposalData(frm, r.message);
                    } else {
                        frappe.msgprint({
                            title: __('Invalid Data'),
                            message: __('Product Proposal contains items without valid Item Code. Please fix the Product Proposal before fetching data.'),
                            indicator: 'red'
                        });
                    }
                } else {
                    frappe.msgprint(__('Error loading Product Proposal'));
                }
            },
            error: function(r) {
                showPermissionError();
            }
        });
    }, __('Enter Product Proposal Name'), __('Fetch Data'));
}

// دالة للتحقق من صحة عناصر Product Proposal
function validatePPItems(pp_items) {
    if (!pp_items || pp_items.length === 0) {
        frappe.msgprint({
            title: __('No Items'),
            message: __('Product Proposal does not contain any items.'),
            indicator: 'orange'
        });
        return false;
    }
    
    let invalidItems = [];
    
    for (let i = 0; i < pp_items.length; i++) {
        let pp_item = pp_items[i];
        
        // التحقق من وجود item_code صالح
        if (!pp_item.item_code || pp_item.item_code.trim() === '' || pp_item.item_code === pp_item.item_name) {
            invalidItems.push({
                index: i + 1,
                item_name: pp_item.item_name || 'Unnamed Item',
                item_code: pp_item.item_code || 'Empty'
            });
        }
    }
    
    if (invalidItems.length > 0) {
        // عرض تفاصيل العناصر غير الصالحة
        let errorMessage = __('The following items have invalid Item Code:');
        errorMessage += '<ul>';
        
        invalidItems.forEach(invalidItem => {
            errorMessage += `<li>Row ${invalidItem.index}: "${invalidItem.item_name}" (Item Code: "${invalidItem.item_code}")</li>`;
        });
        
        errorMessage += '</ul>';
        errorMessage += __('Please fix these items in the Product Proposal before fetching data.');
        
        frappe.msgprint({
            title: __('Invalid Items Found'),
            message: errorMessage,
            indicator: 'red'
        });
        
        return false;
    }
    
    return true;
}

async function processProductProposalData(frm, pp_doc) {
    try {
        let ratio = frm.doc.quantity / pp_doc.quantity;
        
        // تفريغ جدول items الحالي
        frm.clear_table('items');
        
        // التحقق النهائي من صحة البيانات قبل البدء في المعالجة
        if (!validatePPItems(pp_doc.pp_items)) {
            return;
        }
        
        // معالجة جميع العناصر بالترتيب باستخدام async/await
        for (let i = 0; i < pp_doc.pp_items.length; i++) {
            let pp_item = pp_doc.pp_items[i];
            
            // تحقق إضافي لكل عنصر (للأمان)
            if (!pp_item.item_code || pp_item.item_code.trim() === '') {
                frappe.msgprint({
                    title: __('Processing Error'),
                    message: __('Skipping item without valid Item Code at row {0}', [i + 1]),
                    indicator: 'orange'
                });
                continue; // تخطي هذا العنصر والمتابعة للعنصر التالي
            }
            
            await processItemWithConversion(frm, pp_item, ratio, i, pp_doc.quantity);
        }

        frm.refresh_field('items');
        frappe.show_alert({
            message: __('Data fetched from {0} with original order preserved', [pp_doc.name]),
            indicator: 'green'
        });
        
    } catch (error) {
        console.error('Error processing data:', error);
        frappe.msgprint(__('Error processing data: {0}', [error.message]));
    }
}

function processItemWithConversion(frm, pp_item, ratio, index, pp_quantity) {
    return new Promise((resolve) => {
        let item_code = pp_item.item_code;
        let uom = pp_item.uom;
        let final_qty = pp_item.qty * ratio;
        let conversion_rate = 1;
        let original_uom = pp_item.uom;
        let target_uom = pp_item.uom;
        
        // التحقق إذا كانت كمية BOM أصغر أو تساوي كمية Product Proposal
        const shouldConvertUnits = frm.doc.quantity > pp_quantity;
        
        // إذا كان هناك pre_bom، نحاول جلب البيانات من BOM
        if (pp_item.pre_bom) {
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
                        if (r.message.uom && shouldConvertUnits) {
                            target_uom = r.message.uom;
                            // الحصول على معدل التحويل بين الوحدات
                            conversion_rate = getConversionRate(pp_item.uom, target_uom);
                            final_qty = pp_item.qty * conversion_rate * ratio;
                            uom = target_uom;
                        }
                    }
                    addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                    resolve();
                },
                error: function(r) {
                    addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                    resolve();
                }
            });
        } else {
            // محاولة جلب الوحدة الأساسية من Item فقط إذا كانت كمية BOM أكبر
            if (shouldConvertUnits) {
                frappe.call({
                    method: 'frappe.client.get_value',
                    args: {
                        doctype: 'Item',
                        filters: { name: item_code },
                        fieldname: ['stock_uom']
                    },
                    callback: function(r) {
                        if (r.message && r.message.stock_uom && r.message.stock_uom !== uom) {
                            target_uom = r.message.stock_uom;
                            // الحصول على معدل التحويل بين الوحدات
                            conversion_rate = getConversionRate(pp_item.uom, target_uom);
                            final_qty = pp_item.qty * conversion_rate * ratio;
                            uom = target_uom;
                        }
                        addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                        resolve();
                    },
                    error: function(r) {
                        // في حالة الخطأ، نستخدم البيانات الأصلية
                        addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                        resolve();
                    }
                });
            } else {
                // إذا كانت كمية BOM صغيرة، نستخدم البيانات الأصلية بدون تحويل
                addBOMItemWithConversion(frm, pp_item, item_code, uom, final_qty, original_uom, conversion_rate, target_uom, index, shouldConvertUnits);
                resolve();
            }
        }
    });
}

// باقي الدوال تبقى كما هي (getConversionRate, addBOMItemWithConversion, showPermissionError)
// ... [الكود السابق لنفس الدوال]

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