import re
import frappe
from frappe.model.document import Document
from frappe.utils import cint
from frappe import _

class ProductProposal(Document):
    def validate(self):
        """Ensure only one document per product_name is set as default."""
        if self.is_default:
            # Unset is_default for all other docs with same product_name
            frappe.db.sql(
                """
                UPDATE `tabProduct Proposal`
                SET is_default = 0
                WHERE product_name = %s AND name != %s
                """,
                (self.product_name, self.name),
            )

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

    def before_insert(self):
        self._ensure_previous_version_is_submitted()

    def _ensure_previous_version_is_submitted(self):
        """Block creating a new version if the latest version (same product_name) is not submitted."""
        product = (self.product_name or "").strip()
        if not product:
            return

        existing = frappe.get_all(
            self.doctype,
            filters={"name": ["like", f"{product}-%"]},
            fields=["name", "docstatus"],
        )
        if not existing:
            return

        def parse_suffix(n: str) -> int:
            m = re.search(r"(?:-|/)(\d+)$", n)
            return int(m.group(1)) if m else 0

        latest = max(existing, key=lambda d: parse_suffix(d["name"]))
        if latest["docstatus"] != 1:
            # رسالة واضحة للمستخدم
            frappe.throw(
                _("Please submit the current version ({0}) before creating a new one.").format(latest["name"])
            )
    def before_submit(self):
        if self.sensory_decision == "Open":
            frappe.throw(_("Cannot submit while Sensory Decision is 'Open'."))

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

    @frappe.whitelist()
    def create_item(self):
        # لا تنشئ Item إذا كان موجود
        if getattr(self, "item_code", None):
            frappe.throw(_("Item already exists for this Product Proposal: {0}").format(self.item_code))

        default_company = frappe.defaults.get_user_default("Company")

        item_values = {
            "doctype": "Item",
            "naming_series": "FG.####.P",
            "item_name": self.product_name,
            "item_group": "Finished Goods",
            "stock_uom": "Pouch",
            "is_stock_item": 1,
            "brand": "Taj",
            "shelf_life_in_days": 720,
            "default_material_request_type": "Manufacture",
            "has_batch_no": 1,
            "has_expiry_date": 1,
            "is_purchase_item": 0,
            "item_defaults": [{
                "company": default_company,
                "default_warehouse": "Finished Goods - Taj"
            }],
        }

        # ✅ التصحيح هنا: فحص وجود الحقل عبر get_meta().has_field(...)
        item_meta = frappe.get_meta("Item")
        if item_meta.has_field("item_name_arabic") and getattr(self, "product_name_arabic", None):
            item_values["item_name_arabic"] = self.product_name_arabic

        item = frappe.get_doc(item_values)
        item.insert()

        # اربط الكود على وثيقة الـ Product Proposal
        self.db_set("item_code", item.name)

        return {"item_code": item.name}