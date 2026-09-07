import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, getdate, formatdate

class SensoryFeedback(Document):
    def validate(self):
        self.validate_trial_document()

    def validate_trial_document(self):
        trial_document = getattr(
            self,
            "trial_document",
            None,
        )

        if not trial_document:
            return

        trial_proposal = frappe.db.get_value(
            "Product Proposal Trial",
            trial_document,
            "product_proposal",
        )

        if not trial_proposal:
            frappe.throw(
                _("Selected Trial Cooking does not exist.")
            )

        if trial_proposal != (self.item or "").strip():
            frappe.throw(
                _(
                    "Selected Trial Cooking does not belong "
                    "to this Product Proposal."
                )
            )


def sync_to_product_proposal(doc: "SensoryFeedback", method=None):
    """Sync feedback to Product Proposal only for authorized users."""

    # The public Web Form may create Sensory Feedback, but an anonymous
    # submission must never mutate the linked Product Proposal.
    if frappe.session.user == "Guest":
        return

    item_name = (doc.item or "").strip()
    if not item_name:
        return

    if not frappe.db.exists("Product Proposal", item_name):
        return

    eval_date = doc.evaluation_date or today()
    try:
        eval_date = getdate(eval_date)
        eval_date_str = formatdate(eval_date, "yyyy-MM-dd")
    except Exception:
        eval_date_str = eval_date

    trial_document = getattr(
        doc,
        "trial_document",
        None,
    )

    row_values = {
        "evaluation_date": eval_date_str,
        "trial_document": trial_document,
        "your_name": doc.your_name,
        "appearance": doc.appearance,
        "texture": doc.texture,
        "taste": doc.taste,
        "spicy": doc.spicy,
        "comment": doc.comment,
        "final_status": doc.final_status,
    }

    pp = frappe.get_doc("Product Proposal", item_name)
    pp.check_permission("write")

    pp.append(
        "pp_sensory_evaluation",
        row_values,
    )
    pp.save()
