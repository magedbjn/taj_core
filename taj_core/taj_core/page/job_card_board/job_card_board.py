from __future__ import annotations

import datetime
import re
from typing import List, Set, Optional, Dict, Any, Tuple

import frappe
from frappe.utils import flt, cint, get_datetime, today
from taj_core.taj_manufacturing.api.preparation_labels import get_raw_materials_from_job_card

OVERDUE_TOLERANCE_SEC = 120

EVENT_NAME = "job_card_board_update"
DOCTYPE_ROOM_A = "doctype: Job Card"
DOCTYPE_ROOM_B = "doctype:Job Card"

_COL_CACHE: Dict[Tuple[str, str], bool] = {}
_WS_PF_CACHE: Dict[str, str] = {}


def _has_col(doctype: str, fieldname: str) -> bool:
    key = (doctype, fieldname)
    if key not in _COL_CACHE:
      _COL_CACHE[key] = bool(frappe.db.has_column(doctype, fieldname))
    return _COL_CACHE[key]


def _existing_fields(doctype: str, wanted_fields):
    meta = frappe.get_meta(doctype)
    existing = {"name", "parent"} | {df.fieldname for df in meta.fields}
    return [f for f in wanted_fields if f in existing]


def _safe_fields() -> List[str]:
    fields = ["name", "modified", "docstatus", "creation"]
    for f in [
        "posting_date",
        "company",
        "work_order",
        "workstation",
        "operation",
        "status",
        "for_quantity",
        "total_completed_qty",
        "process_loss_qty",
        "is_paused",
        "started_time",
        "operation_id",
        "operation_row_id",
        "taj_plant_floor",
        "total_time_in_mins",
        "taj_manpower_used",
        "taj_total_weight",
        "taj_rm_used_qty",
        "item_code",
        "item_name",
    ]:
        if _has_col("Job Card", f):
            fields.append(f)
    return fields


def _safe_now():
    return get_datetime()


