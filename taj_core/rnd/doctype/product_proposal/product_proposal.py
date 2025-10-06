import re
import frappe
from frappe.model.document import Document
from frappe.utils import cint
from frappe import _

class ProductProposal(Document):
    def autoname(self):
        """Name format: {product_name}-{NN} e.g., My Product-01"""
        product = (self.product_name or "").strip()
        if not product:
            frappe.throw(_("Please fill Product Name before saving."))

        # Find existing versions for the same product_name
        search_key = f"{product}-%"
        existing = frappe.get_all(
            self.doctype,
            filters={"name": ["like", search_key]},
            pluck="name",
        )

        index = self.get_next_version_index(existing)
        name = f"{product}-{index:02d}"

        # Safety loop in case of a race
        while frappe.db.exists(self.doctype, name):
            index += 1
            name = f"{product}-{index:02d}"

        self.name = name

    @staticmethod
    def get_next_version_index(existing_names: list[str]) -> int:
        """
        Extract last segment as version (supports product names with '-' or '/').
        Examples considered valid:
          My Product-01, My-Complex/Product-12
        """
        if not existing_names:
            return 1

        parts = [re.split(r"[/\-]", n) for n in existing_names]
        valid = [p for p in parts if len(p) >= 2 and p[-1].isdigit()]
        if not valid:
            return 1

        indexes = [cint(p[-1]) for p in valid]
        return max(indexes) + 1
