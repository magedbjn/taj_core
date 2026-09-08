import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, nowtime, today

from erpnext.manufacturing.doctype.bom.bom import get_valuation_rate
from erpnext.stock.doctype.item.item import get_uom_conv_factor


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

COMPARE_FIELDS = (
    ("item_code", "Item"),
    ("qty", "Qty"),
    ("uom", "UOM"),
    ("unit_cost", "Unit Cost"),
    ("amount", "Amount"),
    ("operation", "Operation"),
    ("procees_type", "Process Type"),
    ("cooking_type", "Cooking Type"),
    ("temperature", "Temperature"),
    ("duration", "Duration"),
    ("pre_bom", "Preparation BOM"),
    ("notes", "Notes"),
)





def _get_item_uom_factor_to_stock(
    item_code,
    uom,
    stock_uom,
    variant_of=None,
):
    """Return the configured factor from ``uom`` to the Item stock UOM."""
    uom = cstr(uom or "").strip()
    stock_uom = cstr(stock_uom or "").strip()

    if not uom or not stock_uom:
        return None

    if uom == stock_uom:
        return 1.0

    # ERPNext gives Item-specific conversion details priority, including
    # the template conversion for variants.
    for parent in (item_code, variant_of):
        if not parent:
            continue

        factor = frappe.db.get_value(
            "UOM Conversion Detail",
            {
                "parent": parent,
                "uom": uom,
            },
            "conversion_factor",
        )

        if flt(factor) > 0:
            return flt(factor)

    # Fall back to ERPNext global UOM conversions (direct, inverse,
    # or intermediate). Never invent a factor of 1 for missing data.
    factor = get_uom_conv_factor(uom, stock_uom)

    if flt(factor) > 0:
        return flt(factor)

    return None


def _get_trial_conversion_factor(
    item_code,
    uom,
    stock_uom,
    variant_of=None,
):
    """Return the Trial-UOM to stock-UOM factor, or ``None`` if absent."""
    return _get_item_uom_factor_to_stock(
        item_code,
        uom,
        stock_uom,
        variant_of,
    )


def _get_item_uom_conversion_factor(
    item_code,
    from_uom,
    to_uom,
    stock_uom=None,
    variant_of=None,
):
    """Return a configured Item UOM conversion without unsafe assumptions."""
    from_uom = cstr(from_uom or "").strip()
    to_uom = cstr(to_uom or "").strip()

    if not from_uom or not to_uom:
        return None

    if from_uom == to_uom:
        return 1.0

    if not stock_uom:
        item = frappe.db.get_value(
            "Item",
            item_code,
            ["stock_uom", "variant_of"],
            as_dict=True,
        )

        if not item:
            return None

        stock_uom = item.stock_uom
        variant_of = variant_of or item.variant_of

    from_factor = _get_item_uom_factor_to_stock(
        item_code,
        from_uom,
        stock_uom,
        variant_of,
    )
    to_factor = _get_item_uom_factor_to_stock(
        item_code,
        to_uom,
        stock_uom,
        variant_of,
    )

    if flt(from_factor) > 0 and flt(to_factor) > 0:
        return flt(from_factor) / flt(to_factor)

    # A direct global conversion can still be valid even if one of the
    # units is not configured relative to this Item's stock UOM.
    factor = get_uom_conv_factor(from_uom, to_uom)

    if flt(factor) > 0:
        return flt(factor)

    return None


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

    def before_insert(self):
        if not self.posting_date:
            self.posting_date = today()

        if not self.trial_user:
            self.trial_user = frappe.session.user

        if not self.holding_time:
            self.holding_time = nowtime()

        if not self.trial_title:
            self.trial_title = _(
                "Trial {0}"
            ).format(self.trial_no)

    def validate(self):
        self.validate_product_proposal()
        self.validate_based_on_trial()

        self.ensure_line_keys()
        self.validate_line_keys_immutable()

        self.validate_locked_identity()
        self.validate_frozen_snapshot()
        self.invalidate_changed_cost_snapshots()
        self.validate_final_trial()

        self.set_totals()

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

        if (
            old_doc.status != "Draft"
            and self.status == "Draft"
        ):
            frappe.throw(
                _(
                    "A completed Trial cannot be returned "
                    "to Draft. Create a new Trial instead."
                )
            )

        if old_doc.status == "Draft":
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

        parent_rows = frappe.db.sql(
            """
            select docstatus
            from `tabProduct Proposal`
            where name = %s
            for update
            """,
            (self.product_proposal,),
            as_dict=True,
        )

        if (
            not parent_rows
            or cint(parent_rows[0].docstatus) != 1
        ):
            frappe.throw(
                _(
                    "Product Proposal {0} must be submitted "
                    "before a Trial can be marked as Final."
                ).format(self.product_proposal)
            )

        values = [self.product_proposal]
        name_condition = ""

        if self.name:
            name_condition = "and name != %s"
            values.append(self.name)

        existing_rows = frappe.db.sql(
            f"""
            select name
            from `tabProduct Proposal Trial`
            where product_proposal = %s
              and is_final_trial = 1
              {name_condition}
            order by name
            limit 1
            for update
            """,
            tuple(values),
            as_dict=True,
        )

        if existing_rows:
            frappe.throw(
                _(
                    "Final Trial already exists: {0}"
                ).format(existing_rows[0].name)
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
):
    values = {
        fieldname: getattr(
            source_row,
            fieldname,
            None,
        )
        for fieldname in SNAPSHOT_FIELDS
    }

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


