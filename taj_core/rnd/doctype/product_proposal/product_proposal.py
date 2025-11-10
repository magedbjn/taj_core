import re
import frappe
from frappe.model.document import Document
from frappe.utils import cint
from frappe import _

class ProductProposal(Document):
    def validate(self):
        if self.is_default and self.sensory_decision != 'Approve':
            frappe.throw(_("Only approved proposals can be set as default"))

        # """Ensure only one document per product_name is set as default."""
        # if self.is_default:
        #     frappe.db.sql(
        #         """
        #         UPDATE `tabProduct Proposal`
        #         SET is_default = 0
        #         WHERE product_name = %s AND name != %s
        #         """,
        #         (self.product_name, self.name),
        #     )

    def autoname(self):
        """Name format: {product_name}-{NN} e.g., My Product-01"""
        product = (self.product_name or "").strip()
        if not product:
            frappe.throw(_("Please fill Product Name before saving."))

        search_key = f"{product}-%"
        existing = frappe.get_all(
            self.doctype,
            filters={"name": ["like", search_key]},
            pluck="name",
        )

        index = self.get_next_version_index(existing)
        name = f"{product}-{index:02d}"

        while frappe.db.exists(self.doctype, name):
            index += 1
            name = f"{product}-{index:02d}"

        self.name = name
    
    def before_insert(self):
        self._ensure_previous_version_is_submitted()

    def on_update(self):
        if self.sensory_decision != 'Approve':
            self.is_default = 0
        else:
            self.is_default = 1

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
    def link_existing_item(self, item_code: str):
        """Persist the selected existing Item code on this Product Proposal."""
        if not item_code:
            frappe.throw(_("Missing Item Code."))

        # Allow linking even if doc is submitted
        self.db_set("item_code", item_code)

        return {"ok": True, "item_code": item_code}

    @frappe.whitelist()
    def create_item(self):
        # التحقق من الصلاحيات
        # if not frappe.has_permission(self.doctype, 'write'):
        #     frappe.throw(_('You do not have permission to create items'))

        if getattr(self, "item_code", None):
            frappe.throw(_("Item already exists for this Product Proposal: {0}").format(self.item_code))

        product = (self.product_name or "").strip()
        if not product:
            frappe.throw(_("Please fill Product Name before saving."))

        # لو في Item بنفس الاسم: لا تنشئ جديد
        existing = frappe.get_all(
            "Item", filters={"item_name": product}, fields=["item_code", "item_name"], limit=10
        )
        if existing:
            return {"exists": True, "item_code": existing[0]["item_code"], "item_name": existing[0]["item_name"]}

        # اجلب الشركة الافتراضية من أكثر من مصدر
        default_company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )
        if not default_company:
            frappe.throw(_("No default Company is set for your user or Global Defaults."))

        # تأكد من وجود Item Group مناسب
        item_group = "Finished Goods"
        if not frappe.db.exists("Item Group", item_group):
            # خُذ أي مجموعة نهائية (ليست مجموعة) بدلًا منها
            fallback_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
            if not fallback_group:
                frappe.throw(_("No leaf Item Group found to assign to the Item."))
            item_group = fallback_group

        # اختر Warehouse مناسب إن وُجد (لا ترمي خطأ لو مش موجود)
        default_warehouse = (
            frappe.db.get_value("Warehouse", {"company": default_company, "is_group": 0, "warehouse_name": ["like", "%Finished Goods%"]}, "name")
            or frappe.db.get_value("Warehouse", {"company": default_company, "is_group": 0}, "name")
        )

        item_values = {
            "doctype": "Item",
            "naming_series": "FG.####.P",
            "item_name": product,
            "item_group": item_group,
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
                # لا تضع warehouse إن ما وُجد — تجنب Link Validation Error/Not Found
                **({"default_warehouse": default_warehouse} if default_warehouse else {})
            }],
        }

        item_meta = frappe.get_meta("Item")
        if item_meta.has_field("item_name_arabic") and getattr(self, "product_name_arabic", None):
            item_values["item_name_arabic"] = self.product_name_arabic

        try:
            item = frappe.get_doc(item_values)
            item.insert()
        except frappe.LinkValidationError as e:
            # رسالة أوضح بدل "Not Found []"
            frappe.throw(_("Link validation failed while creating Item: {0}").format(e))
        except Exception as e:
            # أعد رسالة مفهومة للواجهة
            frappe.throw(_("Failed to create Item: {0}").format(frappe.as_unicode(e)))

        self.db_set("item_code", item.name)
        return {"exists": False, "item_code": item.name}
