import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})

    data = get_data(filters)
    columns = get_columns()

    report_summary = get_report_summary(data)
    chart = get_chart(data)

    return columns, data, None, chart, report_summary


# =========================
# Columns
# =========================
def get_columns():
    return [
        {"label": _("Production Plan"), "fieldname": "production_plan", "fieldtype": "Link", "options": "Production Plan", "width": 150},
        {"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 95},
        {"label": _("Work Order"), "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 170},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Product Type"), "fieldname": "product_type", "fieldtype": "Data", "width": 115},
        {"label": _("Date"), "fieldname": "report_date", "fieldtype": "Date", "width": 110},
        {"label": _("Required Qty"), "fieldname": "required_qty", "fieldtype": "Float", "width": 120},
        {"label": _("Produced Qty"), "fieldname": "produced_qty", "fieldtype": "Float", "width": 120},
        {"label": _("Loss Qty"), "fieldname": "loss_qty", "fieldtype": "Float", "width": 90},
        {"label": _("Variance Qty"), "fieldname": "variance_qty", "fieldtype": "Float", "width": 120},
    ]
# =========================
# Data
# =========================
def get_data(filters):
    conditions = ["wo.docstatus < 2"]
    values = {}

    if filters.get("production_plan"):
        conditions.append("wo.production_plan = %(production_plan)s")
        values["production_plan"] = filters.get("production_plan")

    product_type = filters.get("product_type") or "Final Product"

    if product_type == "Final Product":
        conditions.append("""
            (
                (ifnull(wo.production_plan_item, '') != '')
                or (
                    ifnull(wo.production_plan_item, '') = ''
                    and ifnull(wo.production_plan_sub_assembly_item, '') = ''
                    and ifnull(i.is_sales_item, 0) = 1
                )
            )
        """)
    elif product_type == "Preparation":
        conditions.append("""
            (
                (ifnull(wo.production_plan_sub_assembly_item, '') != '')
                or (
                    ifnull(wo.production_plan_item, '') = ''
                    and ifnull(wo.production_plan_sub_assembly_item, '') = ''
                    and ifnull(i.is_sales_item, 0) = 0
                )
            )
        """)

    data = frappe.db.sql(
        f"""
        select
            wo.name as work_order,
            wo.status,
            wo.production_plan,
            wo.production_item as item_code,
            DATE(wo.planned_start_date) as report_date,
            wo.qty as required_qty,
            wo.produced_qty as produced_qty,
            wo.process_loss_qty as loss_qty,
            case
                when ifnull(wo.production_plan_item, '') != '' then 'Final Product'
                when ifnull(wo.production_plan_sub_assembly_item, '') != '' then 'Preparation'
                when ifnull(i.is_sales_item, 0) = 1 then 'Final Product'
                else 'Preparation'
            end as product_type
        from `tabWork Order` wo
        left join `tabItem` i on i.name = wo.production_item
        where {' and '.join(conditions)}
        order by wo.planned_start_date asc
        """,
        values,
        as_dict=True,
    )

    # معالجة Draft و Not Started
    for d in data:
        d.produced_qty = flt(d.produced_qty or 0)
        d.loss_qty = flt(d.loss_qty or 0)

        if d.status in ("Draft", "Submitted", "Not Started"):
            d.produced_qty = 0
            d.loss_qty = 0

        d.variance_qty = flt(d.produced_qty) - flt(d.required_qty)

    return data

def get_report_summary(data):
    total_required = round(sum(flt(d.required_qty) for d in data), 3)
    total_produced = round(sum(flt(d.produced_qty) for d in data), 3)
    total_loss = round(sum(flt(d.loss_qty) for d in data), 3)

    achievement = round((total_produced / total_required * 100), 3) if total_required else 0
    work_orders = len(set(d.work_order for d in data if d.work_order))

    return [
        {
            "label": "Required Qty",
            "value": total_required,
            "datatype": "Float",
            "indicator": "Blue",
        },
        {
            "label": "Produced Qty",
            "value": total_produced,
            "datatype": "Float",
            "indicator": "Green",
        },
        {
            "label": "Loss Qty",
            "value": total_loss,
            "datatype": "Float",
            "indicator": "Red" if total_loss > 0 else "Green",
        },
        {
            "label": "Achievement %",
            "value": achievement,
            "datatype": "Percent",
            "indicator": "Green" if achievement >= 100 else "Orange",
        },
        {
            "label": "Work Orders",
            "value": work_orders,
            "datatype": "Int",
            "indicator": "Blue",
        }
    ]

def get_chart(data):
    total_required = round(sum(flt(d.required_qty) for d in data), 3)
    total_produced = round(sum(flt(d.produced_qty) for d in data), 3)
    total_loss = round(sum(flt(d.loss_qty) for d in data), 3)

    return {
        "data": {
            "labels": ["Required", "Produced", "Loss"],
            "datasets": [
                {
                    "name": "Production",
                    "values": [total_required, total_produced, total_loss],
                }
            ],
        },
        "type": "bar",
        "height": 250,
    }