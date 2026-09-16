import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, cstr, flt, getdate, now_datetime, today

from erpnext.manufacturing.doctype.bom.bom import get_valuation_rate

from taj_core.services.item_uom import (
    get_item_uom_conversion_factor as _get_item_uom_conversion_factor,
    get_item_uom_factor_to_stock as _get_item_uom_factor_to_stock,
    validate_item_uom_rows,
)


# Trial costing uses the shared Taj Core Item UOM policy.
# Keep this local alias as the costing seam used by existing logic/tests.
_get_trial_conversion_factor = _get_item_uom_factor_to_stock

from taj_core.rnd.services.quantity_display import format_mass_for_print
from taj_core.rnd.services.snapshot_compare import (
    normalize_snapshot_value,
    snapshot_values_equal,
)


COOKING_SHEET_TEMPLATE = "rnd/templates/trial_run_cooking_sheet.html"


SNAPSHOT_FIELDS = (
    "item_code",
    "item_name",
    "qty",
    "uom",
    "operation",
    "procees_type",
    "cooking_type",
    "temperature",
    "duration",
    "pre_bom",
    "notes",
)


SOLID_LIQUID_SNAPSHOT_FIELDS = (
    "component_type",
    "component_name",
    "size",
    "weight",
    "total_weight_cook",
    "salt",
    "brix",
    "ph",
    "viscosity",
    "spindel_type",
    "rpm",
    "temperature",
)

SOLID_LIQUID_LOCKED_FIELDS = tuple(
    fieldname
    for fieldname in SOLID_LIQUID_SNAPSHOT_FIELDS
    if fieldname != "total_weight_cook"
)


PROPOSAL_FORMULA_ITEM_FIELDS = (
    "item_code",
    "item_name",
    "qty",
    "uom",
    "operation",
    "procees_type",
    "cooking_type",
    "temperature",
    "duration",
    "pre_bom",
    "notes",
)


def _scale_snapshot_qty(source_qty, target_qty, row_qty):
    source_qty = flt(source_qty)
    target_qty = flt(target_qty)

    if target_qty <= 0:
        frappe.throw(
            _("Planned Cooking Qty must be greater than zero.")
        )

    if source_qty <= 0:
        frappe.throw(
            _(
                "Source quantity must be greater than zero "
                "to scale Trial Items."
            )
        )

    return flt(row_qty) * target_qty / source_qty



def _scale_total_weight_cook(source_qty, target_qty, total_weight_cook):
    source_qty = flt(source_qty)
    target_qty = flt(target_qty)

    if target_qty <= 0:
        frappe.throw(_("Planned Cooking Qty must be greater than zero."))

    if source_qty <= 0:
        frappe.throw(
            _(
                "Source quantity must be greater than zero "
                "to scale Solid / Liquid values."
            )
        )

    return flt(total_weight_cook) * target_qty / source_qty

def _is_sensory_window_active(
    enabled,
    from_date,
    until_date,
    reference_date=None,
):
    if not cint(enabled) or not from_date or not until_date:
        return False

    reference_date = getdate(reference_date or today())
    return (
        getdate(from_date)
        <= reference_date
        <= getdate(until_date)
    )


