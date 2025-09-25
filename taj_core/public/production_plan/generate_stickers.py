import frappe
from jinja2 import Environment, FileSystemLoader
import os
from frappe.utils import nowdate
from frappe import _
from datetime import datetime, timedelta

@frappe.whitelist()
def open_production_stickers(plan_name):
    if not plan_name:
        frappe.throw(_("Production Plan name is required"))

    # استعلام SQL وتجهيز الاستكرات كما عندك
    data = frappe.db.sql(""" ... """, plan_name, as_dict=True)

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

    # حفظ الملف باستخدام File Doctype (موافق Cloud)
    file_name = f"{plan_name}_stickers.html"
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "is_private": 0,
        "content": html_content,
        "attached_to_doctype": "Production Plan",
        "attached_to_name": plan_name
    }).insert(ignore_permissions=True)

    return file_doc.file_url  # مثال: /files/MFG-PP-23-00006_stickers.html

@frappe.whitelist()
def delete_old_production_stickers():
    """
    Delete Production Plan sticker HTML files older than 30 days.
    """
    cutoff_date = datetime.now() - timedelta(days=30)
    old_files = frappe.get_all("File",
        filters={
            "attached_to_doctype": "Production Plan",
            "file_name": ["like", "%_stickers.html"],
            "creation": ["<", cutoff_date.strftime("%Y-%m-%d")]
        },
        fields=["name", "file_name"]
    )

    deleted_files = []
    for f in old_files:
        try:
            frappe.delete_doc("File", f.name, force=True)
            deleted_files.append(f.file_name)
        except Exception as e:
            frappe.log_error(f"Failed to delete {f.file_name}: {str(e)}", "delete_old_production_stickers")

    if deleted_files:
        frappe.logger().info(f"Deleted old stickers: {', '.join(deleted_files)}")
