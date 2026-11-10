"""Simulation snapshots built from standard v16 traceability, with explicit QC review."""
from decimal import Decimal, InvalidOperation
import json
import math
import time

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime

EVIDENCE_VERSION = 2
MAX_ROWS = 1800
MAX_TRACE_VISITS = 3600
MAX_TRACE_DEPTH = 40
TRACE_SECONDS = 30
SOURCE_TYPES = frozenset(("Stock Entry", "Purchase Receipt", "Purchase Invoice", "Delivery Note", "Sales Invoice", "Pick List", "Stock Reconciliation", "POS Invoice"))
SNAPSHOT_FIELDS = ("started_at", "completed_at", "snapshot_date", "trace_row_count", "customer_count", "elapsed_seconds", "evidence_version", "snapshot_issues")
REVIEW_FIELDS = ("result", "reviewed_by", "reviewed_at", "review_notes")
TRACE_FIELDS = ("direction", "item_code", "batch_no", "qty", "warehouse", "reference_doctype", "reference_name", "work_order", "supplier", "customer", "trace_level", "uom", "posting_datetime")
DISTRIBUTION_FIELDS = ("customer", "voucher_type", "voucher_no", "item_code", "batch_no", "qty", "uom", "returned_qty", "net_qty", "evidence_type", "source_notes", "return_references")
NUMERIC_FIELDS = frozenset(("qty", "returned_qty", "net_qty", "trace_level", "trace_row_count", "customer_count", "elapsed_seconds", "evidence_version"))


def _same_value(field, first, second):
    if field in NUMERIC_FIELDS:
        if first is None or second is None:
            return first is second
        try:
            return Decimal(str(first)) == Decimal(str(second))
        except InvalidOperation:
            return False
    return str(first or "") == str(second or "")


class MockRecall(Document):
    def on_trash(self):
        if self.status != "Draft" or self.get("trace_rows") or self.get("distribution_rows"):
            frappe.throw(_("Evidence snapshots cannot be deleted. Start a new simulation instead."))

    def validate(self):
        self.is_simulation = 1
        prior = self.get_doc_before_save() if not self.is_new() else None
        action = self.flags.get("mock_recall_action")
        if self.is_new():
            if (self.status or "Draft") != "Draft" or (self.result or "Not Evaluated") != "Not Evaluated":
                frappe.throw(_("A new mock recall must start as Draft / Not Evaluated."))
            if any(self.get(field) not in (None, "", 0, 0.0) for field in SNAPSHOT_FIELDS + REVIEW_FIELDS if field != "result"):
                frappe.throw(_("A new mock recall cannot contain generated evidence or review metadata."))
            if self.get("trace_rows") or self.get("distribution_rows") or any(self.get(field) for field in ("quantity_verified", "customers_verified", "genealogy_verified")):
                frappe.throw(_("Run traceability before entering evidence verification."))
            self.status, self.result = "Draft", "Not Evaluated"
        elif not prior:
            frappe.throw(_("The previous mock recall state could not be loaded. Reload the document."))
        else:
            if prior.status == "Closed":
                frappe.throw(_("Closed mock recalls are immutable. Start a new simulation instead."))
            if prior.status in ("Traced", "Under Review"):
                for field in ("company", "item_code", "batch_no", "scenario_type"):
                    if not _same_value(field, self.get(field), prior.get(field)):
                        frappe.throw(_("Start a new simulation to change the {0}.").format(field))
            allowed = set(SNAPSHOT_FIELDS) if action == "trace" else set()
            if action in ("trace", "review"):
                allowed.update(REVIEW_FIELDS)
            for field in SNAPSHOT_FIELDS + REVIEW_FIELDS:
                if field not in allowed and not _same_value(field, self.get(field), prior.get(field)):
                    frappe.throw(_("The {0} field is managed by server actions.").format(field))
            if self.status != prior.status and action not in ("trace", "review", "start_review"):
                frappe.throw(_("Use the Mock Recall action buttons to change status."))
            if action != "trace":
                self._validate_rows(prior, action)
        if self.batch_no and self.item_code:
            if frappe.db.get_value("Batch", self.batch_no, "item") != self.item_code:
                frappe.throw(_("Selected batch does not belong to the selected item."))
        if self.is_new() or prior and any(self.get(key) != prior.get(key) for key in ("item_code", "scenario_type")):
            _validate_scenario(self)
        if self.status != "Closed":
            self.result = "Not Evaluated"
        elif not self.reviewed_by or not self.reviewed_at:
            frappe.throw(_("A quality review is required before closing."))

    def _validate_rows(self, prior, action):
        for table, fields in (("trace_rows", TRACE_FIELDS), ("distribution_rows", DISTRIBUTION_FIELDS)):
            old_rows, current_rows = prior.get(table) or [], self.get(table) or []
            if [r.name for r in old_rows] != [r.name for r in current_rows]:
                frappe.throw(_("Simulation evidence is immutable. Run a new simulation to refresh it."))
            compare_fields = fields + (() if action == "verify" else ("verification", "notes"))
            for old, current in zip(old_rows, current_rows):
                if any(not _same_value(field, current.get(field), old.get(field)) for field in compare_fields):
                    frappe.throw(_("Use the evidence verification action; generated source evidence cannot be edited."))


