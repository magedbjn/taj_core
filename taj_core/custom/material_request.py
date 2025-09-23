import frappe
from frappe import _

@frappe.whitelist()
def collect_similar_items(docname):
    doc = frappe.get_doc("Material Request", docname)

    total_stock_qty = {}
    item_count = {}
    items_to_delete = []

    # اجمع الكميات لكل صنف واحسب مرات التكرار
    for item in doc.items:
        item_code = item.item_code
        total_stock_qty[item_code] = total_stock_qty.get(item_code, 0) + item.stock_qty
        item_count[item_code] = item_count.get(item_code, 0) + 1

        # إذا مكرر → ضيفه في قائمة الحذف (نترك فقط الأول)
        if item_count[item_code] > 1:
            items_to_delete.append(item)

    # حذف العناصر المكررة
    for item in reversed(items_to_delete):
        doc.remove(item)

    # تحديث العناصر المتبقية
    for item in doc.items:
        stock_qty = total_stock_qty.get(item.item_code, 0)
        if stock_qty:
            if item_count[item.item_code] > 1:
                # إذا الصنف مكرر → نثبت النتيجة بالـ Stock UOM
                stock_uom = frappe.db.get_value("Item", item.item_code, "stock_uom")
                item.uom = stock_uom
                item.conversion_factor = 1
                item.qty = stock_qty
                item.stock_qty = stock_qty
            else:
                # إذا غير مكرر → نتركه كما هو لكن نضمن تحديث stock_qty
                item.stock_qty = item.qty * (item.conversion_factor or 1)

    frappe.msgprint(_("Similar items were collected. Please save the document to apply changes."))
    return doc.as_dict()
