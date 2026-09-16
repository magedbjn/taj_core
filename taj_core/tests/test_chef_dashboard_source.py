import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_DIR = ROOT / "rnd/page/chef_dashboard"


class TestChefDashboardSource(unittest.TestCase):
    def test_page_metadata_exists_with_management_roles(self):
        page_json = PAGE_DIR / "chef_dashboard.json"
        self.assertTrue(page_json.exists(), "Chef Dashboard Page JSON must exist")
        data = json.loads(page_json.read_text())
        self.assertEqual(data["name"], "chef-dashboard")
        self.assertEqual(data["page_name"], "chef-dashboard")
        self.assertEqual(data["title"], "Chef Dashboard")
        self.assertEqual(data["module"], "RND")
        self.assertEqual(data["standard"], "Yes")
        roles = {row["role"] for row in data.get("roles", [])}
        self.assertEqual(roles, {"System Manager", "RND Manager"})

    def test_server_endpoint_is_permission_aware_and_uses_metrics_service(self):
        py_path = PAGE_DIR / "chef_dashboard.py"
        self.assertTrue(py_path.exists(), "Chef Dashboard server controller must exist")
        source = py_path.read_text()
        self.assertIn("@frappe.whitelist()", source)
        self.assertIn("def get_dashboard_data(", source)
        self.assertIn('frappe.has_permission("Product Proposal Trial", "read")', source)
        self.assertIn('frappe.get_list(\n        "Product Proposal Trial"', source)
        self.assertIn('"parent": ["in", trial_names]', source)
        self.assertIn("build_dashboard_metrics(", source)

    def test_server_defaults_to_current_month_and_validates_date_order(self):
        source = (PAGE_DIR / "chef_dashboard.py").read_text() if (PAGE_DIR / "chef_dashboard.py").exists() else ""
        self.assertIn("get_first_day(today_date)", source)
        self.assertIn('"approved_on"', source)
        self.assertIn("if from_date > to_date:", source)
        self.assertIn("From Date cannot be after To Date", source)

    def test_client_page_has_required_filters_kpis_charts_and_details(self):
        js_path = PAGE_DIR / "chef_dashboard.js"
        self.assertTrue(js_path.exists(), "Chef Dashboard client script must exist")
        source = js_path.read_text()
        for fieldname in ("from_date", "to_date", "trial_user", "product_proposal", "status"):
            self.assertIn(f'fieldname: "{fieldname}"', source)
        self.assertIn("frappe.datetime.month_start()", source)
        self.assertIn("frappe.datetime.get_today()", source)
        self.assertIn("get_dashboard_data", source)
        for key in (
            "products_worked_on",
            "trials",
            "cooking_runs",
            "final_approved",
            "under_development",
            "avg_trials_to_approval",
            "avg_days_to_approval",
        ):
            self.assertIn(key, source)
        for chart_id in (
            "trials-by-developer",
            "approved-by-developer",
            "development-activity",
            "product-status",
            "trials-by-product",
            "runs-by-developer",
            "approved-over-time",
            "trials-to-approval",
        ):
            self.assertIn(chart_id, source)
        self.assertIn("new frappe.Chart", source)
        self.assertIn("activity-details", source)
        self.assertIn("Approval Date", source)
        self.assertIn("row.approved_on", source)
        self.assertIn('frappe.set_route("Form", "Product Proposal Trial"', source)
        self.assertIn('frappe.set_route("Form", "Product Proposal"', source)

    def test_workspace_links_to_chef_dashboard(self):
        workspace_path = ROOT / "rnd/workspace/r&d/r&d.json"
        data = json.loads(workspace_path.read_text())
        links = data.get("links", [])
        chef_links = [row for row in links if row.get("label") == "Chef Dashboard"]
        self.assertEqual(len(chef_links), 1)
        chef = chef_links[0]
        self.assertEqual(chef.get("link_to"), "chef-dashboard")
        self.assertEqual(chef.get("link_type"), "Page")

        card = next(
            row
            for row in links
            if row.get("type") == "Card Break" and row.get("label") == "Product Proposal Trial"
        )
        self.assertEqual(card.get("link_count"), 6)


if __name__ == "__main__":
    unittest.main()
