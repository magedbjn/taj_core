import frappe

DEFAULT_LIMIT = 200
MAX_RAW_BATCHES_SCAN = 20000  # protection for scanning batch list
MAX_DEPTH = 12                # forward trace depth protection
MAX_NODES = 50000             # forward trace nodes protection


def execute(filters=None):
    filters = frappe._dict(filters or {})

    supplier_filter = (filters.get("supplier") or "").strip()
    raw_item_filter = (filters.get("raw_item") or "").strip()
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    limit = int(filters.get("limit") or DEFAULT_LIMIT)

    # Must have supplier or raw_item
    if not supplier_filter and not raw_item_filter:
        return get_columns_top_level(), []

    # Must have dates to avoid huge history
    if not from_date or not to_date:
        frappe.throw("From Date and To Date are required.")

    # 1) Find raw batches matching supplier/raw_item
    raw_batches = get_raw_batches(supplier=supplier_filter, raw_item=raw_item_filter, hardcap=MAX_RAW_BATCHES_SCAN)
    if not raw_batches:
        return get_columns_top_level(), []

    # 2) Find stock entries that consumed these raw batches (WITH raw batch)
    consuming = get_consuming_stock_entries_with_raw_batch(
        raw_batches=raw_batches,
        raw_item=raw_item_filter,
        from_date=from_date,
        to_date=to_date
    )
    if not consuming:
        return get_columns_top_level(), []

    # 3) Build level-1 outputs while carrying raw context
    level1 = build_level1_outputs(consuming_rows=consuming, raw_item_filter=raw_item_filter)
    if not level1:
        return get_columns_top_level(), []

    # 4) Walk forward to top/terminal batches, keep raw context
    data = rollup_to_terminal_batches(level1_rows=level1, from_date=from_date, to_date=to_date, limit=limit)

    # Optional: if supplier filter was set, enforce it at end too (extra safety)
    if supplier_filter:
        data = [d for d in data if (d.get("supplier") or "") == supplier_filter]

    return get_columns_top_level(), data


def get_columns_top_level():
    return [
        {"label": "Raw Material Item", "fieldname": "raw_item", "fieldtype": "Link", "options": "Item", "width": 180},
        {"label": "Raw Material Name", "fieldname": "raw_item_name", "fieldtype": "Data", "width": 220},
        {"label": "Raw Batch", "fieldname": "raw_batch", "fieldtype": "Link", "options": "Batch", "width": 140},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},

        {"label": "To Item (Top)", "fieldname": "to_item", "fieldtype": "Link", "options": "Item", "width": 180},
        {"label": "To Item Name", "fieldname": "to_item_name", "fieldtype": "Data", "width": 220},
        {"label": "To Batch (Top)", "fieldname": "to_batch", "fieldtype": "Link", "options": "Batch", "width": 140},

        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 110},
        {"label": "UOM", "fieldname": "uom", "fieldtype": "Data", "width": 80},
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": "Stock Entry", "fieldname": "stock_entry", "fieldtype": "Link", "options": "Stock Entry", "width": 160},
        {"label": "Work Order", "fieldname": "work_order", "fieldtype": "Link", "options": "Work Order", "width": 160},
    ]


# -----------------------------
# Step 1: Find raw batches
# -----------------------------