class ProductProposalTrial(Document):
    def autoname(self):
        if not self.product_proposal:
            frappe.throw(
                _("Product Proposal is required.")
            )

        parent = frappe.db.sql(
            """
            select name
            from `tabProduct Proposal`
            where name = %s
              and docstatus != 2
            for update
            """,
            (self.product_proposal,),
            as_dict=True,
        )

        if not parent:
            frappe.throw(
                _("Product Proposal does not exist.")
            )

        next_no = frappe.db.sql(
            """
            select coalesce(max(trial_no), 0) + 1
            from `tabProduct Proposal Trial`
            where product_proposal = %s
            """,
            (self.product_proposal,),
        )[0][0]

        self.trial_no = cint(next_no)

        self.name = (
            f"{self.product_proposal}"
            f"-TRIAL-{self.trial_no:02d}"
        )

        if not self.trial_title:
            self.trial_title = _(
                "Trial {0}"
            ).format(self.trial_no)

    def before_insert(self):
        if not self.posting_date:
            self.posting_date = today()

        if not self.trial_user:
            self.trial_user = frappe.session.user

    def validate(self):
        self.validate_item_uoms()
        self.validate_product_proposal()
        self.validate_based_on_trial()
        self.set_sensory_availability_defaults()
        self.validate_sensory_availability()
        self.set_approval_timestamp()
        self.set_cooking_run_defaults()
        self.validate_cooking_runs()
        self.set_progress_status_from_cooking_runs()

        self.ensure_line_keys()
        self.validate_line_keys_immutable()
        self.validate_solid_liquid_snapshot()

        self.validate_locked_identity()
        self.validate_formula_locked_after_approval()
        self.validate_frozen_snapshot()
        self.invalidate_changed_cost_snapshots()
        self.validate_final_trial()

        self.set_totals()

    def validate_item_uoms(self):
        validate_item_uom_rows(
            self.get("items") or []
        )

    @frappe.whitelist()
    def approve_formula(self):
        self.check_permission("write")

        if self.status not in ("Draft", "In Progress"):
            frappe.throw(
                _(
                    "Formula quantities can only be approved while "
                    "the Trial is Draft or In Progress."
                )
            )

        if cint(self.formula_approved):
            return {
                "formula_approved": 1,
                "trial": self.name,
            }

        if not self.get("items"):
            frappe.throw(
                _("Add at least one Trial Item before approving the formula.")
            )

        self.formula_approved = 1
        self.save()

        return {
            "formula_approved": 1,
            "trial": self.name,
        }

    @frappe.whitelist()
    def replace_product_proposal_formula(self):
        self.check_permission("read")

        if (
            self.status != "Approved"
            or not cint(self.is_final_trial)
        ):
            frappe.throw(
                _(
                    "Only an Approved Final Trial can update "
                    "the Product Proposal formula."
                )
            )

        if not self.get("items"):
            frappe.throw(
                _("The Trial has no Items to transfer.")
            )

        proposal = frappe.get_doc(
            "Product Proposal",
            self.product_proposal,
        )
        proposal.check_permission("write")

        if cint(proposal.docstatus) != 0:
            frappe.throw(
                _(
                    "Product Proposal must be in Draft before its formula "
                    "can be updated from a Trial: {0}."
                ).format(proposal.name)
            )

        latest_run = max(
            (
                row
                for row in (self.get("cooking_runs") or [])
                if cint(row.run_no) > 0
            ),
            key=lambda row: cint(row.run_no),
            default=None,
        )

        if not latest_run or flt(latest_run.produced_qty) <= 0:
            frappe.throw(
                _(
                    "Latest Trial Cooking Run must have Produced Qty "
                    "greater than zero before updating the Product "
                    "Proposal formula."
                )
            )

        proposal.quantity = flt(latest_run.produced_qty)
        proposal.set("pp_items", [])

        for trial_row in self.get("items") or []:
            proposal.append(
                "pp_items",
                {
                    fieldname: trial_row.get(fieldname)
                    for fieldname in PROPOSAL_FORMULA_ITEM_FIELDS
                },
            )

        proposal.set("pp_solid_liquid", [])

        for trial_row in self.get("solid_liquid") or []:
            proposal.append(
                "pp_solid_liquid",
                {
                    fieldname: trial_row.get(fieldname)
                    for fieldname in SOLID_LIQUID_SNAPSHOT_FIELDS
                },
            )

        proposal.save()

        return {
            "product_proposal": proposal.name,
            "items_replaced": len(proposal.get("pp_items") or []),
            "solid_liquid_replaced": len(
                proposal.get("pp_solid_liquid") or []
            ),
            "quantity": flt(proposal.quantity),
            "run_no": cint(latest_run.run_no),
        }

    def get_latest_run_cooking_sheet(self):
        run_no = max(
            (
                cint(row.run_no)
                for row in (self.get("cooking_runs") or [])
                if cint(row.run_no) > 0
            ),
            default=0,
        )

        if not run_no:
            return None

        return get_trial_run_cooking_sheet(
            self.name,
            run_no,
        )

    def set_approval_timestamp(self):
        old_doc = self.get_doc_before_save()

        if self.status != "Approved":
            self.approved_on = None
            return

        if old_doc and old_doc.status == "Approved":
            self.approved_on = old_doc.get("approved_on")
            return

        self.approved_on = now_datetime()

    def set_cooking_run_defaults(self):
        rows = list(self.get("cooking_runs") or [])
        used = {cint(row.run_no) for row in rows if cint(row.run_no) > 0}
        next_no = max(used or {0}) + 1

        for row in rows:
            if cint(row.run_no) <= 0:
                while next_no in used:
                    next_no += 1
                row.run_no = next_no
                used.add(next_no)
                next_no += 1

            if not row.run_date:
                row.run_date = today()

    def set_progress_status_from_cooking_runs(self):
        if (
            self.status == "Draft"
            and self.get("cooking_runs")
        ):
            self.status = "In Progress"

    def validate_cooking_runs(self):
        rows = list(self.get("cooking_runs") or [])
        old_doc = self.get_doc_before_save()
        old_by_name = {
            row.name: row
            for row in (old_doc.get("cooking_runs") or [])
            if row.name
        } if old_doc else {}
        seen_run_nos = set()

        if old_doc:
            new_names = {row.name for row in rows if row.name}
            deleted = [
                row for row in (old_doc.get("cooking_runs") or [])
                if row.name and row.name not in new_names
            ]
            if deleted:
                frappe.throw(
                    _("Existing Trial Cooking Runs cannot be deleted.")
                )

        for row in rows:
            run_no = cint(row.run_no)

            if run_no <= 0 or run_no in seen_run_nos:
                frappe.throw(
                    _("Trial Cooking Run numbers must be unique and positive.")
                )
            seen_run_nos.add(run_no)

            if flt(row.required_qty) <= 0:
                frappe.throw(
                    _(
                        "Required Qty must be greater than zero for "
                        "Trial Cooking Run {0}."
                    ).format(run_no)
                )

            if flt(row.produced_qty) < 0:
                frappe.throw(
                    _(
                        "Produced Qty cannot be negative for "
                        "Trial Cooking Run {0}."
                    ).format(run_no)
                )

            old_row = old_by_name.get(row.name) if row.name else None
            if not old_row:
                continue

            for fieldname, label in (
                ("run_no", "Run No"),
                ("run_date", "Date"),
                ("required_qty", "Required Qty"),
            ):
                if fieldname == "required_qty":
                    changed = flt(row.get(fieldname)) != flt(
                        old_row.get(fieldname)
                    )
                else:
                    changed = cstr(row.get(fieldname)) != cstr(
                        old_row.get(fieldname)
                    )

                if changed:
                    frappe.throw(
                        _(
                            "{0} cannot be changed after a Trial "
                            "Cooking Run is created."
                        ).format(label)
                    )

    def validate_formula_locked_after_approval(self):
        old_doc = self.get_doc_before_save()

        if not old_doc:
            return

        if not cint(old_doc.get("formula_approved")):
            return

        if not cint(self.formula_approved):
            frappe.throw(
                _(
                    "Formula approval cannot be removed. "
                    "Create a new Trial for formulation changes."
                )
            )

        if self._items_signature() != self._items_signature(old_doc):
            frappe.throw(
                _(
                    "Trial Items cannot be changed after Formula approval. "
                    "Create a new Trial for formulation changes."
                )
            )

        if (
            self._solid_liquid_signature()
            != self._solid_liquid_signature(old_doc)
        ):
            frappe.throw(
                _(
                    "Solid / Liquid formulation values cannot be changed after "
                    "Formula approval. Create a new Trial for formulation changes."
                )
            )

    def set_sensory_availability_defaults(self):
        if not cint(self.enable_sensory_rating):
            return

        if not self.sensory_from_date:
            self.sensory_from_date = today()

        if not self.sensory_until_date:
            self.sensory_until_date = add_months(
                self.sensory_from_date,
                3,
            )

    def validate_sensory_availability(self):
        if not cint(self.enable_sensory_rating):
            return

        if not self.sensory_from_date or not self.sensory_until_date:
            frappe.throw(
                _(
                    "Sensory From Date and Sensory Until Date "
                    "are required when Sensory Rating is enabled."
                )
            )

        if getdate(self.sensory_until_date) < getdate(self.sensory_from_date):
            frappe.throw(
                _("Sensory Until Date cannot be before Sensory From Date.")
            )

    def validate_product_proposal(self):
        docstatus = frappe.db.get_value(
            "Product Proposal",
            self.product_proposal,
            "docstatus",
        )

        if docstatus is None:
            frappe.throw(
                _("Product Proposal does not exist.")
            )

        if cint(docstatus) == 2:
            frappe.throw(
                _(
                    "Cannot create or modify a Trial "
                    "for a cancelled Product Proposal."
                )
            )

    def validate_based_on_trial(self):
        if not self.based_on_trial:
            return

        if self.based_on_trial == self.name:
            frappe.throw(
                _("A Trial cannot be based on itself.")
            )

        proposal = frappe.db.get_value(
            "Product Proposal Trial",
            self.based_on_trial,
            "product_proposal",
        )

        if not proposal:
            frappe.throw(
                _("Based On Trial does not exist.")
            )

        if proposal != self.product_proposal:
            frappe.throw(
                _(
                    "Based On Trial must belong to "
                    "the same Product Proposal."
                )
            )

    def ensure_line_keys(self):
        seen = set()

        for row in self.items or []:
            key = cstr(
                row.line_key or ""
            ).strip()

            if not key or key in seen:
                key = frappe.generate_hash(
                    length=12
                )
                row.line_key = key

            seen.add(key)

    def validate_line_keys_immutable(self):
        old_doc = self.get_doc_before_save()

        if not old_doc:
            return

        old_rows = {
            row.name: row
            for row in old_doc.items or []
            if row.name
        }

        for row in self.items or []:
            if not row.name:
                continue

            old_row = old_rows.get(row.name)

            if not old_row:
                continue

            if (
                cstr(row.line_key)
                != cstr(old_row.line_key)
            ):
                frappe.throw(
                    _(
                        "Trial Item identity cannot "
                        "be changed."
                    )
                )

    def validate_solid_liquid_snapshot(self):
        old_doc = self.get_doc_before_save()

        if not old_doc:
            return

        if not cint(old_doc.get("formula_approved")):
            return

        old_rows = list(old_doc.get("solid_liquid") or [])
        new_rows = list(self.get("solid_liquid") or [])

        if len(old_rows) != len(new_rows):
            frappe.throw(
                _(
                    "Solid / Liquid snapshot rows cannot be added or removed. "
                    "Create a new Trial for formulation changes."
                )
            )

        old_by_name = {row.name: row for row in old_rows if row.name}

        for row in new_rows:
            old_row = old_by_name.get(row.name) if row.name else None

            if not old_row:
                frappe.throw(
                    _(
                        "Solid / Liquid snapshot rows cannot be replaced. "
                        "Create a new Trial for formulation changes."
                    )
                )

            for fieldname in SOLID_LIQUID_SNAPSHOT_FIELDS:
                if not snapshot_values_equal(
                    fieldname,
                    row.get(fieldname),
                    old_row.get(fieldname),
                ):
                    frappe.throw(
                        _(
                            "Solid / Liquid formulation cannot be changed "
                            "after Formula approval."
                        )
                    )

    def _solid_liquid_signature(self, doc=None):
        doc = doc or self
        rows = []

        for row in doc.get("solid_liquid") or []:
            rows.append(
                (
                    cint(row.idx),
                    cstr(row.name),
                    *(
                        normalize_snapshot_value(fieldname, row.get(fieldname))
                        for fieldname in SOLID_LIQUID_SNAPSHOT_FIELDS
                    ),
                )
            )

        return tuple(rows)

    def _solid_liquid_formula_signature(self, doc=None):
        doc = doc or self
        rows = []

        for row in doc.get("solid_liquid") or []:
            rows.append(
                (
                    cint(row.idx),
                    cstr(row.name),
                    *(
                        normalize_snapshot_value(fieldname, row.get(fieldname))
                        for fieldname in SOLID_LIQUID_LOCKED_FIELDS
                    ),
                )
            )

        return tuple(rows)

    def validate_locked_identity(self):
        old_doc = self.get_doc_before_save()

        if not old_doc:
            return

        locked = (
            ("product_proposal", "Product Proposal"),
            ("trial_no", "Trial No"),
            ("based_on_trial", "Based On Trial"),
            ("posting_date", "Posting Date"),
            ("trial_user", "Trial User"),
            ("planned_cooking_qty", "Planned Cooking Qty"),
        )

        for fieldname, label in locked:
            if (
                cstr(self.get(fieldname))
                != cstr(old_doc.get(fieldname))
            ):
                frappe.throw(
                    _(
                        "{0} cannot be changed "
                        "after the Trial is created."
                    ).format(label)
                )

    def validate_frozen_snapshot(self):
        old_doc = self.get_doc_before_save()

        if not old_doc:
            return

        if old_doc.status == "Approved" and self.status != "Approved":
            frappe.throw(
                _(
                    "Approved Trial status cannot be changed. "
                    "Create a new Trial for further development."
                )
            )

        if (
            old_doc.status == "Approved"
            and cint(old_doc.is_final_trial)
            and not cint(self.is_final_trial)
        ):
            frappe.throw(
                _(
                    "The current Final Trial flag cannot be removed directly. "
                    "Mark another Approved Trial as Final instead."
                )
            )

        if (
            old_doc.status != "Draft"
            and self.status == "Draft"
        ):
            frappe.throw(
                _(
                    "An In Progress or completed Trial cannot be returned "
                    "to Draft. Create a new Trial instead."
                )
            )

        if old_doc.status in ("Draft", "In Progress"):
            return

        frozen_fields = (
            "trial_title",
            "planned_cooking_qty",
            "actual_produced_qty",
            "pouch_size",
            "holding_time",
            "remark",
        )

        for fieldname in frozen_fields:
            if (
                cstr(self.get(fieldname))
                != cstr(old_doc.get(fieldname))
            ):
                frappe.throw(
                    _(
                        "Completed Trial data cannot "
                        "be changed. Create a new Trial "
                        "for formulation changes."
                    )
                )

        if (
            self._items_signature()
            != self._items_signature(old_doc)
        ):
            frappe.throw(
                _(
                    "Completed Trial Items cannot be "
                    "changed. Create a new Trial instead."
                )
            )

        if (
            self._solid_liquid_signature()
            != self._solid_liquid_signature(old_doc)
        ):
            frappe.throw(
                _(
                    "Completed Trial Solid / Liquid data cannot be "
                    "changed. Create a new Trial instead."
                )
            )

    def _items_signature(self, doc=None):
        doc = doc or self

        result = []

        for row in doc.items or []:
            result.append(
                (
                    cint(row.idx),
                    cstr(row.line_key),
                    cstr(row.item_code),
                    flt(row.qty),
                    cstr(row.uom),
                    cstr(row.operation),
                    cstr(row.procees_type),
                    cstr(row.cooking_type),
                    flt(row.temperature),
                    flt(row.duration),
                    cstr(row.pre_bom),
                    cstr(row.notes),
                    cstr(row.stock_uom),
                    flt(row.conversion_factor),
                    flt(row.stock_qty),
                    flt(row.unit_cost),
                    flt(row.amount),
                    cstr(row.cost_source),
                    cstr(row.cost_status),
                )
            )

        return tuple(result)

    def validate_final_trial(self):
        if not self.is_final_trial:
            return

        if self.status != "Approved":
            frappe.throw(
                _(
                    "Only an Approved Trial can "
                    "be marked as Final Trial."
                )
            )

        # Keep the parent row locked while choosing the Final Trial so
        # concurrent requests for the same Product Proposal serialize,
        # without requiring the Product Proposal itself to be submitted.
        frappe.db.sql(
            """
            select name
            from `tabProduct Proposal`
            where name = %s
            for update
            """,
            (self.product_proposal,),
        )

        frappe.db.sql(
            """
            select name
            from `tabProduct Proposal Trial`
            where product_proposal = %s
              and name != %s
            for update
            """,
            (
                self.product_proposal,
                self.name,
            ),
        )

    def on_update(self):
        if self.status == "Approved" and cint(self.is_final_trial):
            self._demote_other_final_trials()

    def _demote_other_final_trials(self):
        if not self.name or not self.product_proposal:
            return

        frappe.db.sql(
            """
            update `tabProduct Proposal Trial`
            set is_final_trial = 0
            where product_proposal = %s
              and name != %s
              and status = 'Approved'
              and is_final_trial = 1
            """,
            (self.product_proposal, self.name),
        )

    @staticmethod
    def clear_cost_snapshot(
        row,
        status="",
    ):
        row.stock_uom = None
        row.conversion_factor = 0
        row.stock_qty = 0
        row.unit_cost = 0
        row.amount = 0
        row.cost_source = ""
        row.cost_status = status

    def invalidate_changed_cost_snapshots(self):
        old_doc = self.get_doc_before_save()

        if (
            not old_doc
            or old_doc.status != "Draft"
        ):
            return

        old_rows = {
            row.name: row
            for row in old_doc.items or []
            if row.name
        }

        for row in self.items or []:
            if not row.name:
                continue

            old_row = old_rows.get(row.name)

            if not old_row:
                continue

            if (
                cstr(row.item_code)
                != cstr(old_row.item_code)
                or cstr(row.uom)
                != cstr(old_row.uom)
            ):
                self.clear_cost_snapshot(
                    row
                )

    def refresh_costs_from_items(self):
        company = frappe.db.get_single_value(
            "Global Defaults",
            "default_company",
        )

        if not company:
            frappe.throw(
                _(
                    "Default Company is required "
                    "to calculate Trial costs."
                )
            )

        item_codes = list(
            dict.fromkeys(
                row.item_code
                for row in self.items or []
                if row.item_code
            )
        )

        records = []

        if item_codes:
            records = frappe.get_all(
                "Item",
                filters={
                    "name": [
                        "in",
                        item_codes,
                    ]
                },
                fields=[
                    "name",
                    "stock_uom",
                    "last_purchase_rate",
                    "variant_of",
                ],
            )

        item_map = {
            row.name: row
            for row in records
        }

        summary = {
            "costed": 0,
            "missing_conversion": 0,
            "missing_cost": 0,
            "missing_item": 0,
        }

        for row in self.items or []:
            item = item_map.get(
                row.item_code
            )

            if not item:
                self.clear_cost_snapshot(
                    row,
                    "Missing Item",
                )
                summary[
                    "missing_item"
                ] += 1
                continue

            row.stock_uom = (
                item.stock_uom
            )

            factor = (
                _get_trial_conversion_factor(
                    item.name,
                    row.uom,
                    item.stock_uom,
                    item.variant_of,
                )
            )

            # Example:
            # Gram -> Litre with no valid conversion.
            if not factor:
                row.conversion_factor = 0
                row.stock_qty = 0
                row.unit_cost = 0
                row.amount = 0
                row.cost_source = ""
                row.cost_status = (
                    "Missing Conversion"
                )

                summary[
                    "missing_conversion"
                ] += 1
                continue

            row.conversion_factor = (
                factor
            )

            row.stock_qty = (
                flt(row.qty)
                * flt(factor)
            )

            # Same valuation source used by BOM:
            # Bin -> Stock Ledger -> Item.
            valuation_rate = (
                get_valuation_rate(
                    {
                        "item_code":
                            item.name,
                        "company":
                            company,
                    }
                )
            )

            valuation_rate = flt(
                valuation_rate
            )

            last_purchase_rate = flt(
                item.last_purchase_rate
            )

            if valuation_rate > 0:
                stock_rate = (
                    valuation_rate
                )
                row.cost_source = (
                    "Valuation Rate"
                )

            elif last_purchase_rate > 0:
                stock_rate = (
                    last_purchase_rate
                )
                row.cost_source = (
                    "Last Purchase Rate"
                )

            else:
                row.unit_cost = 0
                row.amount = 0
                row.cost_source = ""
                row.cost_status = (
                    "Missing Cost"
                )

                summary[
                    "missing_cost"
                ] += 1
                continue

            # Same principle as BOM Item.rate:
            # stock rate × conversion factor
            # = rate per Trial UOM.
            row.unit_cost = (
                flt(stock_rate)
                * flt(factor)
            )

            row.amount = (
                flt(row.qty)
                * flt(row.unit_cost)
            )

            row.cost_status = "OK"

            summary["costed"] += 1

        self.set_totals()

        return summary

    def set_totals(self):
        self.total_items = len(
            self.items or []
        )

        total_cost = 0

        for row in self.items or []:
            if (
                row.cost_status == "OK"
                and flt(
                    row.conversion_factor
                ) > 0
                and flt(
                    row.unit_cost
                ) > 0
            ):
                row.stock_qty = (
                    flt(row.qty)
                    * flt(
                        row.conversion_factor
                    )
                )

                row.amount = (
                    flt(row.qty)
                    * flt(row.unit_cost)
                )
            else:
                row.amount = 0

            total_cost += flt(
                row.amount
            )

        self.total_cost = total_cost


