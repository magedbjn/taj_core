import frappe
from frappe import _

def execute(filters=None):
    filters = filters or {}
    cols = [
      {"label":_("Mock Recall"),"fieldname":"name","fieldtype":"Link","options":"Mock Recall","width":180},
      {"label":_("Date"),"fieldname":"snapshot_date","fieldtype":"Datetime","width":170},
      {"label":_("Scenario"),"fieldname":"scenario_type","width":170},
      {"label":_("Item"),"fieldname":"item_code","fieldtype":"Link","options":"Item","width":140},
      {"label":_("Batch"),"fieldname":"batch_no","fieldtype":"Link","options":"Batch","width":140},
      {"label":_("Status"),"fieldname":"status","width":110},
      {"label":_("Assessment"),"fieldname":"result","width":110},
      {"label":_("Trace Evidence Rows"),"fieldname":"trace_row_count","fieldtype":"Int","width":130},
      {"label":_("Customers"),"fieldname":"customer_count","fieldtype":"Int","width":100},
      {"label":_("Trace Duration (s)"),"fieldname":"elapsed_seconds","fieldtype":"Float","width":120},
      {"label":_("Reviewed By"),"fieldname":"reviewed_by","fieldtype":"Link","options":"User","width":170},
    ]
    cond = {}
    for key in ("company","scenario_type","result"):
      if filters.get(key): cond[key] = filters[key]
    if filters.get("status"):
      cond["status"] = filters["status"]
    for key in ("item_code", "batch_no"):
      if filters.get(key): cond[key] = filters[key]
    if filters.get("from_date") and filters.get("to_date"):
      cond["snapshot_date"] = ["between", [filters["from_date"] + " 00:00:00", filters["to_date"] + " 23:59:59.999999"]]
    elif filters.get("from_date"):
      cond["snapshot_date"] = [">=", filters["from_date"] + " 00:00:00"]
    elif filters.get("to_date"):
      cond["snapshot_date"] = ["<=", filters["to_date"] + " 23:59:59.999999"]
    limit = 1000
    rows = frappe.get_list("Mock Recall", filters=cond, fields=[c["fieldname"] for c in cols], order_by="modified desc, name desc", limit_page_length=limit + 1)
    message = _("Showing the latest {0} matching records. Narrow the filters to see the remaining records.").format(limit) if len(rows) > limit else None
    return cols, rows[:limit], message
