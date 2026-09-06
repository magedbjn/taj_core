import math
from decimal import Decimal, ROUND_DOWN

import frappe
from frappe import _
from frappe.utils import flt, cint, getdate, add_days


def _q2_down(value):
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_DOWN))


def _get_item_name(item_code):
    if not item_code:
        return ""
    return frappe.db.get_value("Item", item_code, "item_name") or item_code


def _get_selected_item_codes_from_work_order(wo):
    selected = []
    for row in wo.required_items:
        if cint(getattr(row, "taj_select_for_steamer_label", 0)) == 1 and row.item_code:
            selected.append(row.item_code)

    return list(dict.fromkeys(selected))  # unique keep order


def _get_source_contexts_from_work_order(wo):
    """
    Returns a list of source contexts.
    Every context behaves like the source document for label generation.
    """

    contexts = []

    # CASE 1: Direct Production Plan Item or normal WO flow
    if getattr(wo, "production_plan_item", None):
        contexts.append({
            "source_type": "work_order_direct",
            "source_name": wo.name,
            "qty": flt(wo.qty),
            "bom_no": wo.bom_no,
            "planned_start_date": wo.planned_start_date,
            "item_code": getattr(wo, "production_item", None) or getattr(wo, "item_code", None),
            "item_name": wo.item_name or _get_item_name(getattr(wo, "production_item", None)),
        })
        return contexts

    # CASE 2: production_plan_sub_assembly_item
    sub_assembly_row = getattr(wo, "production_plan_sub_assembly_item", None)
    if sub_assembly_row:
        sub_row = frappe.db.get_value(
            "Production Plan Sub Assembly Item",
            sub_assembly_row,
            [
                "name",
                "parent",
                "production_item",
                "bom_no",
                "taj_merge_group_id",
            ],
            as_dict=True,
        )

        if not sub_row:
            frappe.throw(_("Production Plan Sub Assembly Item not found: {0}").format(sub_assembly_row))

        # merged => taj_merge_group_id
        # non merged => fallback to own row name
        merge_key = sub_row.taj_merge_group_id or sub_row.name

        split_rows = frappe.get_all(
            "Production Plan Sub Assembly Split",
            filters={
                "parent": sub_row.parent,
                "merge_group_id": merge_key
            },
            fields=[
                "name",
                "source_sub_assembly_item",
                "source_assembly_item",
                "merge_group_id",
            ],
            order_by="idx asc"
        )

        if not split_rows:
            frappe.throw(_("No split rows found for sub assembly item: {0}").format(sub_row.name))

        for split_row in split_rows:
            if not split_row.source_assembly_item:
                continue

            asm = frappe.db.get_value(
                "Production Plan Item",
                split_row.source_assembly_item,
                [
                    "name",
                    "item_code",
                    "bom_no",
                    "planned_qty",
                    "planned_start_date",
                ],
                as_dict=True,
            )

            if not asm:
                continue

            contexts.append({
                "source_type": "assembly_item_from_sub_assembly",
                "source_name": asm.name,
                "qty": flt(asm.planned_qty),
                "bom_no": asm.bom_no,
                "planned_start_date": asm.planned_start_date,
                "item_code": asm.item_code,
                "item_name": _get_item_name(asm.item_code),
            })

        return contexts

    # CASE 3: fallback normal WO
    contexts.append({
        "source_type": "work_order_fallback",
        "source_name": wo.name,
        "qty": flt(wo.qty),
        "bom_no": wo.bom_no,
        "planned_start_date": wo.planned_start_date,
        "item_code": getattr(wo, "production_item", None) or getattr(wo, "item_code", None),
        "item_name": wo.item_name or _get_item_name(getattr(wo, "production_item", None)),
    })

    return contexts