def _append_snapshot_row(
    trial,
    source_row,
    line_key=None,
    qty=None,
):
    values = {
        fieldname: getattr(
            source_row,
            fieldname,
            None,
        )
        for fieldname in SNAPSHOT_FIELDS
    }

    if qty is not None:
        values["qty"] = flt(qty)

    values["line_key"] = (
        line_key
        or getattr(
            source_row,
            "line_key",
            None,
        )
        or frappe.generate_hash(
            length=12
        )
    )

    trial.append(
        "items",
        values,
    )


def _append_solid_liquid_snapshot_row(
    trial,
    source_row,
    source_qty,
    target_qty,
):
    values = {
        fieldname: getattr(source_row, fieldname, None)
        for fieldname in SOLID_LIQUID_SNAPSHOT_FIELDS
    }
    values["total_weight_cook"] = _scale_total_weight_cook(
        source_qty,
        target_qty,
        values.get("total_weight_cook"),
    )
    trial.append("solid_liquid", values)


@frappe.whitelist()
def create_trial(
    product_proposal,
    source="previous",
    based_on_trial=None,
    planned_cooking_qty=None,
):
    target_qty = flt(planned_cooking_qty)

    if target_qty <= 0:
        frappe.throw(
            _("Planned Cooking Qty must be greater than zero.")
        )

    if source not in {
        "previous",
        "proposal",
        "empty",
    }:
        frappe.throw(
            _("Invalid Trial source.")
        )

    proposal = frappe.get_doc(
        "Product Proposal",
        product_proposal,
    )
    proposal.check_permission("read")

    if proposal.docstatus == 2:
        frappe.throw(
            _(
                "Cannot create a Trial from "
                "a cancelled Product Proposal."
            )
        )

    base_trial = None

    if source == "previous":
        if based_on_trial:
            base_trial = frappe.get_doc(
                "Product Proposal Trial",
                based_on_trial,
            )
            base_trial.check_permission(
                "read"
            )
        else:
            previous = frappe.get_all(
                "Product Proposal Trial",
                filters={
                    "product_proposal":
                        product_proposal,
                },
                fields=["name"],
                order_by="trial_no desc",
                limit=1,
            )

            if previous:
                base_trial = frappe.get_doc(
                    "Product Proposal Trial",
                    previous[0]["name"],
                )
                base_trial.check_permission(
                    "read"
                )

        if base_trial:
            if (
                base_trial.product_proposal
                != product_proposal
            ):
                frappe.throw(
                    _(
                        "Previous Trial belongs to "
                        "another Product Proposal."
                    )
                )
        else:
            source = "proposal"

    trial = frappe.new_doc(
        "Product Proposal Trial"
    )

    trial.product_proposal = (
        product_proposal
    )

    trial.planned_cooking_qty = target_qty

    if base_trial:
        trial.based_on_trial = (
            base_trial.name
        )

        trial.pouch_size = (
            base_trial.pouch_size
        )

        for row in base_trial.items or []:
            _append_snapshot_row(
                trial,
                row,
                line_key=row.line_key,
                qty=_scale_snapshot_qty(
                    base_trial.planned_cooking_qty,
                    target_qty,
                    row.qty,
                ),
            )

        for row in base_trial.get("solid_liquid") or []:
            _append_solid_liquid_snapshot_row(
                trial,
                row,
                base_trial.planned_cooking_qty,
                target_qty,
            )

    elif source == "proposal":
        for row in proposal.pp_items or []:
            _append_snapshot_row(
                trial,
                row,
                line_key=(
                    f"PP:{row.name}"
                    if row.name
                    else None
                ),
                qty=_scale_snapshot_qty(
                    proposal.quantity,
                    target_qty,
                    row.qty,
                ),
            )

        for row in proposal.get("pp_solid_liquid") or []:
            _append_solid_liquid_snapshot_row(
                trial,
                row,
                proposal.quantity,
                target_qty,
            )

    cost_summary = (
        trial.refresh_costs_from_items()
    )

    trial.insert()

    return {
        "name": trial.name,
        "trial_no": trial.trial_no,
        "source": source,
        "items": len(
            trial.items or []
        ),
        "cost_summary": cost_summary,
    }


