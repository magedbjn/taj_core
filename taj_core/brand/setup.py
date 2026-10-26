"""Idempotent Frappe v16 metadata install and read-only integrity checks.

No core edits and no stock/accounting data writes. Existing Item Tracking
values are preserved; an Item field_order Property Setter may be created.
"""
import importlib
import json

import frappe
from frappe import _

BRAND = {"fieldtype": "Link", "options": "Brand", "label": "Required Brand", "read_only": 1}
ACTUAL = {"fieldtype": "Link", "options": "Brand", "label": "Actual Brand"}

FIELDS = {
    "BOM Item": {
        "taj_required_brand": {**BRAND, "read_only": 0, "insert_after": "item_code", "description": "Blank means any approved actual Brand."},
    },
    "Material Request Plan Item": {
        "taj_required_brand": {**BRAND, "insert_after": "item_code"},
        "taj_available_brand_qty": {"fieldtype": "Float", "label": "Eligible Batch Qty", "read_only": 1, "insert_after": "taj_required_brand"},
    },
    "Material Request Item": {"taj_required_brand": {**BRAND, "insert_after": "item_code"}},
    "Pick List Item": {"taj_required_brand": {**BRAND, "insert_after": "item_code", "description": "Required Brand from the linked Work Order BOM; read only."}},
    "Work Order Item": {"taj_required_brand": {**BRAND, "insert_after": "item_code", "in_list_view": 1}},
    "Stock Entry Detail": {"taj_required_brand": {**BRAND, "insert_after": "item_code"}},
    "Purchase Order Item": {"taj_required_brand": {**BRAND, "insert_after": "item_code"}},
    "Purchase Receipt Item": {"taj_required_brand": {**BRAND, "insert_after": "item_code"}},
    "Purchase Invoice Item": {"taj_required_brand": {**BRAND, "insert_after": "item_code"}},
    "Supplier Quotation Item": {"taj_required_brand": {**BRAND, "insert_after": "item_code"}},
    "Request for Quotation Item": {
        "taj_required_brand": {**BRAND, "insert_after": "item_code"},
    },
    "Batch": {"taj_brand": {**ACTUAL, "insert_after": "supplier", "description": "Physical Brand received; immutable after stock movements."},
    },
    "Item": {
        # A tracked Item may contain multiple actual Brands at Batch level.
        # Keep the standard Item.brand unmodified and place the flag beneath it.
        "taj_brand_tracking": {"fieldtype": "Check", "label": "Brand Tracking", "insert_after": "brand", "default": "0",
                               "read_only_depends_on": "eval:!doc.has_batch_no || !doc.is_stock_item"},
    },
}



# Commercial rows now use the ERPNext native `brand` field. The historical
# `taj_actual_brand` columns have no live values on the reviewed test site;
# keep the columns for reversibility, but stop exposing or creating them.
LEGACY_COMMERCIAL_ACTUAL = (
    "Supplier Quotation Item", "Purchase Order Item",
    "Purchase Receipt Item", "Purchase Invoice Item",
)


def _retire_unused_purchase_actual_fields():
    """Hide empty obsolete Custom Fields only; never delete or rewrite values."""
    retired = []
    for dt in LEGACY_COMMERCIAL_ACTUAL:
        custom_name = frappe.db.get_value(
            "Custom Field", {"dt": dt, "fieldname": "taj_actual_brand"}, "name"
        )
        if not custom_name:
            continue
        # Doctype names come only from the fixed tuple above. A populated
        # legacy column requires manual review, not an automated migration.
        filled = frappe.db.sql(
            "SELECT COUNT(*) FROM `tab{}` WHERE IFNULL(`taj_actual_brand`, '') <> ''".format(dt)
        )[0][0]
        if filled:
            frappe.throw(_(
                "Legacy {0}.taj_actual_brand contains {1} values; "
                "review them before hiding this field."
            ).format(dt, filled))
        field = frappe.get_doc("Custom Field", custom_name)
        if not field.hidden or not field.read_only:
            field.hidden = 1
            field.read_only = 1
            field.save()
            retired.append(dt + ".taj_actual_brand")
    return retired