def _build_labels_for_source(ctx, selected_item_codes=None):
    labels = []

    qty = flt(ctx.get("qty"))
    bom_no = ctx.get("bom_no")
    planned_start_date = ctx.get("planned_start_date")
    product_name = ctx.get("item_name") or ""
    product_code = ctx.get("item_code") or ""

    if not bom_no or qty <= 0:
        return labels

    bom = frappe.get_doc("BOM", bom_no)
    bom_qty = flt(bom.quantity) or 1

    # BOM items direct
    bom_rows = list(bom.items)

    # selection from Work Order required_items
    if selected_item_codes:
        bom_rows = [r for r in bom_rows if r.item_code in selected_item_codes]

    # cache operations
    op_batch_size = {}
    op_split_batch = {}
    op_workstation = {}

    for op in bom.operations:
        if op.operation:
            op_batch_size[op.operation] = flt(op.batch_size)
            op_split_batch[op.operation] = cint(getattr(op, "taj_split_batch", 0))
            op_workstation[op.operation] = op.workstation

    # workstation stage cache
    workstation_stage = {}
    for row in bom_rows:
        op_name = row.operation or ""
        ws_name = op_workstation.get(op_name)
        if ws_name and ws_name not in workstation_stage:
            workstation_stage[ws_name] = frappe.db.get_value(
                "Workstation", ws_name, "taj_production_stage"
            ) or ""

    # shelf life cache
    shelf_life_map = {}
    for row in bom_rows:
        if row.item_code and row.item_code not in shelf_life_map:
            shelf_life_map[row.item_code] = cint(
                frappe.db.get_value("Item", row.item_code, "shelf_life_in_days") or 0
            )

    planned_txt = getdate(planned_start_date).strftime("%d-%m-%Y") if planned_start_date else ""

    for row in bom_rows:
        op_name = row.operation or ""
        ws_name = op_workstation.get(op_name)
        stage = workstation_stage.get(ws_name, "") if ws_name else ""

        # only Cooking
        if stage != "Cooking":
            continue

        batch_size = op_batch_size.get(op_name) or bom_qty
        if batch_size <= 0:
            batch_size = bom_qty

        split_lots = cint(op_split_batch.get(op_name, 0))
        loads = max(1, int(math.ceil(qty / batch_size)))

        per_bom_qty = flt(row.qty)
        if per_bom_qty <= 0:
            continue

        row_total_required = per_bom_qty * (qty / bom_qty)
        remaining = row_total_required

        shelf_days = shelf_life_map.get(row.item_code, 0)
        ep_txt = ""
        if planned_start_date and shelf_days > 0:
            ep_txt = add_days(getdate(planned_start_date), shelf_days).strftime("%d-%m-%Y")

        if split_lots == 1:
            for load_i in range(1, loads + 1):
                load_rem = qty - ((load_i - 1) * batch_size)
                if load_rem <= 0:
                    load_qty = 0
                elif load_rem >= batch_size:
                    load_qty = batch_size
                else:
                    load_qty = load_rem

                if load_qty <= 0:
                    continue

                lot_total = max(1, int(math.ceil(load_qty / bom_qty)))

                for lot_i in range(1, lot_total + 1):
                    lot_rem = load_qty - ((lot_i - 1) * bom_qty)
                    if lot_rem <= 0:
                        lot_qty = 0
                    elif lot_rem >= bom_qty:
                        lot_qty = bom_qty
                    else:
                        lot_qty = lot_rem

                    if lot_qty <= 0:
                        continue

                    calc_qty = per_bom_qty * (lot_qty / bom_qty)
                    out_qty = min(remaining, calc_qty) if remaining > 0 else 0
                    remaining -= out_qty

                    if out_qty <= 0:
                        continue

                    labels.append({
                        "product_name": product_name,
                        "product_code": product_code,
                        "item_name": row.item_name or "",
                        "description": row.description or "",
                        "item_code": row.item_code or "",
                        "used_date": planned_txt,
                        "ep_date": ep_txt,
                        "qty": _q2_down(out_qty),
                        "load_i": load_i,
                        "loads": loads,
                        "lot_i": lot_i,
                        "lot_total": lot_total,
                    })

        else:
            for load_i in range(1, loads + 1):
                load_rem = qty - ((load_i - 1) * batch_size)
                if load_rem <= 0:
                    load_qty = 0
                elif load_rem >= batch_size:
                    load_qty = batch_size
                else:
                    load_qty = load_rem

                if load_qty <= 0:
                    continue

                calc_qty = per_bom_qty * (load_qty / bom_qty)
                out_qty = min(remaining, calc_qty) if remaining > 0 else 0
                remaining -= out_qty

                if out_qty <= 0:
                    continue

                labels.append({
                    "product_name": product_name,
                    "product_code": product_code,
                    "item_name": row.item_name or "",
                    "description": row.description or "",
                    "item_code": row.item_code or "",
                    "used_date": planned_txt,
                    "ep_date": ep_txt,
                    "qty": _q2_down(out_qty),
                    "load_i": load_i,
                    "loads": loads,
                    "lot_i": None,
                    "lot_total": None,
                })

    return labels


@frappe.whitelist()
def get_label_html(work_order, job_card=None):
    wo = frappe.get_doc("Work Order", work_order)

    selected_item_codes = _get_selected_item_codes_from_work_order(wo)
    source_contexts = _get_source_contexts_from_work_order(wo)

    labels = []
    for ctx in source_contexts:
        labels.extend(_build_labels_for_source(ctx, selected_item_codes))

    html = frappe.render_template(
        "taj_custom/templates/steamer_preparation_label.html",
        {
            "labels": labels,
            "work_order": wo.name,
            "job_card": job_card,
        },
    )

    return {
        "html": html,
        "count": len(labels),
    }