@frappe.whitelist()
def create_trial(
    product_proposal,
    source="previous",
    based_on_trial=None,
):
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

    if base_trial:
        trial.based_on_trial = (
            base_trial.name
        )

        trial.planned_cooking_qty = (
            base_trial.planned_cooking_qty
        )

        trial.pouch_size = (
            base_trial.pouch_size
        )

        for row in base_trial.items or []:
            _append_snapshot_row(
                trial,
                row,
                line_key=row.line_key,
            )

    elif source == "proposal":
        trial.planned_cooking_qty = cint(
            proposal.quantity or 0
        )

        for row in proposal.pp_items or []:
            _append_snapshot_row(
                trial,
                row,
                line_key=(
                    f"PP:{row.name}"
                    if row.name
                    else None
                ),
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


def _normal_value(
    fieldname,
    value,
):
    if fieldname in {
        "qty",
        "temperature",
        "duration",
    }:
        return flt(value)

    return cstr(
        value or ""
    )


def _compare_item_rows(
    first,
    second,
):
    first_map = {
        cstr(row.line_key): row
        for row in first.items or []
    }

    second_map = {
        cstr(row.line_key): row
        for row in second.items or []
    }

    ordered_keys = list(
        first_map.keys()
    )

    for key in second_map:
        if key not in first_map:
            ordered_keys.append(key)

    rows = []
    unchanged = 0

    for key in ordered_keys:
        old_row = first_map.get(key)
        new_row = second_map.get(key)

        if old_row is None:
            rows.append({
                "line_key": key,
                "item_code":
                    new_row.item_code,
                "change_type": "Added",
                "changes": [],
                "old_qty": None,
                "new_qty": flt(
                    new_row.qty
                ),
            })
            continue

        if new_row is None:
            rows.append({
                "line_key": key,
                "item_code":
                    old_row.item_code,
                "change_type": "Removed",
                "changes": [],
                "old_qty": flt(
                    old_row.qty
                ),
                "new_qty": None,
            })
            continue

        changes = []

        for fieldname, label in (
            COMPARE_FIELDS
        ):
            old_value = _normal_value(
                fieldname,
                old_row.get(fieldname),
            )

            new_value = _normal_value(
                fieldname,
                new_row.get(fieldname),
            )

            if old_value != new_value:
                changes.append({
                    "fieldname":
                        fieldname,
                    "label": label,
                    "old": old_value,
                    "new": new_value,
                })

        if changes:
            rows.append({
                "line_key": key,
                "item_code": (
                    new_row.item_code
                    or old_row.item_code
                ),
                "change_type":
                    "Changed",
                "changes": changes,
                "old_qty": flt(
                    old_row.qty
                ),
                "new_qty": flt(
                    new_row.qty
                ),
            })
        else:
            unchanged += 1

    return rows, unchanged


def _sensory_summary(
    product_proposal,
    trial_name,
):
    evaluations = frappe.get_all(
        "Product Proposal Sensory Evaluation",
        filters={
            "parent":
                product_proposal,
            "parenttype":
                "Product Proposal",
            "parentfield":
                "pp_sensory_evaluation",
            "trial_document":
                trial_name,
        },
        fields=[
            "evaluation_date",
            "your_name",
            "appearance",
            "texture",
            "taste",
            "spicy",
            "comment",
            "final_status",
        ],
        order_by="idx asc",
    )

    def average(fieldname):
        values = [
            flt(row.get(fieldname))
            for row in evaluations
            if row.get(fieldname)
            not in (
                None,
                "",
            )
        ]

        if not values:
            return None

        return round(
            sum(values) / len(values),
            2,
        )

    statuses = {}

    for row in evaluations:
        status = cstr(
            row.get(
                "final_status"
            )
            or ""
        )

        if not status:
            continue

        statuses[status] = (
            statuses.get(status, 0)
            + 1
        )

    return {
        "count": len(evaluations),
        "appearance":
            average("appearance"),
        "texture":
            average("texture"),
        "taste":
            average("taste"),
        "final_status_counts":
            statuses,
        "evaluations":
            evaluations,
    }


@frappe.whitelist()
def compare_trials(
    first_trial,
    second_trial,
):
    first = frappe.get_doc(
        "Product Proposal Trial",
        first_trial,
    )
    first.check_permission("read")

    second = frappe.get_doc(
        "Product Proposal Trial",
        second_trial,
    )
    second.check_permission("read")

    if (
        first.product_proposal
        != second.product_proposal
    ):
        frappe.throw(
            _(
                "Both Trials must belong to "
                "the same Product Proposal."
            )
        )

    proposal = frappe.get_doc(
        "Product Proposal",
        first.product_proposal,
    )
    proposal.check_permission("read")

    rows, unchanged = (
        _compare_item_rows(
            first,
            second,
        )
    )

    return {
        "product_proposal":
            first.product_proposal,
        "first": {
            "name": first.name,
            "trial_no":
                first.trial_no,
            "title":
                first.trial_title,
            "status":
                first.status,
            "total_items":
                first.total_items,
            "total_cost":
                first.total_cost,
            "sensory":
                _sensory_summary(
                    first.product_proposal,
                    first.name,
                ),
        },
        "second": {
            "name": second.name,
            "trial_no":
                second.trial_no,
            "title":
                second.trial_title,
            "status":
                second.status,
            "total_items":
                second.total_items,
            "total_cost":
                second.total_cost,
            "sensory":
                _sensory_summary(
                    second.product_proposal,
                    second.name,
                ),
        },
        "changes": rows,
        "changed_count":
            len(rows),
        "unchanged_count":
            unchanged,
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
