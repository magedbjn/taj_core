"""Read-only v16 stock distribution and linked-return snapshot evidence.

Modern movements are identified by bundle and actual batch; legacy movements
by SLE name. A bundle is counted once even when multiple ledger rows reference
it. Product Bundle components therefore need no join to their non-stock parent
sales row. No quantities from invoice/delivery item tables are inferred.
"""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json

import frappe
from frappe import _


MAX_ROWS = 1800
MAX_CONTEXTS = 1800
MAX_MOVEMENTS = 18000
MAX_SOURCE_NOTES_BYTES = 60000
VOUCHER_TYPES = ("Delivery Note", "Sales Invoice")


def collect_distribution(batch_pairs, unbatched_outputs, company, as_of):
    """Return unverified gross, returned and net quantities in Item Stock UOM.

    ``batch_pairs`` contains (item_code, batch_no). ``unbatched_outputs`` contains
    item_code/reference_name/posting_datetime dictionaries for manufactured or
    repacked outputs whose output batch is absent. Their scope is deliberately
    broad: every later actual issue of that item/company through ``as_of``.
    Exact batch evidence takes precedence over overlapping candidate evidence.

    The caller checks trace-source documents separately. This reader enforces
    document read permissions on all Items, Batches, dispatches and linked actual
    returns used in its result. It never hides inaccessible rows or truncates a
    snapshot when a bound is reached.
    """
    if not company:
        frappe.throw(_("A company is required for distribution evidence."))
    cutoff = _datetime(as_of)
    pairs, candidates = _contexts(batch_pairs, unbatched_outputs, cutoff)
    if not pairs and not candidates:
        return []

    sources = _Sources()
    for item, batch in sorted(pairs):
        sources.item(item)
        sources.batch(item, batch)
    for item in sorted(candidates):
        sources.item(item)

    reader = _MovementReader(company, cutoff)
    movements = []
    for voucher_type in VOUCHER_TYPES:
        for modern in (True, False):
            params = {}
            scope = _dispatch_scope(pairs, candidates, modern, params)
            movements.extend(reader.read(voucher_type, modern, False, scope, params))

    # Aggregate physical issues before formatting display rows. The actual batch
    # remains in this internal key even when the displayed candidate has none.
    issues = {}
    for movement in movements:
        item, batch = movement["item_code"], movement["batch_no"] or ""
        if (item, batch) in pairs:
            evidence_type = "Batch"
        elif item in candidates and _datetime(movement["posting_datetime"]) >= candidates[item]["since"]:
            evidence_type = "Item Candidate"
        else:
            continue
        sources.item(item)
        if batch:
            sources.batch(item, batch)
        sources.document(movement["voucher_type"], movement["voucher_no"])
        key = (movement["voucher_type"], movement["voucher_no"], item, batch)
        if key not in issues:
            issues[key] = {
                "customer": movement["customer"], "evidence_type": evidence_type,
                "qty": Decimal(0), "returned_qty": Decimal(0), "return_vouchers": set(),
            }
        issues[key]["qty"] += _quantity(movement["qty"])

    if not issues:
        return []

    for voucher_type in VOUCHER_TYPES:
        originals = {key[1] for key in issues if key[0] == voucher_type}
        if not originals:
            continue
        items = {key[2] for key in issues if key[0] == voucher_type}
        for modern in (True, False):
            params = {}
            alias = "sb" if modern else "sle"
            scope = "{0}.item_code IN ({1}) AND v.return_against IN ({2})".format(
                alias, _parameters("return_item", items, params),
                _parameters("original", originals, params),
            )
            for movement in reader.read(voucher_type, modern, True, scope, params):
                key = (voucher_type, movement["return_against"], movement["item_code"], movement["batch_no"] or "")
                if key not in issues:
                    continue
                sources.document(voucher_type, movement["voucher_no"])
                issues[key]["returned_qty"] += _quantity(movement["qty"])
                issues[key]["return_vouchers"].add(movement["voucher_no"])

    grouped = {}
    for (voucher_type, voucher_no, item, batch), issue in sorted(issues.items()):
        if issue["returned_qty"] > issue["qty"]:
            frappe.throw(_("Linked stock returns exceed the dispatched quantity for {0}, item {1}, batch {2}.").format(voucher_no, item, batch))
        evidence_type = issue["evidence_type"]
        visible_batch = batch if evidence_type == "Batch" else ""
        key = (voucher_type, voucher_no, item, evidence_type, visible_batch)
        if key not in grouped:
            grouped[key] = {
                "customer": issue["customer"], "voucher_type": voucher_type,
                "voucher_no": voucher_no, "item_code": item, "batch_no": visible_batch,
                "uom": sources.item(item).get("stock_uom"),
                "qty": Decimal(0), "returned_qty": Decimal(0),
                "evidence_type": evidence_type, "verification": "Unverified",
                "return_vouchers": set(),
            }
        grouped[key]["qty"] += issue["qty"]
        grouped[key]["returned_qty"] += issue["returned_qty"]
        grouped[key]["return_vouchers"].update(issue["return_vouchers"])
        if len(grouped) > MAX_ROWS:
            _limit_error()

    result = []
    for key, row in sorted(grouped.items()):
        item = row["item_code"]
        if row["evidence_type"] == "Batch":
            notes = _("Submitted batch stock movement. Quantities are in the item stock UOM.")
        else:
            candidate = candidates[item]
            notes = _(
                "No manufacturing output batch is recorded. Item/date candidate scope: "
                "all actual stock dispatches of {0} in {1} from {2} through {3}. "
                "Manufacturing references: {4}. This does not establish batch genealogy."
            ).format(item, company, candidate["since"], cutoff, ", ".join(sorted(candidate["references"])))
        returned = row.pop("return_vouchers")
        row["return_references"] = json.dumps(sorted(returned), ensure_ascii=False)
        if returned:
            notes += " " + _("Submitted inward returns linked to the original voucher: {0}.").format(
                ", ".join(sorted(returned))
            )
        if len(notes.encode("utf-8")) > MAX_SOURCE_NOTES_BYTES:
            _limit_error()
        row["source_notes"] = notes
        row["net_qty"] = float(row["qty"] - row["returned_qty"])
        row["qty"] = float(row["qty"])
        row["returned_qty"] = float(row["returned_qty"])
        result.append(row)
    return result


