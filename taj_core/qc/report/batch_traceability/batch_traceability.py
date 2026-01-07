import frappe

MAX_DEPTH_HARDCAP = 10


def execute(filters=None):
    filters = frappe._dict(filters or {})

    trace_type = (filters.get("trace_type") or "Manufacturing").strip()
    batch = (filters.get("batch") or "").strip()
    view_mode = (filters.get("view_mode") or "Table (Printable)").strip()
    include_bundle = int(filters.get("include_bundle") or 0) == 1

    if not batch:
        return get_columns(tree_mode=False, include_sales=False), []

    # ---------------- SOLD ----------------
    if trace_type == "Sold":
        return build_sold_trace(batch)

    # cache for tracing producing WOs
    frappe.local._haccp_wo_cache = {}

    produced_roots = get_production_roots_by_final_batch(batch)

    if not produced_roots:
        msg = f"NO PRODUCTION FOUND FOR FINAL BATCH: {batch}"
        if view_mode == "Tree (Expandable)":
            return get_columns(tree_mode=True, include_sales=False), [{
                "name": f"ROOT::{batch}",
                "parent": "",
                "indent": 0,
                "level": 0,
                "path": "",
                "item_code": "",
                "item_name": msg,
                "item_type": "",
                "qty": None,
                "uom": "",
                "batch_no": batch,
                "supplier": "",
                "source_doctype": "",
                "source_docname": "",
                "stock_entry": "",
                "work_order": "",
                "customer": "",
                "sales_doctype": "",
                "sales_docname": "",
                "is_section_row": 1,
                "is_batch_line": 0,
                "is_bundle_sibling": 0
            }]
        return get_columns(tree_mode=False, include_sales=False), [{
            "level": 0,
            "path": "",
            "item_code": "",
            "item_name": msg,
            "item_type": "",
            "qty": None,
            "uom": "",
            "batch_no": batch,
            "supplier": "",
            "source_doctype": "",
            "source_docname": "",
            "stock_entry": "",
            "work_order": "",
            "customer": "",
            "sales_doctype": "",
            "sales_docname": "",
            "is_section_row": 1,
            "is_batch_line": 0,
            "is_bundle_sibling": 0
        }]

    # -------- Tree Mode --------
    if view_mode == "Tree (Expandable)":
        data = build_tree_view_for_batch(
            final_batch=batch,
            produced_roots=produced_roots,
            max_depth=MAX_DEPTH_HARDCAP,
            include_bundle=include_bundle
        )
        return get_columns(tree_mode=True, include_sales=False), data

    # -------- Table Mode --------
    data = []

    for root in produced_roots:
        wo_name = root.get("work_order") or ""
        se_name = root.get("stock_entry") or ""
        final_item = root.get("item_code") or ""
        bundle_name = root.get("bundle_name") or ""

        uom_final = get_item_uom(final_item)

        # ✅ per-root bundle qty map ONLY (prevents mixing bundles)
        qty_map = get_bundle_batch_qty_map_for_bundle(bundle_name, final_item) if (include_bundle and bundle_name) else {}

        # ✅ final qty = qty of selected batch inside the SAME bundle (if exists)
        final_qty = abs(float(qty_map.get(batch) or root.get("qty") or 0))

        # Final row
        data.append({
            "level": 0,
            "path": "0",
            "item_code": final_item,
            "item_name": get_item_name(final_item),
            "item_type": "Finished",
            "qty": final_qty,
            "uom": uom_final,
            "batch_no": batch,
            "supplier": "",
            "source_doctype": "",
            "source_docname": "",
            "stock_entry": se_name,
            "work_order": wo_name,
            "customer": "",
            "sales_doctype": "",
            "sales_docname": "",
            "is_section_row": 0,
            "is_batch_line": 0,
            "is_bundle_sibling": 0
        })

        # ✅ Yellow sibling rows (QTY + UOM + Batch) from SAME bundle only
        if include_bundle and bundle_name and qty_map:
            siblings = sorted([b for b in qty_map.keys() if b and b != batch])
            for sib in siblings:
                data.append({
                    "level": 0,
                    "path": "",
                    "item_code": "",
                    "item_name": "",
                    "item_type": "",
                    "qty": abs(float(qty_map.get(sib) or 0)),
                    "uom": uom_final,
                    "batch_no": sib,
                    "supplier": "",
                    "source_doctype": "",
                    "source_docname": "",
                    "stock_entry": "",
                    "work_order": "",
                    "customer": "",
                    "sales_doctype": "",
                    "sales_docname": "",
                    "is_section_row": 0,
                    "is_batch_line": 0,
                    "is_bundle_sibling": 1
                })

        wo = frappe.get_doc("Work Order", wo_name) if wo_name else None
        bom = (getattr(wo, "bom_no", None) if wo else None) or get_default_bom(final_item)
        if not bom:
            continue

        consumed_map = get_consumed_batches_from_work_order(wo_name) if wo_name else {}
        visited = set()

        explode_bom_level_order(
            bom=bom,
            parent_path="",
            level=1,
            max_depth=MAX_DEPTH_HARDCAP,
            data=data,
            visited=visited,
            consumed_map=consumed_map
        )

    return get_columns(tree_mode=False, include_sales=False), data


