"""QC label master for standard Item variants and multiple standalone Items.

No modifications to Item, BOM, Work Order, Job Card, inventory or accounting.
Coverage is derived at validation/print time from the standard Item relations.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from taj_core.qc.finished_product_label_math import decimal_value, weight_to_grams

NUTRIENT_OPTIONS = {
    "Protein": "protein_g",
    "Total Fat": "total_fat_g",
    "Saturated Fat": "saturated_fat_g",
    "Trans Fat": "trans_fat_g",
    "Cholesterol": "cholesterol_mg",
    "Total Carbohydrates": "carbohydrates_g",
    "Total Sugars": "total_sugars_g",
    "Added Sugars": "added_sugars_g",
    "Dietary Fiber": "dietary_fiber_g",
    "Sodium": "sodium_mg",
}

NUTRIENT_FIELDS = (
    "calories_kcal", "protein_g", "total_fat_g", "saturated_fat_g", "trans_fat_g",
    "cholesterol_mg", "carbohydrates_g", "total_sugars_g", "added_sugars_g",
    "dietary_fiber_g", "sodium_mg",
)

ITEM_FIELDS = [
    "name", "item_name", "item_name_arabic", "is_sales_item", "item_group", "disabled", "has_variants", "variant_of",
    "weight_per_unit", "weight_uom",
]


class FinishedProductNutritionFacts(Document):
    def validate(self):
        self.validate_items()
        self.validate_nutrients()
        self.validate_amount_rules()

    def validate_items(self):
        if not self.get("item_code"):
            frappe.throw(_("Select an Item."))

        main = self.get_valid_item(self.item_code)
        # Item is the single source for names: ignore any client-supplied values.
        self.item_name = main.item_name or ""
        self.item_name_arabic = main.item_name_arabic or ""
        linked_codes = [row.item_code for row in self.get("additional_items") or []]
        if main.has_variants and linked_codes:
            frappe.throw(
                _("An Item with variants already covers all of its variants; remove Additional Items.")
            )

        seen = {self.item_code}
        for code in linked_codes:
            if not code:
                frappe.throw(_("Select an Item in every Additional Items row."))
            if code in seen:
                frappe.throw(_("Item {0} is listed more than once.").format(code))
            seen.add(code)
            item = self.get_valid_item(code)
            if item.has_variants:
                frappe.throw(_("Additional Item {0} must not be an Item with variants.").format(code))
            self.check_item_weight(code, item)

        if main.has_variants:
            if self._action == "submit":
                # The master Item itself does not have to carry package weight.
                # Validate actual, currently eligible variants before approval.
                variants = frappe.get_all("Item", filters={
                    "variant_of": self.item_code, "disabled": 0,
                    "is_sales_item": 1, "item_group": "Finished Goods",
                }, fields=["name", "weight_per_unit", "weight_uom"])
                for variant in variants:
                    self.check_item_weight(variant.name, variant)
        else:
            self.check_item_weight(self.item_code, main)

    @staticmethod
    def get_valid_item(item_code):
        item = frappe.db.get_value("Item", item_code, ITEM_FIELDS, as_dict=True)
        if not item or item.disabled or not item.is_sales_item or item.item_group != "Finished Goods":
            frappe.throw(
                _("Item {0} must be an enabled sales Item in Finished Goods.").format(item_code)
            )
        return item

    @staticmethod
    def check_item_weight(item_code, item):
        try:
            weight_to_grams(item.weight_per_unit, item.weight_uom)
        except ValueError as exc:
            frappe.throw(_("Item {0}: {1}").format(item_code, str(exc)))

    def validate_nutrients(self):
        # Stored per-100-g nutrition values are integers. Scaling in the
        # print service still uses Decimal for different package weights.
        for fieldname in NUTRIENT_FIELDS:
            try:
                value = decimal_value(self.get(fieldname))
            except ValueError as exc:
                frappe.throw(_("{0}: {1}").format(fieldname, str(exc)))
            if value != value.to_integral_value():
                frappe.throw(_("{0}: Nutritional values must be whole numbers.").format(fieldname))
        if self._action == "submit":
            if not self.ingredients_ar:
                frappe.throw(_("Ingredients are mandatory."))
            self.validate_no_other_approved_profile()

    def validate_amount_rules(self):
        """Keep measured amounts numeric; allow optional '<1 unit' display rules.

        Zero is acceptable for an upper-bound-only lab result because it is
        not printed as zero when the threshold rule is selected.
        """
        seen = set()
        for row in self.get("amount_rules") or []:
            nutrient = row.get("nutrient")
            fieldname = NUTRIENT_OPTIONS.get(nutrient)
            if not fieldname:
                frappe.throw(_("Select a valid Nutrient for Less Than Values."))
            if nutrient in seen:
                frappe.throw(_("Less Than Values contains the same nutrient more than once: {0}.").format(_(nutrient)))
            seen.add(nutrient)
            if row.get("less_than_one") and decimal_value(self.get(fieldname)) >= 1:
                frappe.throw(_("{0} cannot be marked Less than 1 when its numeric value is 1 or greater.").format(_(nutrient)))

    def validate_no_other_approved_profile(self):
        """A source may cover one Item, many independent Items, or one variant family.

        Check both the primary link and any additional rows in *other* approved
        records. Reject template-vs-variant collisions in either direction.
        """
        selected = [self.item_code] + [row.item_code for row in self.get("additional_items") or []]
        main = frappe.db.get_value("Item", self.item_code, ["has_variants"], as_dict=True)
        parent_codes = set()
        for code in selected:
            parent_code = frappe.db.get_value("Item", code, "variant_of")
            if parent_code:
                parent_codes.add(parent_code)

        # Lock selected Item rows, and template Item rows when a variant is chosen,
        # so overlapping concurrent approvals serialize on a common Item record.
        lock_codes = sorted(set(selected) | parent_codes)
        lock_sql = ", ".join(["%s"] * len(lock_codes))
        frappe.db.sql(f"SELECT name FROM `tabItem` WHERE name IN ({lock_sql}) ORDER BY name FOR UPDATE", tuple(lock_codes))

        selected_sql = ", ".join(["%s"] * len(selected))
        args = [self.name, *selected, *selected]
        conditions = [
            f"other.item_code IN ({selected_sql})",
            f"other_row.item_code IN ({selected_sql})",
        ]
        if main.has_variants:
            conditions += ["other_base.variant_of = %s", "other_row_item.variant_of = %s"]
            args.extend([self.item_code, self.item_code])
        if parent_codes:
            parents = sorted(parent_codes)
            parent_sql = ", ".join(["%s"] * len(parents))
            conditions.append(f"(other_base.has_variants = 1 AND other.item_code IN ({parent_sql}))")
            args.extend(parents)

        conflict = frappe.db.sql(f"""
            SELECT DISTINCT other.name
            FROM `tabFinished Product Nutrition Facts` other
            INNER JOIN `tabItem` other_base ON other_base.name = other.item_code
            LEFT JOIN `tabFinished Product Label Item` other_row
              ON other_row.parent = other.name
              AND other_row.parenttype = 'Finished Product Nutrition Facts'
              AND other_row.parentfield = 'additional_items'
            LEFT JOIN `tabItem` other_row_item ON other_row_item.name = other_row.item_code
            WHERE other.docstatus = 1 AND other.name != %s
              AND ({' OR '.join(conditions)})
            LIMIT 1
        """, tuple(args), as_dict=True)
        if conflict:
            frappe.throw(
                _("Approved label {0} already covers an Item in this specification or one of its variants.")
                .format(conflict[0].name)
            )