@frappe.whitelist()
def get_trial_run_cooking_sheet(trial_name, run_no):
    trial = frappe.get_doc("Product Proposal Trial", trial_name)
    trial.check_permission("read")

    run_no = cint(run_no)
    run = next(
        (
            row
            for row in (trial.get("cooking_runs") or [])
            if cint(row.run_no) == run_no
        ),
        None,
    )

    if not run:
        frappe.throw(
            _("Trial Cooking Run {0} does not exist.").format(run_no)
        )

    source_qty = flt(trial.planned_cooking_qty)
    target_qty = flt(run.required_qty)

    if source_qty <= 0:
        frappe.throw(_("Trial Planned Cooking Qty must be greater than zero."))
    if target_qty <= 0:
        frappe.throw(_("Trial Cooking Run Required Qty must be greater than zero."))

    proposal = frappe.db.get_value(
        "Product Proposal",
        trial.product_proposal,
        ["product_name"],
        as_dict=True,
    ) or frappe._dict()

    items = []
    for row in trial.get("items") or []:
        required_qty = _scale_snapshot_qty(
            source_qty,
            target_qty,
            row.qty,
        )
        display_qty, display_uom = format_mass_for_print(required_qty, row.uom)
        items.append(
            frappe._dict(
                item_code=row.item_code,
                item_name=row.item_name,
                uom=row.uom,
                required_qty=required_qty,
                display_qty=display_qty,
                display_uom=display_uom,
            )
        )

    solid_liquid = []
    for row in trial.get("solid_liquid") or []:
        values = {
            fieldname: row.get(fieldname)
            for fieldname in SOLID_LIQUID_SNAPSHOT_FIELDS
        }
        values["total_weight_cook"] = _scale_total_weight_cook(
            source_qty,
            target_qty,
            row.total_weight_cook,
        )
        weight_display, weight_uom = format_mass_for_print(
            row.weight,
            "gm",
        )
        total_display, total_uom = format_mass_for_print(
            values["total_weight_cook"],
            "gm",
        )
        values.update(
            {
                "weight_display": weight_display,
                "weight_display_uom": weight_uom,
                "total_weight_cook_display": total_display,
                "total_weight_cook_display_uom": total_uom,
            }
        )
        solid_liquid.append(frappe._dict(values))

    return frappe._dict(
        trial_name=trial.name,
        trial_no=cint(trial.trial_no),
        trial_title=trial.trial_title or trial.name,
        product_proposal=trial.product_proposal,
        product_name=proposal.get("product_name") or trial.product_proposal,
        run_no=run_no,
        run_date=run.run_date,
        required_qty=target_qty,
        produced_qty=flt(run.produced_qty),
        notes=run.notes,
        items=items,
        solid_liquid=solid_liquid,
    )