def _batch_brand_source_from_fields(fields):
    """Choose one Batch actual-brand source, never create a shadow of existing data.

    `taj_brand` is the canonical physical Batch Brand, including fresh sites.
    Existing sites with only legacy `taj_actual_brand` remain readable until an
    explicit migration.  Having both fields is always unsafe.
    """
    names = {field.get("fieldname"): field for field in fields}
    errors = []
    for name in ("taj_brand", "taj_actual_brand"):
        field = names.get(name)
        if field and (field.get("fieldtype") != "Link" or field.get("options") != "Brand"):
            errors.append("Batch.{0} must be Link -> Brand; existing field will not be altered".format(name))
    if names.get("taj_brand") and names.get("taj_actual_brand"):
        errors.append("Both Batch.taj_brand and Batch.taj_actual_brand exist; manual data/source review needed")
    for field in fields:
        if field.get("fieldtype") == "Link" and field.get("options") == "Brand" and field.get("fieldname") not in ("taj_brand", "taj_actual_brand"):
            errors.append("Another Batch Brand Link needs review: Batch.{0}".format(field.get("fieldname")))
    selected = "taj_actual_brand" if names.get("taj_actual_brand") and not names.get("taj_brand") else "taj_brand"
    return selected, errors


def batch_brand_field():
    """Canonical physical Batch Brand field for this site (metadata only)."""
    meta = frappe.get_meta("Batch")
    fields = []
    for fieldname in ("taj_brand", "taj_actual_brand"):
        df = meta.get_field(fieldname)
        if df:
            fields.append({"fieldname": df.fieldname, "fieldtype": df.fieldtype, "options": df.options})
    selected, errors = _batch_brand_source_from_fields(fields)
    if errors:
        frappe.throw(_("Unsafe Batch Brand configuration: {0}").format("; ".join(errors)))
    return selected


def _site_fields():
    """Use canonical Batch.taj_brand immediately after the Supplier field.

    A legacy site containing only Batch.taj_actual_brand is left unchanged
    until its actual-brand data has been reviewed and migrated explicitly.
    """
    selected = batch_brand_field()
    result = {dt: dict(fields) for dt, fields in FIELDS.items()}
    if selected == "taj_actual_brand":
        result["Batch"] = {}
    return result


def _batch_brand_diagnostic():
    rows = frappe.get_all(
        "Custom Field", filters={"dt": "Batch"},
        fields=["fieldname", "fieldtype", "options", "label", "read_only"],
        limit_page_length=1000,
    )
    selected, errors = _batch_brand_source_from_fields(rows)
    if not errors and frappe.get_meta("Batch").has_field(selected):
        # Count only; no historical Batch or Item values are read/modified.
        # The field is strictly selected from two hard-coded identifiers.
        counts = frappe.db.sql(
            """SELECT COUNT(*) AS total_batches,
                 COALESCE(SUM(CASE WHEN IFNULL(b.`{field}`, '') <> '' THEN 1 ELSE 0 END), 0) AS populated,
                 COALESCE(SUM(CASE WHEN IFNULL(b.`{field}`, '') <> '' AND br.name IS NULL THEN 1 ELSE 0 END), 0) AS invalid_brands
                 FROM `tabBatch` b LEFT JOIN `tabBrand` br ON br.name = b.`{field}`""".format(field=selected),
            as_dict=True,
        )[0]
        if counts.get("invalid_brands"):
            errors.append("Batch.{0} has {1} values not linked to a valid Brand".format(selected, counts.get("invalid_brands")))
        return {"selected_field": selected, "reused_existing_field": selected == "taj_brand", "counts": counts, "errors": errors}
    return {"selected_field": selected, "reused_existing_field": selected == "taj_brand", "counts": None, "errors": errors}


