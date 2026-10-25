"""Pure business rules: required brand is a filter, not an Item variant.

This module deliberately imports no Frappe objects.  It can be tested off-site.
"""
from collections import defaultdict


class MixedBrandRequirementError(ValueError):
    def __init__(self, item_code):
        self.item_code = item_code
        super().__init__(item_code)


def brand(value):
    return (value or "").strip()


def same_requirement(source, target):
    return brand(source) == brand(target)


def allocate_requirements(requirements, balances):
    """Allocate scarce brand-specific stock before flexible requirements.

    requirements: iterable of {item_code, required_brand, warehouse, qty, ...}
    balances: mapping {(item_code, warehouse, actual_brand): stock_qty}

    Returns a new list preserving input order with available_qty / shortage_qty.
    All values are *stock UOM*.  `balances` must already exclude expired,
    blocked and reserved batches.  Demand cannot use a brand's stock twice.
    """
    available = defaultdict(float)
    for key, quantity in balances.items():
        available[key] += max(0.0, float(quantity or 0))
    output = [dict(row) for row in requirements]
    for row in output:
        row["available_qty"] = 0.0
        row["shortage_qty"] = max(0.0, float(row.get("qty") or 0))

    # Required brands first.  Stable order within each priority preserves dates
    # already assigned by the caller, without accidentally prioritizing 'Any'.
    order = sorted(range(len(output)), key=lambda i: not bool(brand(output[i].get("required_brand"))))
    for idx in order:
        row = output[idx]
        code, warehouse = row["item_code"], row["warehouse"]
        requirement = brand(row.get("required_brand"))
        need = row["shortage_qty"]
        eligible = [key for key in available if key[0] == code and key[1] == warehouse and (not requirement or key[2] == requirement)]
        # Deterministic ordering of candidate brands; batch FEFO stays with ERPNext.
        eligible.sort(key=lambda key: key[2])
        for key in eligible:
            used = min(need, max(0.0, available[key]))
            if used <= 0:
                continue
            available[key] -= used
            need -= used
            row["available_qty"] += used
            if need <= 1e-9:
                break
        row["shortage_qty"] = max(0.0, need)
    return output


def unique_brand_requirements(rows):
    """Return item -> brand and reject ambiguous requirements for one item.

    Standard Work Order Item uses Item Code to merge raw material quantities;
    mixing specific and flexible brands for the same item is ambiguous there.
    """
    requirements = {}
    for row in rows:
        code = row["item_code"]
        value = brand(row.get("required_brand"))
        if code in requirements and requirements[code] != value:
            raise MixedBrandRequirementError(code)
        requirements[code] = value
    return requirements