@frappe.whitelist()
def get_trial_run_cooking_sheet_html(trial_name, run_no):
    sheet = get_trial_run_cooking_sheet(trial_name, run_no)
    html = frappe.render_template(
        COOKING_SHEET_TEMPLATE,
        {"sheet": sheet},
    )
    return {"html": html}


@frappe.whitelist()
def refresh_trial_costs(trial_name):
    trial = frappe.get_doc(
        "Product Proposal Trial",
        trial_name,
    )

    trial.check_permission("write")

    if trial.status != "Draft":
        frappe.throw(
            _(
                "Costs can only be refreshed "
                "while the Trial is in Draft."
            )
        )

    summary = (
        trial.refresh_costs_from_items()
    )

    trial.save()

    return {
        **summary,
        "total_cost":
            flt(trial.total_cost),
    }


@frappe.whitelist()
def get_bom_uom_conversion_factors(conversions):
    """Resolve BOM import UOM conversions using configured ERPNext data."""
    conversions = frappe.parse_json(conversions)

    if not isinstance(conversions, list):
        frappe.throw(
            frappe._("UOM conversions must be provided as a list.")
        )

    if len(conversions) > 500:
        frappe.throw(
            frappe._("A maximum of 500 UOM conversions can be resolved at once.")
        )

    item_codes = list(
        dict.fromkeys(
            cstr(row.get("item_code") or "").strip()
            for row in conversions
            if isinstance(row, dict) and row.get("item_code")
        )
    )

    items = {}

    if item_codes:
        items = {
            row.name: row
            for row in frappe.get_all(
                "Item",
                filters={"name": ["in", item_codes]},
                fields=["name", "stock_uom", "variant_of"],
                limit_page_length=len(item_codes),
            )
        }

    results = []

    for position, request in enumerate(conversions):
        if not isinstance(request, dict):
            request = {}

        item_code = cstr(request.get("item_code") or "").strip()
        from_uom = cstr(request.get("from_uom") or "").strip()
        to_uom = cstr(request.get("to_uom") or "").strip()
        key = request.get("key", position)

        result = {
            "key": key,
            "item_code": item_code,
            "from_uom": from_uom,
            "to_uom": to_uom,
            "factor": None,
            "status": "Missing Conversion",
        }

        item = items.get(item_code)

        if not item:
            result["status"] = "Missing Item"
            results.append(result)
            continue

        factor = _get_item_uom_conversion_factor(
            item_code,
            from_uom,
            to_uom,
            item.stock_uom,
            item.variant_of,
        )

        if flt(factor) > 0:
            result["factor"] = flt(factor)
            result["status"] = "OK"

        results.append(result)

    return results