def _require_read(doctype, name):
    if not name or not frappe.has_permission(doctype, "read", doc=name):
        frappe.throw(_("You do not have permission to read one or more source records."), frappe.PermissionError)


def _validate_scenario(doc):
    if doc.scenario_type not in ("Finished Product", "Raw Material", "Preparation"):
        frappe.throw(_("Legacy scenario types cannot be used for new or changed scenarios."))
    if not doc.item_code:
        return
    _require_read("Item", doc.item_code)
    item = frappe.db.get_value("Item", doc.item_code, ["disabled", "item_group"], as_dict=True)
    if not item or item.disabled:
        frappe.throw(_("Select an enabled item."))
    if doc.scenario_type == "Preparation":
        if not doc.item_code.startswith("PRE"):
            frappe.throw(_("Preparation items must start with PRE."))
        return
    group = frappe.db.get_value("Item Group", item.item_group, ["lft", "rgt"], as_dict=True)
    root_name = "Finished Goods" if doc.scenario_type == "Finished Product" else "Raw Material"
    root = frappe.db.get_value("Item Group", root_name, ["lft", "rgt"], as_dict=True)
    if not group or not root or not (root.lft <= group.lft and group.rgt <= root.rgt):
        frappe.throw(_("The selected Item does not match the Scenario Type."))
    if doc.scenario_type == "Finished Product":
        pack = frappe.db.get_value("Item Group", "Ration Pack", ["lft", "rgt"], as_dict=True)
        if pack and pack.lft <= group.lft and group.rgt <= pack.rgt:
            frappe.throw(_("Ration Pack items are excluded from new Finished Product scenarios."))


@frappe.whitelist()
def item_query(doctype, txt, searchfield, start, page_len, filters):
    """Permission-aware Link query; group-tree policy is shared with validation."""
    if doctype != "Item" or not frappe.has_permission("Mock Recall", "read"):
        frappe.throw(_("You do not have permission to select recall items."), frappe.PermissionError)
    filters = frappe.parse_json(filters) if isinstance(filters, str) else filters or {}
    scenario = filters.get("scenario_type")
    if scenario not in ("Finished Product", "Raw Material", "Preparation"):
        return []
    conditions = {"disabled": 0}
    if scenario == "Preparation":
        conditions["name"] = ["like", "PRE%"]
    else:
        root_name = "Finished Goods" if scenario == "Finished Product" else "Raw Material"
        root = frappe.db.get_value("Item Group", root_name, ["lft", "rgt"], as_dict=True)
        if not root:
            return []
        groups = frappe.get_all("Item Group", filters={"lft": [">=", root.lft], "rgt": ["<=", root.rgt]},
            fields=["name", "lft", "rgt"], limit_page_length=1001)
        if len(groups) > 1000:
            frappe.throw(_("Item Group selection limit exceeded."))
        pack = frappe.db.get_value("Item Group", "Ration Pack", ["lft", "rgt"], as_dict=True) if scenario == "Finished Product" else None
        names = [row.name for row in groups if not pack or not (pack.lft <= row.lft and row.rgt <= pack.rgt)]
        if not names:
            return []
        conditions["item_group"] = ["in", names]
    text = "%" + str(txt or "")[:140] + "%"
    return frappe.get_list("Item", filters=conditions, or_filters={"name": ["like", text], "item_name": ["like", text]},
        fields=["name", "item_name"], start=max(0, cint(start)), page_length=max(1, min(100, cint(page_len))),
        order_by="name asc", as_list=True)


