import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("Finished Product"), "fieldname": "finished_product", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Batch"), "fieldname": "finished_batch", "fieldtype": "Data", "width": 150},
        {"label": _("Raw Material"), "fieldname": "raw_material", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Raw Material Batch"), "fieldname": "raw_batch", "fieldtype": "Data", "width": 150},
        {"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
        {"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 70},
        {"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 200},
        {"label": _("Source Document Type"), "fieldname": "reference_doctype", "fieldtype": "Data", "width": 140},
        {"label": _("Source Document"), "fieldname": "reference_name", "fieldtype": "Dynamic Link", "options": "reference_doctype", "width": 220},
        {"label": _("Purchase Receipt"), "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 200}
    ]

def get_serial_batch_bundle_data(serial_and_batch_bundle):
    """جلب جميع الدفعات من Serial and Batch Bundle"""
    if not serial_and_batch_bundle:
        return []
    
    bundle_data = frappe.db.sql("""
        SELECT 
            sbe.batch_no,
            sbe.qty
        FROM `tabSerial and Batch Entry` sbe
        WHERE sbe.parent = %s
    """, (serial_and_batch_bundle), as_dict=1)
    
    return bundle_data

def get_batch_details(batch_no):
    """جلب تفاصيل الـ Batch"""
    if not batch_no:
        return {}
    
    batch_details = frappe.db.sql("""
        SELECT 
            supplier,
            reference_doctype,
            reference_name,
            expiry_date,
            manufacturing_date
        FROM `tabBatch`
        WHERE name = %s
    """, (batch_no), as_dict=1)
    
    return batch_details[0] if batch_details else {}

def get_data(filters=None):
    if not filters:
        filters = {}
    
    conditions = []
    params = {}
    
    # الفلترات الأساسية
    if filters.get("company"):
        conditions.append("ste.company = %(company)s")
        params["company"] = filters.get("company")
    
    if filters.get("finished_product"):
        conditions.append("ste_finished.item_code = %(finished_product)s")
        params["finished_product"] = filters.get("finished_product")
    
    if filters.get("finished_batch"):
        conditions.append("ste_finished.batch_no = %(finished_batch)s")
        params["finished_batch"] = filters.get("finished_batch")
    
    if filters.get("from_date"):
        conditions.append("ste.posting_date >= %(from_date)s")
        params["from_date"] = filters.get("from_date")
    
    if filters.get("to_date"):
        conditions.append("ste.posting_date <= %(to_date)s")
        params["to_date"] = filters.get("to_date")
    
    where_condition = " AND ".join(conditions) if conditions else "1=1"
    
    # استعلام لجلب البيانات الأساسية
    query = """
        SELECT 
            ste.name as stock_entry,
            ste_finished.item_code as finished_product,
            ste_finished.batch_no as finished_batch,
            ste_raw.item_code as raw_material,
            ste_raw.batch_no as direct_batch_no,
            ste_raw.serial_and_batch_bundle,
            ste_raw.qty as stock_entry_qty,
            ste_raw.uom as uom,
            pr.supplier as purchase_receipt_supplier,
            pr.name as purchase_receipt
        FROM `tabStock Entry` ste
        INNER JOIN `tabStock Entry Detail` ste_raw ON ste.name = ste_raw.parent
        INNER JOIN `tabStock Entry Detail` ste_finished ON ste.name = ste_finished.parent
        LEFT JOIN `tabBatch` batch ON ste_raw.batch_no = batch.name
        LEFT JOIN `tabPurchase Receipt Item` pri ON batch.name = pri.batch_no
        LEFT JOIN `tabPurchase Receipt` pr ON pri.parent = pr.name
        WHERE {where_condition}
            AND ste.docstatus = 1 
            AND ste.purpose = 'Manufacture'
            AND ste_raw.s_warehouse IS NOT NULL
            AND ste_finished.t_warehouse IS NOT NULL
        ORDER BY ste_finished.item_code, ste_finished.batch_no, ste_raw.item_code ASC
    """.format(where_condition=where_condition)
    
    try:
        data = frappe.db.sql(query, params, as_dict=1)
        
        # معالجة البيانات لاستخدام الكميات من Serial and Batch Bundle
        processed_data = []
        
        for row in data:
            # إذا كان هناك serial_and_batch_bundle، نستخدم الكميات منه
            if row.get('serial_and_batch_bundle'):
                bundle_entries = get_serial_batch_bundle_data(row.get('serial_and_batch_bundle'))
                
                if bundle_entries:
                    for bundle_entry in bundle_entries:
                        new_row = row.copy()
                        new_row['raw_batch'] = bundle_entry['batch_no']
                        new_row['qty'] = bundle_entry['qty']  # استخدام الكمية من الـ bundle
                        
                        # جلب تفاصيل الـ Batch
                        batch_details = get_batch_details(bundle_entry['batch_no'])
                        new_row['supplier'] = batch_details.get('supplier') or row.get('purchase_receipt_supplier')
                        new_row['reference_doctype'] = batch_details.get('reference_doctype')
                        new_row['reference_name'] = batch_details.get('reference_name')
                        
                        processed_data.append(new_row)
                else:
                    # إذا كان الـ bundle موجوداً ولكن لا توجد مدخلات
                    new_row = row.copy()
                    new_row['raw_batch'] = 'No Batch in Bundle'
                    new_row['qty'] = row.get('stock_entry_qty', 0)
                    new_row['supplier'] = row.get('purchase_receipt_supplier')
                    new_row['reference_doctype'] = ''
                    new_row['reference_name'] = ''
                    processed_data.append(new_row)
            else:
                # إذا لم يكن هناك bundle، نستخدم البيانات المباشرة من Stock Entry
                new_row = row.copy()
                new_row['raw_batch'] = row.get('direct_batch_no')
                new_row['qty'] = row.get('stock_entry_qty', 0)
                
                # جلب تفاصيل الـ Batch المباشر
                batch_details = get_batch_details(row.get('direct_batch_no'))
                new_row['supplier'] = batch_details.get('supplier') or row.get('purchase_receipt_supplier')
                new_row['reference_doctype'] = batch_details.get('reference_doctype')
                new_row['reference_name'] = batch_details.get('reference_name')
                
                processed_data.append(new_row)
        
        # بناء الهيكل المطلوب مع ترتيب raw_material
        grouped_data = []
        current_group = None
        
        # تجميع البيانات حسب المجموعة أولاً
        groups_dict = {}
        for row in processed_data:
            group_key = (
                row.get('finished_product') or '', 
                row.get('finished_batch') or ''
            )
            
            if group_key not in groups_dict:
                groups_dict[group_key] = {
                    'header': {
                        'finished_product': row.get('finished_product'),
                        'finished_batch': row.get('finished_batch')
                    },
                    'items': []
                }
            
            groups_dict[group_key]['items'].append(row)
        
        # ترتيب items داخل كل مجموعة حسب raw_material
        for group_key, group_data in groups_dict.items():
            # ترتيب المواد الخام تصاعدياً داخل المجموعة
            sorted_items = sorted(group_data['items'], key=lambda x: x.get('raw_material', ''))
            
            # إضافة الرأس الرئيسي
            if group_data['header']['finished_product']:
                grouped_data.append({
                    'finished_product': f"{group_data['header']['finished_product']}",
                    'finished_batch': group_data['header']['finished_batch'] or '',
                    'raw_material': '',
                    'raw_batch': '',
                    'qty': '',
                    'uom': '',
                    'supplier': '',
                    'reference_doctype': '',
                    'reference_name': '',
                    'purchase_receipt': '',
                    'is_group': True,
                    'indent': 0
                })
            
            # إضافة العناصر المرتبة
            for item in sorted_items:
                grouped_data.append({
                    'finished_product': '',
                    'finished_batch': '',
                    'raw_material': item['raw_material'],
                    'raw_batch': item['raw_batch'] or '',
                    'qty': item['qty'],
                    'uom': item['uom'],
                    'supplier': item['supplier'],
                    'reference_doctype': item['reference_doctype'],
                    'reference_name': item['reference_name'],
                    'purchase_receipt': item['purchase_receipt'],
                    'is_group': False,
                    'indent': 1
                })
        
        return grouped_data
        
    except Exception as e:
        frappe.log_error(f"Error in Raw Material Traceability: {str(e)}")
        frappe.msgprint(_("Error generating report. Please check error log."))
        return []