def validate_bom_trial_source(doc, method=None):
    proposal_name = cstr(
        getattr(doc, "taj_product_proposal", None)
    ).strip()
    trial_name = cstr(
        getattr(doc, "taj_product_proposal_trial", None)
    ).strip()

    if not proposal_name and not trial_name:
        return

    if not proposal_name or not trial_name:
        frappe.throw(
            _(
                "Both Product Proposal and Product Proposal Trial "
                "are required for a Taj-sourced BOM."
            )
        )

    proposal = frappe.get_doc(
        "Product Proposal", proposal_name
    )
    proposal.check_permission("read")

    if cint(proposal.docstatus) != 1:
        frappe.throw(
            _(
                "Product Proposal {0} must be submitted "
                "before it can be linked to a BOM."
            ).format(proposal.name)
        )

    trial = frappe.get_doc(
        "Product Proposal Trial", trial_name
    )
    trial.check_permission("read")

    if trial.product_proposal != proposal.name:
        frappe.throw(
            _(
                "Trial {0} does not belong to Product Proposal {1}."
            ).format(trial.name, proposal.name)
        )

    if trial.status != "Approved":
        frappe.throw(
            _(
                "Trial {0} must be Approved before it can be "
                "linked to a BOM."
            ).format(trial.name)
        )

    proposal_item = cstr(
        getattr(proposal, "item_code", None)
    ).strip()
    bom_item = cstr(getattr(doc, "item", None)).strip()

    if proposal_item and bom_item != proposal_item:
        frappe.throw(
            _(
                "BOM Item {0} does not match Product Proposal "
                "Item {1}."
            ).format(bom_item, proposal_item)
        )


