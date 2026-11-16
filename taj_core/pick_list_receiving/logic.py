"""Pure, dependency-free rules for Taj Pick List Receiving (read-only release).

This module intentionally imports no Frappe modules. It can be tested offline.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit


PICK_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,139}$")
PAGE_PATH = "/app/pick-list-receiving"


class ReceivingRuleError(ValueError):
    pass


def _validate_code(text: str) -> str:
    value = text.strip()
    if not PICK_CODE.fullmatch(value) or value in {".", ".."}:
        raise ReceivingRuleError("Invalid Pick List identifier")
    return value


def parse_scan(raw: str, origin: str) -> str:
    """Accept a local Pick List Receiving QR URL or a plain Pick List number.

    Reject external links and alternate page paths. Never follow a scanned URL.
    """
    if not isinstance(raw, str) or not isinstance(origin, str):
        raise ReceivingRuleError("Invalid QR input")
    candidate = raw.strip()
    if not candidate or len(candidate) > 2048:
        raise ReceivingRuleError("Invalid QR input")
    if "://" not in candidate:
        return _validate_code(candidate)

    code_url = urlsplit(candidate)
    local = urlsplit(origin)
    if code_url.scheme not in {"http", "https"} or not local.scheme:
        raise ReceivingRuleError("Unsupported QR URL")
    if (code_url.scheme.lower(), code_url.netloc.lower()) != (local.scheme.lower(), local.netloc.lower()):
        raise ReceivingRuleError("The QR code belongs to a different site")
    if code_url.path.rstrip("/") != PAGE_PATH or code_url.fragment or code_url.username or code_url.password:
        raise ReceivingRuleError("The QR code does not point to Pick List Receiving")
    query = parse_qs(code_url.query, keep_blank_values=True)
    if set(query) != {"pl"} or len(query["pl"]) != 1:
        raise ReceivingRuleError("Invalid Pick List link")
    return _validate_code(query["pl"][0])


def fingerprint(snapshot: dict) -> str:
    value = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_rows(expected_rows: list[dict], confirmations: list[dict]) -> None:
    """Confirm each mapped row; quantities come ONLY from ERPNext on the server.

    No client-supplied quantity is allowed. Even duplicate item codes are
    separate rows. This is a review gate, not proof of physical inspection.
    """
    if not isinstance(confirmations, list):
        raise ReceivingRuleError("Received items must be a list")
    expected_ids = [str(r["row_id"]) for r in expected_rows]
    if not expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise ReceivingRuleError("Each transfer row must have a unique Pick List row")
    if len(expected_ids) != len(confirmations):
        raise ReceivingRuleError("Confirm every Pick List row before continuing")

    by_id = {}
    for row in confirmations:
        if not isinstance(row, dict) or not isinstance(row.get("row_id"), str):
            raise ReceivingRuleError("Invalid confirmation row")
        if row["row_id"] in by_id:
            raise ReceivingRuleError("Repeated confirmation row")
        if set(row) != {"row_id", "checked"}:
            raise ReceivingRuleError("Only row ID and Confirmed are allowed")
        by_id[row["row_id"]] = row
    if set(expected_ids) != set(by_id):
        raise ReceivingRuleError("Confirmation rows do not match the Pick List")
    for expected in expected_rows:
        check = by_id[str(expected["row_id"])]
        if check.get("checked") is not True:
            raise ReceivingRuleError("Confirm every item before continuing")


def summarize_reviews(reviews: list[dict]) -> dict:
    return {"count": len(reviews), "verified": sum(bool(x.get("verified")) for x in reviews)}