# ---------------- Columns ----------------

def get_columns(tree_mode=False, include_sales=False):
    base = [
        {"label": "Level", "fieldname": "level", "fieldtype": "Int", "width": 90},
        {"label": "Path", "fieldname": "path", "fieldtype": "Data", "width": 90},
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 200},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 320},
        {"label": "Item Type", "fieldname": "item_type", "fieldtype": "Data", "width": 130},
        {"label": "QTY", "fieldname": "qty", "fieldtype": "Float", "width": 110},
        {"label": "UOM", "fieldname": "uom", "fieldtype": "Data", "width": 70},
        {"label": "Batch", "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 140},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},

        # ✅ Always visible supplier source
        {"label": "Source DocType", "fieldname": "source_doctype", "fieldtype": "Data", "width": 140},
        {"label": "Source DocNo", "fieldname": "source_docname", "fieldtype": "Dynamic Link", "options": "source_doctype", "width": 170},

        {"label": "Stock Entry", "fieldname": "stock_entry", "fieldtype": "Link", "options": "Stock Entry", "width": 160},
        {"label": "Work Order", "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 160},
    ]

    if include_sales:
        base += [
            {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
            {"label": "Sales DocType", "fieldname": "sales_doctype", "fieldtype": "Data", "width": 160},
            {"label": "Sales DocNo", "fieldname": "sales_docname", "fieldtype": "Dynamic Link", "options": "sales_doctype", "width": 180},
        ]

    if tree_mode:
        base = [
            {"label": "ID", "fieldname": "name", "fieldtype": "Data", "width": 120, "hidden": 1},
            {"label": "Parent", "fieldname": "parent", "fieldtype": "Data", "width": 120, "hidden": 1},
            {"label": "Indent", "fieldname": "indent", "fieldtype": "Int", "width": 60, "hidden": 1},
        ] + base

    return base


# ---------------- SOLD trace ----------------

def build_sold_trace(final_batch: str):
    if not final_batch:
        return get_columns(tree_mode=False, include_sales=True), []

    batch_doc = frappe.get_doc("Batch", final_batch)
    item_code = batch_doc.item
    item_name = batch_doc.item_name
    uom = batch_doc.stock_uom

    sle_rows = frappe.db.get_all(
        "Stock Ledger Entry",
        filters={
            "batch_no": final_batch,
            "actual_qty": ["<", 0],
            "docstatus": 1,
            "voucher_type": ["in", ["Delivery Note", "Sales Invoice"]]
        },
        fields=["voucher_type", "voucher_no", "actual_qty", "posting_date", "posting_time"],
        order_by="posting_date asc, posting_time asc"
    )

    data = []
    for sle in sle_rows:
        customer = get_customer_from_voucher(sle.get("voucher_type"), sle.get("voucher_no"))
        data.append({
            "level": 1,
            "path": "",
            "item_code": item_code,
            "item_name": item_name,
            "item_type": "",
            "qty": abs(float(sle.get("actual_qty") or 0)),
            "uom": uom,
            "batch_no": final_batch,
            "supplier": "",
            "source_doctype": "",
            "source_docname": "",
            "stock_entry": "",
            "work_order": "",
            "customer": customer,
            "sales_doctype": sle.get("voucher_type"),
            "sales_docname": sle.get("voucher_no"),
            "is_section_row": 0,
            "is_batch_line": 0,
            "is_bundle_sibling": 0
        })

    return get_columns(tree_mode=False, include_sales=True), data


def get_customer_from_voucher(voucher_type: str, voucher_no: str):
    if not voucher_type or not voucher_no:
        return None
    try:
        return frappe.db.get_value(voucher_type, voucher_no, "customer")
    except Exception:
        return None


# ---------------- Bundle qty map (ONE bundle only) ----------------

def get_bundle_batch_qty_map_for_bundle(bundle_name: str, item_code: str = None):
    """
    Returns {batch_no: qty} from ONE Serial and Batch Bundle only.
    Prevents mixing multiple bundles for the same batch across time.
    """
    if not bundle_name:
        return {}

    sql = """
        SELECT batch_no, COALESCE(SUM(qty), 0) AS qty
        FROM `tabSerial and Batch Entry`
        WHERE parent = %(parent)s
    """
    params = {"parent": bundle_name}

    # Optional filter by item_code if column exists
    if item_code:
        try:
            frappe.db.sql("SELECT item_code FROM `tabSerial and Batch Entry` LIMIT 1")
            sql += " AND item_code = %(item_code)s"
            params["item_code"] = item_code
        except Exception:
            pass

    sql += " GROUP BY batch_no"
    rows = frappe.db.sql(sql, params, as_dict=True)

    out = {}
    for r in rows or []:
        bn = (r.get("batch_no") or "").strip()
        if not bn:
            continue
        out[bn] = float(r.get("qty") or 0)

    return out


# ---------------- Root finder by FINAL batch ----------------

def get_production_roots_by_final_batch(final_batch: str):
    roots = []

    # 1) Direct produced rows (batch_no filled)
    rows = frappe.db.get_all(
        "Stock Entry Detail",
        filters={"batch_no": final_batch, "docstatus": 1, "t_warehouse": ["!=", ""]},
        fields=["parent as stock_entry", "item_code", "qty", "serial_and_batch_bundle"],
    )
    for r in rows:
        se_name = r.get("stock_entry")
        wo = frappe.db.get_value("Stock Entry", se_name, "work_order")
        roots.append({
            "item_code": r.get("item_code"),
            "qty": r.get("qty") or 0,
            "stock_entry": se_name,
            "work_order": wo or "",
            "bundle_name": r.get("serial_and_batch_bundle") or ""
        })

    # 2) Bundle produced rows (batch_no might be empty on SED)
    bundle_names = frappe.db.get_all(
        "Serial and Batch Entry",
        filters={"batch_no": final_batch},
        pluck="parent"
    ) or []

    if bundle_names:
        sed_rows = frappe.db.get_all(
            "Stock Entry Detail",
            filters={
                "serial_and_batch_bundle": ["in", bundle_names],
                "docstatus": 1,
                "t_warehouse": ["!=", ""]
            },
            fields=["parent as stock_entry", "item_code", "qty", "serial_and_batch_bundle"]
        )

        for r in sed_rows:
            se_name = r.get("stock_entry")
            wo = frappe.db.get_value("Stock Entry", se_name, "work_order")
            bundle = r.get("serial_and_batch_bundle") or ""

            # ✅ exact qty for THIS batch from THIS bundle only
            qty_map = get_bundle_batch_qty_map_for_bundle(bundle, r.get("item_code"))
            exact_qty = qty_map.get(final_batch)

            roots.append({
                "item_code": r.get("item_code"),
                "qty": exact_qty if exact_qty is not None else (r.get("qty") or 0),
                "stock_entry": se_name,
                "work_order": wo or "",
                "bundle_name": bundle
            })

    # de-dup
    uniq = {}
    for x in roots:
        key = (x.get("stock_entry"), x.get("item_code"), final_batch, x.get("bundle_name") or "")
        if key not in uniq:
            uniq[key] = x
        else:
            uniq[key]["qty"] = max(float(uniq[key].get("qty") or 0), float(x.get("qty") or 0))

    return list(uniq.values())


# ---------------- Tree View (Manufacturing) ----------------

def build_tree_view_for_batch(final_batch: str, produced_roots: list, max_depth: int, include_bundle: bool = False):
    data = []
    root_id = f"ROOT::{final_batch}"

    bdoc = frappe.get_doc("Batch", final_batch)
    final_item = bdoc.item
    final_item_name = bdoc.item_name
    final_uom = bdoc.stock_uom

    data.append({
        "name": root_id,
        "parent": "",
        "indent": 0,
        "level": 0,
        "path": "0",
        "item_code": final_item,
        "item_name": final_item_name,
        "item_type": "Finished",
        "qty": None,
        "uom": final_uom or "",
        "batch_no": final_batch,
        "supplier": "",
        "source_doctype": "",
        "source_docname": "",
        "stock_entry": "",
        "work_order": "",
        "customer": "",
        "sales_doctype": "",
        "sales_docname": "",
        "is_section_row": 0,
        "is_batch_line": 0,
        "is_bundle_sibling": 0
    })

    for i, root in enumerate(produced_roots, start=1):
        wo_name = root.get("work_order") or ""
        se_name = root.get("stock_entry") or ""
        bundle_name = root.get("bundle_name") or ""
        root_qty = abs(float(root.get("qty") or 0))

        wo_node = f"WO::{final_batch}::{i}::{wo_name or 'NO-WO'}::{se_name}"
        data.append({
            "name": wo_node,
            "parent": root_id,
            "indent": 1,
            "level": 0,
            "path": "",
            "item_code": "",
            "item_name": f"WORK ORDER: {wo_name}" if wo_name else f"STOCK ENTRY: {se_name}",
            "item_type": "",
            "qty": None,
            "uom": "",
            "batch_no": "",
            "supplier": "",
            "source_doctype": "",
            "source_docname": "",
            "stock_entry": se_name,
            "work_order": wo_name,
            "customer": "",
            "sales_doctype": "",
            "sales_docname": "",
            "is_section_row": 1,
            "is_batch_line": 0,
            "is_bundle_sibling": 0
        })

        # ✅ per-root bundle qty map
        qty_map = get_bundle_batch_qty_map_for_bundle(bundle_name, final_item) if (include_bundle and bundle_name) else {}
        final_qty = abs(float(qty_map.get(final_batch) or root_qty or 0))

        final_node = f"FINAL::{final_batch}::{i}::{final_item}"
        data.append({
            "name": final_node,
            "parent": wo_node,
            "indent": 2,
            "level": 0,
            "path": "0",
            "item_code": final_item,
            "item_name": final_item_name,
            "item_type": "Finished",
            "qty": final_qty,
            "uom": final_uom or "",
            "batch_no": final_batch,
            "supplier": "",
            "source_doctype": "",
            "source_docname": "",
            "stock_entry": se_name,
            "work_order": wo_name,
            "customer": "",
            "sales_doctype": "",
            "sales_docname": "",
            "is_section_row": 0,
            "is_batch_line": 0,
            "is_bundle_sibling": 0
        })

        # ✅ siblings from same bundle
        if include_bundle and bundle_name and qty_map:
            siblings = sorted([b for b in qty_map.keys() if b and b != final_batch])
            for si, sib in enumerate(siblings, start=1):
                sib_id = f"SIB::{final_batch}::{i}::{si}::{sib}"
                data.append({
                    "name": sib_id,
                    "parent": final_node,
                    "indent": 3,
                    "level": 0,
                    "path": "",
                    "item_code": "",
                    "item_name": "",
                    "item_type": "",
                    "qty": abs(float(qty_map.get(sib) or 0)),
                    "uom": final_uom or "",
                    "batch_no": sib,
                    "supplier": "",
                    "source_doctype": "",
                    "source_docname": "",
                    "stock_entry": "",
                    "work_order": "",
                    "customer": "",
                    "sales_doctype": "",
                    "sales_docname": "",
                    "is_section_row": 0,
                    "is_batch_line": 0,
                    "is_bundle_sibling": 1
                })

        wo = frappe.get_doc("Work Order", wo_name) if wo_name else None
        bom = (getattr(wo, "bom_no", None) if wo else None) or get_default_bom(final_item)
        if not bom:
            continue

        consumed_map = get_consumed_batches_from_work_order(wo_name) if wo_name else {}
        visited = set()

        explode_bom_tree(
            bom=bom,
            wo_name=wo_name or "",
            parent_row_id=final_node,
            indent=3,
            parent_path="",
            level=1,
            max_depth=max_depth,
            data=data,
            visited=visited,
            consumed_map=consumed_map
        )

    return data


# ---------------- explode (Tree) ----------------

def explode_bom_tree(
    bom: str,
    wo_name: str,
    parent_row_id: str,
    indent: int,
    parent_path: str,
    level: int,
    max_depth: int,
    data: list,
    visited: set,
    consumed_map: dict
):
    if level > max_depth:
        return

    if bom in visited:
        wid = f"WARN::{bom}::{parent_row_id}"
        data.append({
            "name": wid,
            "parent": parent_row_id,
            "indent": indent,
            "level": level,
            "path": parent_path,
            "item_code": "",
            "item_name": f"WARNING: RECURSIVE BOM DETECTED ({bom})",
            "item_type": "",
            "qty": None,
            "uom": "",
            "batch_no": "",
            "supplier": "",
            "source_doctype": "",
            "source_docname": "",
            "stock_entry": "",
            "work_order": "",
            "customer": "",
            "sales_doctype": "",
            "sales_docname": "",
            "is_section_row": 1,
            "is_batch_line": 0,
            "is_bundle_sibling": 0
        })
        return

    visited.add(bom)
    bom_doc = frappe.get_doc("BOM", bom)

    idx = 0
    for it in bom_doc.items:
        idx += 1
        path = f"{idx}" if not parent_path else f"{parent_path}.{idx}"

        item_code = it.item_code
        uom = it.uom

        item_type = classify_item(item_code)
        if (item_code or "").upper().startswith("RAW-"):
            item_type = "Raw Material"

        child_bom = get_default_bom(item_code)
        is_leaf = not bool(child_bom)

        batches = consumed_map.get(item_code) or []

        qty_val = abs(float(it.qty or 0))
        batch_no_val = ""
        stock_entry_val = ""
        work_order_val = ""
        supplier_val = ""
        src_dt_val, src_dn_val = ("", "")

        if batches:
            first = batches[0]
            qty_val = abs(float(first.get("qty") or 0))
            batch_no_val = first.get("batch_no") or ""
            stock_entry_val = first.get("stock_entry") or ""
            work_order_val = first.get("work_order") or ""

            if batch_no_val and is_raw_material_leaf(item_code, item_type, is_leaf):
                supplier_val = get_supplier_for_batch(batch_no_val)
                src_dt_val, src_dn_val = get_batch_source(batch_no_val)

        item_id = f"ITEM::{wo_name}::{level}::{path}::{item_code}"
        data.append({
            "name": item_id,
            "parent": parent_row_id,
            "indent": indent,
            "level": level,
            "path": path,
            "item_code": item_code,
            "item_name": get_item_name(item_code),
            "item_type": item_type,
            "qty": qty_val,
            "uom": uom,
            "batch_no": batch_no_val,
            "supplier": supplier_val,
            "source_doctype": src_dt_val,
            "source_docname": src_dn_val,
            "stock_entry": stock_entry_val,
            "work_order": work_order_val,
            "customer": "",
            "sales_doctype": "",
            "sales_docname": "",
            "is_section_row": 0,
            "is_batch_line": 0,
            "is_bundle_sibling": 0
        })

        if len(batches) > 1:
            for bi, b in enumerate(batches[1:], start=2):
                bn = b.get("batch_no") or ""
                supplier2 = ""
                src_dt2, src_dn2 = ("", "")
                if bn and is_raw_material_leaf(item_code, item_type, is_leaf):
                    supplier2 = get_supplier_for_batch(bn)
                    src_dt2, src_dn2 = get_batch_source(bn)

                extra_id = f"ITEMB::{wo_name}::{level}::{path}::{item_code}::{bi}::{bn}"
                data.append({
                    "name": extra_id,
                    "parent": item_id,
                    "indent": indent + 1,
                    "level": level,
                    "path": path,
                    "item_code": "",
                    "item_name": "",
                    "item_type": "",
                    "qty": abs(float(b.get("qty") or 0)),
                    "uom": uom,
                    "batch_no": bn,
                    "supplier": supplier2,
                    "source_doctype": src_dt2,
                    "source_docname": src_dn2,
                    "stock_entry": b.get("stock_entry") or "",
                    "work_order": b.get("work_order") or "",
                    "customer": "",
                    "sales_doctype": "",
                    "sales_docname": "",
                    "is_section_row": 0,
                    "is_batch_line": 1,
                    "is_bundle_sibling": 0
                })

        if child_bom:
            if batches:
                for cb in batches:
                    cb_batch = cb.get("batch_no")
                    sub_map = get_consumed_map_for_producing_wo(item_code, cb_batch)
                    explode_bom_tree(
                        bom=child_bom,
                        wo_name=wo_name,
                        parent_row_id=item_id,
                        indent=indent + 1,
                        parent_path=path,
                        level=level + 1,
                        max_depth=max_depth,
                        data=data,
                        visited=visited,
                        consumed_map=sub_map
                    )
            else:
                explode_bom_tree(
                    bom=child_bom,
                    wo_name=wo_name,
                    parent_row_id=item_id,
                    indent=indent + 1,
                    parent_path=path,
                    level=level + 1,
                    max_depth=max_depth,
                    data=data,
                    visited=visited,
                    consumed_map=consumed_map
                )


# ---------------- explode (Table) ----------------

def explode_bom_level_order(
    bom: str,
    parent_path: str,
    level: int,
    max_depth: int,
    data: list,
    visited: set,
    consumed_map: dict
):
    if level > max_depth:
        return

    if bom in visited:
        data.append({
            "level": level,
            "path": parent_path,
            "item_code": "",
            "item_name": f"WARNING: RECURSIVE BOM DETECTED ({bom})",
            "item_type": "",
            "qty": None,
            "uom": "",
            "batch_no": "",
            "supplier": "",
            "source_doctype": "",
            "source_docname": "",
            "stock_entry": "",
            "work_order": "",
            "customer": "",
            "sales_doctype": "",
            "sales_docname": "",
            "is_section_row": 1,
            "is_batch_line": 0,
            "is_bundle_sibling": 0
        })
        return

    visited.add(bom)
    bom_doc = frappe.get_doc("BOM", bom)

    children_to_expand = []
    idx = 0

    for it in bom_doc.items:
        idx += 1
        path = f"{idx}" if not parent_path else f"{parent_path}.{idx}"

        item_code = it.item_code
        item_type = classify_item(item_code)
        if (item_code or "").upper().startswith("RAW-"):
            item_type = "Raw Material"

        uom = it.uom
        child_bom = get_default_bom(item_code)
        is_leaf = not bool(child_bom)

        batches = consumed_map.get(item_code) or []
        if batches:
            first = batches[0]
            bn = first.get("batch_no") or ""

            supplier = ""
            src_dt, src_dn = ("", "")
            if bn and is_raw_material_leaf(item_code, item_type, is_leaf):
                supplier = get_supplier_for_batch(bn)
                src_dt, src_dn = get_batch_source(bn)

            data.append({
                "level": level,
                "path": path,
                "item_code": item_code,
                "item_name": get_item_name(item_code),
                "item_type": item_type,
                "qty": abs(float(first.get("qty") or 0)),
                "uom": uom,
                "batch_no": bn,
                "supplier": supplier,
                "source_doctype": src_dt,
                "source_docname": src_dn,
                "stock_entry": first.get("stock_entry") or "",
                "work_order": first.get("work_order") or "",
                "customer": "",
                "sales_doctype": "",
                "sales_docname": "",
                "is_section_row": 0,
                "is_batch_line": 0,
                "is_bundle_sibling": 0
            })

            for b in batches[1:]:
                bn2 = b.get("batch_no") or ""
                supplier2 = ""
                src_dt2, src_dn2 = ("", "")
                if bn2 and is_raw_material_leaf(item_code, item_type, is_leaf):
                    supplier2 = get_supplier_for_batch(bn2)
                    src_dt2, src_dn2 = get_batch_source(bn2)

                data.append({
                    "level": level,
                    "path": path,
                    "item_code": "",
                    "item_name": "",
                    "item_type": "",
                    "qty": abs(float(b.get("qty") or 0)),
                    "uom": uom,
                    "batch_no": bn2,
                    "supplier": supplier2,
                    "source_doctype": src_dt2,
                    "source_docname": src_dn2,
                    "stock_entry": b.get("stock_entry") or first.get("stock_entry") or "",
                    "work_order": b.get("work_order") or first.get("work_order") or "",
                    "customer": "",
                    "sales_doctype": "",
                    "sales_docname": "",
                    "is_section_row": 0,
                    "is_batch_line": 1,
                    "is_bundle_sibling": 0
                })
        else:
            data.append({
                "level": level,
                "path": path,
                "item_code": item_code,
                "item_name": get_item_name(item_code),
                "item_type": item_type,
                "qty": abs(float(it.qty or 0)),
                "uom": uom,
                "batch_no": "",
                "supplier": "",
                "source_doctype": "",
                "source_docname": "",
                "stock_entry": "",
                "work_order": "",
                "customer": "",
                "sales_doctype": "",
                "sales_docname": "",
                "is_section_row": 0,
                "is_batch_line": 0,
                "is_bundle_sibling": 0
            })

        if child_bom:
            children_to_expand.append((item_code, child_bom, path))

    for (child_item_code, child_bom, child_path) in children_to_expand:
        child_batches = consumed_map.get(child_item_code) or []
        if child_batches:
            for cb in child_batches:
                cb_batch = cb.get("batch_no")
                sub_consumed_map = get_consumed_map_for_producing_wo(child_item_code, cb_batch)
                explode_bom_level_order(
                    bom=child_bom,
                    parent_path=child_path,
                    level=level + 1,
                    max_depth=max_depth,
                    data=data,
                    visited=visited,
                    consumed_map=sub_consumed_map
                )
        else:
            explode_bom_level_order(
                bom=child_bom,
                parent_path=child_path,
                level=level + 1,
                max_depth=max_depth,
                data=data,
                visited=visited,
                consumed_map=consumed_map
            )


# ---------------- helpers ----------------

def is_raw_material_leaf(item_code: str, item_type: str, is_leaf: bool) -> bool:
    if not is_leaf:
        return False
    if (item_code or "").upper().startswith("RAW-"):
        return True
    return (item_type == "Raw Material")


def get_consumed_map_for_producing_wo(item_code: str, batch_no: str):
    cache = getattr(frappe.local, "_haccp_wo_cache", {})
    key = (item_code, batch_no)
    if key in cache:
        return cache[key]

    wo = get_work_order_that_produced_item_batch(item_code, batch_no)
    if not wo:
        cache[key] = {}
        frappe.local._haccp_wo_cache = cache
        return cache[key]

    cache[key] = get_consumed_batches_from_work_order(wo)
    frappe.local._haccp_wo_cache = cache
    return cache[key]


def get_work_order_that_produced_item_batch(item_code: str, batch_no: str):
    if not item_code or not batch_no:
        return None

    parent_se = frappe.db.get_value(
        "Stock Entry Detail",
        {"item_code": item_code, "batch_no": batch_no, "t_warehouse": ["!=", ""], "docstatus": 1},
        "parent"
    )
    if parent_se:
        return frappe.db.get_value("Stock Entry", parent_se, "work_order")

    bundle_names = frappe.db.get_all(
        "Serial and Batch Entry",
        filters={"batch_no": batch_no},
        pluck="parent"
    ) or []
    if not bundle_names:
        return None

    sed_parent = frappe.db.get_value(
        "Stock Entry Detail",
        {"serial_and_batch_bundle": ["in", bundle_names], "item_code": item_code, "t_warehouse": ["!=", ""], "docstatus": 1},
        "parent"
    )
    if not sed_parent:
        return None

    return frappe.db.get_value("Stock Entry", sed_parent, "work_order")


def get_consumed_batches_from_work_order(work_order: str):
    mp = {}
    if not work_order:
        return mp

    se_names = frappe.get_all(
        "Stock Entry",
        filters={"work_order": work_order, "docstatus": 1},
        pluck="name"
    )

    for se_name in se_names:
        se = frappe.get_doc("Stock Entry", se_name)

        for row in se.items:
            if not row.s_warehouse:
                continue

            item_code = row.item_code
            if not item_code:
                continue

            bundle = getattr(row, "serial_and_batch_bundle", None) or getattr(row, "serial_and_batch_bundle_no", None)
            if bundle:
                for b in read_bundle_batches(bundle, item_code=item_code):
                    bn = b.get("batch_no")
                    if not bn:
                        continue
                    mp.setdefault(item_code, []).append({
                        "batch_no": bn,
                        "qty": abs(float(b.get("qty") or 0)),
                        "stock_entry": se_name,
                        "work_order": work_order
                    })
                continue

            if row.batch_no:
                mp.setdefault(item_code, []).append({
                    "batch_no": row.batch_no,
                    "qty": abs(float(row.qty or 0)),
                    "stock_entry": se_name,
                    "work_order": work_order
                })

    for k in mp.keys():
        mp[k] = sorted(mp[k], key=lambda x: (x.get("batch_no") or "", x.get("stock_entry") or ""))

    return mp


def get_batch_source(batch_no: str):
    if not batch_no:
        return ("", "")

    row = frappe.db.get_value(
        "Batch",
        batch_no,
        ["reference_doctype", "reference_name"],
        as_dict=True
    ) or {}

    return (row.get("reference_doctype") or "", row.get("reference_name") or "")


def get_supplier_for_batch(batch_no: str):
    if not batch_no:
        return ""

    direct = frappe.db.get_value("Batch", batch_no, "supplier")
    if direct:
        return direct

    src_dt, src_dn = get_batch_source(batch_no)
    if src_dt and src_dn and src_dt in ("Purchase Receipt", "Purchase Invoice"):
        return frappe.db.get_value(src_dt, src_dn, "supplier") or ""

    sle = frappe.db.get_all(
        "Stock Ledger Entry",
        filters={
            "batch_no": batch_no,
            "docstatus": 1,
            "actual_qty": [">", 0],
            "voucher_type": ["in", ["Purchase Receipt", "Purchase Invoice"]],
        },
        fields=["voucher_type", "voucher_no", "posting_date", "posting_time", "creation"],
        order_by="posting_date desc, posting_time desc, creation desc",
        limit=1
    )
    if not sle:
        return ""

    vtype = sle[0]["voucher_type"]
    vno = sle[0]["voucher_no"]
    return frappe.db.get_value(vtype, vno, "supplier") or ""


def get_default_bom(item_code: str):
    return frappe.db.get_value(
        "BOM",
        {"item": item_code, "is_default": 1, "is_active": 1, "docstatus": 1},
        "name"
    )


def get_item_name(item_code: str) -> str:
    return frappe.db.get_value("Item", item_code, "item_name") or ""


def get_item_uom(item_code: str) -> str:
    return frappe.db.get_value("Item", item_code, "stock_uom") or ""


def classify_item(item_code: str) -> str:
    if not item_code:
        return ""

    has_bom = frappe.db.get_value(
        "BOM",
        {"item": item_code, "is_default": 1, "is_active": 1, "docstatus": 1},
        "name"
    )
    if has_bom:
        return "Sub BOM"

    ig = frappe.db.get_value("Item", item_code, "item_group") or ""
    ig_l = ig.lower()

    if "raw" in ig_l or "material" in ig_l or "خام" in ig:
        return "Raw Material"

    if "pack" in ig_l or "packing" in ig_l or "packaging" in ig_l or "تغليف" in ig:
        return "Packaging"

    if "finish" in ig_l or "finished" in ig_l or "نهائي" in ig:
        return "Finished"

    return "Material"


def read_bundle_batches(bundle_name: str, item_code: str = None):
    if not bundle_name:
        return []

    doc = frappe.get_doc("Serial and Batch Bundle", bundle_name)

    rows = []
    for attr in ("entries", "items", "serial_and_batch_entries"):
        if hasattr(doc, attr):
            val = getattr(doc, attr)
            if isinstance(val, list) and val:
                rows = val
                break

    if not rows:
        meta = frappe.get_meta("Serial and Batch Bundle")
        for df in meta.fields:
            if df.fieldtype == "Table" and hasattr(doc, df.fieldname):
                val = getattr(doc, df.fieldname)
                if isinstance(val, list) and val:
                    rows = val
                    break

    out = []
    for r in rows:
        r_item = getattr(r, "item_code", None) or getattr(r, "item", None)
        if item_code and r_item and r_item != item_code:
            continue

        batch_no = getattr(r, "batch_no", None) or getattr(r, "batch", None)
        qty = getattr(r, "qty", None) or getattr(r, "quantity", None) or 0

        if batch_no:
            out.append({"batch_no": batch_no, "qty": abs(float(qty or 0))})

    if item_code and not out:
        for r in rows:
            batch_no = getattr(r, "batch_no", None) or getattr(r, "batch", None)
            qty = getattr(r, "qty", None) or getattr(r, "quantity", None) or 0
            if batch_no:
                out.append({"batch_no": batch_no, "qty": abs(float(qty or 0))})

    return out