def _validate_version():
    versions = {}
    for package in ("frappe", "erpnext"):
        versions[package] = getattr(importlib.import_module(package), "__version__", "unknown")
    if any(not str(v).startswith("16.") for v in versions.values()):
        frappe.throw(_("This package requires Frappe / ERPNext v16; detected {0}").format(versions))
    return versions


def _validate_meta():
    problems = []
    for dt, fields in _site_fields().items():
        if not frappe.db.exists("DocType", dt):
            problems.append("Missing DocType: " + dt)
            continue
        for name, spec in fields.items():
            custom_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": name}, "name")
            if custom_name:
                existing = frappe.db.get_value("Custom Field", custom_name, ["fieldtype", "options"], as_dict=True)
                if existing.fieldtype != spec["fieldtype"]:
                    problems.append("Type conflict: " + dt + "." + name)
                if spec["fieldtype"] == "Link" and existing.options != "Brand":
                    problems.append("Link conflict: " + dt + "." + name)
            elif frappe.get_meta(dt).has_field(name):
                problems.append("Standard field conflicts with custom field: " + dt + "." + name)
    problems.extend(_batch_brand_diagnostic()["errors"])
    problems.extend(_item_layout_blockers())
    for fieldname in frappe.get_all(
        "Custom Field", filters={"dt": "Item", "insert_after": "taj_brand_tracking"}, pluck="fieldname"
    ):
        problems.append("Item layout field depends on taj_brand_tracking ordering: " + fieldname)
    return problems


def _item_brand_usage():
    if not frappe.get_meta("Item").has_field("taj_brand_tracking"):
        return {"flagged_items": 0, "flagged_without_batches": 0}
    rows = frappe.db.sql("""SELECT COUNT(*) AS flagged_items,
        COALESCE(SUM(CASE WHEN has_batch_no=0 THEN 1 ELSE 0 END),0) AS flagged_without_batches,
        COALESCE(SUM(CASE WHEN IFNULL(brand,'')!='' THEN 1 ELSE 0 END),0) AS flagged_with_item_master_brand
        FROM `tabItem` WHERE IFNULL(taj_brand_tracking,0)=1""", as_dict=True)
    return rows[0] if rows else {}


def _ledger_snapshot():
    # Read-only totals prove the install itself did not post quantity/value.
    stock = frappe.db.sql("""SELECT COUNT(*) AS rows_count,
        COALESCE(SUM(actual_qty), 0) AS total_qty,
        COALESCE(SUM(stock_value_difference), 0) AS stock_value_delta
        FROM `tabStock Ledger Entry`""", as_dict=True)[0]
    gl = frappe.db.sql("""SELECT COUNT(*) AS rows_count,
        COALESCE(SUM(debit), 0) AS debit,
        COALESCE(SUM(credit), 0) AS credit
        FROM `tabGL Entry`""", as_dict=True)[0]
    return {"stock_ledger": stock, "general_ledger": gl}


def preflight():
    versions = _validate_version()
    problems = _validate_meta()
    usage = _item_brand_usage()
    values = {
        "versions": versions,
        "errors": problems,
        "batch_brand_source": _batch_brand_diagnostic(),
        "item_brand_tracking": usage,
        "existing_item_field": frappe.db.get_value(
            "Custom Field", {"dt": "Item", "fieldname": "taj_brand_tracking"},
            ["name", "fieldtype", "insert_after"], as_dict=True
        ),
        "existing_column": frappe.db.get_value(
            "Custom Field", {"dt": "Item", "fieldname": "taj_brand_column"},
            ["name", "fieldtype", "insert_after"], as_dict=True
        ),
        "enforcement_mode": "Item.taj_brand_tracking",
        "ledger_snapshot": _ledger_snapshot(),
    }
    print("TAJ BRAND PREFLIGHT (READ ONLY):", frappe.as_json(values, indent=2))
    if problems:
        frappe.throw(_("Brand metadata conflicts detected. No changes applied: {0}").format(", ".join(problems)))
    return values