def get_raw_batches(supplier: str = "", raw_item: str = "", hardcap: int = 20000):
    """
    Returns list of raw batch numbers that match:
    - raw_item (Batch.item) if provided
    - supplier if provided (Batch.supplier OR derived from PR/PI reference)
    """
    conds = ["IFNULL(b.disabled, 0) = 0"]
    params = {}

    if raw_item:
        conds.append("b.item = %(raw_item)s")
        params["raw_item"] = raw_item

    base_where = " AND ".join(conds)

    # Fast path: Batch.supplier directly
    if supplier:
        direct = frappe.db.sql(
            f"""
            SELECT b.name
            FROM `tabBatch` b
            WHERE {base_where}
              AND b.supplier = %(supplier)s
            ORDER BY b.creation DESC
            LIMIT {hardcap}
            """,
            {**params, "supplier": supplier},
            as_list=True
        ) or []
        direct = [r[0] for r in direct]
    else:
        direct = frappe.db.sql(
            f"""
            SELECT b.name
            FROM `tabBatch` b
            WHERE {base_where}
            ORDER BY b.creation DESC
            LIMIT {hardcap}
            """,
            params,
            as_list=True
        ) or []
        direct = [r[0] for r in direct]

    if not supplier:
        return direct[:hardcap]

    # Also check reference_doctype PR/PI if Batch.supplier empty/not used
    ref_batches = frappe.db.sql(
        f"""
        SELECT b.name, b.reference_doctype, b.reference_name
        FROM `tabBatch` b
        WHERE {base_where}
          AND b.reference_doctype IN ("Purchase Receipt", "Purchase Invoice")
          AND IFNULL(b.reference_name, "") != ""
        ORDER BY b.creation DESC
        LIMIT {hardcap}
        """,
        params,
        as_dict=True
    ) or []

    matched = []
    for r in ref_batches:
        dt = r.get("reference_doctype")
        dn = r.get("reference_name")
        if not dt or not dn:
            continue
        try:
            s = frappe.db.get_value(dt, dn, "supplier")
        except Exception:
            s = None
        if s == supplier:
            matched.append(r["name"])

    out = list(dict.fromkeys(direct + matched))
    return out[:hardcap]


# -----------------------------
# Step 2: Consuming Stock Entries (WITH raw batch)
# -----------------------------

def get_consuming_stock_entries_with_raw_batch(raw_batches, raw_item, from_date, to_date):
    """
    Returns rows: {raw_batch, stock_entry}
    Supports:
      - sed.batch_no
      - sed.serial_and_batch_bundle -> tabSerial and Batch Entry
    """
    if not raw_batches:
        return []

    # detect if Serial and Batch Entry has item_code column
    sbe_has_item_code = False
    try:
        frappe.db.sql("SELECT item_code FROM `tabSerial and Batch Entry` LIMIT 1")
        sbe_has_item_code = True
    except Exception:
        sbe_has_item_code = False

    chunks = chunk_list(raw_batches, 1000)
    out = []

    for ch in chunks:
        args = {
            "from_date": from_date,
            "to_date": to_date,
            "batches": tuple(ch),
        }

        extra_sed_item = ""
        extra_sbe_item = ""
        if raw_item:
            extra_sed_item = " AND sed.item_code = %(raw_item)s "
            args["raw_item"] = raw_item
            if sbe_has_item_code:
                extra_sbe_item = " AND sbe.item_code = %(raw_item)s "

        rows = frappe.db.sql(
            f"""
            SELECT DISTINCT
                sed.batch_no AS raw_batch,
                sed.parent AS stock_entry
            FROM `tabStock Entry Detail` sed
            INNER JOIN `tabStock Entry` se ON se.name = sed.parent
            WHERE se.docstatus = 1
              AND IFNULL(sed.s_warehouse, "") != ""     -- consumed
              AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
              {extra_sed_item}
              AND sed.batch_no IN %(batches)s

            UNION ALL

            SELECT DISTINCT
                sbe.batch_no AS raw_batch,
                sed.parent AS stock_entry
            FROM `tabStock Entry Detail` sed
            INNER JOIN `tabStock Entry` se ON se.name = sed.parent
            INNER JOIN `tabSerial and Batch Entry` sbe
                    ON sbe.parent = sed.serial_and_batch_bundle
            WHERE se.docstatus = 1
              AND IFNULL(sed.s_warehouse, "") != ""     -- consumed
              AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND IFNULL(sed.serial_and_batch_bundle, "") != ""
              {extra_sbe_item}
              AND sbe.batch_no IN %(batches)s
            """,
            args,
            as_dict=True
        ) or []

        for r in rows:
            rb = (r.get("raw_batch") or "").strip()
            se = (r.get("stock_entry") or "").strip()
            if rb and se:
                out.append({"raw_batch": rb, "stock_entry": se})

    # dedup
    uniq = {}
    for r in out:
        k = (r["raw_batch"], r["stock_entry"])
        if k not in uniq:
            uniq[k] = r

    return list(uniq.values())


# -----------------------------
# Step 3: Level-1 outputs with raw context
# -----------------------------