def _get_recall(name):
    doc = frappe.get_doc("Mock Recall", name)
    doc.check_permission("write")
    _require_read("Company", doc.company)
    return doc


def _quality_role(manager=False):
    allowed = {"Quality Manager", "System Manager"}
    if not manager:
        allowed.add("QC User")
    if not allowed.intersection(frappe.get_roles()):
        frappe.throw(_("You do not have the required quality review role."), frappe.PermissionError)


def _save_action(doc, action):
    previous = doc.flags.get("mock_recall_action")
    doc.flags.mock_recall_action = action
    try:
        doc.save()
    finally:
        doc.flags.mock_recall_action = previous


def _trace(batch_no, item_code):
    """Bound visits/depth between calls; keep all genealogy logic in ERPNext."""
    from erpnext.stock.report.serial_no_and_batch_traceability.serial_no_and_batch_traceability import ReportData

    deadline = time.monotonic() + TRACE_SECONDS
    budget = {"visits": 0, "depth": 0}
    stock_details = {}

    def stock_detail(name):
        if name not in stock_details:
            stock_details[name] = frappe.db.get_value("Stock Entry Detail", name,
                ["transfer_qty", "conversion_factor"], as_dict=True)
        detail = stock_details[name]
        if not detail or not math.isfinite(flt(detail.conversion_factor)) or flt(detail.conversion_factor) <= 0:
            frappe.throw(_("Manufacturing source UOM conversion is missing or invalid."))
        return detail

    class BoundedReport(ReportData):
        def get_finished_item_from_stock_entry(self, *args, **kwargs):
            result = super().get_finished_item_from_stock_entry(*args, **kwargs)
            if result:
                # Standard mapped-bundle sums and partial-unmapped subtraction
                # already use stock units. Normalize only their initial SED.qty.
                detail = stock_detail(result.name)
                if detail.transfer_qty is None or not math.isfinite(flt(detail.transfer_qty)) or flt(detail.transfer_qty) <= 0:
                    frappe.throw(_("Manufacturing finished stock quantity is missing or invalid."))
                result.qty = flt(detail.transfer_qty)
            return result

        def _enter(self):
            budget["visits"] += 1
            budget["depth"] += 1
            if budget["visits"] > MAX_TRACE_VISITS or budget["depth"] > MAX_TRACE_DEPTH or time.monotonic() > deadline:
                frappe.throw(_("Traceability safety limit exceeded. Investigate the source chain before continuing."))

        def set_backward_data(self, *args, **kwargs):
            self._enter()
            try:
                return super().set_backward_data(*args, **kwargs)
            finally:
                budget["depth"] -= 1

        def set_forward_data(self, *args, **kwargs):
            self._enter()
            try:
                return super().set_forward_data(*args, **kwargs)
            finally:
                budget["depth"] -= 1

        def get_sabb_entries(self, *args, **kwargs):
            if time.monotonic() > deadline:
                frappe.throw(_("Traceability time limit exceeded."))
            rows = super().get_sabb_entries(*args, **kwargs)
            if len(rows) > MAX_ROWS:
                frappe.throw(_("Trace limit exceeded; no partial snapshot was saved."))
            return rows

        def get_materials(self, *args, **kwargs):
            rows = super().get_materials(*args, **kwargs)
            if len(rows) > MAX_ROWS or time.monotonic() > deadline:
                frappe.throw(_("Trace limit exceeded; no partial snapshot was saved."))
            for material in rows:
                if not any(material.get(field) for field in ("batch_no", "serial_no", "fg_batch_no", "fg_serial_no")):
                    # get_material_qty's unbatched branch uses transaction row_qty.
                    # Batched/serial/mapped SABE quantities are already stock UOM.
                    material.qty = flt(material.qty) * flt(stock_detail(material.name).conversion_factor)
            return rows

    result = []
    for direction in ("Backward", "Forward"):
        report = BoundedReport(frappe._dict(item_code=item_code, batches=[batch_no], serial_nos=[], traceability_direction=direction))
        report.validate_filters()
        direction_rows = report.get_data()
        for row in direction_rows:
            if not row.get("item_code"):
                continue
            result.append({key: row.get(key) for key in TRACE_FIELDS if key not in ("direction", "trace_level", "uom")})
            result[-1].update(direction=direction, trace_level=row.get("indent") or 0, verification="Unverified")
            if len(result) > MAX_ROWS or time.monotonic() > deadline:
                frappe.throw(_("Trace limit exceeded; no partial snapshot was saved."))
    return result


