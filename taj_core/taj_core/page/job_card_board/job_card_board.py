from __future__ import annotations

import datetime
import re
from typing import List, Set, Optional, Dict, Any, Tuple

import frappe
from frappe.utils import flt, get_datetime, today

OVERDUE_TOLERANCE_SEC = 120  # 2 minutes

EVENT_NAME = "job_card_board_update"
DOCTYPE_ROOM = "doctype: Job Card"


# -------------------------
# Column cache (performance)
# -------------------------
_COL_CACHE: Dict[Tuple[str, str], bool] = {}


def _has_col(doctype: str, fieldname: str) -> bool:
    key = (doctype, fieldname)
    if key not in _COL_CACHE:
        _COL_CACHE[key] = bool(frappe.db.has_column(doctype, fieldname))
    return _COL_CACHE[key]


def _safe_fields() -> List[str]:
    # Only DB columns here (get_list / SQL safe)
    fields = ["name", "modified", "docstatus", "creation"]
    for f in [
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
    """
    مصدر المسموح:
    1) User Permission (allow = Plant Floor)
    2) User Default "Plant Floor" (fallback)
    """
    if not user:
        return []

    # User Permission records
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

    # Fallback: user default
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
    # Cooking Mode rule requested:
    # taj_plant_floor == 'Cooking Area' OR workstation.taj_production_stage == 'Cooking'
    return ((jc_pf or "").strip() == "Cooking Area") or ((ws_stage or "").strip() == "Cooking")


# -------------------------
# Time logs helpers
# -------------------------
def _jobcards_by_time_logs(start_dt, end_dt) -> List[str]:
    """
    Any overlap with time logs in range.
    IMPORTANT FIX:
      - Open logs (to_time NULL/invalid) must be treated as ending NOW(), not from_time.
    """
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
    """Running if ANY time log row is open."""
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
    """Timer = sum of closed logs + open logs (now-from). Works even if multiple open rows exist."""
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
    """
    Expected time priority:
    1) Work Order Operation time_in_mins
    2) BOM Operation time_in_mins (fallback)
    """
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

    # BOM fallback
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
    # completed for alarms = submitted OR status Completed OR qty finished
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
    """
    Enforce Plant Floor access for action endpoints & single card payload.
    """
    user = frappe.session.user
    if _is_admin_user(user):
        return

    allowed = _allowed_plant_floors_for_user(user)
    if not allowed:
        raise frappe.PermissionError("No Plant Floor is assigned to this user.")

    # read minimal values
    fields = ["workstation"]
    if _has_col("Job Card", "taj_plant_floor"):
        fields.append("taj_plant_floor")

    jc = frappe.db.get_value("Job Card", job_card_name, fields, as_dict=True)
    if not jc:
        # if deleted, allow (remove events)
        return

    ws = (jc.get("workstation") or "").strip()
    jc_pf = (jc.get("taj_plant_floor") or "").strip() if _has_col("Job Card", "taj_plant_floor") else ""

    ws_pf_map = _get_ws_pf_map([ws]) if ws else {}
    eff_pf = _effective_plant_floor_from_values(jc_pf, ws, ws_pf_map)

    if eff_pf and eff_pf not in allowed:
        raise frappe.PermissionError(f"Job Card '{job_card_name}' is not in an allowed Plant Floor.")


# -------------------------
# Payload builders
# -------------------------
def _build_payloads_for_cards(job_cards: List[dict]) -> List[dict]:
    if not job_cards:
        return []

    names = [d["name"] for d in job_cards]
    running_set = _get_running_parents(names)
    timer_map = _compute_timer_seconds(names)
    expected_map = _get_expected_seconds_map(job_cards)

    ws_names = [d.get("workstation") for d in job_cards if d.get("workstation")]
    ws_stage_map = _workstation_to_production_stage(ws_names)
    ws_pf_map = _get_ws_pf_map(ws_names)

    items = []
    for d in job_cards:
        docstatus = int(d.get("docstatus") or 0)
        status = (d.get("status") or "").strip()

        planned = flt(d.get("for_quantity")) or 0.0
        done = flt(d.get("total_completed_qty")) or 0.0
        remaining = max(planned - done, 0.0)

        is_paused = _get_is_paused(d)
        is_finished = _is_finished_qty(planned, done)
        is_completed = _is_completed(docstatus, status, planned, done)

        running = (
            docstatus == 0
            and (d["name"] in running_set)
            and (not is_completed)
            and (is_paused == 0)
        )

        timer_seconds = int(timer_map.get(d["name"], 0) or 0)
        expected_seconds = int(expected_map.get(d["name"], 0) or 0)

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
                "timer_seconds": timer_seconds,
                "expected_seconds": expected_seconds,
                "is_overdue": int(bool(is_overdue)),
                "plant_floor": eff_pf,
                "taj_production_stage": ws_stage,
                "is_cooking_mode": int(_is_cooking_mode(jc_pf, ws_stage)),
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
    """
    Bulk payload for polling / refresh:
      - names: JSON list OR comma-separated string
      - returns: {items: [...]}  (only allowed plant floors)
    """
    raw = _parse_json_if_needed(names) or names or []
    if isinstance(raw, str):
        arr = [x.strip() for x in raw.split(",") if x and x.strip()]
    elif isinstance(raw, list):
        arr = [str(x).strip() for x in raw if x and str(x).strip()]
    else:
        arr = []

    # cap to protect server
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

    # filter by Plant Floor server-side (mandatory)
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

    # Default dates = today
    if not date_from and not date_to:
        date_from = today()
        date_to = today()

    # Plant Floor enforcement
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

    # --- Plant Floor filter (server-side enforced) ---
    if effective_pfs:
        if _has_col("Job Card", "taj_plant_floor"):
            filters["taj_plant_floor"] = ["in", effective_pfs] if len(effective_pfs) > 1 else effective_pfs[0]
        else:
            # fallback via Workstation.plant_floor
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

    # Date filter: time logs in range + new cards with no logs created in range
    start_dt, end_dt = _time_range_to_datetimes(date_from, date_to)
    if start_dt and end_dt:
        names_logs = _jobcards_by_time_logs(start_dt, end_dt)
        names_nologs = _jobcards_without_time_logs_in_range(start_dt, end_dt)
        names = sorted(list(set((names_logs or []) + (names_nologs or []))))
        if not names:
            return {"items": [], "limit": limit, "offset": offset}
        filters["name"] = ["in", names]

    post_search = None
    if search:
        if "name" in filters:
            post_search = str(search).strip()
        else:
            filters["name"] = ["like", f"%{search}%"]

    # IMPORTANT: use get_list (applies user permissions)
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

    return {"items": _build_payloads_for_cards(job_cards), "limit": limit, "offset": offset}


# ==========================
# Actions used by board buttons
# ==========================

def _ensure_employee_table(doc, employees: List[str]):
    # employee is a child table field (not DB column) => check meta, not has_column
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


@frappe.whitelist()
def board_start_job(job_card: str, employees=None, start_time=None):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("write")

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

    _ensure_employee_table(doc, emp_list)

    # avoid duplicates if already running
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
def board_complete_job(job_card: str, qty: float):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("write")

    if int(doc.docstatus or 0) != 0:
        frappe.throw("Only Draft Job Cards can be completed from the board.")

    qty = flt(qty)
    if qty <= 0:
        frappe.throw("Quantity should be greater than 0.")

    if (doc.get("status") or "").strip() == "On Hold" or int(doc.get("is_paused") or 0) == 1:
        frappe.throw("Job is On Hold. Please Resume first.")

    end_time = _safe_now()

    open_rows = _open_time_log_rows(doc)
    if not open_rows:
        return {"ok": True, "card": get_card_payload(job_card)}

    for r in open_rows:
        r.to_time = _ensure_to_time_after(r.from_time, end_time)

    open_rows[-1].completed_qty = qty

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

    # show Start Job again in Job Card UI when remaining exists
    if planned and total_done < planned:
        _set_started_time(doc, None)

    doc.save()
    return {"ok": True, "card": get_card_payload(job_card)}


@frappe.whitelist()
def board_submit_job(job_card: str, for_quantity=None, confirm_loss=0):
    _assert_user_can_access_job_card_pf(job_card)

    doc = frappe.get_doc("Job Card", job_card)
    doc.check_permission("submit")

    if int(doc.docstatus or 0) != 0:
        frappe.throw("Only Draft Job Cards can be submitted.")

    if _is_running_now(job_card):
        frappe.throw("Please Pause/Complete the running timer before submitting.")

    done = flt(doc.get("total_completed_qty") or 0)
    current_fq = flt(doc.get("for_quantity") or 0)

    if for_quantity is None:
        if current_fq > done:
            frappe.throw("Qty to Manufacture is greater than Completed Qty. Use the Submit dialog to confirm Process Loss.")
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


# ==========================
# Realtime triggers (hooks.py)
# ==========================
def _scrub(txt: str) -> str:
    if not txt:
        return ""
    s = str(txt).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"^_+|_+$", "", s)
    return s