def build_level1_outputs(consuming_rows, raw_item_filter=""):
    """
    consuming_rows: [{raw_batch, stock_entry}]
    Returns rows:
      {raw_item, raw_batch, supplier, next_item, next_batch, qty, posting_date, stock_entry, work_order}
    """
    if not consuming_rows:
        return []

    raw_batch_list = list({r["raw_batch"] for r in consuming_rows})
    batch_meta = get_batch_meta_map(raw_batch_list)  # {batch: {item, supplier}}

    se_names = list({r["stock_entry"] for r in consuming_rows})
    if not se_names:
        return []

    produced = frappe.db.sql(
        """
        SELECT
            sed.parent AS stock_entry,
            sed.item_code AS produced_item,
            sed.batch_no AS produced_batch,
            sed.serial_and_batch_bundle AS bundle_name,
            ABS(sed.qty) AS produced_qty,
            se.posting_date,
            se.work_order
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.docstatus = 1
          AND se.purpose IN ("Manufacture", "Repack")
          AND IFNULL(sed.t_warehouse, "") != ""
          AND sed.parent IN %(se_names)s
        """,
        {"se_names": tuple(se_names)},
        as_dict=True
    ) or []

    # map stock_entry -> raw_batches consumed in it
    se_to_raw_batches = {}
    for r in consuming_rows:
        se_to_raw_batches.setdefault(r["stock_entry"], set()).add(r["raw_batch"])

    rows = []
    for p in produced:
        se = (p.get("stock_entry") or "").strip()
        if not se:
            continue

        raw_batches_for_se = list(se_to_raw_batches.get(se, []))
        if not raw_batches_for_se:
            continue

        item = (p.get("produced_item") or "").strip()
        if not item:
            continue

        posting_date = p.get("posting_date")
        wo = p.get("work_order") or ""

        produced_batch = (p.get("produced_batch") or "").strip()
        bundle_name = (p.get("bundle_name") or "").strip()

        for raw_batch in raw_batches_for_se:
            meta = batch_meta.get(raw_batch, {}) or {}
            raw_item = (raw_item_filter or meta.get("item") or "").strip()
            supplier = (meta.get("supplier") or "").strip()

            # normal produced batch
            if produced_batch:
                rows.append({
                    "raw_item": raw_item,
                    "raw_batch": raw_batch,
                    "supplier": supplier,
                    "next_item": item,
                    "next_batch": produced_batch,
                    "qty": float(p.get("produced_qty") or 0),
                    "posting_date": posting_date,
                    "stock_entry": se,
                    "work_order": wo
                })

            # bundle produced batch split
            if bundle_name:
                qty_map = get_bundle_batch_qty_map_for_bundle(bundle_name=bundle_name, item_code=item)
                for bn2, q in qty_map.items():
                    if not bn2:
                        continue
                    rows.append({
                        "raw_item": raw_item,
                        "raw_batch": raw_batch,
                        "supplier": supplier,
                        "next_item": item,
                        "next_batch": bn2,
                        "qty": float(q or 0),
                        "posting_date": posting_date,
                        "stock_entry": se,
                        "work_order": wo
                    })

    # dedup
    uniq = {}
    for r in rows:
        k = (r["raw_batch"], r["next_item"], r["next_batch"], r["stock_entry"])
        if k not in uniq:
            uniq[k] = r

    return list(uniq.values())


# -----------------------------
# Step 4: Forward trace to TOP (terminal) with raw context
# -----------------------------