def apply():
    """Only creates Custom Fields and repositions Item metadata. No stock updates."""
    before = preflight()
    before_count = before["item_brand_tracking"]
    before_ledger = before["ledger_snapshot"]
    created = []
    changed = []
    for dt, fields in _site_fields().items():
        for name, spec in fields.items():
            existing_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": name}, "name")
            if existing_name:
                field = frappe.get_doc("Custom Field", existing_name)
                wanted = {}
                # Preserve existing Item tracking options and *all stored values*;
                # only its layout is changed.  Other fields follow the new contract.
                for property_name in (
                    ("insert_after", "read_only_depends_on") if dt == "Item"
                    else ("insert_after", "read_only", "label") if dt == "Batch"
                    else ("insert_after", "read_only", "in_list_view") if dt == "Work Order Item"
                    else ("insert_after", "read_only")
                ):
                    if property_name in spec and field.get(property_name) != spec[property_name]:
                        wanted[property_name] = spec[property_name]
                if wanted:
                    field.update(wanted)
                    field.save()
                    changed.append(dt + "." + name)
                continue
            field = frappe.get_doc({"doctype": "Custom Field", "dt": dt, "fieldname": name, **spec})
            field.insert()
            created.append(dt + "." + name)
    for dt in FIELDS:
        frappe.clear_cache(doctype=dt)
    # Stop showing redundant empty commercial Actual Brand inputs, while
    # preserving their Custom Field records and any historical columns.
    hidden_legacy_actual = _retire_unused_purchase_actual_fields()
    # Reconcile an existing Item field_order setter and remove the old layout
    # Column Break as part of the same metadata-only installation.
    apply_item_layout()
    frappe.clear_cache(doctype="Item")
    after_count = _item_brand_usage()
    if before_count.get("flagged_items") != after_count.get("flagged_items"):
        frappe.throw(_("Unexpected Item Brand Tracking values changed. Stop metadata installation."))
    if _ledger_snapshot() != before_ledger:
        frappe.throw(_("Stock/GL Ledger totals changed while installing metadata. Investigate concurrent activity."))
    # Frappe owns the transaction (bench execute / migrate / web request).
    print("APPLY OK:", frappe.as_json({"created": created, "repositioned": changed,
        "hidden_legacy_actual": hidden_legacy_actual,
        "flagged_before": before_count, "flagged_after": after_count}, indent=2))
    return {"created": created, "repositioned": changed,
            "hidden_legacy_actual": hidden_legacy_actual}


def audit_integrity():
    result = {"issues": [], "batches_without_verified_actual_brand": 0, "required_bom_lines": 0}
    if not frappe.get_meta("BOM Item").has_field("taj_required_brand"):
        return result
    requirements = frappe.get_all(
        "BOM Item", filters={"taj_required_brand": ["is", "set"]},
        fields=["name", "parent", "item_code", "taj_required_brand"], limit_page_length=100000
    )
    result["required_bom_lines"] = len(requirements)
    for row in requirements:
        item = frappe.get_cached_value(
            "Item", row.item_code,
            ["has_batch_no", "is_stock_item", "taj_brand_tracking"], as_dict=True,
        )
        if not item or not item.has_batch_no or not item.is_stock_item:
            result["issues"].append("Required BOM item without batch tracking: " + row.parent + " / " + row.item_code)
        elif not item.taj_brand_tracking:
            result["issues"].append("Required BOM item without Brand Tracking: " + row.parent + " / " + row.item_code)
    actual_field = batch_brand_field()
    if frappe.get_meta("Batch").has_field(actual_field):
        # Existing brand values on historical batches are not modified.
        result["batches_without_verified_actual_brand"] = frappe.db.count("Batch", {actual_field: ["is", "not set"]})
    usage = _item_brand_usage()
    result["item_brand_tracking"] = usage
    if usage.get("flagged_without_batches"):
        result["issues"].append("Brand-tracked items without Batch tracking: " + str(usage["flagged_without_batches"]))
    if usage.get("flagged_with_item_master_brand"):
        result["issues"].append("Brand-tracked Items still have an Item-master Brand; this conflicts with multiple actual Brands: " + str(usage["flagged_with_item_master_brand"]))
    return result


