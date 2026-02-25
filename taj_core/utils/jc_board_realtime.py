from __future__ import annotations
import re
import frappe

EVENT_NAME = "job_card_board_update"
DOCTYPE_ROOM = "doctype: Job Card"


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
	if not frappe.db.has_column("Workstation", "plant_floor"):
		return ""
	return (frappe.db.get_value("Workstation", workstation, "plant_floor") or "").strip()


def _effective_pf(doc) -> str:
	# Job Card first, fallback Workstation.plant_floor
	jc_pf = (doc.get("taj_plant_floor") or "").strip() if frappe.db.has_column("Job Card", "taj_plant_floor") else ""
	if jc_pf:
		return jc_pf
	return _get_ws_plant_floor(doc.get("workstation"))


# def job_card_changed(doc, method=None):
# 	try:
# 		from taj_core.taj_core.page.job_card_board import job_card_board as board

# 		payload = board.get_card_payload(doc.name) or {"name": doc.name}
# 		payload["__event"] = EVENT_NAME

# 		# publish to plant floor room
# 		pf = _effective_pf(doc)
# 		pf_room = f"jc_board:pf:{_scrub(pf)}" if pf else None
# 		if pf_room:
# 			frappe.publish_realtime(EVENT_NAME, payload, room=pf_room, after_commit=True)

# 		# fallback: doctype room (for screens without plant floor filter)
# 		frappe.publish_realtime(EVENT_NAME, payload, room=DOCTYPE_ROOM, after_commit=True)

# 		# if plant floor changed, tell old room to remove this card
# 		before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
# 		if before:
# 			old_pf = _effective_pf(before)
# 			old_room = f"jc_board:pf:{_scrub(old_pf)}" if old_pf else None
# 			if old_room and old_room != pf_room:
# 				frappe.publish_realtime(
# 					EVENT_NAME,
# 					{"name": doc.name, "__action": "remove"},
# 					room=old_room,
# 					after_commit=True,
# 				)

# 	except Exception:
# 		frappe.log_error(title="Job Card Board realtime publish failed", message=frappe.get_traceback())

def job_card_changed(doc, method=None):
	try:
		from taj_core.taj_core.page.job_card_board import job_card_board as board

		payload = board.get_card_payload(doc.name) or {"name": doc.name}
		payload["__event"] = EVENT_NAME

		# ✅ publish to this specific document room
		doc_room = f"doc:Job Card/{doc.name}"
		frappe.publish_realtime(EVENT_NAME, payload, room=doc_room, after_commit=True)
		frappe.publish_realtime(event=EVENT_NAME,message=payload,room="doctype: Job Card",after_commit=True,)
		# (اختياري) publish to doctype room فقط للـ inserts/new discovery
		# frappe.publish_realtime(EVENT_NAME, payload, room="doctype: Job Card", after_commit=True)

	except Exception:
		frappe.log_error("Job Card Board realtime publish failed", frappe.get_traceback())