def _get_ws_plant_floor(workstation: str | None) -> str:
    if not workstation:
        return ""
    if not _has_col("Workstation", "plant_floor"):
        return ""
    return (frappe.db.get_value("Workstation", workstation, "plant_floor") or "").strip()


def _effective_pf_from_doc(doc) -> str:
    jc_pf = (doc.get("taj_plant_floor") or "").strip() if _has_col("Job Card", "taj_plant_floor") else ""
    if jc_pf:
        return jc_pf
    return _get_ws_plant_floor(doc.get("workstation"))

# كان يوجد تأخير من 3 إلى 7 ثواني فأستبدلت الكود
# def job_card_changed(doc, method=None):
#     try:
#         # Delete/Trash should explicitly remove
#         is_delete = str(method or "").lower() in ("on_trash", "after_delete", "on_delete", "after_trash")

#         if is_delete:
#             payload = {"name": doc.name, "__action": "remove"}
#         else:
#             payload = get_card_payload(doc.name) or {"name": doc.name}

#         payload["__event"] = EVENT_NAME

#         # publish to doc room
#         doc_room = f"doc:Job Card/{doc.name}"
#         frappe.publish_realtime(EVENT_NAME, payload, room=doc_room, after_commit=True)

#         # publish to doctype room (discovery / general)
#         frappe.publish_realtime(EVENT_NAME, payload, room=DOCTYPE_ROOM, after_commit=True)

