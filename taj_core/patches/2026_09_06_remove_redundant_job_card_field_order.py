import json

import frappe


DOCTYPE = "Job Card"
PROPERTY_SETTER = "Job Card-main-field_order"

STALE_STERILIZATION_ORDER = (
    "taj_qc",
    "taj_is_data_logger",
    "taj_hold",
    "taj_hold_temp",
    "taj_retort_no",
    "taj_cool",
    "taj_heat",
    "taj_batch_id",
)


def execute():
    if not frappe.db.exists("Property Setter", PROPERTY_SETTER):
        return

    setter = frappe.get_doc(
        "Property Setter",
        PROPERTY_SETTER,
    )

    if (
        setter.doc_type != DOCTYPE
        or setter.doctype_or_field != "DocType"
        or setter.property != "field_order"
    ):
        return

    try:
        setter_order = json.loads(setter.value or "[]")
    except (TypeError, json.JSONDecodeError):
        return

    if not isinstance(setter_order, list):
        return

    standard_doc = frappe.get_doc(
        "DocType",
        DOCTYPE,
    )

    standard_order = [
        df.fieldname
        for df in standard_doc.fields
    ]

    standard_set = set(standard_order)

    setter_standard_order = [
        fieldname
        for fieldname in setter_order
        if fieldname in standard_set
    ]

    # Never remove a genuine customization of standard field order.
    if setter_standard_order != standard_order:
        return

    custom_fields = set(
        frappe.get_all(
            "Custom Field",
            filters={"dt": DOCTYPE},
            pluck="fieldname",
        )
    )

    extras = [
        fieldname
        for fieldname in setter_order
        if fieldname not in standard_set
    ]

    if not extras:
        return

    # Do not touch field orders containing fields outside Taj customizations.
    if any(
        fieldname not in custom_fields
        or not fieldname.startswith("taj_")
        for fieldname in extras
    ):
        return

    stale_group_order = [
        fieldname
        for fieldname in setter_order
        if fieldname in STALE_STERILIZATION_ORDER
    ]

    # Delete only the exact stale ordering observed in the old snapshot.
    if tuple(stale_group_order) != STALE_STERILIZATION_ORDER:
        return

    frappe.delete_doc(
        "Property Setter",
        PROPERTY_SETTER,
        ignore_permissions=True,
    )

    frappe.clear_cache(
        doctype=DOCTYPE
    )