def verify():
    missing = []
    for dt, fields in _site_fields().items():
        meta = frappe.get_meta(dt)
        for name in fields:
            if not meta.has_field(name):
                missing.append(dt + "." + name)
    missing.extend(_item_layout_errors())
    tracking = frappe.get_meta("Item").get_field("taj_brand_tracking")
    if not tracking or tracking.read_only_depends_on != FIELDS["Item"]["taj_brand_tracking"]["read_only_depends_on"]:
        missing.append("Item.taj_brand_tracking must be disabled when Batch/Stock tracking is off")
    work_order_brand = frappe.get_meta("Work Order Item").get_field("taj_required_brand")
    if not work_order_brand or not work_order_brand.in_list_view:
        missing.append("Work Order Item.taj_required_brand must be visible in the grid")
    for dt in LEGACY_COMMERCIAL_ACTUAL:
        cf = frappe.db.get_value(
            "Custom Field", {"dt": dt, "fieldname": "taj_actual_brand"}, "name"
        )
        if cf:
            legacy = frappe.get_doc("Custom Field", cf)
            if not (legacy.hidden and legacy.read_only):
                missing.append(dt + ".taj_actual_brand must remain hidden and read only")
    planning_method = "erpnext.manufacturing.doctype.production_plan.production_plan.get_items_for_material_requests"
    expected_method = "taj_core.brand.planning.get_items_for_material_requests"
    override = frappe.get_hooks("override_whitelisted_methods", {}).get(planning_method, [])
    configured = expected_method in override if isinstance(override, (list, tuple)) else override == expected_method
    if not configured:
        missing.append("Production Plan API override not registered")
    batch_state = _batch_brand_diagnostic()
    missing.extend(batch_state["errors"])
    if not frappe.get_meta("Batch").has_field(batch_state["selected_field"]):
        missing.append("Missing canonical Batch Brand field: " + batch_state["selected_field"])
    status = {"metadata_errors": missing, "batch_brand_source": batch_state, "integrity": audit_integrity(), "enforcement_mode": "Item.taj_brand_tracking"}
    print("VERIFY (READ ONLY):", frappe.as_json(status, indent=2))
    if missing:
        frappe.throw(_("Brand metadata verification failed."))
    return status


def _place_brand_fields_in_item_order(order):
    """Place Brand Tracking directly after the standard Item.brand field.

    Remove the obsolete layout-only Column Break, without changing the relative
    order of any unrelated Item field. This helper is pure (no database writes).
    """
    if not isinstance(order, list) or any(not isinstance(x, str) or not x for x in order):
        raise ValueError("Item field order must contain only non-empty field names")
    if len(order) != len(set(order)):
        raise ValueError("Item field order contains duplicate field names")
    missing = [name for name in ("brand", "taj_brand_tracking") if name not in order]
    if missing:
        raise ValueError("Item fields are missing: " + ", ".join(missing))
    without_brand_layout = [
        name for name in order
        if name not in ("taj_brand_tracking", "taj_brand_column")
    ]
    desired = without_brand_layout.copy()
    desired.insert(desired.index("brand") + 1, "taj_brand_tracking")
    assert [name for name in desired if name != "taj_brand_tracking"] == without_brand_layout
    return desired, desired != order


def _doctype_field_order_setters():
    return frappe.get_all(
        "Property Setter",
        filters={"doc_type": "Item", "doctype_or_field": "DocType", "property": "field_order"},
        fields=["name", "value"], limit_page_length=10,
    )