def _datetime(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        if parsed.tzinfo is not None:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        frappe.throw(_("A valid site-local posting datetime is required for distribution evidence."))


def _quantity(value):
    try:
        quantity = Decimal(str(value))
        if not quantity.is_finite() or quantity <= 0:
            raise InvalidOperation
        return quantity
    except (InvalidOperation, TypeError, ValueError):
        frappe.throw(_("Distribution stock movement quantities must be positive finite values."))


def _contexts(batch_pairs, unbatched_outputs, cutoff):
    pairs, candidates = set(), {}
    count = 0
    for pair in batch_pairs:
        count += 1
        if count > MAX_CONTEXTS:
            _limit_error()
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or not all(isinstance(value, str) and value for value in pair):
            frappe.throw(_("Each distribution batch selection requires an item and batch."))
        pairs.add(tuple(pair))
    for output in unbatched_outputs:
        count += 1
        if count > MAX_CONTEXTS:
            _limit_error()
        if not isinstance(output, dict) or not output.get("item_code") or not output.get("reference_name"):
            frappe.throw(_("An unbatched manufacturing output requires an item and source reference."))
        since = _datetime(output.get("posting_datetime"))
        if since > cutoff:
            frappe.throw(_("A manufacturing output cannot be later than the distribution snapshot."))
        item = output["item_code"]
        candidate = candidates.setdefault(item, {"since": since, "references": set()})
        candidate["since"] = min(candidate["since"], since)
        candidate["references"].add(output["reference_name"])
    return pairs, candidates


def _parameters(prefix, values, params):
    placeholders = []
    for index, value in enumerate(sorted(values)):
        name = "{0}_{1}".format(prefix, index)
        params[name] = value
        placeholders.append("%({0})s".format(name))
    return ", ".join(placeholders)


def _dispatch_scope(pairs, candidates, modern, params):
    batches = defaultdict(set)
    for item, batch in pairs:
        batches[item].add(batch)
    alias = "sb" if modern else "sle"
    batch_field = "sabe.batch_no" if modern else "sle.batch_no"
    scopes = []
    for index, item in enumerate(sorted(set(batches) | set(candidates))):
        params["item_{0}".format(index)] = item
        alternatives = []
        if item in batches:
            alternatives.append("IFNULL({0}, '') IN ({1})".format(
                batch_field, _parameters("batch_{0}".format(index), batches[item], params)
            ))
        if item in candidates:
            params["since_{0}".format(index)] = candidates[item]["since"].isoformat(sep=" ")
            alternatives.append("{0}.posting_datetime >= %(since_{1})s".format(alias, index))
        scopes.append("({0}.item_code = %(item_{1})s AND ({2}))".format(alias, index, " OR ".join(alternatives)))
    return "(" + " OR ".join(scopes) + ")"


def _limit_error():
    frappe.throw(_("Distribution evidence limit exceeded. Narrow the recall scope before continuing."))


class _Sources:
    def __init__(self):
        self.documents = {}

    def document(self, doctype, name):
        key = (doctype, name)
        if key not in self.documents:
            doc = frappe.get_doc(doctype, name)
            doc.check_permission("read")
            self.documents[key] = doc
        return self.documents[key]

    def item(self, name):
        item = self.document("Item", name)
        if not item.get("stock_uom"):
            frappe.throw(_("Stock UOM is missing for item {0}.").format(name))
        return item

    def batch(self, item, name):
        batch = self.document("Batch", name)
        if batch.get("item") != item:
            frappe.throw(_("Distribution batch {0} does not belong to item {1}.").format(name, item))
        return batch


class _MovementReader:
    def __init__(self, company, cutoff):
        self.company = company
        self.cutoff = cutoff
        self.count = 0

    def read(self, voucher_type, modern, returns, scope, scope_params):
        # This identifier is selected from a fixed tuple, never caller input.
        if voucher_type not in VOUCHER_TYPES:
            raise ValueError("Unsupported distribution voucher type")
        header = "`tab{0}`".format(voucher_type)
        params = {
            **scope_params, "company": self.company,
            "as_of": self.cutoff.isoformat(sep=" "),
            "as_of_date": self.cutoff.date().isoformat(),
            "as_of_time": self.cutoff.time().isoformat(),
            "voucher_type": voucher_type, "is_return": int(returns),
            "transaction": "Inward" if returns else "Outward",
            "row_limit": MAX_MOVEMENTS + 1,
        }
        sign = ">" if returns else "<"
        invoice_condition = "AND v.update_stock = 1" if voucher_type == "Sales Invoice" else ""
        header_condition = """
            v.docstatus = 1 AND IFNULL(v.is_return, 0) = %(is_return)s
            AND v.company = %(company)s
            AND (v.posting_date < %(as_of_date)s OR
                (v.posting_date = %(as_of_date)s
                 AND IFNULL(v.posting_time, '00:00:00') <= %(as_of_time)s))
        """
        if modern:
            quantity = "sabe.qty" if returns else "-sabe.qty"
            query = """
                SELECT sb.name AS movement_id, sb.voucher_type, sb.voucher_no,
                       v.customer, v.return_against, sb.item_code,
                       IFNULL(sabe.batch_no, '') AS batch_no,
                       sb.posting_datetime, SUM({quantity}) AS qty
                FROM `tabSerial and Batch Bundle` sb
                INNER JOIN `tabSerial and Batch Entry` sabe ON sabe.parent = sb.name
                INNER JOIN {header} v ON v.name = sb.voucher_no
                WHERE sb.voucher_type = %(voucher_type)s
                  AND sb.company = %(company)s
                  AND sb.docstatus = 1 AND sb.is_cancelled = 0
                  AND sb.type_of_transaction = %(transaction)s
                  AND sb.posting_datetime <= %(as_of)s
                  AND sabe.docstatus = 1 AND sabe.is_cancelled = 0
                  AND sabe.qty {sign} 0
                  AND {header_condition} {invoice_condition}
                  AND {scope}
                  AND EXISTS (
                      SELECT 1 FROM `tabStock Ledger Entry` sle
                      WHERE sle.serial_and_batch_bundle = sb.name
                        AND sle.voucher_type = sb.voucher_type
                        AND sle.voucher_no = sb.voucher_no
                        AND sle.item_code = sb.item_code
                        AND sle.company = %(company)s
                        AND sle.docstatus < 2 AND sle.is_cancelled = 0
                        AND sle.actual_qty {sign} 0
                        AND sle.posting_datetime <= %(as_of)s
                  )
                GROUP BY sb.name, sb.voucher_type, sb.voucher_no, v.customer,
                         v.return_against, sb.item_code, IFNULL(sabe.batch_no, ''),
                         sb.posting_datetime
                ORDER BY sb.name, batch_no
                LIMIT %(row_limit)s
            """.format(
                quantity=quantity, header=header, sign=sign,
                header_condition=header_condition, invoice_condition=invoice_condition,
                scope=scope,
            )
        else:
            quantity = "sle.actual_qty" if returns else "-sle.actual_qty"
            query = """
                SELECT sle.name AS movement_id, sle.voucher_type, sle.voucher_no,
                       v.customer, v.return_against, sle.item_code,
                       IFNULL(sle.batch_no, '') AS batch_no,
                       sle.posting_datetime, {quantity} AS qty
                FROM `tabStock Ledger Entry` sle
                INNER JOIN {header} v ON v.name = sle.voucher_no
                WHERE sle.voucher_type = %(voucher_type)s
                  AND sle.company = %(company)s
                  AND sle.docstatus < 2 AND sle.is_cancelled = 0
                  AND sle.actual_qty {sign} 0
                  AND IFNULL(sle.serial_and_batch_bundle, '') = ''
                  AND sle.posting_datetime <= %(as_of)s
                  AND {header_condition} {invoice_condition}
                  AND {scope}
                ORDER BY sle.name
                LIMIT %(row_limit)s
            """.format(
                quantity=quantity, header=header, sign=sign,
                header_condition=header_condition, invoice_condition=invoice_condition,
                scope=scope,
            )
        rows = frappe.db.sql(query, params, as_dict=True)
        self.count += len(rows)
        if self.count > MAX_MOVEMENTS:
            _limit_error()
        return rows