def _is_empty_time(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        v = val.strip()
        return (v == "") or v.startswith("0000-00-00")
    return False


def _ensure_to_time_after(from_time, to_time):
    ft = get_datetime(from_time)
    tt = get_datetime(to_time)
    if tt <= ft:
        tt = ft + datetime.timedelta(seconds=1)
    return tt


def _seconds_diff(a, b) -> int:
    try:
        return int((get_datetime(a) - get_datetime(b)).total_seconds())
    except Exception:
        return 0


def _parse_json_if_needed(val):
    if not val:
        return None
    if isinstance(val, str):
        if not val.strip():
            return None
        return frappe.parse_json(val)
    return val


def _time_range_to_datetimes(date_from: Optional[str], date_to: Optional[str]):
    if date_from and not date_to:
        date_to = date_from
    if date_to and not date_from:
        date_from = date_to
    if not date_from and not date_to:
        return None, None
    start_dt = get_datetime(f"{date_from} 00:00:00")
    end_dt = get_datetime(f"{date_to} 23:59:59")
    return start_dt, end_dt


# -------------------------
# Plant Floor security
# -------------------------
def _is_admin_user(user: str) -> bool:
    if not user:
        return False
    if user == "Administrator":
        return True
    try:
        roles = frappe.get_roles(user) or []
        return "System Manager" in roles
    except Exception:
        return False


def _allowed_plant_floors_for_user(user: str) -> List[str]:
    if not user:
        return []

    try:
        vals = frappe.get_all(
            "User Permission",
            filters={"user": user, "allow": "Plant Floor"},
            pluck="for_value",
        ) or []
        vals = [v.strip() for v in vals if v and str(v).strip()]
        if vals:
            return sorted(list(set(vals)))
    except Exception:
        pass

    try:
        d = frappe.defaults.get_user_default("Plant Floor", user=user)
        if d and str(d).strip():
            return [str(d).strip()]
    except Exception:
        pass

    return []


def _assert_pf_allowed(pf: str, user: str):
    if _is_admin_user(user):
        return
    allowed = _allowed_plant_floors_for_user(user)
    if not allowed:
        raise frappe.PermissionError("No Plant Floor is assigned to this user.")
    if pf and pf not in allowed:
        raise frappe.PermissionError(f"Plant Floor '{pf}' is not allowed for this user.")


def _get_ws_pf_map(workstations: List[str]) -> Dict[str, str]:
    if not workstations:
        return {}
    if not _has_col("Workstation", "plant_floor"):
        return {}
    rows = frappe.get_all(
        "Workstation",
        filters={"name": ["in", list(set(workstations))]},
        fields=["name", "plant_floor"],
        limit_page_length=0,
    )
    return {r["name"]: (r.get("plant_floor") or "").strip() for r in rows}


def _workstations_for_plant_floors(plant_floors: List[str]) -> List[str]:
    if not plant_floors:
        return []
    if not _has_col("Workstation", "plant_floor"):
        return []
    return frappe.get_all(
        "Workstation",
        filters={"plant_floor": ["in", list(set(plant_floors))]},
        pluck="name",
    ) or []


def _workstation_to_production_stage(workstations: List[str]) -> Dict[str, str]:
    if not workstations or not _has_col("Workstation", "taj_production_stage"):
        return {}
    rows = frappe.get_all(
        "Workstation",
        filters={"name": ["in", list(set(workstations))]},
        fields=["name", "taj_production_stage"],
        limit_page_length=0,
    )
    return {r["name"]: (r.get("taj_production_stage") or "").strip() for r in rows}


def _effective_plant_floor_from_values(jc_pf: str, ws: str, ws_pf_map: Dict[str, str]) -> str:
    jc_pf = (jc_pf or "").strip()
    if jc_pf:
        return jc_pf
    return (ws_pf_map.get(ws) or "").strip() if ws else ""


def _is_cooking_mode(jc_pf: str, ws_stage: str) -> bool:
    return ((jc_pf or "").strip() == "Cooking Area") or ((ws_stage or "").strip() == "Cooking")


def _wo_op_seq_map(work_orders, operations, effective_pfs=None):
    if not work_orders or not operations:
        return {}

    filters = {
        "docstatus": ["<", 2],
        "work_order": ["in", list(set(work_orders))],
        "operation": ["in", list(set(operations))],
    }

    if effective_pfs:
        if _has_col("Job Card", "taj_plant_floor"):
            filters["taj_plant_floor"] = ["in", list(set(effective_pfs))]

    rows = frappe.get_all(
        "Job Card",
        filters=filters,
        fields=["name", "work_order", "operation"],
        order_by="work_order asc, operation asc, name asc",
        limit_page_length=0,
    ) or []

    counters = {}
    out = {}
    for r in rows:
        key = (r.get("work_order") or "", r.get("operation") or "")
        counters[key] = counters.get(key, 0) + 1
        out[r["name"]] = counters[key]
    return out


# -------------------------
# Time logs helpers
# -------------------------
def _jobcards_by_time_logs(start_dt, end_dt) -> List[str]:
    rows = frappe.db.sql(
        """
        SELECT DISTINCT parent
        FROM `tabJob Card Time Log`
        WHERE parenttype='Job Card'
          AND from_time IS NOT NULL
          AND from_time <= %(end_dt)s
          AND (
                CASE
                    WHEN to_time IS NULL THEN NOW()
                    WHEN CAST(to_time AS CHAR) LIKE '0000-00-00%%' THEN NOW()
                    WHEN CAST(to_time AS CHAR) = '' THEN NOW()
                    ELSE to_time
                END
          ) >= %(start_dt)s
        """,
        {"start_dt": start_dt, "end_dt": end_dt},
        as_dict=True,
    )
    return [r["parent"] for r in rows] if rows else []


def _jobcards_without_time_logs_in_range(start_dt, end_dt) -> List[str]:
    rows = frappe.db.sql(
        """
        SELECT jc.name
        FROM `tabJob Card` jc
        LEFT JOIN `tabJob Card Time Log` tl
            ON tl.parent = jc.name AND tl.parenttype = 'Job Card'
        WHERE jc.docstatus < 2
          AND jc.creation BETWEEN %s AND %s
        GROUP BY jc.name
        HAVING COUNT(tl.name) = 0
        """,
        (start_dt, end_dt),
        as_dict=True,
    )
    return [r["name"] for r in rows] if rows else []


def _get_running_parents(job_card_names: List[str]) -> Set[str]:
    if not job_card_names:
        return set()

    placeholders = ", ".join(["%s"] * len(job_card_names))
    args = tuple(job_card_names)

    rows = frappe.db.sql(
        f"""
        SELECT DISTINCT parent
        FROM `tabJob Card Time Log`
        WHERE parenttype='Job Card'
          AND parent IN ({placeholders})
          AND from_time IS NOT NULL
          AND (
             to_time IS NULL
             OR CAST(to_time AS CHAR) LIKE '0000-00-00%%'
             OR CAST(to_time AS CHAR) = ''
          )
        """,
        args,
        as_dict=True,
    )
    return {r["parent"] for r in rows} if rows else set()


def _compute_timer_seconds(job_card_names: List[str]) -> Dict[str, int]:
    if not job_card_names:
        return {}

    rows = frappe.get_all(
        "Job Card Time Log",
        filters={"parenttype": "Job Card", "parent": ["in", job_card_names]},
        fields=["parent", "from_time", "to_time"],
        order_by="parent asc, idx asc",
        limit_page_length=0,
    )

    now_dt = _safe_now()
    out: Dict[str, int] = {name: 0 for name in job_card_names}

    for r in rows:
        parent = r["parent"]
        ft = r.get("from_time")
        tt = r.get("to_time")
        if not ft:
            continue

        if tt and not _is_empty_time(tt):
            sec = _seconds_diff(tt, ft)
        else:
            sec = _seconds_diff(now_dt, ft)

        if sec > 0:
            out[parent] = out.get(parent, 0) + int(sec)

    return out


def _get_expected_seconds_map(job_cards: List[dict]) -> Dict[str, int]:
    if not job_cards:
        return {}

    names = [d["name"] for d in job_cards]
    work_orders = list({d.get("work_order") for d in job_cards if d.get("work_order")})
    operations = list({d.get("operation") for d in job_cards if d.get("operation")})

    if not work_orders or not operations:
        return {n: 0 for n in names}

    wo_rows = frappe.get_all(
        "Work Order",
        filters={"name": ["in", work_orders]},
        fields=["name", "bom_no"],
        limit_page_length=0,
    )
    wo_to_bom = {r["name"]: r.get("bom_no") for r in wo_rows}

    wo_op_rows = frappe.get_all(
        "Work Order Operation",
        filters={"parent": ["in", work_orders], "operation": ["in", operations]},
        fields=["parent", "operation", "idx", "time_in_mins"],
        limit_page_length=0,
    )

    wo_by_parent_op = {}
    for r in sorted(wo_op_rows, key=lambda x: int(x.get("idx") or 999999)):
        key = (r.get("parent"), r.get("operation"))
        if key not in wo_by_parent_op:
            wo_by_parent_op[key] = flt(r.get("time_in_mins"))

    boms = list({wo_to_bom.get(wo) for wo in work_orders if wo_to_bom.get(wo)})
    bom_by_parent_op = {}
    if boms:
        bom_op_rows = frappe.get_all(
            "BOM Operation",
            filters={"parent": ["in", boms], "operation": ["in", operations]},
            fields=["parent", "operation", "idx", "time_in_mins"],
            limit_page_length=0,
        )
        for r in sorted(bom_op_rows, key=lambda x: int(x.get("idx") or 999999)):
            key = (r.get("parent"), r.get("operation"))
            if key not in bom_by_parent_op:
                bom_by_parent_op[key] = flt(r.get("time_in_mins"))

    out: Dict[str, int] = {}
    for d in job_cards:
        wo = d.get("work_order")
        op = d.get("operation")

        expected_mins = 0.0
        if wo and op:
            expected_mins = flt(wo_by_parent_op.get((wo, op), 0.0))

        if not expected_mins and wo and op:
            bom = wo_to_bom.get(wo)
            if bom:
                expected_mins = flt(bom_by_parent_op.get((bom, op), 0.0))

        out[d["name"]] = int(expected_mins * 60)

    return out


def _is_finished_qty(planned: float, done: float) -> bool:
    return bool(planned and done >= planned)


def _is_completed(docstatus: int, status: str, planned: float, done: float) -> bool:
    if docstatus == 1:
        return True
    if (status or "").strip() == "Completed":
        return True
    if _is_finished_qty(planned, done):
        return True
    return False


def _get_is_paused(doc_dict: dict) -> int:
    status = (doc_dict.get("status") or "").strip()
    if _has_col("Job Card", "is_paused"):
        return int(doc_dict.get("is_paused") or 0)
    return 1 if status == "On Hold" else 0


def _set_started_time(doc, value):
    if _has_col("Job Card", "started_time"):
        doc.set("started_time", value if value else None)


def _set_status(doc, status: str):
    if _has_col("Job Card", "status"):
        doc.set("status", status)


def _set_is_paused(doc, val: int):
    if _has_col("Job Card", "is_paused"):
        doc.set("is_paused", 1 if val else 0)


def _open_time_log_rows(doc) -> List[Any]:
    open_rows = []
    for r in (doc.get("time_logs") or []):
        if r.get("from_time") and _is_empty_time(r.get("to_time")):
            open_rows.append(r)
    return open_rows


def _is_running_now(job_card_name: str) -> bool:
    return job_card_name in _get_running_parents([job_card_name])


def _assert_user_can_access_job_card_pf(job_card_name: str):
    user = frappe.session.user
    if _is_admin_user(user):
        return

    allowed = _allowed_plant_floors_for_user(user)
    if not allowed:
        raise frappe.PermissionError("No Plant Floor is assigned to this user.")

    fields = ["workstation"]
    if _has_col("Job Card", "taj_plant_floor"):
        fields.append("taj_plant_floor")

    jc = frappe.db.get_value("Job Card", job_card_name, fields, as_dict=True)
    if not jc:
        return

    ws = (jc.get("workstation") or "").strip()
    jc_pf = (jc.get("taj_plant_floor") or "").strip() if _has_col("Job Card", "taj_plant_floor") else ""

    ws_pf_map = _get_ws_pf_map([ws]) if ws else {}
    eff_pf = _effective_plant_floor_from_values(jc_pf, ws, ws_pf_map)

    if eff_pf and eff_pf not in allowed:
        raise frappe.PermissionError(f"Job Card '{job_card_name}' is not in an allowed Plant Floor.")


# -------------------------
# Filling helpers
# -------------------------
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


def _get_current_sub_assembly_row_from_work_order(work_order: str):
    if not work_order:
        return None

    if not frappe.db.has_column("Work Order", "production_plan_sub_assembly_item"):
        return None

    sub_row_name = frappe.db.get_value("Work Order", work_order, "production_plan_sub_assembly_item")
    if not sub_row_name:
        return None

    return frappe.db.get_value(
        "Production Plan Sub Assembly Item",
        sub_row_name,
        _get_sub_assembly_row_fields(),
        as_dict=True,
    )


def _get_filling_bom_no(job_card: str, work_order: str) -> str:
    current_sub = _get_current_sub_assembly_row_from_work_order(work_order)
    if current_sub:
        pp_item_ref = (current_sub.get("production_plan_item") or "").strip()
        production_plan = current_sub.get("parent")

        actual_pp_item = _resolve_pp_item_reference(production_plan, pp_item_ref)
        if actual_pp_item:
            bom_no = (frappe.db.get_value("Production Plan Item", actual_pp_item, "bom_no") or "").strip()
            # frappe.log_error(
            #     title="Filling Area Debug",
            #     message=f"job_card={job_card}\nwork_order={work_order}\nsource=Production Plan Item\nproduction_plan_item={actual_pp_item}\nbom_no={bom_no}",
            # )
            if bom_no:
                return bom_no

    bom_no = (frappe.db.get_value("Work Order", work_order, "bom_no") or "").strip()
    # frappe.log_error(
    #     title="Filling Area Debug",
    #     message=f"job_card={job_card}\nwork_order={work_order}\nsource=Work Order fallback\nbom_no={bom_no}",
    # )
    return bom_no


def _get_filling_details_from_bom(bom_no: str):
    if not bom_no:
        return {
            "bom_no": "",
            "rows": [],
            "totals": {
                "weight": 0,
                "under_weight": 0,
                "over_weight": 0,
            },
            "pouch_size": "",
        }

    fieldnames = _existing_fields("BOM", [
        "name",
        "taj_liquid_filling",
        "taj_liquid_viscosity",
        "taj_liquid_weight",
        "taj_liquid_under_weight",
        "taj_liquid_over_weight",
        "taj_solid_filling_1",
        "taj_solid_size_1",
        "taj_solid_weight_1",
        "taj_solid_under_weight_1",
        "taj_solid_over_weight_1",
        "taj_solid_filling_2",
        "taj_solid_size_2",
        "taj_solid_weight_2",
        "taj_solid_under_weight_2",
        "taj_solid_over_weight_2",
        "taj_total_weight",
        "taj_total_under_weight",
        "taj_total_over_weight",
        "taj_pouch_size",
    ])

    bom = frappe.db.get_value("BOM", bom_no, fieldnames, as_dict=True) or {}

    rows = []

    liquid_filling = str(bom.get("taj_liquid_filling") or "").strip()
    liquid_weight = flt(bom.get("taj_liquid_weight") or 0)
    solid_filling_1 = str(bom.get("taj_solid_filling_1") or "").strip()
    solid_filling_2 = str(bom.get("taj_solid_filling_2") or "").strip()

    if liquid_weight > 0:
        rows.append({
            "type": "Liquid Filling",
            "value": liquid_filling,
            "viscosity_or_size": bom.get("taj_liquid_viscosity") or "",
            "weight": liquid_weight,
            "under_weight": bom.get("taj_liquid_under_weight") or 0,
            "over_weight": bom.get("taj_liquid_over_weight") or 0,
        })

    if solid_filling_1 and solid_filling_1 not in ("0", "0.0"):
        rows.append({
            "type": "Solid Filling 1",
            "value": solid_filling_1,
            "viscosity_or_size": bom.get("taj_solid_size_1") or "",
            "weight": bom.get("taj_solid_weight_1") or 0,
            "under_weight": bom.get("taj_solid_under_weight_1") or 0,
            "over_weight": bom.get("taj_solid_over_weight_1") or 0,
        })

    if solid_filling_2 and solid_filling_2 not in ("0", "0.0"):
        rows.append({
            "type": "Solid Filling 2",
            "value": solid_filling_2,
            "viscosity_or_size": bom.get("taj_solid_size_2") or "",
            "weight": bom.get("taj_solid_weight_2") or 0,
            "under_weight": bom.get("taj_solid_under_weight_2") or 0,
            "over_weight": bom.get("taj_solid_over_weight_2") or 0,
        })

    
    return {
        "bom_no": bom_no,
        "rows": rows,
        "totals": {
            "weight": bom.get("taj_total_weight") or 0,
            "under_weight": bom.get("taj_total_under_weight") or 0,
            "over_weight": bom.get("taj_total_over_weight") or 0,
        },
        "pouch_size": bom.get("taj_pouch_size") or "",
    }
# -------------------------
# Popup APIs
# -------------------------
@frappe.whitelist()
def get_operation_spec(job_card: str):
    _assert_user_can_access_job_card_pf(job_card)

    jc_fields = ["name", "work_order", "operation", "workstation"]
    if _has_col("Job Card", "taj_plant_floor"):
        jc_fields.append("taj_plant_floor")

    jc = frappe.db.get_value("Job Card", job_card, jc_fields, as_dict=True)
    if not jc:
        return {
            "job_card": job_card,
            "work_order": "",
            "operation": "",
            "plant_floor": "",
            "description": "",
            "raw_materials": [],
            "filling_details": {
                "bom_no": "",
                "rows": [],
                "totals": {"weight": 0, "under_weight": 0, "over_weight": 0},
                "pouch_size": "",
            },
        }

    work_order = (jc.get("work_order") or "").strip()
    operation = (jc.get("operation") or "").strip()
    workstation = (jc.get("workstation") or "").strip()
    jc_pf = (jc.get("taj_plant_floor") or "").strip() if _has_col("Job Card", "taj_plant_floor") else ""

    ws_pf_map = _get_ws_pf_map([workstation]) if workstation else {}
    plant_floor = _effective_plant_floor_from_values(jc_pf, workstation, ws_pf_map)

    description = ""

    wo_op_desc_field = None
    if _has_col("Work Order Operation", "description"):
        wo_op_desc_field = "description"
    elif _has_col("Work Order Operation", "operation_description"):
        wo_op_desc_field = "operation_description"

    if work_order and operation and wo_op_desc_field:
        row = frappe.get_all(
            "Work Order Operation",
            filters={
                "parent": work_order,
                "parenttype": "Work Order",
                "operation": operation,
            },
            fields=[wo_op_desc_field, "idx"],
            order_by="idx asc",
            limit_page_length=1,
        )
        if row:
            description = (row[0].get(wo_op_desc_field) or "").strip()

    if not description and operation and frappe.db.exists("Operation", operation):
        if _has_col("Operation", "description"):
            description = (frappe.db.get_value("Operation", operation, "description") or "").strip()

    raw_materials = []
    filling_details = {
        "bom_no": "",
        "rows": [],
        "totals": {"weight": 0, "under_weight": 0, "over_weight": 0},
        "pouch_size": "",
    }

    if plant_floor == "Preparation Area":
        try:
            raw_payload = get_raw_materials_from_job_card(job_card)
            raw_materials = raw_payload.get("items") or []
        except Exception:
            raw_materials = []

    elif plant_floor == "Filling Area":
        bom_no = _get_filling_bom_no(job_card, work_order)
        filling_details = _get_filling_details_from_bom(bom_no)

    return {
        "job_card": job_card,
        "work_order": work_order,
        "operation": operation,
        "plant_floor": plant_floor,
        "description": description,
        "raw_materials": raw_materials,
        "filling_details": filling_details,
    }


@frappe.whitelist()
def get_cooking_operation_items(job_card: str):
    _assert_user_can_access_job_card_pf(job_card)

    jc_fields = ["name", "work_order", "operation", "workstation"]
    if _has_col("Job Card", "taj_plant_floor"):
        jc_fields.append("taj_plant_floor")

    jc = frappe.db.get_value("Job Card", job_card, jc_fields, as_dict=True)
    if not jc:
        return {
            "job_card": job_card,
            "work_order": "",
            "operation": "",
            "plant_floor": "",
            "items": [],
        }

    work_order = (jc.get("work_order") or "").strip()
    operation = (jc.get("operation") or "").strip()
    workstation = (jc.get("workstation") or "").strip()
    jc_pf = (jc.get("taj_plant_floor") or "").strip() if _has_col("Job Card", "taj_plant_floor") else ""

    ws_pf_map = _get_ws_pf_map([workstation]) if workstation else {}
    plant_floor = _effective_plant_floor_from_values(jc_pf, workstation, ws_pf_map)

    if plant_floor != "Cooking Area":
        return {
            "job_card": job_card,
            "work_order": work_order,
            "operation": operation,
            "plant_floor": plant_floor,
            "items": [],
        }

    if not work_order or not operation:
        return {
            "job_card": job_card,
            "work_order": work_order,
            "operation": operation,
            "plant_floor": plant_floor,
            "items": [],
        }

    bom_no = frappe.db.get_value("Work Order", work_order, "bom_no")
    if not bom_no:
        return {
            "job_card": job_card,
            "work_order": work_order,
            "operation": operation,
            "plant_floor": plant_floor,
            "items": [],
        }

    req_fields = ["item_code", "item_name", "idx"]
    has_req_operation = _has_col("Work Order Item", "operation")
    if has_req_operation:
        req_fields.append("operation")

    req_rows = frappe.get_all(
        "Work Order Item",
        filters={
            "parent": work_order,
            "parenttype": "Work Order",
        },
        fields=req_fields,
        order_by="idx asc",
        limit_page_length=0,
    ) or []

    if has_req_operation:
        req_rows = [r for r in req_rows if (r.get("operation") or "").strip() == operation]

    item_codes = [r.get("item_code") for r in req_rows if r.get("item_code")]

    if not item_codes:
        return {
            "job_card": job_card,
            "work_order": work_order,
            "operation": operation,
            "plant_floor": plant_floor,
            "items": [],
        }

    bom_fields = ["item_code", "item_name", "idx"]
    if _has_col("BOM Item", "taj_temperature"):
        bom_fields.append("taj_temperature")
    if _has_col("BOM Item", "taj_duration"):
        bom_fields.append("taj_duration")
    if _has_col("BOM Item", "taj_notes"):
        bom_fields.append("taj_notes")

    bom_rows = frappe.get_all(
        "BOM Item",
        filters={
            "parent": bom_no,
            "parenttype": "BOM",
            "item_code": ["in", list(set(item_codes))],
        },
        fields=bom_fields,
        order_by="idx asc",
        limit_page_length=0,
    ) or []

    bom_by_code = {}
    for r in bom_rows:
        code = (r.get("item_code") or "").strip()
        if code and code not in bom_by_code:
            bom_by_code[code] = r

    items = []
    for r in req_rows:
        code = (r.get("item_code") or "").strip()
        bom_item = bom_by_code.get(code, {}) if code else {}

        items.append(
            {
                "item_code": code,
                "item_name": (r.get("item_name") or bom_item.get("item_name") or "").strip(),
                "taj_temperature": bom_item.get("taj_temperature"),
                "taj_duration": bom_item.get("taj_duration"),
                "taj_notes": bom_item.get("taj_notes"),
            }
        )

    return {
        "job_card": job_card,
        "work_order": work_order,
        "operation": operation,
        "plant_floor": plant_floor,
        "items": items,
    }


# -------------------------
# Payload builders
# -------------------------
def _add_wo_op_seq(job_cards: List[dict]) -> None:
    if not job_cards:
        return

    wos = sorted({d.get("work_order") for d in job_cards if d.get("work_order")})
    ops = sorted({d.get("operation") for d in job_cards if d.get("operation")})
    if not wos or not ops:
        for d in job_cards:
            d["wo_op_seq"] = 0
        return

    rows = frappe.get_all(
        "Job Card",
        filters={
            "docstatus": ["<", 2],
            "work_order": ["in", wos],
            "operation": ["in", ops],
        },
        fields=["name", "work_order", "operation"],
        order_by="work_order asc, operation asc, name asc",
        limit_page_length=0,
    ) or []

    counters: Dict[Tuple[str, str], int] = {}
    rank_by_name: Dict[str, int] = {}
    for r in rows:
        key = (r.get("work_order") or "", r.get("operation") or "")
        counters[key] = counters.get(key, 0) + 1
        rank_by_name[r["name"]] = counters[key]

    for d in job_cards:
        d["wo_op_seq"] = int(rank_by_name.get(d["name"], 0) or 0)


def _get_work_order_status_map(work_orders: List[str]) -> Dict[str, Dict[str, Any]]:
    if not work_orders:
        return {}

    rows = frappe.get_all(
        "Work Order",
        filters={"name": ["in", list(set(work_orders))]},
        fields=["name", "status", "docstatus"],
        limit_page_length=0,
    ) or []

    return {
        r["name"]: {
            "status": (r.get("status") or "").strip(),
            "docstatus": int(r.get("docstatus") or 0),
        }
        for r in rows
    }


def _is_work_order_closed_or_done(wo_status: str, wo_docstatus: int) -> bool:
    closed_statuses = {"Closed", "Completed", "Cancelled"}
    return int(wo_docstatus or 0) == 2 or (wo_status or "").strip() in closed_statuses


def _build_payloads_for_cards(job_cards: List[dict]) -> List[dict]:
    if not job_cards:
        return []

    names = [d["name"] for d in job_cards]
    has_total_time = _has_col("Job Card", "total_time_in_mins")

    base: Dict[str, Dict[str, Any]] = {}
    active_names: List[str] = []
    active_cards: List[dict] = []

    for d in job_cards:
        name = d["name"]
        docstatus = int(d.get("docstatus") or 0)
        status = (d.get("status") or "").strip()

        planned = flt(d.get("for_quantity")) or 0.0
        done = flt(d.get("total_completed_qty")) or 0.0

        is_paused = _get_is_paused(d)
        is_finished = _is_finished_qty(planned, done)
        is_completed = _is_completed(docstatus, status, planned, done)

        base[name] = {
            "docstatus": docstatus,
            "status": status,
            "planned": planned,
            "done": done,
            "is_paused": is_paused,
            "is_finished": is_finished,
            "is_completed": is_completed,
        }

        if docstatus == 0 and not is_completed and is_paused == 0:
            active_names.append(name)
            active_cards.append(d)

    running_set = _get_running_parents(active_names)
    timer_map_running = _compute_timer_seconds(list(running_set)) if running_set else {}

    work_orders = [d.get("work_order") for d in job_cards if d.get("work_order")]
    wo_status_map = _get_work_order_status_map(work_orders)
    operations = [d.get("operation") for d in job_cards if d.get("operation")]
    seq_map = _wo_op_seq_map(work_orders, operations)

    expected_map_all: Dict[str, int] = {n: 0 for n in names}
    if active_cards:
        expected_map_all.update(_get_expected_seconds_map(active_cards))

    ws_names = [d.get("workstation") for d in job_cards if d.get("workstation")]
    ws_stage_map = _workstation_to_production_stage(ws_names)
    ws_pf_map = _get_ws_pf_map(ws_names)

    timer_map_fallback = _compute_timer_seconds(names) if not has_total_time else {}

    items = []
    for d in job_cards:
        name = d["name"]
        docstatus = base[name]["docstatus"]
        status = base[name]["status"]

        planned = base[name]["planned"]
        done = base[name]["done"]
        remaining = max(planned - done, 0.0)

        wo_name = (d.get("work_order") or "").strip()
        wo_meta = wo_status_map.get(wo_name, {}) if wo_name else {}
        wo_status = (wo_meta.get("status") or "").strip()
        wo_docstatus = int(wo_meta.get("docstatus") or 0)
        wo_is_closed = _is_work_order_closed_or_done(wo_status, wo_docstatus)

        is_paused = int(base[name]["is_paused"])
        is_finished = bool(base[name]["is_finished"])
        is_completed = bool(base[name]["is_completed"])

        running = (
            docstatus == 0
            and (name in running_set)
            and (not is_completed)
            and (is_paused == 0)
        )

        expected_seconds = int(expected_map_all.get(name, 0) or 0)

        if has_total_time and not running:
            timer_seconds = int(flt(d.get("total_time_in_mins") or 0) * 60)
        elif running:
            timer_seconds = int(timer_map_running.get(name, 0) or 0)
        else:
            timer_seconds = int(timer_map_fallback.get(name, 0) or 0)

        is_overdue = bool(
            (not is_completed)
            and (not is_finished)
            and docstatus == 0
            and (is_paused == 0)
            and expected_seconds > 0
            and timer_seconds > (expected_seconds + OVERDUE_TOLERANCE_SEC)
        )

        ws = (d.get("workstation") or "").strip()
        ws_stage = (ws_stage_map.get(ws) or "").strip()
        jc_pf = (d.get("taj_plant_floor") or "").strip() if _has_col("Job Card", "taj_plant_floor") else ""
        eff_pf = _effective_plant_floor_from_values(jc_pf, ws, ws_pf_map)

        items.append(
            {
                **d,
                "planned": planned,
                "done": done,
                "remaining": remaining,
                "is_paused": int(is_paused),
                "running": int(bool(running)),
                "is_completed": int(bool(is_completed)),
                "is_finished_qty": int(is_finished),
                "timer_seconds": int(timer_seconds),
                "expected_seconds": int(expected_seconds),
                "is_overdue": int(bool(is_overdue)),
                "plant_floor": eff_pf,
                "taj_production_stage": ws_stage,
                "is_cooking_mode": int(_is_cooking_mode(jc_pf, ws_stage)),
                "wo_op_seq": int(seq_map.get(name, 0) or 0),
                "work_order_status": wo_status,
                "work_order_docstatus": wo_docstatus,
                "hide_actions_due_to_wo_closed": int(bool(wo_is_closed)),
            }
        )

    return items


def get_card_payload(name: str) -> dict:
    _assert_user_can_access_job_card_pf(name)

    rows = frappe.get_list(
        "Job Card",
        fields=_safe_fields(),
        filters={"name": name, "docstatus": ["<", 2]},
        limit_page_length=1,
    )
    if not rows:
        return {}

    items = _build_payloads_for_cards([rows[0]])
    return items[0] if items else {}


@frappe.whitelist()
def get_card_payload_api(name: str):
    return get_card_payload(name)


@frappe.whitelist()
def get_cards_payload_bulk_api(names):
    raw = _parse_json_if_needed(names) or names or []
    if isinstance(raw, str):
        arr = [x.strip() for x in raw.split(",") if x and x.strip()]
    elif isinstance(raw, list):
        arr = [str(x).strip() for x in raw if x and str(x).strip()]
    else:
        arr = []

    arr = arr[:120]
    if not arr:
        return {"items": []}

    user = frappe.session.user
    allowed = _allowed_plant_floors_for_user(user) if not _is_admin_user(user) else None

    job_cards = frappe.get_list(
        "Job Card",
        fields=_safe_fields(),
        filters={"name": ["in", arr], "docstatus": ["<", 2]},
        limit_page_length=0,
    ) or []

    if allowed is not None:
        ws_names = [d.get("workstation") for d in job_cards if d.get("workstation")]
        ws_pf_map = _get_ws_pf_map(ws_names)
        filtered = []
        for d in job_cards:
            ws = (d.get("workstation") or "").strip()
            jc_pf = (d.get("taj_plant_floor") or "").strip() if _has_col("Job Card", "taj_plant_floor") else ""
            eff_pf = _effective_plant_floor_from_values(jc_pf, ws, ws_pf_map)
            if eff_pf and eff_pf in allowed:
                filtered.append(d)
        job_cards = filtered

    _add_wo_op_seq(job_cards)
    return {"items": _build_payloads_for_cards(job_cards)}


@frappe.whitelist()
def get_board_data(
    work_order=None,
    plant_floor=None,
    workstation=None,
    operation=None,
    status_filter=None,
    docstatus_filter=None,
    search=None,
    date_from=None,
    date_to=None,
    limit=60,
    offset=0,
):
    user = frappe.session.user
    limit = int(limit or 60)
    offset = int(offset or 0)

    if not date_from and not date_to:
        date_from = today()
        date_to = today()

    if not _is_admin_user(user):
        allowed = _allowed_plant_floors_for_user(user)
        if not allowed:
            raise frappe.PermissionError("No Plant Floor is assigned to this user.")

        if plant_floor:
            _assert_pf_allowed(str(plant_floor).strip(), user)
            effective_pfs = [str(plant_floor).strip()]
        else:
            effective_pfs = allowed
    else:
        effective_pfs = [str(plant_floor).strip()] if plant_floor else []

    filters: Dict[str, Any] = {"docstatus": ["<", 2]}

    if docstatus_filter == "DRAFT":
        filters["docstatus"] = 0
    elif docstatus_filter == "SUBMITTED":
        filters["docstatus"] = 1

    if work_order:
        filters["work_order"] = work_order

    if effective_pfs:
        if _has_col("Job Card", "taj_plant_floor"):
            filters["taj_plant_floor"] = ["in", effective_pfs] if len(effective_pfs) > 1 else effective_pfs[0]
        else:
            if not _has_col("Workstation", "plant_floor"):
                raise frappe.ValidationError("Cannot enforce Plant Floor because Workstation.plant_floor column is missing.")
            ws_list = _workstations_for_plant_floors(effective_pfs)
            if not ws_list:
                return {"items": [], "limit": limit, "offset": offset}
            filters["workstation"] = ["in", ws_list]
    elif workstation:
        filters["workstation"] = workstation

    if operation:
        filters["operation"] = operation

    active_statuses = ["Open", "Work In Progress", "On Hold", "Material Transferred"]
    if not status_filter or status_filter == "ALL":
        pass
    elif status_filter == "ACTIVE":
        filters["status"] = ["in", active_statuses]
    else:
        filters["status"] = status_filter

    if date_from and not date_to:
        date_to = date_from
    if date_to and not date_from:
        date_from = date_to

    if date_from and date_to:
        start_dt, end_dt = _time_range_to_datetimes(date_from, date_to)

        wo_names = frappe.get_all(
            "Work Order",
            filters={
                "docstatus": ["<", 2],
                "planned_start_date": ["between", [start_dt, end_dt]],
            },
            pluck="name",
        ) or []

        if work_order:
            if work_order not in set(wo_names):
                return {"items": [], "limit": limit, "offset": offset}
        else:
            if not wo_names:
                return {"items": [], "limit": limit, "offset": offset}
            filters["work_order"] = ["in", wo_names]

    post_search = None
    if search:
        if "name" in filters:
            post_search = str(search).strip()
        else:
            filters["name"] = ["like", f"%{search}%"]

    job_cards = frappe.get_list(
        "Job Card",
        fields=_safe_fields(),
        filters=filters,
        order_by="name asc",
        limit_start=offset,
        limit_page_length=limit,
    ) or []

    if post_search:
        job_cards = [d for d in job_cards if post_search in str(d.get("name") or "")]

    _add_wo_op_seq(job_cards)
    return {"items": _build_payloads_for_cards(job_cards), "limit": limit, "offset": offset}


# -------------------------
# Actions used by board buttons
# -------------------------
def _ensure_employee_table(doc, employees: List[str]):
    if not doc.meta.has_field("employee"):
        return

    existing = set()
    for r in (doc.get("employee") or []):
        if r.get("employee"):
            existing.add(r.get("employee"))

    for emp in employees:
        if emp and emp not in existing:
            doc.append("employee", {"employee": emp, "completed_qty": 0.0})
            existing.add(emp)



def _metal_detector_guard_enabled() -> int:
    return 1


def _metal_detector_check_fields() -> List[str]:
    return [
        "taj_ferrous_detection",
        "taj_non_ferrous_detection",
        "taj_sus_detection",
    ]


def _metal_detector_numeric_fields() -> Dict[str, str]:
    return {
        "taj_threshold_set_point": "float",
        "taj_gain_set_point": "float",
        "taj_check_weight_1": "int",
        "taj_anritus_weight_1": "float",
        "taj_check_weight_2": "int",
        "taj_anritus_weight_2": "int",
    }


def _metal_detector_all_fields() -> List[str]:
    return _metal_detector_check_fields() + list(_metal_detector_numeric_fields().keys())


def _metal_detector_always_fields() -> List[str]:
    return [
        "taj_check_weight_1",
        "taj_anritus_weight_1",
        "taj_check_weight_2",
        "taj_anritus_weight_2",
    ]


def _metal_detector_liquid_fields() -> List[str]:
    return [
        "taj_ferrous_detection",
        "taj_non_ferrous_detection",
        "taj_sus_detection",
        "taj_threshold_set_point",
        "taj_gain_set_point",
    ]


def _metal_detector_required_fields(liquid_weight: float) -> List[str]:
    fields = list(_metal_detector_always_fields())
    if flt(liquid_weight) > 0:
        fields.extend(_metal_detector_liquid_fields())
    return fields


def _metal_detector_field_labels() -> Dict[str, str]:
    return {
        "taj_ferrous_detection": "Ferrous Detection 2mm",
        "taj_non_ferrous_detection": "Non Ferrous Detection 2mm",
        "taj_sus_detection": "SUS Detection 2mm",
        "taj_threshold_set_point": "Threshold set point",
        "taj_gain_set_point": "Gain Set point",
        "taj_check_weight_1": "Check Weight #1",
        "taj_anritus_weight_1": "Anritus Weight #1",
        "taj_check_weight_2": "Check Weight #2",
        "taj_anritus_weight_2": "Anritus Weight #2",
    }


def _metal_detector_db_field_map() -> Dict[str, str]:
    out = {
        "taj_ferrous_detection": "taj_ferrous_detection",
        "taj_non_ferrous_detection": "taj_non_ferrous_detection",
        "taj_sus_detection": "taj_sus_detection",
        "taj_threshold_set_point": "taj_threshold_set_point",
        "taj_check_weight_1": "taj_check_weight_1",
        "taj_anritus_weight_1": "taj_anritus_weight_1",
        "taj_check_weight_2": "taj_check_weight_2",
        "taj_anritus_weight_2": "taj_anritus_weight_2",
    }

    if _has_col("Work Order", "taj_gain_set_point"):
        out["taj_gain_set_point"] = "taj_gain_set_point"
    elif _has_col("Work Order", "taj_gain_set_point_"):
        out["taj_gain_set_point"] = "taj_gain_set_point_"
    else:
        out["taj_gain_set_point"] = "taj_gain_set_point"

    return out


def _get_metal_detector_values(work_order: str) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "taj_ferrous_detection": 0,
        "taj_non_ferrous_detection": 0,
        "taj_sus_detection": 0,
        "taj_threshold_set_point": 0,
        "taj_gain_set_point": 0,
        "taj_check_weight_1": 0,
        "taj_anritus_weight_1": 0,
        "taj_check_weight_2": 0,
        "taj_anritus_weight_2": 0,
    }

    if not work_order:
        return defaults

    field_map = _metal_detector_db_field_map()
    db_fields = sorted({dbf for dbf in field_map.values() if _has_col("Work Order", dbf)})
    if not db_fields:
        return defaults

    raw = frappe.db.get_value("Work Order", work_order, db_fields, as_dict=True) or {}

    out = dict(defaults)

    for logical in _metal_detector_check_fields():
        dbf = field_map.get(logical)
        out[logical] = cint(raw.get(dbf or logical) or 0)

    for logical, kind in _metal_detector_numeric_fields().items():
        dbf = field_map.get(logical)
        raw_val = raw.get(dbf or logical)
        if kind == "int":
            out[logical] = cint(raw_val or 0)
        else:
            out[logical] = flt(raw_val or 0)

    return out