def _item_layout_blockers():
    """Read-only safety checks before removing the obsolete Column Break."""
    problems = []
    meta = frappe.get_meta("Item")
    brand = meta.get_field("brand")
    if not brand or brand.fieldtype != "Link" or brand.options != "Brand":
        problems.append("Standard Item.brand must be Link -> Brand")
    names = [field.fieldname for field in meta.fields]
    if "inventory_section" in names and "brand" in names:
        if names.index("brand") > names.index("inventory_section"):
            problems.append("Standard Item.brand is no longer in Details; review its position")

    old_column = frappe.db.get_value(
        "Custom Field", {"dt": "Item", "fieldname": "taj_brand_column"},
        ["name", "fieldtype", "owner"], as_dict=True,
    )
    if old_column:
        if old_column.fieldtype != "Column Break":
            problems.append("Item.taj_brand_column exists but is not a Column Break")
        if old_column.owner == "Administrator" and frappe.session.user != "Administrator":
            problems.append("Delete the Administrator-owned Item.taj_brand_column as Administrator")
    elif meta.has_field("taj_brand_column"):
        problems.append("Item.taj_brand_column exists without a Custom Field record")

    dependents = frappe.get_all(
        "Custom Field", filters={"dt": "Item", "insert_after": "taj_brand_column"},
        pluck="fieldname",
    )
    dependents = [name for name in dependents if name != "taj_brand_tracking"]
    if dependents:
        problems.append("Other Item fields depend on taj_brand_column: " + ", ".join(dependents))

    property_dependents = frappe.get_all(
        "Property Setter",
        filters={"doc_type": "Item", "property": "insert_after", "value": "taj_brand_column"},
        fields=["name", "field_name"], limit_page_length=100,
    )
    property_dependents = [
        row for row in property_dependents
        if row.field_name not in ("taj_brand_tracking", "taj_brand_column")
    ]
    if property_dependents:
        problems.append(
            "Other Item insert_after Property Setters depend on taj_brand_column: "
            + ", ".join(row.name for row in property_dependents)
        )

    tracking_setters = frappe.get_all(
        "Property Setter",
        filters={"doc_type": "Item", "field_name": "taj_brand_tracking", "property": "insert_after"},
        fields=["name", "value"], limit_page_length=10,
    )
    if len(tracking_setters) > 1:
        problems.append("Multiple Item.taj_brand_tracking insert_after Property Setters found")

    setters = _doctype_field_order_setters()
    if len(setters) > 1:
        problems.append("Multiple Item field_order Property Setters found")
    elif setters:
        try:
            raw = json.loads(setters[0].value or "[]")
            if not isinstance(raw, list) or any(not isinstance(x, str) or not x for x in raw):
                raise ValueError("field_order must be a list of non-empty field names")
            if len(raw) != len(set(raw)):
                raise ValueError("field_order contains duplicate field names")
        except (TypeError, ValueError) as exc:
            problems.append("Invalid Item field_order Property Setter: " + str(exc))
    return problems


def _ensure_item_field_order():
    """Maintain the effective Item order via its existing standard mechanism.

    `insert_after` suffices when no field_order setter overrides it. If one
    exists, reuse it and remove the obsolete field reference. Only create a
    new setter when the effective order actually needs it.
    """
    setters = _doctype_field_order_setters()
    if len(setters) > 1:
        frappe.throw(_("Multiple Item field_order Property Setters found; review required."))
    current = [field.fieldname for field in frappe.get_meta("Item").fields]
    try:
        desired, changed = _place_brand_fields_in_item_order(current)
    except ValueError as exc:
        frappe.throw(_("Cannot safely place Item Brand Tracking: {0}").format(str(exc)))

    if setters:
        setter = frappe.get_doc("Property Setter", setters[0].name)
        raw = json.loads(setter.value or "[]")
        contains_obsolete = "taj_brand_column" in raw
        if changed or contains_obsolete:
            # Build from the *effective* metadata, retaining the exact relative
            # order of all other standard and custom fields.
            setter.value = json.dumps(desired, ensure_ascii=False)
            setter.save()
            return "updated-existing-field-order"
        return "already-correct"

    if not changed:
        return "already-correct"

    frappe.make_property_setter(
        {"doctype": "Item", "doctype_or_field": "DocType", "property": "field_order",
         "value": json.dumps(desired, ensure_ascii=False)},
        is_system_generated=False,
    )
    return "created-standard-field-order"