def rollup_to_terminal_batches(level1_rows, from_date, to_date, limit):
    """
    level1_rows: [{raw_item, raw_batch, supplier, next_item, next_batch, ...}]
    Returns final rows: Raw -> Top (Terminal)
    """
    if not level1_rows:
        return []

    terminals = []
    visited = set()
    frontier = []

    for r in level1_rows:
        frontier.append({
            "raw_item": r.get("raw_item") or "",
            "raw_batch": r.get("raw_batch") or "",
            "supplier": r.get("supplier") or "",
            "item": r.get("next_item") or "",
            "batch": r.get("next_batch") or "",
            "qty": r.get("qty"),
            "posting_date": r.get("posting_date"),
            "stock_entry": r.get("stock_entry"),
            "work_order": r.get("work_order"),
        })

    depth = 0
    nodes_count = 0

    while frontier and depth < MAX_DEPTH and nodes_count < MAX_NODES:
        depth += 1
        next_frontier = []

        frontier_batches = list({x["batch"] for x in frontier if x.get("batch")})
        batch_to_consuming_ses = get_manufacturing_consuming_stock_entries_for_batches(
            batches=frontier_batches,
            from_date=from_date,
            to_date=to_date
        )

        for node in frontier:
            # per raw-batch we might traverse different chains
            key = (node["raw_batch"], node["item"], node["batch"])
            if key in visited:
                continue
            visited.add(key)
            nodes_count += 1

            consuming_ses = batch_to_consuming_ses.get(node["batch"], [])

            # terminal if not consumed again
            if not consuming_ses:
                terminals.append(node)
                continue

            # if consumed, take outputs of those SEs
            produced_rows = get_produced_outputs_for_stock_entries(consuming_ses)
            for p in produced_rows:
                it2 = (p.get("finished_item") or "").strip()
                bn2 = (p.get("finished_batch") or "").strip()
                if not it2 or not bn2:
                    continue

                next_frontier.append({
                    "raw_item": node["raw_item"],
                    "raw_batch": node["raw_batch"],
                    "supplier": node["supplier"],
                    "item": it2,
                    "batch": bn2,
                    "qty": p.get("produced_qty"),
                    "posting_date": p.get("posting_date"),
                    "stock_entry": p.get("stock_entry"),
                    "work_order": p.get("work_order"),
                })

        frontier = next_frontier

    # dedup final output
    uniq = {}
    for t in terminals:
        k = (t["raw_batch"], t["item"], t["batch"])
        if k not in uniq:
            uniq[k] = t

    out = list(uniq.values())
    out.sort(key=lambda x: (x.get("posting_date") or "0000-00-00", x.get("batch") or ""))

    lim = max(1, int(limit or DEFAULT_LIMIT))
    out = out[:lim]

    final_rows = []
    for t in out:
        final_rows.append({
            "raw_item": t.get("raw_item"),
            "raw_item_name": get_item_name(t.get("raw_item")),
            "raw_batch": t.get("raw_batch"),
            "supplier": t.get("supplier"),

            "to_item": t.get("item"),
            "to_item_name": get_item_name(t.get("item")),
            "to_batch": t.get("batch"),

            "qty": float(t.get("qty") or 0),
            "uom": get_item_uom(t.get("item")),
            "posting_date": t.get("posting_date"),
            "stock_entry": t.get("stock_entry"),
            "work_order": t.get("work_order"),
        })

    return final_rows


def get_manufacturing_consuming_stock_entries_for_batches(batches, from_date, to_date):
    """
    For each batch_no, returns Stock Entries that CONSUMED it in Manufacture/Repack.
    Supports:
      - sed.batch_no
      - sed.serial_and_batch_bundle -> tabSerial and Batch Entry
    """
    if not batches:
        return {}

    out = {}
    chunks = list(chunk_list(batches, 800))

    for ch in chunks:
        rows = frappe.db.sql(
            """
            SELECT
                sed.batch_no AS batch_no,
                sed.parent AS stock_entry
            FROM `tabStock Entry Detail` sed
            INNER JOIN `tabStock Entry` se ON se.name = sed.parent
            WHERE se.docstatus = 1
              AND se.purpose IN ("Manufacture","Repack")
              AND IFNULL(sed.s_warehouse, "") != ""
              AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND sed.batch_no IN %(batches)s

            UNION ALL

            SELECT
                sbe.batch_no AS batch_no,
                sed.parent AS stock_entry
            FROM `tabStock Entry Detail` sed
            INNER JOIN `tabStock Entry` se ON se.name = sed.parent
            INNER JOIN `tabSerial and Batch Entry` sbe ON sbe.parent = sed.serial_and_batch_bundle
            WHERE se.docstatus = 1
              AND se.purpose IN ("Manufacture","Repack")
              AND IFNULL(sed.s_warehouse, "") != ""
              AND se.posting_date BETWEEN %(from_date)s AND %(to_date)s
              AND sbe.batch_no IN %(batches)s
              AND IFNULL(sed.serial_and_batch_bundle,"") != ""
            """,
            {"from_date": from_date, "to_date": to_date, "batches": tuple(ch)},
            as_dict=True
        ) or []

        for r in rows:
            bn = (r.get("batch_no") or "").strip()
            se = r.get("stock_entry")
            if not bn or not se:
                continue
            out.setdefault(bn, []).append(se)

    for bn in list(out.keys()):
        out[bn] = sorted(list(set(out[bn])))

    return out