def _scoped_sources(rows, company):
    """Fail closed on unreadable records and exclude other-company evidence."""
    result, issues, source_cache, item_cache = [], set(), {}, {}
    for row in rows:
        item_code = row["item_code"]
        if item_code not in item_cache:
            _require_read("Item", item_code)
            item_cache[item_code] = frappe.db.get_value("Item", item_code, "stock_uom")
        row["uom"] = item_cache[item_code]
        if row.get("batch_no"):
            _require_read("Batch", row["batch_no"])
            if frappe.db.get_value("Batch", row["batch_no"], "item") != item_code:
                frappe.throw(_("Trace source batch and item do not match."))
        source_type, source_name = row.get("reference_doctype"), row.get("reference_name")
        source = None
        if source_type and source_name:
            if source_type not in SOURCE_TYPES:
                issues.add(_("Some trace sources use an unsupported document type."))
                continue
            key = (source_type, source_name)
            if key not in source_cache:
                _require_read(source_type, source_name)
                source_cache[key] = frappe.get_doc(source_type, source_name)
            source = source_cache[key]
            if cint(source.get("docstatus")) != 1:
                issues.add(_("Some trace sources are not submitted."))
                continue
            if source.get("company") and source.company != company:
                issues.add(_("Some source movements fall outside the selected company."))
                continue
            if source_type in ("Delivery Note", "Sales Invoice", "POS Invoice"):
                row["customer"] = source.get("customer")
            if source_type in ("Purchase Receipt", "Purchase Invoice"):
                row["supplier"] = source.get("supplier")
            if source_type == "Stock Entry":
                row["work_order"] = source.get("work_order")
        warehouse_company = frappe.db.get_value("Warehouse", row["warehouse"], "company") if row.get("warehouse") else None
        if warehouse_company and warehouse_company != company:
            issues.add(_("Some source movements fall outside the selected company."))
            continue
        if not source and not warehouse_company:
            # Do not expose unscoped supplier/customer details from a global batch.
            row["supplier"] = row["customer"] = row["work_order"] = None
        if not source_type or not source_name:
            issues.add(_("Some trace rows have no source transaction reference."))
        if not row.get("uom"):
            issues.add(_("Some trace rows have no stock UOM."))
        result.append(row)
    return result, sorted(issues), source_cache


def _distribution(batch, item_code, company, as_of=None):
    from taj_core.qc.doctype.mock_recall.distribution import collect_distribution
    return collect_distribution([(item_code, batch)], [], company, as_of or now_datetime())


