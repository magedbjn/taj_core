# file : taj_core.taj_manufacutring.api.preparation_labels.py
import frappe
from math import ceil
from frappe.utils import flt, cint


TEMPLATE_PATH = "taj_manufacturing/templates/preparation_label.html"
WORK_ORDER_REQUIRED_ITEMS_FIELD = "required_items"


# ---------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------

def _as_list(value):
    if not value:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, str):
        try:
            parsed = frappe.parse_json(value)
        except Exception:
            parsed = [x.strip() for x in value.split(",") if x.strip()]

        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            return [parsed]

    return []


def _row_value(row, fieldname, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(fieldname, default)
    return getattr(row, fieldname, default)


def _norm_txt(value):
    if value is None:
        return ""
    return str(value).strip()


def _flt0(value):
    return flt(value or 0)


def _empty_operation_meta():
    return {
        "operation": "",
        "batch_size": 0,
        "split_lots": 0,
        "workstation": "",
        "production_stage": "",
    }


def _get_item_name(item_code, fallback=None):
    if fallback:
        return fallback
    if not item_code:
        return ""
    return frappe.db.get_value("Item", item_code, "item_name") or item_code



def _get_item_description(item_code, fallback=None):
    if fallback:
        return fallback
    if not item_code:
        return ""
    return frappe.db.get_value("Item", item_code, "description") or ""


def _get_item_stock_uom(item_code):
    if not item_code:
        return ""
    return frappe.db.get_value("Item", item_code, "stock_uom") or ""


def _get_item_shelf_life(item_code):
    return cint(frappe.db.get_value("Item", item_code, "shelf_life_in_days") or 0)


def _existing_fields(doctype, wanted_fields):
    meta = frappe.get_meta(doctype)
    existing = {"name", "parent"} | {df.fieldname for df in meta.fields}
    return [f for f in wanted_fields if f in existing]


def _get_job_card_stage(source_job_card=None):
    if not source_job_card:
        return ""

    jc_ws = frappe.db.get_value("Job Card", source_job_card, "workstation") or ""
    if not jc_ws:
        return ""

    return _norm_txt(
        frappe.db.get_value("Workstation", jc_ws, "taj_production_stage") or ""
    ).lower()


def _should_allow_print(job_card_stage, source_stage):
    return (job_card_stage == "cooking") or (_norm_txt(source_stage).lower() == "cooking")


def _qty_close(a, b, tolerance=0.05):
    return abs(flt(a) - flt(b)) <= tolerance


def _format_planned_and_ep(planned_start_date, shelf_days):
    planned_txt = ""
    ep_txt = ""

    if planned_start_date:
        planned_dt = frappe.utils.get_datetime(planned_start_date)
        planned_txt = planned_dt.strftime("%d-%m-%Y")

        if cint(shelf_days) > 0:
            ep_dt = frappe.utils.add_days(planned_dt.date(), cint(shelf_days))
            ep_txt = frappe.utils.get_datetime(ep_dt).strftime("%d-%m-%Y")

    return planned_txt, ep_txt


# ---------------------------------------------------------------------
# BOM helpers
# ---------------------------------------------------------------------

def _get_bom_doc(bom_no):
    if not bom_no:
        return None
    return frappe.get_cached_doc("BOM", bom_no)


def _get_workstation_stage(workstation):
    if not workstation:
        return ""
    return _norm_txt(
        frappe.db.get_value("Workstation", workstation, "taj_production_stage") or ""
    )


def _get_operation_meta_index(bom):
    op_map = {}
    cooking_meta = None
    first_meta = None

    for op in (bom.operations or []):
        op_name = _norm_txt(op.operation)
        stage = _get_workstation_stage(op.workstation)

        meta = {
            "operation": op_name,
            "batch_size": flt(op.batch_size),
            "split_lots": cint(op.taj_split_batch or 0),
            "workstation": op.workstation or "",
            "production_stage": stage,
        }

        if op_name:
            op_map[op_name] = meta

        if not first_meta:
            first_meta = meta

        if not cooking_meta and stage.lower() == "cooking":
            cooking_meta = meta

    return op_map, cooking_meta, first_meta


def _get_operation_meta_from_bom(bom_no, operation=None):
    bom = _get_bom_doc(bom_no)
    if not bom:
        return _empty_operation_meta()

    op_map, cooking_meta, first_meta = _get_operation_meta_index(bom)
    op_name = _norm_txt(operation)

    if op_name and op_name in op_map:
        return dict(op_map[op_name])

    if cooking_meta:
        return dict(cooking_meta)

    if first_meta:
        return dict(first_meta)

    return _empty_operation_meta()


def _get_link_rows_from_source_bom(source_bom_no, linked_item_code):
    rows = []

    if not source_bom_no or not linked_item_code:
        return rows

    bom = _get_bom_doc(source_bom_no)
    if not bom:
        return rows

    source_bom_qty = flt(bom.quantity) or 1
    linked_item_code = _norm_txt(linked_item_code)

    for bi in (bom.items or []):
        if _norm_txt(bi.item_code) != linked_item_code:
            continue

        op_name = _norm_txt(bi.operation)
        op_meta = _get_operation_meta_from_bom(source_bom_no, op_name)

        rows.append({
            "linked_row_name": _row_value(bi, "name"),
            "linked_item_code": linked_item_code,
            "linked_item_qty": flt(bi.qty),
            "source_bom_qty": source_bom_qty,
            "linked_item_name": bi.item_name or "",
            "linked_item_description": bi.description or "",
            "linked_item_operation": op_name,
            "linked_bom_no": _norm_txt(_row_value(bi, "bom_no")),
            "batch_size": flt(op_meta.get("batch_size") or 0),
            "split_lots": cint(op_meta.get("split_lots") or 0),
            "workstation": op_meta.get("workstation") or "",
            "production_stage": op_meta.get("production_stage") or "",
        })

    return rows


# ---------------------------------------------------------------------
# selected rows helpers
# ---------------------------------------------------------------------

def _get_selected_required_item_filters(work_order_doc, selected_row_names):
    selected_row_names = set(_as_list(selected_row_names))
    if not selected_row_names:
        return []

    out = []
    seen = set()

    for row in (work_order_doc.get(WORK_ORDER_REQUIRED_ITEMS_FIELD) or []):
        if row.name not in selected_row_names:
            continue

        item_code = _norm_txt(_row_value(row, "item_code"))
        operation = _norm_txt(_row_value(row, "operation"))
        key = (item_code, operation, row.name)

        if key in seen:
            continue

        seen.add(key)
        out.append({
            "name": row.name,
            "item_code": item_code,
            "operation": operation,
        })

    return out


def _build_selected_lookup(selected_item_filters):
    pair_set = set()
    code_only_set = set()

    for row in (selected_item_filters or []):
        item_code = _norm_txt(row.get("item_code"))
        operation = _norm_txt(row.get("operation"))

        if not item_code:
            continue

        if operation:
            pair_set.add((item_code, operation))
        else:
            code_only_set.add(item_code)

    return pair_set, code_only_set


def _is_row_selected(row, selected_lookup):
    pair_set, code_only_set = selected_lookup

    if not pair_set and not code_only_set:
        return True

    row_item_code = _norm_txt(_row_value(row, "item_code"))
    row_operation = _norm_txt(_row_value(row, "operation"))

    if row_item_code in code_only_set:
        return True

    if (row_item_code, row_operation) in pair_set:
        return True

    return False


# ---------------------------------------------------------------------
# chunk helpers
# ---------------------------------------------------------------------

def _build_loads(total_qty, batch_size):
    total_qty = flt(total_qty)
    batch_size = flt(batch_size)

    if total_qty <= 0:
        return []

    if batch_size <= 0:
        batch_size = total_qty

    loads = int(ceil(total_qty / batch_size)) if total_qty > 0 else 0
    if loads < 1:
        loads = 1

    out = []
    for load_i in range(1, loads + 1):
        rem = total_qty - ((load_i - 1) * batch_size)

        if rem <= 0:
            qty = 0
        elif rem >= batch_size:
            qty = batch_size
        else:
            qty = rem

        if qty <= 0:
            continue

        out.append({
            "load_i": load_i,
            "loads": loads,
            "qty": qty,
        })

    return out


def _build_lots(load_qty, lot_size):
    load_qty = flt(load_qty)
    lot_size = flt(lot_size)

    if load_qty <= 0:
        return []

    if lot_size <= 0:
        return [{
            "lot_i": None,
            "lot_total": None,
            "qty": load_qty,
        }]

    lot_total = int(ceil(load_qty / lot_size)) if load_qty > 0 else 0
    if lot_total < 1:
        lot_total = 1

    out = []
    for lot_i in range(1, lot_total + 1):
        rem = load_qty - ((lot_i - 1) * lot_size)

        if rem <= 0:
            qty = 0
        elif rem >= lot_size:
            qty = lot_size
        else:
            qty = rem

        if qty <= 0:
            continue

        out.append({
            "lot_i": lot_i,
            "lot_total": lot_total,
            "qty": qty,
        })

    return out


def _distribute_total_across_chunks(total_required_qty, chunks, base_total_qty):
    total_required_qty = flt(total_required_qty)
    base_total_qty = flt(base_total_qty)

    if total_required_qty <= 0 or base_total_qty <= 0 or not chunks:
        return []

    out = []
    remaining = total_required_qty

    for idx, chunk in enumerate(chunks, start=1):
        calc_qty = total_required_qty * (flt(chunk.get("chunk_qty")) / base_total_qty)

        if idx < len(chunks):
            out_qty = calc_qty if remaining >= calc_qty else remaining
        else:
            out_qty = remaining

        out_qty = flt(out_qty)
        if out_qty <= 0:
            continue

        row = dict(chunk)
        row["out_qty"] = out_qty
        out.append(row)

        remaining = flt(remaining - out_qty)

    return out


# ---------------------------------------------------------------------
# source builders / resolvers
# ---------------------------------------------------------------------

def _default_work_order_source(doc):
    item_code = getattr(doc, "production_item", None) or getattr(doc, "item_code", None)
    op_meta = _get_operation_meta_from_bom(doc.bom_no, "")

    return {
        "source_type": "work_order",
        "source_name": doc.name,
        "qty": flt(doc.qty),
        "bom_no": doc.bom_no,
        "planned_start_date": doc.planned_start_date,
        "item_code": item_code,
        "item_name": doc.item_name or _get_item_name(item_code),
        "operation": op_meta.get("operation") or "",
        "batch_size": flt(op_meta.get("batch_size") or 0),
        "split_lots": cint(op_meta.get("split_lots") or 0),
        "workstation": op_meta.get("workstation") or "",
        "production_stage": op_meta.get("production_stage") or "",
        "linked_rows": [],
        "linked_bom_hint": "",
        "linked_operation_hint": "",
    }


def _build_source_from_pp_item(pp_item_name, linked_item_code=None, linked_bom_hint=None, linked_operation_hint=None):
    if not pp_item_name:
        return None

    pp_item_fields = _existing_fields(
        "Production Plan Item",
        ["name", "item_code", "bom_no", "planned_qty", "planned_start_date", "operation"]
    )

    assembly_row = frappe.db.get_value(
        "Production Plan Item",
        pp_item_name,
        pp_item_fields,
        as_dict=True,
    )

    if not assembly_row:
        return None

    item_code = assembly_row.get("item_code")
    bom_no = assembly_row.get("bom_no")
    operation = _norm_txt(assembly_row.get("operation"))
    op_meta = _get_operation_meta_from_bom(bom_no, operation)

    linked_rows = []
    if linked_item_code:
        linked_rows = _get_link_rows_from_source_bom(bom_no, linked_item_code)

    return {
        "source_type": "assembly_item",
        "source_name": assembly_row.get("name"),
        "qty": flt(assembly_row.get("planned_qty")),
        "bom_no": bom_no,
        "planned_start_date": assembly_row.get("planned_start_date"),
        "item_code": item_code,
        "item_name": _get_item_name(item_code),
        "operation": op_meta.get("operation") or operation,
        "batch_size": flt(op_meta.get("batch_size") or 0),
        "split_lots": cint(op_meta.get("split_lots") or 0),
        "workstation": op_meta.get("workstation") or "",
        "production_stage": op_meta.get("production_stage") or "",
        "linked_rows": linked_rows,
        "linked_bom_hint": _norm_txt(linked_bom_hint),
        "linked_operation_hint": _norm_txt(linked_operation_hint),
    }


def _resolve_pp_item_reference(production_plan, pp_item_ref):
    if not pp_item_ref:
        return None

    if frappe.db.exists("Production Plan Item", pp_item_ref):
        return pp_item_ref

    return frappe.db.get_value(
        "Production Plan Item",
        {
            "parent": production_plan,
            "temporary_name": pp_item_ref,
        },
        "name",
    )


def _get_sub_assembly_row_fields():
    return _existing_fields(
        "Production Plan Sub Assembly Item",
        [
            "name",
            "parent",
            "production_item",
            "bom_no",
            "planned_start_date",
            "schedule_date",
            "operation",
            "qty",
            "stock_qty",
            "planned_qty",
            "required_qty",
            "sub_assembly_qty",
            "production_qty",
            "taj_merge_group_id",
            "production_plan_item",
            "parent_item_code",
        ],
    )


def _get_current_sub_assembly_row(doc):
    sub_assembly_row_name = getattr(doc, "production_plan_sub_assembly_item", None)
    if not sub_assembly_row_name:
        return None

    return frappe.db.get_value(
        "Production Plan Sub Assembly Item",
        sub_assembly_row_name,
        _get_sub_assembly_row_fields(),
        as_dict=True,
    )


def _get_sub_assembly_row_qty(current_sub):
    for fieldname in (
        "required_qty",
        "stock_qty",
        "qty",
        "planned_qty",
        "sub_assembly_qty",
        "production_qty",
    ):
        qty = flt(current_sub.get(fieldname) or 0)
        if qty > 0:
            return qty
    return 0


def _get_relevant_link_rows(source):
    link_rows = list(source.get("linked_rows") or [])
    if not link_rows:
        return []

    bom_hint = _norm_txt(source.get("linked_bom_hint"))
    if bom_hint:
        bom_rows = [r for r in link_rows if _norm_txt(r.get("linked_bom_no")) == bom_hint]
        if bom_rows:
            link_rows = bom_rows

    operation_hint = _norm_txt(source.get("linked_operation_hint"))
    if operation_hint:
        op_rows = [r for r in link_rows if _norm_txt(r.get("linked_item_operation")) == operation_hint]
        if op_rows:
            link_rows = op_rows

    return link_rows


def _calculate_expected_sub_qty_for_source(source):
    total = 0

    for row in _get_relevant_link_rows(source):
        source_bom_qty = flt(row.get("source_bom_qty") or 1)
        linked_item_qty = flt(row.get("linked_item_qty") or 0)
        source_qty = flt(source.get("qty") or 0)

        if source_bom_qty <= 0 or linked_item_qty <= 0 or source_qty <= 0:
            continue

        total += linked_item_qty * (source_qty / source_bom_qty)

    return total


def _resolve_pp_item_from_sub_assembly(current_sub):
    return _resolve_pp_item_reference(
        current_sub.get("parent"),
        current_sub.get("production_plan_item"),
    )


def _get_parent_assembly_candidates(current_sub):
    pp_item_fields = _existing_fields(
        "Production Plan Item",
        ["name", "item_code", "bom_no", "planned_qty", "planned_start_date", "operation"]
    )

    filters = {"parent": current_sub.get("parent")}
    if current_sub.get("parent_item_code"):
        filters["item_code"] = current_sub.get("parent_item_code")

    return frappe.get_all(
        "Production Plan Item",
        filters=filters,
        fields=pp_item_fields,
        order_by="idx asc",
    )


def _resolve_merged_sources(current_sub):
    pp = frappe.get_doc("Production Plan", current_sub.get("parent"))
    split_rows = []

    for row in (getattr(pp, "taj_sub_assembly_items_split", None) or []):
        if _norm_txt(getattr(row, "merge_group_id", None)) == _norm_txt(current_sub.get("taj_merge_group_id")):
            split_rows.append(row.as_dict())

    if not split_rows:
        return []

    sources = []
    seen_source_names = set()

    for split_row in split_rows:
        actual_pp_item = _resolve_pp_item_reference(
            current_sub.get("parent"),
            split_row.get("source_assembly_item"),
        )

        if not actual_pp_item:
            frappe.throw(
                "Could not resolve source Production Plan Item from split row reference "
                f"{split_row.get('source_assembly_item')}"
            )

        source = _build_source_from_pp_item(
            actual_pp_item,
            linked_item_code=current_sub.get("production_item"),
            linked_bom_hint=current_sub.get("bom_no"),
            linked_operation_hint=current_sub.get("operation"),
        )

        if not source:
            frappe.throw(f"Could not build source from Production Plan Item: {actual_pp_item}")

        if not source.get("linked_rows"):
            frappe.throw(
                f"Item {current_sub.get('production_item')} was not found in source BOM {source.get('bom_no')}."
            )

        source_key = _norm_txt(source.get("source_name")) or _norm_txt(actual_pp_item)
        if source_key in seen_source_names:
            continue

        seen_source_names.add(source_key)
        sources.append(source)

    return sources


def _find_matching_parent_source_for_non_merged(current_sub):
    current_sub_qty = _get_sub_assembly_row_qty(current_sub)
    if current_sub_qty <= 0:
        return None

    candidates = []

    for row in _get_parent_assembly_candidates(current_sub):
        source = _build_source_from_pp_item(
            row.get("name"),
            linked_item_code=current_sub.get("production_item"),
            linked_bom_hint=current_sub.get("bom_no"),
            linked_operation_hint=current_sub.get("operation"),
        )

        if not source or not source.get("linked_rows"):
            continue

        expected_qty = _calculate_expected_sub_qty_for_source(source)
        diff = abs(expected_qty - current_sub_qty)

        candidates.append({
            "source": source,
            "expected_qty": expected_qty,
            "diff": diff,
        })

    if not candidates:
        return None

    exact_matches = [c for c in candidates if _qty_close(c["expected_qty"], current_sub_qty)]

    if len(exact_matches) == 1:
        return exact_matches[0]["source"]

    if len(exact_matches) > 1:
        exact_matches = sorted(exact_matches, key=lambda x: x["diff"])

        if len(exact_matches) >= 2 and exact_matches[0]["diff"] < exact_matches[1]["diff"]:
            return exact_matches[0]["source"]

        candidates_txt = ", ".join(
            [
                f"{c['source'].get('item_code')} ({c['source'].get('source_name')}) => expected {round(c['expected_qty'], 3)}"
                for c in exact_matches
            ]
        )
        frappe.throw(
            "More than one Assembly Item matched the current non-merged Sub Assembly qty. "
            f"Candidates: {candidates_txt}"
        )

    best = min(candidates, key=lambda x: x["diff"])
    if best["diff"] <= 0.05:
        return best["source"]

    return None


def _find_safe_single_source_from_bom_match(current_sub):
    matched = []

    for row in _get_parent_assembly_candidates(current_sub):
        source = _build_source_from_pp_item(
            row.get("name"),
            linked_item_code=current_sub.get("production_item"),
            linked_bom_hint=current_sub.get("bom_no"),
            linked_operation_hint=current_sub.get("operation"),
        )

        if source and source.get("linked_rows"):
            matched.append(source)

    if len(matched) == 1:
        return matched[0]

    return None


def _resolve_sub_assembly_sources(doc):
    current_sub = _get_current_sub_assembly_row(doc)
    if not current_sub:
        return []

    if _norm_txt(current_sub.get("taj_merge_group_id")):
        merged_sources = _resolve_merged_sources(current_sub)
        if merged_sources:
            return merged_sources

    non_merged_source = _resolve_non_merged_source(current_sub)
    if non_merged_source:
        return [non_merged_source]

    frappe.throw(
        "Could not resolve source for Sub Assembly row "
        f"{current_sub.get('name')}. "
        "Expected merged split rows or a direct non-merged Production Plan Item link."
    )
    
def _get_print_sources(doc):
    if getattr(doc, "production_plan_sub_assembly_item", None):
        return _resolve_sub_assembly_sources(doc)

    return [_default_work_order_source(doc)]


# ---------------------------------------------------------------------
# label builders
# ---------------------------------------------------------------------

def _append_label(labels, row, distribution, product_name, label_operation, planned_start_date, show_ep=True):
    item_code = _norm_txt(_row_value(row, "item_code"))
    item_name = _row_value(row, "item_name") or _get_item_name(item_code)
    description = _row_value(row, "description") or _get_item_description(item_code)
    shelf_days = _get_item_shelf_life(item_code)

    planned_txt, ep_txt = _format_planned_and_ep(planned_start_date, shelf_days)

    if not show_ep:
        ep_txt = ""

    labels.append({
        "product_name": product_name or "",
        "item_code": item_code,
        "item_name": item_name,
        "description": description,
        "planned_txt": planned_txt,
        "ep_txt": ep_txt,
        "show_ep": 1 if show_ep else 0,
        "qty": flt(distribution.get("out_qty") or 0),
        "load_i": distribution.get("load_i"),
        "loads": distribution.get("loads"),
        "lot_i": distribution.get("lot_i"),
        "lot_total": distribution.get("lot_total"),
        "label_operation": label_operation or "",
    })


def _build_regular_work_order_labels(doc, source, selected_item_filters=None, source_job_card=None, show_ep=True):
    labels = []
    selected_lookup = _build_selected_lookup(selected_item_filters or [])
    job_card_stage = _get_job_card_stage(source_job_card)

    bom = _get_bom_doc(source.get("bom_no"))
    if not bom:
        return labels

    bom_qty = flt(bom.quantity) or 1
    op_map, _, _ = _get_operation_meta_index(bom)

    for row in (bom.items or []):
        if not _is_row_selected(row, selected_lookup):
            continue

        row_qty = flt(_row_value(row, "qty") or 0)
        if row_qty <= 0:
            continue

        op_name = _norm_txt(_row_value(row, "operation")) or _norm_txt(source.get("operation"))
        op_meta = dict(op_map.get(op_name) or {})
        if not op_meta:
            op_meta = _get_operation_meta_from_bom(source.get("bom_no"), op_name)

        source_stage = _norm_txt(op_meta.get("production_stage") or source.get("production_stage")).lower()
        if not _should_allow_print(job_card_stage, source_stage):
            continue

        source_qty = flt(source.get("qty") or 0)
        if source_qty <= 0:
            continue

        row_total_required = row_qty * (source_qty / bom_qty)
        if row_total_required <= 0:
            continue

        batch_size = flt(op_meta.get("batch_size") or source.get("batch_size") or bom_qty)
        if batch_size <= 0:
            batch_size = source_qty

        split_lots = cint(op_meta.get("split_lots") or source.get("split_lots") or 0)

        chunk_defs = []
        for load in _build_loads(source_qty, batch_size):
            if split_lots == 1:
                lots = _build_lots(load["qty"], bom_qty)
                for lot in lots:
                    chunk_defs.append({
                        "chunk_qty": flt(lot["qty"]),
                        "load_i": load["load_i"],
                        "loads": load["loads"],
                        "lot_i": lot["lot_i"],
                        "lot_total": lot["lot_total"],
                    })
            else:
                chunk_defs.append({
                    "chunk_qty": flt(load["qty"]),
                    "load_i": load["load_i"],
                    "loads": load["loads"],
                    "lot_i": None,
                    "lot_total": None,
                })

        distributions = _distribute_total_across_chunks(
            total_required_qty=row_total_required,
            chunks=chunk_defs,
            base_total_qty=source_qty,
        )

        for dist in distributions:
            _append_label(
                labels=labels,
                row=row,
                distribution=dist,
                product_name=source.get("item_name") or doc.item_name or "",
                label_operation=op_name,
                planned_start_date=source.get("planned_start_date"),
                show_ep=show_ep,
            )

    return labels


def _build_sub_assembly_chunks(doc, sources, source_job_card=None):
    job_card_stage = _get_job_card_stage(source_job_card)
    chunks = []

    for source in (sources or []):
        source_qty = flt(source.get("qty") or 0)
        if source_qty <= 0:
            continue

        for link_row in _get_relevant_link_rows(source):
            source_stage = _norm_txt(link_row.get("production_stage")).lower()
            if not _should_allow_print(job_card_stage, source_stage):
                continue

            batch_size = flt(link_row.get("batch_size") or source.get("batch_size") or source_qty)
            if batch_size <= 0:
                batch_size = source_qty

            source_bom_qty = flt(link_row.get("source_bom_qty") or 1)
            linked_item_qty = flt(link_row.get("linked_item_qty") or 0)

            if source_bom_qty <= 0 or linked_item_qty <= 0:
                continue

            for load in _build_loads(source_qty, batch_size):
                sub_chunk_qty = linked_item_qty * (flt(load["qty"]) / source_bom_qty)

                if sub_chunk_qty <= 0:
                    continue

                chunks.append({
                    "chunk_qty": flt(sub_chunk_qty),
                    "load_i": load["load_i"],
                    "loads": load["loads"],
                    "lot_i": None,
                    "lot_total": None,
                    "planned_start_date": source.get("planned_start_date"),
                    "product_name": source.get("item_name") or "",
                    "label_operation": _norm_txt(link_row.get("linked_item_operation")),
                })

    return chunks


def _build_sub_assembly_labels(doc, sources, selected_item_filters=None, source_job_card=None, show_ep=True):
    labels = []
    selected_lookup = _build_selected_lookup(selected_item_filters or [])
    sub_total_qty = flt(doc.qty or 0)

    if sub_total_qty <= 0:
        return labels

    chunks = _build_sub_assembly_chunks(doc, sources, source_job_card=source_job_card)
    if not chunks:
        return labels

    for row in (doc.required_items or []):
        if not _is_row_selected(row, selected_lookup):
            continue

        total_required_qty = flt(_row_value(row, "required_qty") or _row_value(row, "qty") or 0)
        if total_required_qty <= 0:
            continue

        distributions = _distribute_total_across_chunks(
            total_required_qty=total_required_qty,
            chunks=chunks,
            base_total_qty=sub_total_qty,
        )

        for dist in distributions:
            _append_label(
                labels=labels,
                row=row,
                distribution=dist,
                product_name=dist.get("product_name") or doc.item_name or "",
                label_operation=dist.get("label_operation") or "",
                planned_start_date=dist.get("planned_start_date"),
                show_ep=show_ep,
            )

    return labels


def _build_sub_assembly_product_labels(doc, sources, source_job_card=None):
    labels = []

    produced_item_code = getattr(doc, "production_item", None) or getattr(doc, "item_code", None)
    if not produced_item_code:
        return labels

    produced_row = {
        "item_code": produced_item_code,
        "item_name": doc.item_name or _get_item_name(produced_item_code),
        "description": _get_item_description(produced_item_code),
    }

    chunks = _build_sub_assembly_chunks(doc, sources, source_job_card=source_job_card)
    if not chunks:
        return labels

    for chunk in chunks:
        out_qty = flt(chunk.get("chunk_qty") or 0)
        if out_qty <= 0:
            continue

        distribution = dict(chunk)
        distribution["out_qty"] = out_qty

        _append_label(
            labels=labels,
            row=produced_row,
            distribution=distribution,
            product_name=chunk.get("product_name") or doc.item_name or "",
            label_operation=chunk.get("label_operation") or "",
            planned_start_date=chunk.get("planned_start_date"),
            show_ep=True,
        )

    return labels


def _build_all_labels(doc, selected_item_filters=None, source_job_card=None, label_mode="standard"):
    sources = _get_print_sources(doc)

    if getattr(doc, "production_plan_sub_assembly_item", None):
        if label_mode == "cooking":
            labels = _build_sub_assembly_product_labels(
                doc,
                sources,
                source_job_card=source_job_card,
            )
        elif label_mode == "raw":
            labels = _build_sub_assembly_labels(
                doc,
                sources,
                selected_item_filters=selected_item_filters,
                source_job_card=source_job_card,
                show_ep=False,
            )
        else:
            labels = _build_sub_assembly_labels(
                doc,
                sources,
                selected_item_filters=selected_item_filters,
                source_job_card=source_job_card,
                show_ep=True,
            )
    else:
        labels = []
        for source in sources:
            labels.extend(
                _build_regular_work_order_labels(
                    doc,
                    source,
                    selected_item_filters=selected_item_filters,
                    source_job_card=source_job_card,
                    show_ep=(label_mode != "raw"),
                )
            )

    return labels




# ---------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------

@frappe.whitelist()
def get_required_items_for_work_order(work_order):
    work_order_doc = frappe.get_doc("Work Order", work_order)
    work_order_doc.check_permission("read")

    rows = []
    for row in (work_order_doc.get(WORK_ORDER_REQUIRED_ITEMS_FIELD) or []):
        rows.append({
            "name": row.name,
            "item_code": row.item_code,
            "item_name": row.item_name or _get_item_name(row.item_code),
            "description": row.description,
            "operation": _norm_txt(_row_value(row, "operation")),
        })

    return rows


@frappe.whitelist()
def render_preparation_labels_html(work_order, selected_rows=None, source_job_card=None, label_mode="standard"):
    work_order_doc = frappe.get_doc("Work Order", work_order)
    work_order_doc.check_permission("read")

    selected_item_filters = _get_selected_required_item_filters(
        work_order_doc,
        _as_list(selected_rows),
    )

    labels = _build_all_labels(
        work_order_doc,
        selected_item_filters=selected_item_filters,
        source_job_card=source_job_card,
        label_mode=label_mode,
    )

    if not labels:
        frappe.throw(
            "No labels were built. Check source resolution, operation stage, "
            "required items, and BOM links."
        )

    context = {
        "labels": labels,
    }

    html = frappe.render_template(TEMPLATE_PATH, context)
    return {"html": html}


@frappe.whitelist()
def render_preparation_labels_from_job_card(job_card, selected_rows=None, label_mode="standard"):
    jc = frappe.get_doc("Job Card", job_card)
    jc.check_permission("read")

    if not jc.work_order:
        frappe.throw("Job Card does not have a linked Work Order.")

    return render_preparation_labels_html(
        work_order=jc.work_order,
        selected_rows=selected_rows,
        source_job_card=jc.name,
        label_mode=label_mode,
    )



def _resolve_non_merged_source(current_sub):
    pp_item_name = _norm_txt(current_sub.get("production_plan_item"))
    parent_item_code = _norm_txt(current_sub.get("parent_item_code"))
    parent = current_sub.get("parent")

    if not pp_item_name or not parent_item_code or not parent:
        return None

    ppi = frappe.db.get_value(
        "Production Plan Item",
        {
            "parent": parent,
            "name": pp_item_name,
            "item_code": parent_item_code,
        },
        ["name"],
        as_dict=True,
    )

    if not ppi:
        return None

    return _build_source_from_pp_item(
        ppi.get("name"),
        linked_item_code=current_sub.get("production_item"),
        linked_bom_hint=current_sub.get("bom_no"),
        linked_operation_hint=current_sub.get("operation"),
    )



def _aggregate_labels_by_item(labels):
    grouped = {}

    for lbl in (labels or []):
        item_code = _norm_txt(lbl.get("item_code"))
        if not item_code:
            continue

        if item_code not in grouped:
            grouped[item_code] = {
                "item_code": item_code,
                "item_name": lbl.get("item_name") or _get_item_name(item_code),
                "qty": 0.0,
                "uom": _get_item_stock_uom(item_code),
            }

        grouped[item_code]["qty"] = flt(grouped[item_code]["qty"]) + flt(lbl.get("qty") or 0)

    return list(grouped.values())





def _aggregate_items(items):
    grouped = {}

    for row in (items or []):
        item_code = _norm_txt(row.get("item_code"))
        if not item_code:
            continue

        if item_code not in grouped:
            grouped[item_code] = {
                "item_code": item_code,
                "item_name": row.get("item_name") or _get_item_name(item_code),
                "qty": 0.0,
                "uom": row.get("uom") or _get_item_stock_uom(item_code),
            }

        grouped[item_code]["qty"] = flt(grouped[item_code]["qty"]) + flt(row.get("qty") or 0)

    return list(grouped.values())

@frappe.whitelist()
def get_raw_materials_from_job_card(job_card, selected_rows=None):
    jc = frappe.get_doc("Job Card", job_card)
    jc.check_permission("read")

    if not jc.work_order:
        frappe.throw("Job Card does not have a linked Work Order.")

    work_order_doc = frappe.get_doc("Work Order", jc.work_order)
    work_order_doc.check_permission("read")

    selected_item_filters = _get_selected_required_item_filters(
        work_order_doc,
        _as_list(selected_rows),
    )

    # المسار الأول: استخدم منطق الملصقات الحالي.
    # الأخطاء الحقيقية يجب أن تظهر للمستخدم بدل إخفائها
    # والتحول بصمت إلى نتيجة مختلفة.
    labels = _build_all_labels(
        work_order_doc,
        selected_item_filters=selected_item_filters,
        source_job_card=jc.name,
    )

    items = _aggregate_labels_by_item(labels)

    if items:
        return {"items": items}

    # fallback فقط عندما لا ينتج المسار الأساسي أي عناصر.
    # وارجع required_items بالكميات الكاملة الحالية
    selected_lookup = _build_selected_lookup(selected_item_filters or [])
    direct_rows = []

    for row in (work_order_doc.get(WORK_ORDER_REQUIRED_ITEMS_FIELD) or []):
        if not _is_row_selected(row, selected_lookup):
            continue

        item_code = _norm_txt(_row_value(row, "item_code"))
        if not item_code:
            continue

        qty = flt(_row_value(row, "required_qty") or _row_value(row, "qty") or 0)
        if qty <= 0:
            continue

        direct_rows.append({
            "item_code": item_code,
            "item_name": _row_value(row, "item_name") or _get_item_name(item_code),
            "qty": qty,
            "uom": _get_item_stock_uom(item_code),
        })

    return {"items": _aggregate_items(direct_rows)}