def _item_layout_errors():
    """Validate actual metadata instead of assuming insert_after is enough."""
    fields = frappe.get_meta("Item").fields
    names = [field.fieldname for field in fields]
    issues = []
    for name in ("brand", "taj_brand_tracking"):
        if name not in names:
            issues.append("Missing Item field: " + name)
    if "taj_brand_column" in names or frappe.db.exists(
        "Custom Field", {"dt": "Item", "fieldname": "taj_brand_column"}
    ):
        issues.append("Obsolete Item.taj_brand_column still exists")
    if "brand" in names and "taj_brand_tracking" in names:
        if names.index("taj_brand_tracking") != names.index("brand") + 1:
            issues.append("Item.taj_brand_tracking must immediately follow Item.brand")
        tracking = fields[names.index("taj_brand_tracking")]
        if tracking.fieldtype != "Check":
            issues.append("Item.taj_brand_tracking must remain a Check field")
        if "inventory_section" in names and names.index("brand") > names.index("inventory_section"):
            issues.append("Item.brand is not in the Details tab")
    tracking_after = frappe.db.get_value(
        "Custom Field", {"dt": "Item", "fieldname": "taj_brand_tracking"}, "insert_after"
    )
    if tracking_after != "brand":
        issues.append("Item.taj_brand_tracking Custom Field insert_after is not brand")
    tracking_setters = frappe.get_all(
        "Property Setter",
        filters={"doc_type": "Item", "field_name": "taj_brand_tracking", "property": "insert_after"},
        fields=["name", "value"], limit_page_length=10,
    )
    if len(tracking_setters) > 1 or any(row.value != "brand" for row in tracking_setters):
        issues.append("Item.taj_brand_tracking insert_after Property Setter is not brand")
    for setter in _doctype_field_order_setters():
        try:
            if "taj_brand_column" in json.loads(setter.value or "[]"):
                issues.append("Item.field_order still contains taj_brand_column")
        except (TypeError, ValueError):
            issues.append("Item.field_order is not valid JSON")
    return issues


def inspect_item_layout():
    """Read-only metadata inspection; do not modify Item rows or Custom Fields."""
    fields = frappe.get_meta("Item").fields
    order = [field.fieldname for field in fields]
    names = ("brand", "taj_brand_tracking", "description", "taj_brand_column",
             "serial_nos_and_batches", "variants_section")
    positions = {name: (order.index(name) if name in order else None) for name in names}
    brand_position = positions["brand"]
    inventory_position = positions["serial_nos_and_batches"]
    variants_position = positions["variants_section"]
    setters = _doctype_field_order_setters()
    result = {
        "effective_positions": positions,
        "effective_brand_context": [
            {"fieldname": field.fieldname, "fieldtype": field.fieldtype}
            for field in (fields[max(0, brand_position - 3):brand_position + 5]
                          if brand_position is not None else [])
        ],
        "effective_inventory_fields": [
            {"fieldname": field.fieldname, "fieldtype": field.fieldtype}
            for field in (fields[inventory_position:variants_position + 1]
                          if inventory_position is not None and variants_position is not None
                          and inventory_position <= variants_position else [])
        ],
        "custom_fields": frappe.get_all(
            "Custom Field", filters={"dt": "Item", "fieldname": ["in", ["taj_brand_column", "taj_brand_tracking"]]},
            fields=["name", "fieldname", "fieldtype", "insert_after", "idx"],
        ),
        "field_order_setters": [
            {"name": row.name, "contains_tracking": "taj_brand_tracking" in (row.value or ""),
             "contains_column": "taj_brand_column" in (row.value or "")}
            for row in setters
        ],
        "layout_blockers": _item_layout_blockers(),
        "field_order_errors": _item_layout_errors(),
    }
    print("ITEM_LAYOUT_DIAGNOSTIC (READ ONLY):", frappe.as_json(result, indent=2))
    return result


