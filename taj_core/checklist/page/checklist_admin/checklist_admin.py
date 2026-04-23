from frappe.utils import getdate, add_days, nowdate

today = getdate(nowdate())
from_date = add_days(today, -7)
to_date = add_days(today, -1)

prev_open_filters = {
    "posting_date": ["between", [from_date, to_date]],
    "status": ["in", ["Draft", "In Progress", "Expired"]],
}

# أضف هنا نفس فلاتر template / department / assigned_user / issue_filter عندك

prev_open_docs = frappe.get_all(
    "Checklist Answer",
    filters=prev_open_filters,
    fields=[
        "name",
        "template",
        "status",
        "department",
        "assigned_user",
        "result_status",
        "time_status",
        "delay_minutes",
    ],
    order_by="posting_date asc, modified desc",
)

summary["prev_open"] = len(prev_open_docs)
data["prev_open_docs"] = prev_open_docs