@frappe.whitelist()
def get_bom_trial_snapshot(
    product_proposal,
    trial_name=None,
):
    """
    Return the formulation snapshot used to populate a BOM.

    Initial fetch:
        Approved + Final Trial only.

    Re-fetch:
        Uses the exact previously selected Trial.
    """
    from frappe.utils import flt

    if not product_proposal:
        frappe.throw(
            frappe._("Product Proposal is required.")
        )

    proposal = frappe.get_doc(
        "Product Proposal",
        product_proposal,
    )

    proposal.check_permission("read")

    if proposal.docstatus != 1:
        frappe.throw(
            frappe._(
                "Product Proposal {0} must be submitted "
                "before it can be used in a BOM."
            ).format(product_proposal)
        )

    if trial_name:
        trial = frappe.get_doc(
            "Product Proposal Trial",
            trial_name,
        )
        trial.check_permission("read")

        if (
            trial.product_proposal
            != proposal.name
        ):
            frappe.throw(
                frappe._(
                    "Trial {0} does not belong to "
                    "Product Proposal {1}."
                ).format(
                    trial.name,
                    proposal.name,
                )
            )

        if trial.status != "Approved":
            frappe.throw(
                frappe._(
                    "Trial {0} is no longer Approved."
                ).format(trial.name)
            )

    else:
        trials = frappe.get_all(
            "Product Proposal Trial",
            filters={
                "product_proposal":
                    proposal.name,
                "status": "Approved",
                "is_final_trial": 1,
            },
            fields=[
                "name",
                "trial_no",
            ],
            order_by="trial_no desc",
            limit_page_length=2,
        )

        if not trials:
            frappe.throw(
                frappe._(
                    "No Approved Final Trial exists "
                    "for Product Proposal {0}."
                ).format(proposal.name),
                title=frappe._(
                    "Final Trial Required"
                ),
            )

        if len(trials) > 1:
            frappe.throw(
                frappe._(
                    "More than one Approved Final Trial "
                    "exists for Product Proposal {0}."
                ).format(proposal.name)
            )

        trial = frappe.get_doc(
            "Product Proposal Trial",
            trials[0].name,
        )
        trial.check_permission("read")

    source_qty = (
        flt(trial.actual_produced_qty)
        or flt(trial.planned_cooking_qty)
        or flt(proposal.quantity)
    )

    if source_qty <= 0:
        frappe.throw(
            frappe._(
                "Trial {0} has no valid produced or "
                "planned quantity for BOM scaling."
            ).format(trial.name)
        )

    item_fields = (
        "line_key",
        "item_code",
        "item_name",
        "qty",
        "uom",
        "operation",
        "procees_type",
        "cooking_type",
        "temperature",
        "duration",
        "pre_bom",
        "notes",
    )

    items = []

    for row in trial.items or []:
        items.append(
            {
                fieldname:
                    row.get(fieldname)
                for fieldname
                in item_fields
            }
        )

    if not items:
        frappe.throw(
            frappe._(
                "Trial {0} has no formulation items."
            ).format(trial.name)
        )

    return {
        "product_proposal":
            proposal.name,
        "trial_name":
            trial.name,
        "trial_no":
            trial.trial_no,
        "trial_title":
            trial.trial_title,
        "status":
            trial.status,
        "is_final_trial":
            trial.is_final_trial,
        "quantity":
            source_qty,
        "quantity_source": (
            "Actual Produced Qty"
            if flt(
                trial.actual_produced_qty
            ) > 0
            else (
                "Planned Cooking Qty"
                if flt(
                    trial.planned_cooking_qty
                ) > 0
                else "Product Proposal Qty"
            )
        ),
        "items":
            items,
    }