@frappe.whitelist()
def run_mock_recall(name):
    from taj_core.qc.doctype.mock_recall.distribution import collect_distribution
    doc = _get_recall(name)
    _quality_role()
    if doc.status == "Closed":
        frappe.throw(_("Closed simulations cannot be rerun."))
    if not doc.batch_no or not doc.item_code:
        frappe.throw(_("Item and batch are required."))
    _require_read("Item", doc.item_code)
    _require_read("Batch", doc.batch_no)
    if frappe.db.get_value("Batch", doc.batch_no, "item") != doc.item_code:
        frappe.throw(_("Batch and item do not match."))
    started, clock = now_datetime(), time.monotonic()
    rows, issues, sources = _scoped_sources(_trace(doc.batch_no, doc.item_code), doc.company)
    pairs = {(doc.item_code, doc.batch_no)}
    unbatched = []
    for row in rows:
        if row["direction"] != "Forward":
            continue
        if row.get("batch_no"):
            pairs.add((row["item_code"], row["batch_no"]))
        source = sources.get((row.get("reference_doctype"), row.get("reference_name")))
        if source and source.doctype == "Stock Entry" and source.get("purpose") in ("Manufacture", "Repack"):
            for output in source.get("items") or []:
                if output.get("is_finished_item") and output.get("item_code") == row["item_code"] and not row.get("batch_no"):
                    unbatched.append(dict(item_code=row["item_code"], reference_name=source.name,
                        posting_datetime=row.get("posting_datetime") or str(source.get("posting_date")) + " " + str(source.get("posting_time") or "00:00:00")))
    distribution = collect_distribution(sorted(pairs), unbatched, doc.company, started)
    if len(distribution) > MAX_ROWS:
        frappe.throw(_("Distribution limit exceeded; no partial snapshot was saved."))
    if any(row.get("evidence_type") == "Item Candidate" for row in distribution):
        issues.append(_("Unbatched output distributions are item/date candidates, not proven batch lineage."))
    doc.set("trace_rows", [])
    doc.set("distribution_rows", [])
    for row in rows:
        doc.append("trace_rows", row)
    for row in distribution:
        doc.append("distribution_rows", row)
    doc.started_at, doc.completed_at = started, now_datetime()
    doc.snapshot_date = started
    doc.elapsed_seconds = round(time.monotonic() - clock, 2)
    doc.evidence_version = EVIDENCE_VERSION
    doc.snapshot_issues = "\n".join(sorted(set(issues))) or None
    doc.trace_row_count = len(rows)
    doc.customer_count = len({row["customer"] for row in distribution if row.get("customer")})
    doc.quantity_verified = doc.customers_verified = doc.genealogy_verified = 0
    doc.coverage_notes = doc.exceptions = doc.review_notes = doc.reviewed_at = doc.reviewed_by = None
    doc.status, doc.result = "Traced", "Not Evaluated"
    _save_action(doc, "trace")
    return dict(name=doc.name, trace_rows=len(rows), distribution_rows=len(distribution), status=doc.status, snapshot_issues=doc.snapshot_issues)


def _current_evidence(doc):
    if cint(doc.get("evidence_version")) != EVIDENCE_VERSION:
        frappe.throw(_("This is a legacy snapshot. Run a new trace before verifying or passing it."))


def _valid_trace_row(row):
    return bool(row.get("item_code") and row.get("reference_doctype") in SOURCE_TYPES and row.get("reference_name") and row.get("uom") and abs(flt(row.get("qty"))) > 0)


def _review_source(doctype, name, company):
    _require_read(doctype, name)
    source = frappe.get_doc(doctype, name)
    if cint(source.get("docstatus")) != 1 or source.get("company") and source.company != company:
        frappe.throw(_("A source transaction changed status or company after capture. Run a new trace."))


def _return_sources(row):
    try:
        names = json.loads(row.get("return_references") or "[]")
    except (TypeError, ValueError):
        frappe.throw(_("Invalid saved return references. Run a new trace."))
    if not isinstance(names, list) or len(names) > MAX_ROWS or any(not isinstance(name, str) or not name for name in names):
        frappe.throw(_("Invalid saved return references. Run a new trace."))
    if flt(row.get("returned_qty")) > 0 and not names:
        frappe.throw(_("Returned quantities require saved source references. Run a new trace."))
    return {(row.voucher_type, name) for name in names}


