import frappe
from jinja2 import Environment, FileSystemLoader
from frappe.utils import nowdate
from frappe import _
from datetime import datetime, timedelta
import os

@frappe.whitelist()
def open_production_stickers(plan_name):
    """
    Generate HTML stickers for a Production Plan and save as File Doctype.
    """
    if not plan_name:
        frappe.throw(_("Production Plan name is required"))

    # استعلام SQL للبيانات
    data = frappe.db.sql("""
        SELECT 
            poi.item_code AS assembly_item_code,
            poi.description AS assembly_item_name,
            poi.bom_no AS assembly_bom_no,
            poi.planned_qty AS assembly_qty,
            poi.stock_uom AS assembly_uom,

            bi.item_code AS sub_assembly_item_code,
            bi.item_name AS sub_assembly_item_name,
            bi.operation AS sub_assembly_operation,
            bi.qty AS sub_assembly_qty,
            bi.uom AS sub_assembly_uom,

            bo.batch_size AS sub_assembly_batch_size,
            b.quantity AS bom_qty,

            CASE
                WHEN bi.operation IS NULL OR bi.operation = '' THEN NULL
                WHEN bo.batch_size = 1 THEN 1
                ELSE CEIL(poi.planned_qty / NULLIF(bo.batch_size, 0))
            END AS cooking_runs

        FROM `tabProduction Plan Item` poi
        LEFT JOIN `tabBOM Item` bi
            ON bi.parent = poi.bom_no
        LEFT JOIN `tabBOM Operation` bo
            ON bo.parent = poi.bom_no
            AND bo.operation <=> bi.operation
        LEFT JOIN `tabBOM` b
            ON b.name = poi.bom_no
        WHERE poi.parent = %s
        ORDER BY poi.item_code, bi.item_code
    """, (plan_name,), as_dict=True)  # ✅ تمرير tuple

    # تجهيز الاستكرات
    stickers = []
    for row in data:
        remaining_qty = row.assembly_qty
        batch_size = row.sub_assembly_batch_size or 0
        bom_qty = row.bom_qty
        runs = int(row.cooking_runs) if row.cooking_runs else 1

        for run in range(runs):
            if batch_size <= 1 or batch_size == bom_qty:
                qty = (row.sub_assembly_qty / bom_qty) * min(remaining_qty, bom_qty)
            else:
                qty = (row.sub_assembly_qty / bom_qty) * min(remaining_qty, batch_size)

            stickers.append({
                "assembly_item_code": row.assembly_item_code,
                "assembly_item_name": row.assembly_item_name,
                "sub_assembly_item_code": row.sub_assembly_item_code,
                "sub_assembly_item_name": row.sub_assembly_item_name,
                "sub_assembly_operation": row.sub_assembly_operation,
                "cooking_run": run + 1,
                "cooking_runs": runs,
                "qty": round(qty, 2),
                "assembly_qty": row.assembly_qty,
                "assembly_uom": row.assembly_uom
            })
            remaining_qty -= batch_size

    # تحميل القالب
    base_path = os.path.dirname(__file__)
    env = Environment(loader=FileSystemLoader(os.path.join(base_path, 'templates')))
    template = env.get_template('production_stickers.html')
    html_content = template.render(
        stickers=stickers,
        plan_name=plan_name,
        today=nowdate(),
        stickers_count=len(stickers)
    )

    # حفظ الملف باستخدام File Doctype
    file_name = f"{plan_name}_stickers.html"
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "is_private": 0,
        "content": html_content,
        "attached_to_doctype": "Production Plan",
        "attached_to_name": plan_name
    }).insert(ignore_permissions=True)

    return file_doc.file_url  # مثال: /files/MFG-PP-23-00002_stickers.html