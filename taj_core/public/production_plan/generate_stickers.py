import frappe
from jinja2 import Environment, FileSystemLoader
import os
from frappe.utils import nowdate
from frappe import _
from datetime import datetime, timedelta

@frappe.whitelist()
def open_production_stickers(plan_name):
    """
    Generate HTML stickers for a Production Plan.
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
                WHEN bo.batch_size = 1 THEN 1
                ELSE CEIL(poi.planned_qty / bo.batch_size)
            END AS cooking_runs

        FROM `tabProduction Plan Item` poi
        LEFT JOIN `tabBOM Item` bi 
            ON bi.parent = poi.bom_no
        LEFT JOIN `tabBOM Operation` bo
            ON bo.parent = poi.bom_no
        AND bo.operation = bi.operation
        LEFT JOIN `tabBOM` b
            ON b.name = poi.bom_no
        WHERE poi.parent = %s
        ORDER BY poi.item_code, bi.item_code
    """, plan_name, as_dict=True)

    # تجهيز الاستكرات
    stickers = []
    for row in data:
        remaining_qty = row.assembly_qty
        batch_size = row.sub_assembly_batch_size or 0  # التعامل مع None بأمان
        if batch_size > 1: # لان الكمية سوف تكون كلها ولا يحتاج إلى لاصق أو إستكر
            for run in range(int(row.cooking_runs)):
                if remaining_qty <= batch_size:
                    qty = (row.sub_assembly_qty / row.bom_qty) * remaining_qty
                else:
                    qty = row.sub_assembly_qty

                stickers.append({
                    "assembly_item_code": row.assembly_item_code,
                    "assembly_item_name": row.assembly_item_name,
                    "sub_assembly_item_code": row.sub_assembly_item_code,
                    "sub_assembly_item_name": row.sub_assembly_item_name,
                    "sub_assembly_operation": row.sub_assembly_operation,
                    "cooking_run": run + 1,
                    "cooking_runs": int(row.cooking_runs),
                    "qty": round(qty, 2),
                    "assembly_qty": row.assembly_qty,
                    "assembly_uom": row.assembly_uom
                })

                # تحديث الكمية المتبقية
                remaining_qty -= batch_size

    # تحميل القالب
    base_path = os.path.dirname(__file__)
    env = Environment(loader=FileSystemLoader(os.path.join(base_path, 'templates')))
    template = env.get_template('production_stickers.html')

    # تمرير البيانات للقالب
    html_content = template.render(
        stickers=stickers,
        plan_name=plan_name,
        today=nowdate(),
        stickers_count=len(stickers)
    )

    # تخزين في public
    public_path = os.path.abspath(os.path.join(base_path, '../../public/production_plan'))
    os.makedirs(public_path, exist_ok=True)
    temp_file = os.path.join(public_path, f'{plan_name}_stickers.html')

    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return f"/assets/taj_core/production_plan/{plan_name}_stickers.html"


@frappe.whitelist()
def delete_production_stickers(plan_name):
    """
    Delete the HTML file generated for a Production Plan stickers.
    """
    if not plan_name:
        frappe.throw(_("Production Plan name is required"))

    try:
        base_path = os.path.dirname(__file__)
        public_path = os.path.abspath(os.path.join(base_path, '../../public/production_plan'))
        file_path = os.path.join(public_path, f'{plan_name}_stickers.html')

        if os.path.exists(file_path):
            os.remove(file_path)
            return _("Sticker HTML file deleted successfully.")
        else:
            return _("Sticker HTML file not found.")

    except Exception as e:
        frappe.log_error(message=str(e), title="Delete Production Stickers Error")
        frappe.throw(_("An error occurred while deleting the sticker HTML file."))

def delete_old_production_stickers():
    """
    Delete Production Plan sticker HTML files older than 1 month.
    """
    try:
        base_path = os.path.dirname(__file__)
        public_path = os.path.abspath(os.path.join(base_path, '../../public/production_plan'))

        if not os.path.exists(public_path):
            return _("No production stickers directory found.")

        deleted_files = []
        now = datetime.now()
        cutoff_date = now - timedelta(days=30)

        for file_name in os.listdir(public_path):
            if file_name.endswith("_stickers.html"):
                file_path = os.path.join(public_path, file_name)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))

                if file_mtime < cutoff_date:
                    os.remove(file_path)
                    deleted_files.append(file_name)

        if deleted_files:
            return _("Deleted files: ") + ", ".join(deleted_files)
        else:
            return _("No old sticker HTML files to delete.")

    except Exception as e:
        frappe.log_error(message=str(e), title="Delete Old Production Stickers Error")
        frappe.throw(_("An error occurred while deleting old sticker HTML files."))
