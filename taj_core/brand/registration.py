"""Merge brand hooks without overriding the site's existing Taj hooks."""


def add_event(doc_events, doctype, event, handler):
    handlers = doc_events.setdefault(doctype, {})
    old = handlers.get(event)
    if old is None:
        handlers[event] = handler
    elif isinstance(old, str):
        if old != handler:
            handlers[event] = [old, handler]
    elif handler not in old:
        old.append(handler)


def register_hooks(doc_events, override_whitelisted_methods):
    prefix = "taj_core.brand.validation."
    for dt, handlers in {
        "Item": {"validate": "validate_item_tracking_transition"},
        "BOM": {"validate": "validate_bom"},
        "Batch": {"validate": "validate_batch"},
        "Production Plan": {"validate": "validate_production_plan"},
        "Material Request": {"validate": "validate_material_request", "before_submit": "validate_material_request"},
        "Purchase Order": {"validate": "validate_purchase_order", "before_submit": "validate_purchase_order"},
        "Supplier Quotation": {"validate": "validate_supplier_quotation", "before_submit": "validate_supplier_quotation"},
        "Request for Quotation": {"validate": "validate_request_for_quotation", "before_submit": "validate_request_for_quotation"},
        "Purchase Receipt": {"validate": "validate_purchase_receipt", "before_submit": "validate_purchase_receipt", "on_submit": "bind_purchase_receipt_batches"},
        "Purchase Invoice": {"validate": "validate_purchase_invoice", "before_submit": "validate_purchase_invoice", "on_submit": "bind_purchase_invoice_batches"},
        "Work Order": {"before_validate": "validate_work_order", "validate": "validate_work_order", "before_submit": "validate_work_order"},
        "Stock Entry": {"before_validate": "preserve_pick_list_stock_entry_batches", "validate": "validate_stock_entry", "before_submit": "validate_stock_entry"},
    }.items():
        for event, handler in handlers.items():
            add_event(doc_events, dt, event, prefix + handler)

    # The validator lives in brand.pick_list, NOT brand.validation.  Keeping
    # these paths importable is essential: Frappe resolves them on every
    # Pick List save/submit even when Brand enforcement is turned off.
    pick_list_validator = "taj_core.brand.pick_list.validate_pick_list"
    for event in ("before_save", "before_submit", "on_update_after_submit"):
        add_event(doc_events, "Pick List", event, pick_list_validator)

    original = "erpnext.manufacturing.doctype.production_plan.production_plan.get_items_for_material_requests"
    replacement = "taj_core.brand.planning.get_items_for_material_requests"
    installed = override_whitelisted_methods.get(original)
    # Never prevent an existing Frappe site from booting merely because an
    # older local materials customization already owns this API.  Leave it
    # intact; setup.verify() will block enabling until deliberately reconciled.
    if installed and installed != replacement:
        return
    override_whitelisted_methods[original] = replacement
