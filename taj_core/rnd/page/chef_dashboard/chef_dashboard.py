import frappe
from frappe import _
from frappe.utils import get_first_day, getdate, today

from taj_core.rnd.services.chef_dashboard_metrics import build_dashboard_metrics


TRIAL_FIELDS = [
    "name",
    "product_proposal",
    "trial_no",
    "trial_title",
    "status",
    "is_final_trial",
    "posting_date",
    "approved_on",
    "trial_user",
]

RUN_FIELDS = [
    "parent",
    "run_no",
    "run_date",
]


@frappe.whitelist()
def get_dashboard_data(
    from_date=None,
    to_date=None,
    trial_user=None,
    product_proposal=None,
    status=None,
):
    if not frappe.has_permission("Product Proposal Trial", "read"):
        frappe.throw(_("Not permitted to read Product Proposal Trials."), frappe.PermissionError)

    today_date = getdate(today())
    from_date = getdate(from_date) if from_date else get_first_day(today_date)
    to_date = getdate(to_date) if to_date else today_date

    if from_date > to_date:
        frappe.throw(_("From Date cannot be after To Date."))

    trials = frappe.get_list(
        "Product Proposal Trial",
        fields=TRIAL_FIELDS,
        order_by="posting_date asc, trial_no asc, name asc",
        limit_page_length=0,
    )

    proposal_names = sorted(
        {row.product_proposal for row in trials if row.product_proposal}
    )
    product_names = {}
    if proposal_names and frappe.has_permission("Product Proposal", "read"):
        proposal_rows = frappe.get_list(
            "Product Proposal",
            filters={"name": ["in", proposal_names]},
            fields=["name", "product_name"],
            limit_page_length=0,
        )
        product_names = {
            row.name: row.product_name or row.name
            for row in proposal_rows
        }

    for row in trials:
        row["product_name"] = product_names.get(row.product_proposal, row.product_proposal)

    trial_names = [row.name for row in trials]
    runs = []
    if trial_names:
        runs = frappe.get_all(
            "Product Proposal Trial Run",
            filters={
                "parenttype": "Product Proposal Trial",
                "parentfield": "cooking_runs",
                "parent": ["in", trial_names],
            },
            fields=RUN_FIELDS,
            order_by="run_date asc, parent asc, run_no asc",
            limit_page_length=0,
        )

    payload = build_dashboard_metrics(
        trials,
        runs,
        from_date,
        to_date,
        trial_user=trial_user or None,
        product_proposal=product_proposal or None,
        status=status or None,
    )
    payload["filters"] = {
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "trial_user": trial_user or "",
        "product_proposal": product_proposal or "",
        "status": status or "",
    }
    return payload