@frappe.whitelist()
def verify_evidence(name, table_field, row_name, verification, notes=None):
    doc = _get_recall(name)
    _quality_role()
    _current_evidence(doc)
    if doc.status not in ("Traced", "Under Review") or table_field not in ("trace_rows", "distribution_rows"):
        frappe.throw(_("Evidence can only be verified on an open traced simulation."))
    if verification not in ("Unverified", "Verified", "Discrepancy"):
        frappe.throw(_("Invalid evidence verification status."))
    if verification != "Unverified" and not (notes or "").strip():
        frappe.throw(_("Source-check notes are required for evidence verification."))
    matches = [row for row in doc.get(table_field) if row.name == row_name]
    if len(matches) != 1:
        frappe.throw(_("The evidence row was not found. Reload the document."))
    row = matches[0]
    if verification == "Verified":
        if table_field == "trace_rows":
            if not _valid_trace_row(row):
                frappe.throw(_("A trace row requires a source transaction, nonzero quantity and stock UOM before verification."))
            _review_source(row.reference_doctype, row.reference_name, doc.company)
        else:
            if row.get("evidence_type") != "Batch" or not row.get("batch_no") or not row.get("uom") or flt(row.get("qty")) <= 0:
                frappe.throw(_("Item/date candidates cannot be verified as batch distribution evidence."))
            _review_source(row.voucher_type, row.voucher_no, doc.company)
            for source_type, source_name in _return_sources(row):
                _review_source(source_type, source_name, doc.company)
    row.verification, row.notes = verification, (notes or "").strip() or None
    _save_action(doc, "verify")
    return dict(name=doc.name, row_name=row_name, verification=verification)


@frappe.whitelist()
def start_review(name):
    doc = _get_recall(name)
    _quality_role()
    if doc.status != "Traced":
        frappe.throw(_("Only a traced simulation can enter quality review."))
    doc.status = "Under Review"
    _save_action(doc, "start_review")
    return dict(name=doc.name, status=doc.status)


def _check_pass(doc):
    _current_evidence(doc)
    if not doc.get("trace_rows") or doc.trace_row_count != len(doc.trace_rows):
        frappe.throw(_("No complete trace evidence was found. The simulation cannot pass."))
    if (doc.get("snapshot_issues") or "").strip():
        frappe.throw(_("Resolve the source evidence limitations before passing."))
    if not (doc.coverage_notes or "").strip() or not (doc.quantity_verified and doc.customers_verified and doc.genealogy_verified):
        frappe.throw(_("Verify quantities, customers and genealogy, and document their reconciliation before passing."))
    if (doc.exceptions or "").strip():
        frappe.throw(_("Unresolved exceptions prevent passing."))
    for row in doc.trace_rows:
        if row.get("verification") != "Verified" or not (row.get("notes") or "").strip() or not _valid_trace_row(row):
            frappe.throw(_("Every trace evidence row must be checked and verified before passing."))
    for row in doc.distribution_rows:
        if row.get("verification") != "Verified" or row.get("evidence_type") != "Batch" or not row.get("batch_no") or not row.get("uom") or not (row.get("notes") or "").strip():
            frappe.throw(_("Every distribution row must have verified batch evidence before passing."))
    source_keys = {(row.reference_doctype, row.reference_name) for row in doc.trace_rows}
    source_keys.update((row.voucher_type, row.voucher_no) for row in doc.distribution_rows)
    for row in doc.distribution_rows:
        source_keys.update(_return_sources(row))
    for source_type, source_name in source_keys:
        _review_source(source_type, source_name, doc.company)


@frappe.whitelist()
def submit_mock_review(name, decision, notes):
    doc = _get_recall(name)
    _quality_role(manager=True)
    if doc.status not in ("Traced", "Under Review"):
        frappe.throw(_("Run traceability before reviewing."))
    if decision not in ("Passed", "Failed") or not (notes or "").strip():
        frappe.throw(_("Select a valid assessment and enter review notes."))
    if decision == "Passed":
        if doc.status != "Under Review":
            frappe.throw(_("Start quality review before passing the exercise."))
        _check_pass(doc)
    doc.review_notes, doc.result = notes.strip(), decision
    doc.reviewed_by, doc.reviewed_at = frappe.session.user, now_datetime()
    doc.status = "Closed"
    _save_action(doc, "review")
    return dict(name=doc.name, result=doc.result)