def get_produced_outputs_for_stock_entries(se_names):
    """
    Produced outputs for given Stock Entries (Manufacture/Repack).
    Returns rows with keys: finished_item / finished_batch / produced_qty / posting_date / stock_entry / work_order
    Supports normal batch_no and bundle splitting.
    """
    if not se_names:
        return []

    produced = frappe.db.sql(
        """
        SELECT
            sed.parent AS stock_entry,
            sed.item_code AS finished_item,
            sed.batch_no AS finished_batch,
            sed.serial_and_batch_bundle AS bundle_name,
            ABS(sed.qty) AS produced_qty,
            se.posting_date,
            se.work_order
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.docstatus = 1
          AND se.purpose IN ("Manufacture", "Repack")
          AND IFNULL(sed.t_warehouse, "") != ""
          AND sed.parent IN %(se_names)s
        """,
        {"se_names": tuple(se_names)},
        as_dict=True
    ) or []

    rows = []
    for p in produced:
        item = (p.get("finished_item") or "").strip()
        if not item:
            continue

        posting_date = p.get("posting_date")
        se = p.get("stock_entry")
        wo = p.get("work_order") or ""

        bn = (p.get("finished_batch") or "").strip()
        if bn:
            rows.append({
                "finished_item": item,
                "finished_batch": bn,
                "produced_qty": float(p.get("produced_qty") or 0),
                "posting_date": posting_date,
                "stock_entry": se,
                "work_order": wo,
            })

        bundle = (p.get("bundle_name") or "").strip()
        if bundle:
            qty_map = get_bundle_batch_qty_map_for_bundle(bundle_name=bundle, item_code=item)
            for bn2, q in qty_map.items():
                if not bn2:
                    continue
                rows.append({
                    "finished_item": item,
                    "finished_batch": bn2,
                    "produced_qty": float(q or 0),
                    "posting_date": posting_date,
                    "stock_entry": se,
                    "work_order": wo,
                })

    return rows


# -----------------------------
# Batch meta / helpers
# -----------------------------

def get_batch_meta_map(batch_list):
    """
    Returns {batch: {item:..., supplier:...}}
    supplier from Batch.supplier OR from referenced PR/PI supplier.
    """
    if not batch_list:
        return {}

    rows = frappe.db.sql(
        """
        SELECT name, item, supplier, reference_doctype, reference_name
        FROM `tabBatch`
        WHERE name IN %(batches)s
        """,
        {"batches": tuple(batch_list)},
        as_dict=True
    ) or []

    out = {}
    for r in rows:
        bn = r.get("name")
        if not bn:
            continue

        item = r.get("item") or ""
        supplier = r.get("supplier") or ""

        if not supplier and r.get("reference_doctype") in ("Purchase Receipt", "Purchase Invoice") and r.get("reference_name"):
            try:
                supplier = frappe.db.get_value(r["reference_doctype"], r["reference_name"], "supplier") or ""
            except Exception:
                supplier = ""

        out[bn] = {"item": item, "supplier": supplier}

    return out


def get_bundle_batch_qty_map_for_bundle(bundle_name: str, item_code: str = None):
    if not bundle_name:
        return {}

    sql = """
        SELECT batch_no, COALESCE(SUM(qty), 0) AS qty
        FROM `tabSerial and Batch Entry`
        WHERE parent = %(parent)s
    """
    params = {"parent": bundle_name}

    # Optional item_code filter if column exists
    if item_code:
        try:
            frappe.db.sql("SELECT item_code FROM `tabSerial and Batch Entry` LIMIT 1")
            sql += " AND item_code = %(item_code)s"
            params["item_code"] = item_code
        except Exception:
            pass

    sql += " GROUP BY batch_no"
    rows = frappe.db.sql(sql, params, as_dict=True) or []

    out = {}
    for r in rows:
        bn = (r.get("batch_no") or "").strip()
        if not bn:
            continue
        out[bn] = float(r.get("qty") or 0)

    return out


def get_item_name(item_code: str) -> str:
    if not item_code:
        return ""
    return frappe.db.get_value("Item", item_code, "item_name") or ""


def get_item_uom(item_code: str) -> str:
    if not item_code:
        return ""
    return frappe.db.get_value("Item", item_code, "stock_uom") or ""


def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]
