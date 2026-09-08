import frappe
from frappe import _
from frappe.utils import cint, today

from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
    _is_sensory_window_active,
)


def get_context(context):
    return context


def _get_product_proposal_evaluation_context(product_proposal):
    proposal = frappe.db.get_value(
        "Product Proposal",
        product_proposal,
        ["product_name", "docstatus"],
        as_dict=True,
    )

    if not proposal or cint(proposal.docstatus) == 2:
        frappe.throw(_("Product Proposal is no longer available for Sensory Rating."))

    return proposal


@frappe.whitelist(allow_guest=True)
def resolve_sample_evaluation_context(sample_token):
    sample_token = (sample_token or "").strip()

    if not sample_token:
        frappe.throw(_("Sample evaluation token is required."))

    sample = frappe.db.get_value(
        "Product Proposal Sample",
        {"evaluation_token": sample_token},
        [
            "name",
            "parent",
            "parenttype",
            "parentfield",
            "trial_document",
            "customer",
        ],
        as_dict=True,
    )

    if not sample:
        frappe.throw(_("Sample evaluation link is invalid."))

    if (
        sample.parenttype != "Product Proposal"
        or sample.parentfield != "customer_samples"
    ):
        frappe.throw(_("Sample evaluation link is invalid."))

    trial = frappe.db.get_value(
        "Product Proposal Trial",
        sample.trial_document,
        ["product_proposal", "trial_title", "trial_no"],
        as_dict=True,
    )

    if not trial or trial.product_proposal != sample.parent:
        frappe.throw(_("Sample Trial is no longer valid for this Product Proposal."))

    proposal = _get_product_proposal_evaluation_context(sample.parent)
    product_name = proposal.product_name or sample.parent
    customer_name = frappe.db.get_value(
        "Customer",
        sample.customer,
        "customer_name",
    ) or sample.customer

    return frappe._dict({
        "sample_name": sample.name,
        "product_proposal": sample.parent,
        "product_name": product_name,
        "trial_document": sample.trial_document,
        "trial_title": trial.trial_title or sample.trial_document,
        "trial_no": trial.trial_no,
        "customer": sample.customer,
        "customer_name": customer_name,
    })


@frappe.whitelist(allow_guest=True)
def get_active_sensory_trials(txt=""):
    txt = (txt or "").strip()
    search = f"%{txt}%"
    current_date = today()

    return frappe.db.sql(
        """
        select
            trial.name,
            trial.product_proposal,
            proposal.product_name,
            trial.trial_title,
            trial.trial_no
        from `tabProduct Proposal Trial` trial
        inner join `tabProduct Proposal` proposal
            on proposal.name = trial.product_proposal
        where trial.enable_sensory_rating = 1
          and trial.sensory_from_date <= %(current_date)s
          and trial.sensory_until_date >= %(current_date)s
          and proposal.docstatus != 2
          and (
                trial.name like %(search)s
                or trial.trial_title like %(search)s
                or trial.product_proposal like %(search)s
                or proposal.product_name like %(search)s
          )
        order by proposal.product_name, trial.trial_no
        limit 100
        """,
        {
            "current_date": current_date,
            "search": search,
        },
        as_dict=True,
    )


@frappe.whitelist(allow_guest=True)
def get_trial_evaluation_context(trial_document):
    trial_document = (trial_document or "").strip()

    if not trial_document:
        frappe.throw(_("Trial is required."))

    trial = frappe.db.get_value(
        "Product Proposal Trial",
        trial_document,
        [
            "name",
            "product_proposal",
            "trial_title",
            "trial_no",
            "enable_sensory_rating",
            "sensory_from_date",
            "sensory_until_date",
        ],
        as_dict=True,
    )

    if not trial:
        frappe.throw(_("Selected Trial does not exist."))

    active = _is_sensory_window_active(
        trial.enable_sensory_rating,
        trial.sensory_from_date,
        trial.sensory_until_date,
    )

    if not active:
        if frappe.session.user == "Guest":
            frappe.throw(_("This Trial is not currently open for Sensory Rating."))

        trial_doc = frappe.get_doc(
            "Product Proposal Trial",
            trial_document,
        )
        trial_doc.check_permission("read")

    proposal = _get_product_proposal_evaluation_context(
        trial.product_proposal
    )
    product_name = proposal.product_name or trial.product_proposal

    return frappe._dict({
        "product_proposal": trial.product_proposal,
        "product_name": product_name,
        "trial_document": trial.name,
        "trial_title": trial.trial_title or trial.name,
        "trial_no": cint(trial.trial_no),
        "active": cint(active),
    })
