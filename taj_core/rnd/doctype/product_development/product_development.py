# Copyright (c) 2025, Maged Bajandooh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr

class ProductDevelopment(Document):
	pass

@frappe.whitelist()
def product_name_distinct_query(doctype, txt, searchfield, start, page_len, filters):
    """
    تُرجّع أحدث سجل لكل product_name من Doctype "Product Proposal"
    بالشكل المتوقع للـ Link: [[name, product_name], ...]
    - تحاول أولاً استخدام Window Functions (ROW_NUMBER)
    - إن لم تتوفر (DB قديمة)، تسقط لفولباك يضمن عدم التكرار
    """
    search_term = f"%{cstr(txt or '').strip()}%" if txt else "%%"
    start = max(int(start or 0), 0)
    page_len = min(int(page_len or 20), 100)

    params = {"txt": search_term, "start": start, "page_len": page_len}

    # محاولة: CTE + ROW_NUMBER()
    try:
        rows = frappe.db.sql(
            """
            WITH RankedProposals AS (
                SELECT
                    name,
                    product_name,
                    ROW_NUMBER() OVER (
                        PARTITION BY product_name
                        ORDER BY modified DESC
                    ) AS rn
                FROM `tabProduct Proposal`
                WHERE docstatus != 2
                  AND is_default = 1
                  AND sensory_decision != 'Reject'
                  AND IFNULL(product_name, '') != ''
                  AND (product_name LIKE %(txt)s OR name LIKE %(txt)s)
            )
            SELECT name, product_name
            FROM RankedProposals
            WHERE rn = 1
            ORDER BY product_name ASC
            LIMIT %(start)s, %(page_len)s
            """,
            params,
            as_list=True,
        )
        return rows

    except Exception:
        # فولباك: الأحدث لكل product_name عبر join على MAX(modified)
        rows = frappe.db.sql(
            """
            SELECT pp2.name, pp2.product_name
            FROM `tabProduct Proposal` pp2
            INNER JOIN (
                SELECT product_name, MAX(modified) AS max_modified
                FROM `tabProduct Proposal`
                WHERE docstatus != 2
                  AND IFNULL(product_name, '') != ''
                  AND (product_name LIKE %(txt)s OR name LIKE %(txt)s)
                GROUP BY product_name
            ) latest
              ON latest.product_name = pp2.product_name
             AND latest.max_modified = pp2.modified
            ORDER BY pp2.product_name ASC
            LIMIT %(start)s, %(page_len)s
            """,
            params,
            as_list=True,
        )
        return rows


@frappe.whitelist()
def proposal_versions_query(doctype, txt, searchfield, start, page_len, filters):
    """
    تُرجّع جميع سجلات Product Proposal لاسم product_name معيّن (إن وُجد)
    بالشكل: [[name, product_name], ...] مرتّبة بالأحدث تعديلًا.
    """
    pn = ""
    if isinstance(filters, dict):
        pn = cstr(filters.get("product_name") or "").strip()

    like_txt = f"%{cstr(txt or '').strip()}%"
    params = {
        "pn": pn,
        "txt": like_txt,
        "start": int(start or 0),
        "page_len": min(int(page_len or 20), 100),
    }

    where = ["pp.docstatus != 2"]
    if pn:
        where.append("pp.product_name = %(pn)s")
    where_sql = " AND ".join(where)

    rows = frappe.db.sql(
        f"""
        SELECT pp.name, pp.product_name
        FROM `tabProduct Proposal` pp
        WHERE {where_sql}
          AND (pp.name LIKE %(txt)s OR pp.product_name LIKE %(txt)s)
        ORDER BY pp.modified DESC
        LIMIT %(start)s, %(page_len)s
        """,
        params,
        as_list=True,
    )
    return rows