def _normalize_metal_detector_save_values(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = data or {}
    out: Dict[str, Any] = {}

    for f in _metal_detector_check_fields():
        if f in data:
            out[f] = cint(data.get(f))

    for f, kind in _metal_detector_numeric_fields().items():
        raw = data.get(f)

        if f == "taj_gain_set_point" and raw is None and "taj_gain_set_point_" in data:
            raw = data.get("taj_gain_set_point_")

        if raw is None:
            continue

        if isinstance(raw, str):
            raw = raw.strip()

        if raw == "":
            out[f] = None
        elif kind == "int":
            out[f] = cint(raw)
        else:
            out[f] = flt(raw)

    return out


def _save_metal_detector_values(work_order: str, data: Dict[str, Any] | None = None):
    if not work_order or not data:
        return

    normalized = _normalize_metal_detector_save_values(data)
    if not normalized:
        return

    field_map = _metal_detector_db_field_map()
    values = {}
    for logical, val in normalized.items():
        dbf = field_map.get(logical)
        if dbf and _has_col("Work Order", dbf):
            values[dbf] = val

    if values:
        frappe.db.set_value("Work Order", work_order, values, update_modified=True)


def _metal_detector_field_is_filled(fieldname: str, value: Any) -> bool:
    if fieldname in _metal_detector_check_fields():
        return cint(value or 0) != 0
    return flt(value or 0) != 0


def _is_metal_detector_dialog_completed(wo_vals: Dict[str, Any], liquid_weight: float) -> bool:
    for fieldname in _metal_detector_required_fields(liquid_weight):
        if not _metal_detector_field_is_filled(fieldname, wo_vals.get(fieldname)):
            return False
    return True


def _get_job_card_metal_detector_context(doc) -> Dict[str, Any]:
    plant_floor = _effective_pf_for_doc(doc)
    work_order = (doc.get("work_order") or "").strip()

    ctx = {
        "plant_floor": plant_floor,
        "work_order": work_order,
        "filling_details": {
            "bom_no": "",
            "rows": [],
            "totals": {"weight": 0, "under_weight": 0, "over_weight": 0},
            "pouch_size": "",
        },
        "liquid_weight": 0.0,
        "show_dialog": False,
        "show_liquid_fields": False,
    }

    if not cint(_metal_detector_guard_enabled()):
        return ctx

    if plant_floor != "Filling Area":
        return ctx

    if not work_order:
        ctx["show_dialog"] = True
        return ctx

    bom_no = _get_filling_bom_no(doc.name, work_order)
    filling = _get_filling_details_from_bom(bom_no)
    ctx["filling_details"] = filling

    for row in (filling.get("rows") or []):
        if (row.get("type") or "").strip() == "Liquid Filling":
            ctx["liquid_weight"] = flt(row.get("weight") or 0)
            break

    ctx["show_liquid_fields"] = bool(ctx["liquid_weight"] > 0)

    wo_vals = _get_metal_detector_values(work_order)
    ctx["show_dialog"] = not _is_metal_detector_dialog_completed(wo_vals, ctx["liquid_weight"])
    return ctx


def _job_card_needs_metal_detector(doc) -> bool:
    return bool(_get_job_card_metal_detector_context(doc).get("show_dialog"))


def _validate_metal_detector_before_start(doc):
    ctx = _get_job_card_metal_detector_context(doc)
    if not ctx.get("show_dialog"):
        return

    wo = (ctx.get("work_order") or "").strip()
    if not wo:
        frappe.throw("Work Order is required.")

    vals = _get_metal_detector_values(wo)
    labels = _metal_detector_field_labels()
    missing = []

    for fieldname in _metal_detector_required_fields(ctx.get("liquid_weight") or 0):
        if not _metal_detector_field_is_filled(fieldname, vals.get(fieldname)):
            missing.append(labels.get(fieldname, fieldname))

    if missing:
        frappe.throw(
            "Please complete Metal Detector checks before starting: " + ", ".join(missing)
        )


@frappe.whitelist()
def get_start_requirements(job_card: str):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("read")

    ctx = _get_job_card_metal_detector_context(doc)
    work_order = (doc.get("work_order") or "").strip()

    return {
        "enabled": cint(_metal_detector_guard_enabled()),
        "needs_metal_detector": cint(ctx.get("show_dialog")),
        "show_liquid_fields": cint(ctx.get("show_liquid_fields")),
        "liquid_weight": flt(ctx.get("liquid_weight") or 0),
        "plant_floor": ctx.get("plant_floor") or "",
        "work_order": work_order,
        "values": _get_metal_detector_values(work_order),
    }


@frappe.whitelist()
def save_metal_detector_checks(
    job_card: str,
    taj_ferrous_detection=None,
    taj_non_ferrous_detection=None,
    taj_sus_detection=None,
    taj_threshold_set_point=None,
    taj_gain_set_point=None,
    taj_gain_set_point_=None,
    taj_check_weight_1=None,
    taj_anritus_weight_1=None,
    taj_check_weight_2=None,
    taj_anritus_weight_2=None,
):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("write")

    _save_metal_detector_values(
        (doc.get("work_order") or "").strip(),
        {
            "taj_ferrous_detection": taj_ferrous_detection,
            "taj_non_ferrous_detection": taj_non_ferrous_detection,
            "taj_sus_detection": taj_sus_detection,
            "taj_threshold_set_point": taj_threshold_set_point,
            "taj_gain_set_point": taj_gain_set_point if taj_gain_set_point is not None else taj_gain_set_point_,
            "taj_check_weight_1": taj_check_weight_1,
            "taj_anritus_weight_1": taj_anritus_weight_1,
            "taj_check_weight_2": taj_check_weight_2,
            "taj_anritus_weight_2": taj_anritus_weight_2,
        },
    )

    ctx = _get_job_card_metal_detector_context(doc)

    return {
        "ok": True,
        "show_liquid_fields": cint(ctx.get("show_liquid_fields")),
        "liquid_weight": flt(ctx.get("liquid_weight") or 0),
        "values": _get_metal_detector_values((doc.get("work_order") or "").strip()),
    }


@frappe.whitelist()
def board_start_job(
    job_card: str,
    employees=None,
    start_time=None,
    taj_ferrous_detection=None,
    taj_non_ferrous_detection=None,
    taj_sus_detection=None,
    taj_threshold_set_point=None,
    taj_gain_set_point=None,
    taj_gain_set_point_=None,
    taj_check_weight_1=None,
    taj_anritus_weight_1=None,
    taj_check_weight_2=None,
    taj_anritus_weight_2=None,
):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("write")
    _assert_work_order_not_closed(doc)

    if int(doc.docstatus or 0) != 0:
        frappe.throw("Only Draft Job Cards can be started from the board.")

    employees = _parse_json_if_needed(employees) or []
    emp_list = []
    for e in employees:
        if isinstance(e, dict) and e.get("employee"):
            emp_list.append(e.get("employee"))
        elif isinstance(e, str):
            emp_list.append(e)
    emp_list = [x for x in emp_list if x]
    if not emp_list:
        frappe.throw("Please select at least one employee.")

    start_time = get_datetime(start_time) if start_time else _safe_now()

    if cint(_metal_detector_guard_enabled()):
        _save_metal_detector_values(
            (doc.get("work_order") or "").strip(),
            {
                "taj_ferrous_detection": taj_ferrous_detection,
                "taj_non_ferrous_detection": taj_non_ferrous_detection,
                "taj_sus_detection": taj_sus_detection,
                "taj_threshold_set_point": taj_threshold_set_point,
                "taj_gain_set_point": taj_gain_set_point if taj_gain_set_point is not None else taj_gain_set_point_,
                "taj_check_weight_1": taj_check_weight_1,
                "taj_anritus_weight_1": taj_anritus_weight_1,
                "taj_check_weight_2": taj_check_weight_2,
                "taj_anritus_weight_2": taj_anritus_weight_2,
            },
        )
        _validate_metal_detector_before_start(doc)

    _ensure_employee_table(doc, emp_list)

    if _is_running_now(job_card) and (doc.get("status") or "") != "On Hold" and not int(doc.get("is_paused") or 0):
        return {"ok": True, "card": get_card_payload(job_card)}

    for emp in emp_list:
        doc.append("time_logs", {"employee": emp, "from_time": start_time, "to_time": None, "completed_qty": 0.0})

    _set_is_paused(doc, 0)
    _set_status(doc, "Work In Progress")
    _set_started_time(doc, start_time)

    doc.save()
    return {"ok": True, "card": get_card_payload(job_card)}


@frappe.whitelist()
def board_pause_job(job_card: str, end_time=None):

    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("write")
    _assert_work_order_not_closed(doc)

    if int(doc.docstatus or 0) != 0:
        frappe.throw("Only Draft Job Cards can be paused from the board.")

    if (doc.get("status") or "").strip() == "On Hold" or int(doc.get("is_paused") or 0) == 1:
        return {"ok": True, "card": get_card_payload(job_card)}

    end_time = get_datetime(end_time) if end_time else _safe_now()

    open_rows = _open_time_log_rows(doc)
    if not open_rows:
        return {"ok": True, "card": get_card_payload(job_card)}

    for r in open_rows:
        r.to_time = _ensure_to_time_after(r.from_time, end_time)

    _set_is_paused(doc, 1)
    _set_status(doc, "On Hold")
    doc.save()

    return {"ok": True, "card": get_card_payload(job_card)}


@frappe.whitelist()
def board_resume_job(job_card: str, start_time=None):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("write")
    _assert_work_order_not_closed(doc)

    if int(doc.docstatus or 0) != 0:
        frappe.throw("Only Draft Job Cards can be resumed from the board.")

    if _is_running_now(job_card) and (doc.get("status") or "") != "On Hold" and not int(doc.get("is_paused") or 0):
        return {"ok": True, "card": get_card_payload(job_card)}

    start_time = get_datetime(start_time) if start_time else _safe_now()

    emp_list = [r.get("employee") for r in (doc.get("employee") or []) if r.get("employee")]
    if not emp_list:
        seen = set()
        for r in (doc.get("time_logs") or []):
            if r.get("employee") and r.get("employee") not in seen:
                emp_list.append(r.get("employee"))
                seen.add(r.get("employee"))

    if not emp_list:
        doc.append("time_logs", {"from_time": start_time, "to_time": None, "completed_qty": 0.0})
    else:
        for emp in emp_list:
            doc.append("time_logs", {"employee": emp, "from_time": start_time, "to_time": None, "completed_qty": 0.0})

    _set_is_paused(doc, 0)
    _set_status(doc, "Work In Progress")
    _set_started_time(doc, start_time)

    doc.save()
    return {"ok": True, "card": get_card_payload(job_card)}


@frappe.whitelist()
def board_complete_job(job_card: str, qty: float, taj_temperature=None):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("write")
    _assert_work_order_not_closed(doc)

    if int(doc.docstatus or 0) != 0:
        frappe.throw("Only Draft Job Cards can be completed from the board.")

    qty = flt(qty)
    if qty <= 0:
        frappe.throw("Quantity should be greater than 0.")

    if (doc.get("status") or "").strip() == "On Hold" or int(doc.get("is_paused") or 0) == 1:
        frappe.throw("Job is On Hold. Please Resume first.")

    operation_name = (doc.get("operation") or "").strip()
    requires_temperature = 0
    min_temp = 0.0
    max_temp = 0.0

    if operation_name and frappe.db.exists("Operation", operation_name):
        if _has_col("Operation", "taj_requires_temperature"):
            requires_temperature = int(
                frappe.db.get_value("Operation", operation_name, "taj_requires_temperature") or 0
            )

        op_fields = []
        if _has_col("Operation", "taj_min_temperature"):
            op_fields.append("taj_min_temperature")
        if _has_col("Operation", "taj_max_temperature"):
            op_fields.append("taj_max_temperature")

        if op_fields:
            op_vals = frappe.db.get_value("Operation", operation_name, op_fields, as_dict=True) or {}
            min_temp = flt(op_vals.get("taj_min_temperature") or 0)
            max_temp = flt(op_vals.get("taj_max_temperature") or 0)

        if requires_temperature:
            raw_temp = taj_temperature

            if raw_temp is None or str(raw_temp).strip() == "":
                frappe.throw("Temperature is required for this operation.")

            temp_val = flt(raw_temp)

        if not (min_temp == 0 and max_temp == 0):
            low = min(min_temp, max_temp)
            high = max(min_temp, max_temp)

            if temp_val < low or temp_val > high:
                frappe.msgprint(
                    message=(
                        f"Temperature {temp_val} is outside the recommended range "
                        f"({low} to {high}) for operation {operation_name}."
                    ),
                    title="Temperature Warning",
                    indicator="orange",
                )

    end_time = _safe_now()

    open_rows = _open_time_log_rows(doc)
    if not open_rows:
        return {"ok": True, "card": get_card_payload(job_card)}

    for r in open_rows:
        r.to_time = _ensure_to_time_after(r.from_time, end_time)

    open_rows[-1].completed_qty = qty

    if requires_temperature and hasattr(open_rows[-1], "meta") and open_rows[-1].meta.has_field("taj_temperature"):
        open_rows[-1].taj_temperature = flt(taj_temperature)

    total_done = 0.0
    for r in (doc.get("time_logs") or []):
        total_done += flt(r.get("completed_qty") or 0)

    if _has_col("Job Card", "total_completed_qty"):
        doc.set("total_completed_qty", total_done)

    if _has_col("Job Card", "process_loss_qty"):
        doc.set("process_loss_qty", 0)

    planned = flt(doc.get("for_quantity") or 0)

    if planned and total_done >= planned:
        _set_status(doc, "Completed")
    else:
        _set_status(doc, "Work In Progress")

    _set_is_paused(doc, 0)

    if planned and total_done < planned:
        _set_started_time(doc, None)

    doc.save()
    return {"ok": True, "card": get_card_payload(job_card)}


def _doc_has_open_time_logs(doc) -> bool:
    if not doc:
        return False
    return bool(_open_time_log_rows(doc))


def _is_job_card_start_transition(doc) -> bool:
    if not doc or int(doc.get("docstatus") or 0) != 0:
        return False

    before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
    new_status = (doc.get("status") or "").strip()
    old_status = (before.get("status") or "").strip() if before else ""

    new_started = not _is_empty_time(doc.get("started_time"))
    old_started = (not _is_empty_time(before.get("started_time"))) if before else False

    new_running = _doc_has_open_time_logs(doc)
    old_running = _doc_has_open_time_logs(before) if before else False

    if new_status == "Work In Progress" and old_status != "Work In Progress":
        return True
    if new_started and not old_started:
        return True
    if new_running and not old_running:
        return True
    return False


def job_card_validate_metal_detector_guard(doc, method=None):
    if not cint(_metal_detector_guard_enabled()):
        return
    if not _is_job_card_start_transition(doc):
        return
    _assert_work_order_not_closed(doc)
    _validate_metal_detector_before_start(doc)


def _effective_pf_for_doc(doc) -> str:
    jc_pf = (doc.get("taj_plant_floor") or "").strip() if _has_col("Job Card", "taj_plant_floor") else ""
    if jc_pf:
        return jc_pf

    ws = (doc.get("workstation") or "").strip()
    if not ws:
        return ""

    if _has_col("Workstation", "plant_floor"):
        return (frappe.db.get_value("Workstation", ws, "plant_floor") or "").strip()

    return ""


def _set_field_if_exists(doc, fieldname: str, value):
    if value is None:
        return
    if not doc.meta.has_field(fieldname):
        return
    doc.set(fieldname, value)


@frappe.whitelist()
def board_submit_job(
    job_card: str,
    for_quantity=None,
    confirm_loss=0,
    taj_manpower_used=None,
    taj_total_weight=None,
    taj_rm_used_qty=None,
):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("submit")
    _assert_work_order_not_closed(doc)

    if int(doc.docstatus or 0) != 0:
        frappe.throw("Only Draft Job Cards can be submitted.")

    if _is_running_now(job_card):
        frappe.throw("Please Pause/Complete the running timer before submitting.")

    pf = _effective_pf_for_doc(doc)

    if doc.meta.has_field("taj_manpower_used"):
        mp = int(taj_manpower_used or 0)
        if mp <= 0:
            frappe.throw("Manpower is required.")
        doc.set("taj_manpower_used", mp)

    if pf == "Cooking Area" and doc.meta.has_field("taj_total_weight"):
        tw = flt(taj_total_weight)
        if tw <= 0:
            frappe.throw("Total Weight is required for Cooking Area.")
        doc.set("taj_total_weight", tw)

    if pf == "Preparation Area" and doc.meta.has_field("taj_rm_used_qty"):
        rq = flt(taj_rm_used_qty)
        if rq <= 0:
            frappe.throw("RM Used Qty is required for Preparation Area.")
        doc.set("taj_rm_used_qty", rq)

    done = flt(doc.get("total_completed_qty") or 0)
    current_fq = flt(doc.get("for_quantity") or 0)

    if for_quantity is None:
        if current_fq > done:
            frappe.throw("Qty to Manufacture is greater than Completed Qty. Use the Submit dialog to confirm Process Loss.")
        doc.save()
        doc.submit()
        return {"ok": True, "card": get_card_payload(job_card)}

    fq = flt(for_quantity)
    if fq < done:
        frappe.throw("Qty to Manufacture cannot be less than Completed Qty.")

    loss = flt(fq - done) if fq > done else 0.0
    if loss > 0 and not int(confirm_loss or 0):
        frappe.throw("Confirmation required to submit with Process Loss.")

    if _has_col("Job Card", "for_quantity"):
        doc.set("for_quantity", fq)

    if _has_col("Job Card", "process_loss_qty"):
        doc.set("process_loss_qty", loss)

    if _has_col("Job Card", "status"):
        doc.set("status", "Completed")

    doc.save()
    doc.submit()
    return {"ok": True, "card": get_card_payload(job_card)}


# -------------------------
# Realtime triggers
# -------------------------
def _scrub(txt: str) -> str:
    if not txt:
        return ""
    s = str(txt).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"^_+|_+$", "", s)
    return s


