import re
import frappe
from frappe.model.document import Document
from frappe.utils import cint, cstr
from frappe import _


TRIAL_COOKING_ALLOWED_ROLES = {
    "System Manager",
    "RND Manager",
    "RND Trial Cooking User",
}


class ProductProposal(Document):
    # -------------------------------------------------------------------------
    # Main Events
    # -------------------------------------------------------------------------

    def validate(self):
        self.set_trial_cooking_defaults()
        self.validate_trial_cooking_locked_fields()
        self.validate_trial_cooking_permission()
        self.is_default = cint(
            self.sensory_decision == "Approve"
        )

    def before_update_after_submit(self):
        self.set_trial_cooking_defaults()
        self.validate_trial_cooking_locked_fields()
        self.validate_trial_cooking_permission()

    def before_submit(self):
        # 1) منع السبمت لو القرار Open
        if self.sensory_decision == "Open":
            frappe.throw(_("Cannot submit while Sensory Decision is 'Open'."))

        # 2) إذا القرار Approve، تأكد أن كل pp_items لها item_code
        if self.sensory_decision == "Approve":
            missing = []

            for row in (self.get("pp_items") or []):
                if not row.item_code:
                    missing.append(cstr(row.idx))

            if missing:
                frappe.throw(
                    _(
                        "Cannot submit with Sensory Decision 'Approve'. "
                        "Please set Item Code for all rows in Raw Materials table. Missing in rows: {0}"
                    ).format(", ".join(missing))
                )

        # 3) تعبئة pre_bom قبل Submit
        self.set_preparation_bom_before_submit()

    def before_insert(self):
        self._ensure_previous_version_is_submitted()

    # -------------------------------------------------------------------------
    # Naming / Version
    # -------------------------------------------------------------------------

    def autoname(self):
        """Name format: {product_name}-{NN} e.g. My Product-01"""
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

    def _ensure_previous_version_is_submitted(self):
        """Block creating a new version if the latest version for same product_name is not submitted."""
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
                _("Please submit the current version ({0}) before creating a new one.").format(
                    latest["name"]
                )
            )

    @staticmethod
    def get_next_version_index(existing_names: list[str]) -> int:
        if not existing_names:
            return 1

        parts = [re.split(r"[/\-]", n) for n in existing_names]
        valid = [p for p in parts if len(p) >= 2 and p[-1].isdigit()]

        if not valid:
            return 1

        indexes = [cint(p[-1]) for p in valid]
        return max(indexes) + 1

    # -------------------------------------------------------------------------
    # Trial Cooking
    # -------------------------------------------------------------------------

    def set_trial_cooking_defaults(self):
        """
        Auto fill Trial Cooking rows:
        - posting_date = Today
        - trial_user = current user
        - holding_time = current time if empty

        Important:
        - trial_qty is the actual produced quantity.
        - trial_qty must be entered by the user after cooking.
        """
        rows = self.get("trial_cooking") or []

        for row in rows:
            if not row.posting_date:
                row.posting_date = frappe.utils.today()

            if not row.trial_user:
                row.trial_user = frappe.session.user

            # Holding Time يكون تلقائي بالوقت الحالي فقط إذا كان فاضي
            # المستخدم يستطيع تعديله بعد ذلك
            if not row.holding_time:
                row.holding_time = frappe.utils.nowtime()

    def validate_trial_cooking_permission(self):
        """
        Only selected roles can add/edit/delete Trial Cooking rows.
        Other users can only view.
        """
        if self.has_trial_cooking_permission():
            return

        old_doc = self.get_doc_before_save()

        # أثناء إنشاء مستند جديد
        if not old_doc:
            if self.get("trial_cooking"):
                frappe.throw(_("You are not allowed to add Trial Cooking records."))
            return

        old_rows = self.get_trial_cooking_signature(old_doc)
        new_rows = self.get_trial_cooking_signature(self)

        if old_rows != new_rows:
            frappe.throw(_("You are not allowed to add, edit, or delete Trial Cooking records."))

    def validate_trial_cooking_locked_fields(self):
        """
        Prevent changing automatic fields after the row is created:
        - posting_date
        - trial_user

        Editable by allowed users:
        - trial_qty
        - pouch_size
        - holding_time
        - remark
        """
        old_doc = self.get_doc_before_save()

        if not old_doc:
            return

        old_rows_map = {}

        for old_row in (old_doc.get("trial_cooking") or []):
            old_rows_map[old_row.name] = old_row

        for row in (self.get("trial_cooking") or []):
            if not row.name or row.name not in old_rows_map:
                continue

            old_row = old_rows_map[row.name]

            if cstr(row.posting_date) != cstr(old_row.posting_date):
                frappe.throw(_("Posting Date cannot be changed in Trial Cooking."))

            if cstr(row.trial_user) != cstr(old_row.trial_user):
                frappe.throw(_("Trial User cannot be changed in Trial Cooking."))

    def has_trial_cooking_permission(self):
        user_roles = set(frappe.get_roles(frappe.session.user))
        return bool(user_roles.intersection(TRIAL_COOKING_ALLOWED_ROLES))

    @staticmethod
    def get_trial_cooking_signature(doc):
        """
        Compare Trial Cooking rows to detect changes.
        """
        result = []

        for row in (doc.get("trial_cooking") or []):
            result.append({
                "name": cstr(row.name),
                "idx": cint(row.idx),
                "posting_date": cstr(row.posting_date),
                "trial_user": cstr(row.trial_user),
                "trial_qty": cint(row.trial_qty),
                "pouch_size": cstr(row.pouch_size),
                "holding_time": cstr(row.holding_time),
                "remark": cstr(row.remark),
            })

        return result

    # -------------------------------------------------------------------------
    # Preparation BOM
    # -------------------------------------------------------------------------

    def set_preparation_bom_before_submit(self):
        child_table_field = "pp_items"
        rows = self.get(child_table_field) or []

        items = [
            row.item_code
            for row in rows
            if row.item_code and not row.pre_bom
        ]

        if not items:
            return

        prep_items = frappe.get_all(
            "Preparation Items",
            filters={"item_code": ["in", items]},
            fields=["item_code", "bom_no"],
            as_list=True,
        )

        prep_map = {
            item_code: bom_no
            for item_code, bom_no in prep_items
            if bom_no
        }

        for row in rows:
            if row.item_code and not row.pre_bom:
                row.pre_bom = prep_map.get(row.item_code)

    @frappe.whitelist()
    def sync_preparation_bom(self):
        """Sync Preparation BOM on pp_items from Preparation Items."""
        child_table_field = "pp_items"
        rows = self.get(child_table_field) or []

        if not rows:
            return {
                "updated": 0,
                "total": 0,
                "missing_items": [],
            }

        item_codes = list({
            row.item_code
            for row in rows
            if getattr(row, "item_code", None)
        })

        if not item_codes:
            return {
                "updated": 0,
                "total": len(rows),
                "missing_items": [],
            }

        prep_items = frappe.get_all(
            "Preparation Items",
            filters={"item_code": ["in", item_codes]},
            fields=["item_code", "bom_no"],
            order_by="modified desc",
            as_list=True,
        )

        prep_map = {}

        for item_code, bom_no in prep_items:
            if item_code not in prep_map and bom_no:
                prep_map[item_code] = bom_no

        updated_rows = []
        missing_items = set()

        for row in rows:
            if not row.item_code:
                continue

            new_bom = prep_map.get(row.item_code)

            if not new_bom:
                missing_items.add(row.item_code)
                continue

            if row.pre_bom != new_bom:
                frappe.db.set_value(
                    "Product Proposal Raw Material",
                    row.name,
                    "pre_bom",
                    new_bom,
                )
                updated_rows.append(row.name)

        return {
            "updated": len(updated_rows),
            "total": len(rows),
            "missing_items": list(missing_items),
        }

    # -------------------------------------------------------------------------
    # Item Creation / Link
    # -------------------------------------------------------------------------

    @frappe.whitelist()
    def link_existing_item(self, item_code: str):
        if not item_code:
            frappe.throw(_("Missing Item Code."))

        self.db_set("item_code", item_code)

        return {
            "ok": True,
            "item_code": item_code,
        }

    @frappe.whitelist()
    def create_item(self):
        if getattr(self, "item_code", None):
            frappe.throw(
                _("Item already exists for this Product Proposal: {0}").format(self.item_code)
            )

        product = (self.product_name or "").strip()

        if not product:
            frappe.throw(_("Please fill Product Name before saving."))

        existing = frappe.get_all(
            "Item",
            filters={"item_name": product},
            fields=["item_code", "item_name"],
            limit=10,
        )

        if existing:
            return {
                "exists": True,
                "item_code": existing[0]["item_code"],
                "item_name": existing[0]["item_name"],
            }

        default_company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )

        if not default_company:
            frappe.throw(_("No default Company is set for your user or Global Defaults."))

        item_group = "Finished Goods"

        if not frappe.db.exists("Item Group", item_group):
            fallback_group = frappe.db.get_value(
                "Item Group",
                {"is_group": 0},
                "name",
            )

            if not fallback_group:
                frappe.throw(_("No leaf Item Group found to assign to the Item."))

            item_group = fallback_group

        default_warehouse = (
            frappe.db.get_value(
                "Warehouse",
                {
                    "company": default_company,
                    "is_group": 0,
                    "warehouse_name": ["like", "%Finished Goods%"],
                },
                "name",
            )
            or frappe.db.get_value(
                "Warehouse",
                {
                    "company": default_company,
                    "is_group": 0,
                },
                "name",
            )
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
                **({"default_warehouse": default_warehouse} if default_warehouse else {}),
            }],
        }

        item_meta = frappe.get_meta("Item")

        if item_meta.has_field("item_name_arabic") and getattr(self, "product_name_arabic", None):
            item_values["item_name_arabic"] = self.product_name_arabic

        try:
            item = frappe.get_doc(item_values)
            item.insert()

        except frappe.LinkValidationError as e:
            frappe.throw(_("Link validation failed while creating Item: {0}").format(e))

        except Exception as e:
            frappe.throw(_("Failed to create Item: {0}").format(frappe.as_unicode(e)))

        self.db_set("item_code", item.name)

        return {
            "exists": False,
            "item_code": item.name,
        }