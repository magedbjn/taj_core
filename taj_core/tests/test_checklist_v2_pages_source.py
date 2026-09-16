import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ROOT / "checklist"


class TestChecklistV2PagesSource(unittest.TestCase):
    def test_api_exposes_role_aware_today_and_manager_control_room(self):
        api = (CHECKLIST / "api.py").read_text(encoding="utf-8")
        self.assertIn("def get_checklist_today_data", api)
        self.assertIn("def get_checklist_control_room_data", api)
        self.assertIn("frappe.get_list", api)
        start = api.index("def get_checklist_control_room_data")
        control_source = api[start:]
        self.assertIn("_ensure_manager()", control_source)

    def test_checklist_today_page_is_role_aware_and_tablet_friendly(self):
        page_dir = CHECKLIST / "page" / "checklist_today"
        self.assertTrue((page_dir / "checklist_today.json").exists())
        self.assertTrue((page_dir / "checklist_today.js").exists())
        self.assertTrue((page_dir / "checklist_today.css").exists())

        page = json.loads((page_dir / "checklist_today.json").read_text(encoding="utf-8"))
        roles = {row["role"] for row in page["roles"]}
        self.assertTrue({"Employee", "Checklist Manager", "System Manager", "IT Manager"}.issubset(roles))

        js = (page_dir / "checklist_today.js").read_text(encoding="utf-8")
        css = (page_dir / "checklist_today.css").read_text(encoding="utf-8")
        self.assertIn("taj_core.checklist.api.get_checklist_today_data", js)
        for label in ("Today", "Team", "Issues", "History"):
            self.assertIn(label, js)
        self.assertIn("is_manager", js)
        self.assertIn("frappe.route_options", js)
        self.assertIn("checklist-user", js)
        self.assertIn("direct_open: 1", js)
        self.assertIn('origin: "checklist-today"', js)
        self.assertIn("format_checklist_delay", js)
        self.assertIn("checklist_scope_label", js)
        classic_user_js = (CHECKLIST / "page" / "checklist_user" / "checklist_user.js").read_text(encoding="utf-8")
        self.assertIn("checklist_answer", classic_user_js)
        self.assertIn("direct_open", classic_user_js)
        self.assertIn("checklist-direct-open-mode", classic_user_js)
        self.assertIn('frappe.set_route("checklist-today")', classic_user_js)
        self.assertIn('frappe.pages["checklist-user"].on_page_show', classic_user_js)
        self.assertIn('wrapper.checklist_user_page', classic_user_js)
        self.assertIn("@media", css)
        self.assertIn("min-height", css)


    def test_checklist_user_actions_are_outside_scrollable_question_body(self):
        js = (CHECKLIST / "page" / "checklist_user" / "checklist_user.js").read_text(encoding="utf-8")
        css = (CHECKLIST / "page" / "checklist_user" / "checklist_user.css").read_text(encoding="utf-8")

        expected_layout = (
            '<div class="selected-doc-body"></div>\n'
            '                    </div>\n'
            '                    <div class="selected-doc-actions"></div>'
        )
        self.assertIn(expected_layout, js)
        self.assertIn(".selected-doc-actions:empty", css)
        self.assertIn("flex: 0 0 auto", css)

    def test_control_room_page_is_manager_only_and_attention_focused(self):
        page_dir = CHECKLIST / "page" / "checklist_control_room"
        self.assertTrue((page_dir / "checklist_control_room.json").exists())
        self.assertTrue((page_dir / "checklist_control_room.js").exists())
        self.assertTrue((page_dir / "checklist_control_room.css").exists())

        page = json.loads((page_dir / "checklist_control_room.json").read_text(encoding="utf-8"))
        roles = {row["role"] for row in page["roles"]}
        self.assertEqual(roles, {"Checklist Manager", "System Manager", "IT Manager"})

        js = (page_dir / "checklist_control_room.js").read_text(encoding="utf-8")
        self.assertIn("taj_core.checklist.api.get_checklist_control_room_data", js)
        self.assertIn("Department Health", js)
        self.assertIn("Needs Attention", js)
        self.assertIn("department", js)

    def test_workspace_keeps_baseline_pages_and_adds_experimental_pages(self):
        workspace = json.loads(
            (CHECKLIST / "workspace" / "checklist" / "checklist.json").read_text(encoding="utf-8")
        )
        page_links = {
            row.get("link_to")
            for row in workspace.get("links", [])
            if row.get("link_type") == "Page"
        }
        self.assertIn("checklist-user", page_links)
        self.assertIn("checklist-admin", page_links)
        self.assertIn("checklist-today", page_links)
        self.assertIn("checklist-control-room", page_links)


if __name__ == "__main__":
    unittest.main()