def _get_ws_plant_floor_cached(workstation: str | None) -> str:
    ws = (workstation or "").strip()
    if not ws:
        return ""
    if not _has_col("Workstation", "plant_floor"):
        return ""
    if ws in _WS_PF_CACHE:
        return _WS_PF_CACHE[ws]
    pf = (frappe.db.get_value("Workstation", ws, "plant_floor") or "").strip()
    _WS_PF_CACHE[ws] = pf
    return pf


def _effective_pf_lite_from_doc(doc) -> str:
    if _has_col("Job Card", "taj_plant_floor"):
        pf = (getattr(doc, "taj_plant_floor", "") or "").strip()
        if pf:
            return pf
    return _get_ws_plant_floor_cached(getattr(doc, "workstation", None))


def _publish_job_card_lite_by_name(job_card_name: str, is_delete: bool = False):
    if not job_card_name:
        return

    fields = ["name", "modified", "docstatus", "status", "work_order", "workstation", "operation"]

    for f in [
        "is_paused",
        "for_quantity",
        "total_completed_qty",
        "total_time_in_mins",
        "taj_plant_floor",
        "taj_manpower_used",
        "taj_total_weight",
        "taj_rm_used_qty",
    ]:
        if frappe.db.has_column("Job Card", f):
            fields.append(f)

    jc = frappe.db.get_value("Job Card", job_card_name, fields, as_dict=True)
    if not jc:
        return

    pf = (jc.get("taj_plant_floor") or "").strip() if frappe.db.has_column("Job Card", "taj_plant_floor") else ""
    if not pf:
        pf = _get_ws_plant_floor_cached(jc.get("workstation"))

    payload = {
        "__lite": 1,
        "name": jc.get("name"),
        "modified": str(jc.get("modified") or ""),
        "docstatus": int(jc.get("docstatus") or 0),
        "status": (jc.get("status") or "").strip(),
        "work_order": jc.get("work_order"),
        "workstation": jc.get("workstation"),
        "operation": jc.get("operation"),
        "is_paused": int(jc.get("is_paused") or 0),
        "for_quantity": float(jc.get("for_quantity") or 0),
        "total_completed_qty": float(jc.get("total_completed_qty") or 0),
        "total_time_in_mins": float(jc.get("total_time_in_mins") or 0),
        "taj_manpower_used": int(jc.get("taj_manpower_used") or 0),
        "taj_total_weight": float(jc.get("taj_total_weight") or 0),
        "taj_rm_used_qty": float(jc.get("taj_rm_used_qty") or 0),
        "plant_floor": pf,
        "__event": EVENT_NAME,
    }

    if is_delete:
        payload["__action"] = "remove"

    doc_room = f"doc:Job Card/{job_card_name}"
    frappe.publish_realtime(EVENT_NAME, payload, room=doc_room, after_commit=True)

    for room in (DOCTYPE_ROOM_A, DOCTYPE_ROOM_B):
        frappe.publish_realtime(EVENT_NAME, payload, room=room, after_commit=True)

    if pf:
        pf_room = f"jc_board:pf:{_scrub(pf)}"
        frappe.publish_realtime(EVENT_NAME, payload, room=pf_room, after_commit=True)


