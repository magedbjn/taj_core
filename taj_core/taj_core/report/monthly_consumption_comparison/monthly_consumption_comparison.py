import frappe
from frappe.utils import add_months, getdate, get_url_to_form
from collections import defaultdict
from calendar import month_name

def format_number(value):
    if not value or value == 0:
        return ""
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"

def execute(filters=None):
    if not filters:
        filters = {}

    # الموردين المسموحين
    allowed_suppliers = [
        "Water Distribution - Aquaphor",
        "Saudi Electricity Company",
        "STC"
    ]

    supplier = filters.get("supplier")
    if not supplier:
        return [], []

    if supplier not in allowed_suppliers:
        frappe.throw(f"Supplier {supplier} not allowed.")

    # الفترات (بالأشهر)
    period_map = {
        "3 Months": 3,
        "6 Months": 6,
        "9 Months": 9,
        "12 Months": 12
    }
    months = period_map.get(filters.get("period") or "12 Months", 12)

    # تحديد الفترة
    end_date = getdate()
    start_date = add_months(end_date, -months + 1).replace(day=1)

    # جلب البيانات
    items = frappe.db.sql("""
        SELECT
            pi_item.item_code,
            pi_item.item_name,
            pi.posting_date,
            pi.name as invoice,
            SUM(pi_item.qty) as qty
        FROM `tabPurchase Invoice Item` pi_item
        JOIN `tabPurchase Invoice` pi ON pi_item.parent = pi.name
        WHERE pi.docstatus = 1
          AND pi.supplier = %s
          AND pi.posting_date BETWEEN %s AND %s
        GROUP BY pi_item.item_code, pi_item.item_name, pi.posting_date, pi.name
        ORDER BY pi_item.item_code, pi.posting_date
    """, (supplier, start_date, end_date), as_dict=1)

    # تنظيم البيانات لكل صنف ولكل شهر
    monthly_qty = defaultdict(lambda: [0]*months)
    invoices_map = defaultdict(lambda: [[] for _ in range(months)])

    for d in items:
        month_index = (getdate(d.posting_date).month - start_date.month) % 12
        key = (d.item_code, d.item_name)
        monthly_qty[key][month_index] += d.qty
        invoices_map[key][month_index].append(d.invoice)

    # بناء data_dict مع روابط لكل شهر
    data_dict = {}
    totals_dict = {}

    for key, qty_list in monthly_qty.items():
        row_vals = []
        total = 0
        for idx, qty in enumerate(qty_list):
            if qty:
                links = "<br>".join([
                    f'<a href="{get_url_to_form("Purchase Invoice", inv)}" target="_blank">{format_number(qty)}</a>'
                    for inv in invoices_map[key][idx]
                ])
                row_vals.append(links)
            else:
                row_vals.append("")
            total += qty
        data_dict[key] = row_vals
        totals_dict[key] = total

    # الأعمدة
    columns = ["Item Code", "Item Name"]
    for i in range(months):
        month_index = (start_date.month + i - 1) % 12 + 1
        columns.append(month_name[month_index])
    columns.append("Total Qty")

    # بناء الصفوف
    data = []
    for (item_code, item_name), monthly_vals in data_dict.items():
        row = [item_code, item_name]
        row.extend(monthly_vals)
        row.append(format_number(totals_dict[(item_code, item_name)]))
        data.append(row)

    return columns, data
