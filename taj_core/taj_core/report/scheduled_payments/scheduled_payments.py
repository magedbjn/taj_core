import calendar
import frappe
from frappe import _


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Type", "fieldname": "transaction_type", "fieldtype": "Data", "width": 110},
        {"label": "Source DocType", "fieldname": "source_doctype", "fieldtype": "Data", "width": 150},

        {"label": "Party Type", "fieldname": "party_type", "fieldtype": "Data", "width": 110},
        {"label": "Party", "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 220},

        {"label": "Document", "fieldname": "document", "fieldtype": "Dynamic Link", "options": "source_doctype", "width": 220},
        {"label": "Posting / Transaction Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 170},

        {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 120},
        {"label": "Scheduled Amount", "fieldname": "scheduled_amount", "fieldtype": "Currency", "width": 160},

        {"label": "Currency", "fieldname": "currency", "fieldtype": "Data", "width": 90},
        {"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 180},
    ]


def pick_first_existing_db_column(doctype, candidates, fallback):
    for col in candidates:
        try:
            if frappe.db.has_column(doctype, col):
                return col
        except Exception:
            pass
    return fallback


def pick_payment_schedule_amount_field():
    meta = frappe.get_meta("Payment Schedule")
    if meta.has_field("payment_amount"):
        return "payment_amount"
    if meta.has_field("amount"):
        return "amount"
    return "payment_amount"


def year_month_to_range(year_value, month_value):
    """
    Filter by Due Date only.

    - If year is "All" (or empty) => no due date filtering
    - If year is set:
        - month = All => full year range
        - month = Jan..Dec => month range
    """
    if not year_value or str(year_value).strip() == "All":
        return None, None

    year = int(year_value)
    month = (month_value or "All").strip()

    if month == "All":
        return f"{year}-01-01", f"{year}-12-31"

    month_map = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
        "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
        "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }
    m = month_map.get(month)
    if not m:
        return f"{year}-01-01", f"{year}-12-31"

    last_day = calendar.monthrange(year, m)[1]
    return f"{year}-{m:02d}-01", f"{year}-{m:02d}-{last_day:02d}"


def get_sources(transaction_type):
    """
    Option B:
    - Purchases: Purchase Order, and Purchase Invoice only if direct (no PO linked).
    - Sales: Sales Order, and Sales Invoice only if direct (no SO linked).
    """
    if transaction_type == "Purchases":
        return [
            {
                "doctype": "Purchase Order",
                "table": "tabPurchase Order",
                "party_type": "Supplier",
                "party_field": "supplier",
                "date_candidates": ["transaction_date", "posting_date", "schedule_date"],
                "extra_where": "",
            },
            {
                "doctype": "Purchase Invoice",
                "table": "tabPurchase Invoice",
                "party_type": "Supplier",
                "party_field": "supplier",
                "date_candidates": ["posting_date"],
                "extra_where": """
                    AND NOT EXISTS (
                        SELECT 1
                        FROM `tabPurchase Invoice Item` pii
                        WHERE pii.parent = doc.name
                          AND IFNULL(pii.purchase_order, '') <> ''
                    )
                """,
            },
        ]

    if transaction_type == "Sales":
        return [
            {
                "doctype": "Sales Order",
                "table": "tabSales Order",
                "party_type": "Customer",
                "party_field": "customer",
                "date_candidates": ["transaction_date", "posting_date", "delivery_date"],
                "extra_where": "",
            },
            {
                "doctype": "Sales Invoice",
                "table": "tabSales Invoice",
                "party_type": "Customer",
                "party_field": "customer",
                "date_candidates": ["posting_date"],
                "extra_where": """
                    AND NOT EXISTS (
                        SELECT 1
                        FROM `tabSales Invoice Item` sii
                        WHERE sii.parent = doc.name
                          AND IFNULL(sii.sales_order, '') <> ''
                    )
                """,
            },
        ]

    frappe.throw(_("Invalid Transaction Type"))


def get_data(filters):
    transaction_type = (filters.get("transaction_type") or "Purchases").strip()
    supplier = filters.get("supplier")
    customer = filters.get("customer")
    company = filters.get("company")

    # JS will send year default = current year, but keep safe fallbacks here
    year = filters.get("year") or str(frappe.utils.now_datetime().year)
    month = filters.get("month") or "All"

    from_date, to_date = year_month_to_range(year, month)
    amount_field = pick_payment_schedule_amount_field()

    params = {
        "transaction_type": transaction_type,
        "from_date": from_date,
        "to_date": to_date,
        "company": company,
        "supplier": supplier,
        "customer": customer,
    }

    queries = []

    for src in get_sources(transaction_type):
        date_field = pick_first_existing_db_column(
            src["doctype"],
            src["date_candidates"],
            src["date_candidates"][0],
        )

        # ✅ unique parenttype per doctype (fix UNION overriding)
        key = f"parenttype_{src['doctype'].replace(' ', '_')}"
        params[key] = src["doctype"]

        conditions = [
            f"ps.parenttype = %({key})s",
            "doc.docstatus < 2",
        ]

        # Due Date filtering only when year != All
        if from_date:
            conditions.append("ps.due_date >= %(from_date)s")
        if to_date:
            conditions.append("ps.due_date <= %(to_date)s")

        if company:
            conditions.append("doc.company = %(company)s")

        if transaction_type == "Purchases" and supplier:
            conditions.append("doc.supplier = %(supplier)s")

        if transaction_type == "Sales" and customer:
            conditions.append("doc.customer = %(customer)s")

        query = f"""
            SELECT
                %(transaction_type)s AS transaction_type,
                '{src['doctype']}' AS source_doctype,
                '{src['party_type']}' AS party_type,
                doc.{src['party_field']} AS party,
                doc.name AS document,
                doc.{date_field} AS posting_date,
                ps.due_date AS due_date,
                ps.{amount_field} AS scheduled_amount,
                doc.currency AS currency,
                doc.company AS company
            FROM `tabPayment Schedule` ps
            INNER JOIN `{src['table']}` doc
                ON doc.name = ps.parent
            WHERE {" AND ".join(conditions)}
            {src.get("extra_where") or ""}
        """
        queries.append(query)

    final_sql = " UNION ALL ".join(queries) + " ORDER BY due_date ASC, document ASC"
    return frappe.db.sql(final_sql, params, as_dict=True)