def apply_item_layout():
    """Move Item Brand Tracking below Item.brand; remove only old layout UI.

    All writes are to Custom Field / Property Setter metadata. The caller
    controls commit/rollback (in bench console commit only after inspection).
    """
    _validate_version()
    existing = frappe.db.get_value(
        "Custom Field", {"dt": "Item", "fieldname": "taj_brand_tracking"}, "name"
    )
    if not existing:
        frappe.throw(_("Existing Item.taj_brand_tracking Custom Field not found; no changes applied."))
    tracking = frappe.get_doc("Custom Field", existing)
    if tracking.fieldtype != "Check":
        frappe.throw(_("Item.taj_brand_tracking must be Check; no changes applied."))

    problems = _item_layout_blockers()
    if problems:
        frappe.throw(_("Item layout blockers; no changes applied: {0}").format("; ".join(problems)))
    dependents = frappe.get_all(
        "Custom Field", filters={"dt": "Item", "insert_after": "taj_brand_tracking"},
        pluck="fieldname",
    )
    if dependents:
        frappe.throw(_("Other Item fields are positioned after Brand Tracking: {0}.").format(", ".join(dependents)))

    before_usage = _item_brand_usage()
    before_ledger = _ledger_snapshot()
    original_order = [field.fieldname for field in frappe.get_meta("Item").fields]
    changes = []

    if tracking.insert_after != "brand":
        tracking.insert_after = "brand"
        tracking.save()
        changes.append("Item.taj_brand_tracking.insert_after")

    property_setter_name = frappe.db.get_value(
        "Property Setter",
        {"doc_type": "Item", "field_name": "taj_brand_tracking", "property": "insert_after"},
        "name",
    )
    if property_setter_name:
        setter = frappe.get_doc("Property Setter", property_setter_name)
        if setter.value != "brand":
            setter.value = "brand"
            setter.save()
            changes.append("Item.taj_brand_tracking.insert_after(Property Setter)")

    column_name = frappe.db.get_value(
        "Custom Field", {"dt": "Item", "fieldname": "taj_brand_column"}, "name"
    )
    if column_name:
        # Delete through Frappe document events (do not bypass Core).
        frappe.get_doc("Custom Field", column_name).delete(ignore_permissions=True)
        changes.append("deleted Item.taj_brand_column")

    frappe.clear_cache(doctype="Item")
    order_action = _ensure_item_field_order()
    frappe.clear_cache(doctype="Item")

    final_order = [field.fieldname for field in frappe.get_meta("Item").fields]
    non_brand = lambda order: [
        name for name in order if name not in ("taj_brand_column", "taj_brand_tracking")
    ]
    errors = _item_layout_errors()
    if non_brand(original_order) != non_brand(final_order):
        errors.append("Relative order of unrelated Item fields changed")
    if before_usage != _item_brand_usage():
        errors.append("Existing Item Brand Tracking counts changed unexpectedly")
    if before_ledger != _ledger_snapshot():
        errors.append("Stock/GL Ledger totals changed during Item layout migration")
    if errors:
        frappe.throw(_("Item layout verification failed: {0}").format("; ".join(errors)))

    result = {
        "tracking_insert_after": "brand",
        "removed_column": "taj_brand_column" not in final_order,
        "changes": changes,
        "field_order_action": order_action,
        "tracking_item_counts": before_usage,
    }
    print("ITEM_LAYOUT_OK:", frappe.as_json(result, indent=2))
    return True


def assert_ready_to_enable():
    result = verify()
    issues = result["integrity"]["issues"]
    if issues:
        frappe.throw(_("Cannot enable brand enforcement until preflight issues are resolved: {0}").format("; ".join(issues)))
    return True