#         # publish to Plant Floor room (current)
#         pf = _effective_pf_from_doc(doc)
#         pf_room = f"jc_board:pf:{_scrub(pf)}" if pf else None
#         if pf_room:
#             frappe.publish_realtime(EVENT_NAME, payload, room=pf_room, after_commit=True)

#         # if Plant Floor changed, tell old room to remove this card
#         before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
#         if before and not is_delete:
#             old_pf = _effective_pf_from_doc(before)
#             old_room = f"jc_board:pf:{_scrub(old_pf)}" if old_pf else None
#             if old_room and old_room != pf_room:
#                 frappe.publish_realtime(
#                     EVENT_NAME,
#                     {"name": doc.name, "__action": "remove"},
#                     room=old_room,
#                     after_commit=True,
#                 )

#         # on delete: also remove from old pf (if any)
#         if before and is_delete:
#             old_pf = _effective_pf_from_doc(before)
#             old_room = f"jc_board:pf:{_scrub(old_pf)}" if old_pf else None
#             if old_room:
#                 frappe.publish_realtime(
#                     EVENT_NAME,
#                     {"name": doc.name, "__action": "remove"},
#                     room=old_room,
#                     after_commit=True,
#                 )

#     except Exception:
#         frappe.log_error("Job Card Board realtime publish failed", frappe.get_traceback())

def job_card_changed(doc, method=None):
    try:
        is_delete = str(method or "").lower() in ("on_trash", "after_delete", "on_delete", "after_trash")

        if is_delete:
            payload = {"name": doc.name, "__action": "remove", "__lite": 1}
        else:
            # ✅ Lite payload from doc itself (no heavy queries)
            payload = {
                "__lite": 1,
                "name": doc.name,
                "modified": str(doc.modified) if getattr(doc, "modified", None) else None,
                "docstatus": int(getattr(doc, "docstatus", 0) or 0),
                "status": (getattr(doc, "status", "") or "").strip(),
                "work_order": getattr(doc, "work_order", None),
                "workstation": getattr(doc, "workstation", None),
                "operation": getattr(doc, "operation", None),
                "is_paused": int(getattr(doc, "is_paused", 0) or 0),
                "for_quantity": float(getattr(doc, "for_quantity", 0) or 0),
                "total_completed_qty": float(getattr(doc, "total_completed_qty", 0) or 0),
                # أفضل لو taj_plant_floor موجود عندكم (حتى نتجنب query على Workstation)
                "plant_floor": (getattr(doc, "taj_plant_floor", "") or "").strip() if frappe.db.has_column("Job Card", "taj_plant_floor") else "",
            }

        payload["__event"] = EVENT_NAME

        doc_room = f"doc:Job Card/{doc.name}"
        frappe.publish_realtime(EVENT_NAME, payload, room=doc_room, after_commit=True)
        frappe.publish_realtime(EVENT_NAME, payload, room=DOCTYPE_ROOM, after_commit=True)

        # Plant Floor room (only if we have pf in payload)
        pf = (payload.get("plant_floor") or "").strip()
        if pf:
            pf_room = f"jc_board:pf:{_scrub(pf)}"
            frappe.publish_realtime(EVENT_NAME, payload, room=pf_room, after_commit=True)

        # remove from old plant floor if changed
        before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
        if before and not is_delete:
            old_pf = ((before.get("taj_plant_floor") or "").strip()
                      if frappe.db.has_column("Job Card", "taj_plant_floor") else "")
            old_room = f"jc_board:pf:{_scrub(old_pf)}" if old_pf else None
            new_room = f"jc_board:pf:{_scrub(pf)}" if pf else None
            if old_room and old_room != new_room:
                frappe.publish_realtime(EVENT_NAME, {"name": doc.name, "__action": "remove", "__lite": 1},
                                        room=old_room, after_commit=True)

    except Exception:
        frappe.log_error("Job Card Board realtime publish failed", frappe.get_traceback())