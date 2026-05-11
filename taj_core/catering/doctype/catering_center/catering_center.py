from collections import defaultdict

import frappe
from frappe.model.document import Document
from frappe.utils import flt, cint


class CateringCenter(Document):
    def validate(self):
        self.calculate_totals()
        self.validate_buffet_rows()
        self.validate_buffet_exceptions()

    def calculate_totals(self):
        total = 0

        for row in self.get("buffet") or []:
            if row.is_closed:
                continue

            total += flt(row.person_qty or 0)

        self.total_buffet_person_qty = total
        self.person_qty_difference = flt(self.person_qty or 0) - total

    def validate_buffet_rows(self):
        seen = set()

        for row in self.get("buffet") or []:
            if not row.buffet:
                frappe.throw(f"Buffet Row #{row.idx}: Buffet is required.")

            if not row.buffet_company:
                frappe.throw(f"Buffet Row #{row.idx}: Buffet Company is required.")

            if flt(row.person_qty or 0) < 0:
                frappe.throw(f"Buffet Row #{row.idx}: Person Qty cannot be negative.")

            key = (row.buffet, row.buffet_company)

            if key in seen:
                frappe.throw(
                    f"Buffet Row #{row.idx}: Duplicate Buffet / Company is not allowed: "
                    f"{row.buffet} / {row.buffet_company}"
                )

            seen.add(key)

    def validate_buffet_exceptions(self):
        open_buffet_map = {}
        open_buffets = set()

        for row in self.get("buffet") or []:
            if row.is_closed:
                continue

            if flt(row.person_qty or 0) <= 0:
                continue

            if not row.buffet:
                continue

            open_buffets.add(row.buffet)

            if row.buffet_company:
                open_buffet_map[(row.buffet, row.buffet_company)] = row

        seen_standard_exceptions = set()
        seen_distribution_locations = set()
        distribution_groups = defaultdict(list)
        standard_rules = []

        for ex in self.get("buffet_exception") or []:
            self.validate_single_exception(
                ex=ex,
                open_buffets=open_buffets,
                open_buffet_map=open_buffet_map,
                seen_standard_exceptions=seen_standard_exceptions,
                seen_distribution_locations=seen_distribution_locations,
                distribution_groups=distribution_groups,
                standard_rules=standard_rules,
            )

        self.validate_distribution_conflicts(
            distribution_groups=distribution_groups,
            standard_rules=standard_rules,
        )

        self.validate_distribution_groups(distribution_groups)

    def validate_single_exception(
        self,
        ex,
        open_buffets,
        open_buffet_map,
        seen_standard_exceptions,
        seen_distribution_locations,
        distribution_groups,
        standard_rules,
    ):
        if not ex.service_period:
            frappe.throw(f"Exception Row #{ex.idx}: Service Period is required.")

        if not ex.meal_type:
            frappe.throw(f"Exception Row #{ex.idx}: Meal Type is required.")

        if not ex.apply_to:
            frappe.throw(f"Exception Row #{ex.idx}: Apply To is required.")

        if ex.apply_to not in ["All Buffets", "Buffet", "Company"]:
            frappe.throw(
                f"Exception Row #{ex.idx}: Apply To must be All Buffets, Buffet, or Company."
            )

        if not ex.exception_type:
            frappe.throw(f"Exception Row #{ex.idx}: Exception Type is required.")

        if ex.exception_type not in ["Distribution", "Closed", "Percent", "Fixed Qty"]:
            frappe.throw(
                f"Exception Row #{ex.idx}: Exception Type must be Distribution, Closed, Percent, or Fixed Qty."
            )

        if ex.exception_type == "Distribution":
            self.validate_distribution_exception(
                ex=ex,
                open_buffets=open_buffets,
                open_buffet_map=open_buffet_map,
                seen_distribution_locations=seen_distribution_locations,
                distribution_groups=distribution_groups,
            )
            return

        self.validate_standard_exception(
            ex=ex,
            open_buffets=open_buffets,
            open_buffet_map=open_buffet_map,
            seen_standard_exceptions=seen_standard_exceptions,
            standard_rules=standard_rules,
        )

    def validate_distribution_exception(
        self,
        ex,
        open_buffets,
        open_buffet_map,
        seen_distribution_locations,
        distribution_groups,
    ):
        if ex.apply_to != "Company":
            frappe.throw(
                f"Exception Row #{ex.idx}: Distribution must apply to Company."
            )

        if not ex.buffet:
            frappe.throw(
                f"Exception Row #{ex.idx}: Buffet is required for Distribution."
            )

        if ex.buffet not in open_buffets:
            frappe.throw(
                f"Exception Row #{ex.idx}: Buffet {ex.buffet} is closed or not available "
                f"in the base Buffet table."
            )

        if not ex.buffet_company:
            frappe.throw(
                f"Exception Row #{ex.idx}: Buffet Company is required for Distribution."
            )

        if (ex.buffet, ex.buffet_company) not in open_buffet_map:
            frappe.throw(
                f"Exception Row #{ex.idx}: Company {ex.buffet_company} is not available "
                f"or is closed in Buffet {ex.buffet}."
            )

        if not ex.location:
            frappe.throw(
                f"Exception Row #{ex.idx}: Location is required for Distribution."
            )

        if ex.location not in ["Mina", "Arafat"]:
            frappe.throw(
                f"Exception Row #{ex.idx}: Location must be Mina or Arafat."
            )

        if flt(ex.person_qty or 0) <= 0:
            frappe.throw(
                f"Exception Row #{ex.idx}: Person Qty must be greater than zero for Distribution."
            )

        duplicate_key = (
            ex.service_period,
            ex.meal_type,
            ex.buffet,
            ex.buffet_company,
            ex.location,
        )

        if duplicate_key in seen_distribution_locations:
            frappe.throw(
                f"Exception Row #{ex.idx}: Duplicate Distribution row for the same "
                f"Service Period / Meal Type / Buffet / Company / Location is not allowed."
            )

        seen_distribution_locations.add(duplicate_key)

        ex.percent = 0
        ex.fixed_qty = 0

        group_key = (
            ex.service_period,
            ex.meal_type,
            ex.buffet,
            ex.buffet_company,
        )

        distribution_groups[group_key].append(ex)

    def validate_standard_exception(
        self,
        ex,
        open_buffets,
        open_buffet_map,
        seen_standard_exceptions,
        standard_rules,
    ):
        ex.location = None
        ex.person_qty = 0

        if ex.apply_to == "All Buffets":
            ex.buffet = None
            ex.buffet_company = None

            duplicate_key = (
                ex.service_period,
                ex.meal_type,
                ex.apply_to,
                "",
                "",
            )

        elif ex.apply_to == "Buffet":
            if not ex.buffet:
                frappe.throw(f"Exception Row #{ex.idx}: Buffet is required.")

            if ex.buffet not in open_buffets:
                frappe.throw(
                    f"Exception Row #{ex.idx}: Buffet {ex.buffet} is closed or not available "
                    f"in the base Buffet table."
                )

            ex.buffet_company = None

            duplicate_key = (
                ex.service_period,
                ex.meal_type,
                ex.apply_to,
                ex.buffet,
                "",
            )

        elif ex.apply_to == "Company":
            if not ex.buffet:
                frappe.throw(f"Exception Row #{ex.idx}: Buffet is required.")

            if ex.buffet not in open_buffets:
                frappe.throw(
                    f"Exception Row #{ex.idx}: Buffet {ex.buffet} is closed or not available "
                    f"in the base Buffet table."
                )

            if not ex.buffet_company:
                frappe.throw(
                    f"Exception Row #{ex.idx}: Buffet Company is required when Apply To is Company."
                )

            if (ex.buffet, ex.buffet_company) not in open_buffet_map:
                frappe.throw(
                    f"Exception Row #{ex.idx}: Company {ex.buffet_company} is not available "
                    f"or is closed in Buffet {ex.buffet}."
                )

            duplicate_key = (
                ex.service_period,
                ex.meal_type,
                ex.apply_to,
                ex.buffet,
                ex.buffet_company,
            )

        if duplicate_key in seen_standard_exceptions:
            frappe.throw(
                f"Exception Row #{ex.idx}: Duplicate exception for the same Service Period / "
                f"Meal Type / Apply To / Buffet / Company."
            )

        seen_standard_exceptions.add(duplicate_key)

        base_qty = self.get_exception_base_qty(ex)

        if base_qty <= 0:
            frappe.throw(
                f"Exception Row #{ex.idx}: Base Qty is zero. Please check Buffet setup."
            )

        if ex.exception_type == "Closed":
            ex.percent = 0
            ex.fixed_qty = 0

        elif ex.exception_type == "Percent":
            ex.fixed_qty = 0

            if flt(ex.percent or 0) <= 0:
                frappe.throw(
                    f"Exception Row #{ex.idx}: Percent must be greater than 0."
                )

            if flt(ex.percent or 0) > 100:
                frappe.throw(
                    f"Exception Row #{ex.idx}: Percent cannot be greater than 100."
                )

        elif ex.exception_type == "Fixed Qty":
            ex.percent = 0

            if flt(ex.fixed_qty or 0) < 0:
                frappe.throw(
                    f"Exception Row #{ex.idx}: Fixed Qty cannot be negative."
                )

            if flt(ex.fixed_qty or 0) > flt(base_qty):
                frappe.throw(
                    f"Exception Row #{ex.idx}: Fixed Qty cannot be greater than base qty "
                    f"({cint(base_qty)})."
                )

        standard_rules.append(
            {
                "service_period": ex.service_period,
                "meal_type": ex.meal_type,
                "apply_to": ex.apply_to,
                "buffet": ex.buffet or "",
                "buffet_company": ex.buffet_company or "",
                "idx": ex.idx,
            }
        )

        self.set_exception_preview_fields(ex, base_qty)

    def validate_distribution_conflicts(self, distribution_groups, standard_rules):
        for group_key in distribution_groups:
            service_period, meal_type, buffet, buffet_company = group_key

            for rule in standard_rules:
                if rule["service_period"] != service_period:
                    continue

                if rule["meal_type"] != meal_type:
                    continue

                if rule["apply_to"] == "All Buffets":
                    frappe.throw(
                        f"Distribution for {service_period} / {meal_type} / "
                        f"{buffet} / {buffet_company} conflicts with an All Buffets exception."
                    )

                if rule["apply_to"] == "Buffet" and rule["buffet"] == buffet:
                    frappe.throw(
                        f"Distribution for {service_period} / {meal_type} / "
                        f"{buffet} / {buffet_company} conflicts with a Buffet exception."
                    )

                if (
                    rule["apply_to"] == "Company"
                    and rule["buffet"] == buffet
                    and rule["buffet_company"] == buffet_company
                ):
                    frappe.throw(
                        f"Distribution for {service_period} / {meal_type} / "
                        f"{buffet} / {buffet_company} conflicts with another exception."
                    )

    def validate_distribution_groups(self, distribution_groups):
        for group_key, rows in distribution_groups.items():
            service_period, meal_type, buffet, buffet_company = group_key

            base_qty = self.get_base_buffet_company_qty(
                buffet=buffet,
                buffet_company=buffet_company,
            )

            total_distribution_qty = 0

            for row in rows:
                total_distribution_qty += flt(row.person_qty or 0)

            if total_distribution_qty > base_qty:
                frappe.throw(
                    f"Distribution for {service_period} / {meal_type} / {buffet} / "
                    f"{buffet_company} cannot exceed base qty ({cint(base_qty)}). "
                    f"Current distributed qty is ({cint(total_distribution_qty)})."
                )

            self.set_distribution_preview_fields(
                rows=rows,
                base_qty=base_qty,
                total_distribution_qty=total_distribution_qty,
            )

    def get_base_buffet_company_qty(self, buffet, buffet_company):
        total = 0

        for row in self.get("buffet") or []:
            if row.is_closed:
                continue

            if flt(row.person_qty or 0) <= 0:
                continue

            if row.buffet == buffet and row.buffet_company == buffet_company:
                total += flt(row.person_qty or 0)

        return total

    def get_exception_base_qty(self, ex):
        total = 0

        for row in self.get("buffet") or []:
            if row.is_closed:
                continue

            if flt(row.person_qty or 0) <= 0:
                continue

            if ex.apply_to == "All Buffets":
                total += flt(row.person_qty or 0)

            elif ex.apply_to == "Buffet":
                if row.buffet == ex.buffet:
                    total += flt(row.person_qty or 0)

            elif ex.apply_to == "Company":
                if row.buffet == ex.buffet and row.buffet_company == ex.buffet_company:
                    total += flt(row.person_qty or 0)

        return total

    def set_exception_preview_fields(self, ex, base_qty):
        base_qty = flt(base_qty or 0)
        effective_qty = base_qty
        reduction_qty = 0

        if ex.exception_type == "Closed":
            effective_qty = 0
            reduction_qty = base_qty

        elif ex.exception_type == "Percent":
            reduction_percent = flt(ex.percent or 0)
            effective_qty = base_qty * (1 - reduction_percent / 100)
            reduction_qty = base_qty - effective_qty

        elif ex.exception_type == "Fixed Qty":
            effective_qty = flt(ex.fixed_qty or 0)
            reduction_qty = base_qty - effective_qty

        if effective_qty < 0:
            effective_qty = 0

        if reduction_qty < 0:
            reduction_qty = 0

        ex.base_qty = round(base_qty)
        ex.reduction_qty = round(reduction_qty)
        ex.effective_qty = round(effective_qty)

        if ex.apply_to == "All Buffets":
            target = "All Buffets"
        elif ex.apply_to == "Buffet":
            target = ex.buffet
        elif ex.apply_to == "Company" and ex.buffet_company:
            target = f"{ex.buffet_company} in {ex.buffet}"
        else:
            target = ex.buffet or ""

        if ex.exception_type == "Closed":
            ex.impact_summary = (
                f"{ex.service_period} {ex.meal_type}: {target} will be closed. "
                f"Final Qty: 0."
            )

        elif ex.exception_type == "Percent":
            ex.impact_summary = (
                f"{ex.service_period} {ex.meal_type}: {target} will be reduced by "
                f"{flt(ex.percent)}%. Final Qty: {round(effective_qty)}."
            )

        elif ex.exception_type == "Fixed Qty":
            ex.impact_summary = (
                f"{ex.service_period} {ex.meal_type}: {target} will use fixed qty "
                f"{round(effective_qty)}."
            )

    def set_distribution_preview_fields(self, rows, base_qty, total_distribution_qty):
        base_qty = flt(base_qty or 0)
        total_distribution_qty = flt(total_distribution_qty or 0)
        reduction_qty = base_qty - total_distribution_qty

        if reduction_qty < 0:
            reduction_qty = 0

        breakdown_map = defaultdict(float)

        for row in rows:
            if row.location:
                breakdown_map[row.location] += flt(row.person_qty or 0)

        breakdown_parts = []

        for location in ["Mina", "Arafat"]:
            if breakdown_map.get(location):
                breakdown_parts.append(f"{location}: {cint(breakdown_map[location])}")

        for location, qty in breakdown_map.items():
            if location not in ["Mina", "Arafat"]:
                breakdown_parts.append(f"{location}: {cint(qty)}")

        breakdown = ", ".join(breakdown_parts)

        for row in rows:
            row.base_qty = round(base_qty)
            row.effective_qty = round(total_distribution_qty)
            row.reduction_qty = round(reduction_qty)

            target = f"{row.buffet_company} in {row.buffet}"

            row.impact_summary = (
                f"{row.service_period} {row.meal_type}: {target} distributed "
                f"{round(total_distribution_qty)} of {round(base_qty)}. "
                f"{row.location}: {round(flt(row.person_qty or 0))}."
            )

            if breakdown:
                row.impact_summary += f" Breakdown: {breakdown}."

            row.impact_summary += f" Difference: {round(reduction_qty)}."

    def get_effective_qty_for_exception(self, base_qty, ex):
        base_qty = flt(base_qty or 0)

        if not ex:
            return base_qty

        if ex.exception_type == "Distribution":
            return flt(ex.person_qty or 0)

        if ex.exception_type == "Closed":
            return 0

        if ex.exception_type == "Percent":
            reduction_percent = flt(ex.percent or 0)
            return base_qty * (1 - reduction_percent / 100)

        if ex.exception_type == "Fixed Qty":
            return flt(ex.fixed_qty or 0)

        return base_qty