def job_card_changed(doc, method=None):
    try:
        is_delete = str(method or "").lower() in ("on_trash", "after_delete", "on_delete", "after_trash")
        _publish_job_card_lite_by_name(doc.name, is_delete=is_delete)

        before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
        if before and not is_delete:
            old_pf = _effective_pf_lite_from_doc(before)
            new_pf = _effective_pf_lite_from_doc(doc)
            if old_pf and old_pf != new_pf:
                old_room = f"jc_board:pf:{_scrub(old_pf)}"
                frappe.publish_realtime(
                    EVENT_NAME,
                    {"name": doc.name, "__action": "remove", "__lite": 1, "plant_floor": old_pf, "__event": EVENT_NAME},
                    room=old_room,
                    after_commit=True,
                )

    except Exception:
        frappe.log_error("Job Card Board realtime publish failed", frappe.get_traceback())


def job_card_time_log_changed(doc, method=None):
    try:
        parent = (getattr(doc, "parent", None) or "").strip()
        if not parent:
            return
        is_delete = str(method or "").lower() in ("on_trash", "after_delete", "on_delete", "after_trash")
        _publish_job_card_lite_by_name(parent, is_delete=is_delete)
    except Exception:
        frappe.log_error("Job Card Board realtime publish (time log) failed", frappe.get_traceback())


def _assert_work_order_not_closed(doc):
    wo = (doc.get("work_order") or "").strip()
    if not wo:
        return

    wo_vals = frappe.db.get_value("Work Order", wo, ["status", "docstatus"], as_dict=True) or {}
    wo_status = (wo_vals.get("status") or "").strip()
    wo_docstatus = int(wo_vals.get("docstatus") or 0)

    if _is_work_order_closed_or_done(wo_status, wo_docstatus):
        frappe.throw(
            f"Cannot perform this action because Work Order '{wo}' is {wo_status or 'Cancelled'}."
        )
