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
    """Return the newest readable Product Proposal for each product name."""
    search_term = f"%{cstr(txt or '').strip()}%" if txt else "%%"
    start = max(int(start or 0), 0)
    page_len = min(int(page_len or 20), 100)

    rows = frappe.get_list(
        "Product Proposal",
        filters={
            "docstatus": ["!=", 2],
            "is_default": 1,
            "sensory_decision": ["!=", "Reject"],
            "product_name": ["!=", ""],
        },
        or_filters=[
            ["product_name", "like", search_term],
            ["name", "like", search_term],
        ],
        fields=["name", "product_name", "modified"],
        order_by="modified desc",
        limit_page_length=0,
    )

    newest_by_product = {}
    for row in rows:
        product_name = cstr(row.get("product_name") or "").strip()
        if product_name and product_name not in newest_by_product:
            newest_by_product[product_name] = row.get("name")

    result = [
        [name, product_name]
        for product_name, name in newest_by_product.items()
    ]
    result.sort(key=lambda row: cstr(row[1]).casefold())
    return result[start:start + page_len]


@frappe.whitelist()
def proposal_versions_query(doctype, txt, searchfield, start, page_len, filters):
    """Return readable Product Proposal versions for a product name."""
    pn = ""
    if isinstance(filters, dict):
        pn = cstr(filters.get("product_name") or "").strip()

    like_txt = f"%{cstr(txt or '').strip()}%"
    start = max(int(start or 0), 0)
    page_len = min(int(page_len or 20), 100)

    list_filters = {
        "docstatus": ["!=", 2],
    }
    if pn:
        list_filters["product_name"] = pn

    return frappe.get_list(
        "Product Proposal",
        filters=list_filters,
        or_filters=[
            ["name", "like", like_txt],
            ["product_name", "like", like_txt],
        ],
        fields=["name", "product_name"],
        order_by="modified desc",
        limit_start=start,
        limit_page_length=page_len,
        as_list=True,
    )
