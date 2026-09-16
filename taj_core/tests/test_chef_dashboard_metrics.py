import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "rnd/services/chef_dashboard_metrics.py"


def load_build_dashboard_metrics(testcase):
    if not MODULE_PATH.exists():
        testcase.fail("chef_dashboard_metrics.py does not exist")
    spec = importlib.util.spec_from_file_location("chef_dashboard_metrics", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_dashboard_metrics


class TestChefDashboardMetrics(unittest.TestCase):
    def setUp(self):
        self.build_dashboard_metrics = load_build_dashboard_metrics(self)
        self.trials = [
            {
                "name": "SOUP-TRIAL-01",
                "product_proposal": "SOUP-01",
                "product_name": "Soup",
                "trial_no": 1,
                "trial_title": "Trial 1",
                "status": "Completed",
                "is_final_trial": 0,
                "posting_date": "2026-08-28",
                "trial_user": "chef.a@example.com",
            },
            {
                "name": "SOUP-TRIAL-02",
                "product_proposal": "SOUP-01",
                "product_name": "Soup",
                "trial_no": 2,
                "trial_title": "Trial 2",
                "status": "Approved",
                "is_final_trial": 1,
                "posting_date": "2026-08-30",
                "approved_on": "2026-09-05 10:30:00",
                "trial_user": "chef.a@example.com",
            },
            {
                "name": "PASTA-TRIAL-01",
                "product_proposal": "PASTA-01",
                "product_name": "Pasta",
                "trial_no": 1,
                "trial_title": "Trial 1",
                "status": "Draft",
                "is_final_trial": 0,
                "posting_date": "2026-09-07",
                "trial_user": "chef.b@example.com",
            },
            {
                "name": "RICE-TRIAL-01",
                "product_proposal": "RICE-01",
                "product_name": "Rice",
                "trial_no": 1,
                "trial_title": "Trial 1",
                "status": "Completed",
                "is_final_trial": 0,
                "posting_date": "2026-07-01",
                "trial_user": "chef.b@example.com",
            },
        ]
        self.runs = [
            {
                "parent": "SOUP-TRIAL-02",
                "run_no": 1,
                "run_date": "2026-09-06",
            },
            {
                "parent": "SOUP-TRIAL-02",
                "run_no": 2,
                "run_date": "2026-09-08",
            },
            {
                "parent": "PASTA-TRIAL-01",
                "run_no": 1,
                "run_date": "2026-09-08",
            },
            {
                "parent": "RICE-TRIAL-01",
                "run_no": 1,
                "run_date": "2026-09-10",
            },
        ]

    def test_current_period_metrics_include_trial_and_run_activity(self):
        result = self.build_dashboard_metrics(
            self.trials,
            self.runs,
            "2026-09-01",
            "2026-09-30",
        )

        self.assertEqual(result["kpis"]["products_worked_on"], 3)
        self.assertEqual(result["kpis"]["trials"], 1)
        self.assertEqual(result["kpis"]["cooking_runs"], 4)
        self.assertEqual(result["kpis"]["final_approved"], 1)
        self.assertEqual(result["kpis"]["under_development"], 2)
        self.assertEqual(result["kpis"]["avg_trials_to_approval"], 2.0)
        self.assertEqual(result["kpis"]["avg_days_to_approval"], 8.0)
        details = {row["trial"]: row for row in result["details"]}
        self.assertIn("SOUP-TRIAL-02", details)
        self.assertEqual(details["SOUP-TRIAL-02"]["approved_on"], "2026-09-05")

    def test_developer_filter_applies_to_activity_but_keeps_full_history_for_approval(self):
        result = self.build_dashboard_metrics(
            self.trials,
            self.runs,
            "2026-09-01",
            "2026-09-30",
            trial_user="chef.a@example.com",
        )

        self.assertEqual(result["kpis"]["products_worked_on"], 1)
        self.assertEqual(result["kpis"]["trials"], 0)
        self.assertEqual(result["kpis"]["cooking_runs"], 2)
        self.assertEqual(result["kpis"]["final_approved"], 1)
        self.assertEqual(result["kpis"]["avg_trials_to_approval"], 2.0)
        self.assertEqual(result["kpis"]["avg_days_to_approval"], 8.0)

    def test_run_on_old_trial_counts_as_product_activity_and_detail_row(self):
        result = self.build_dashboard_metrics(
            self.trials,
            self.runs,
            "2026-09-01",
            "2026-09-30",
            trial_user="chef.b@example.com",
        )

        self.assertEqual(result["kpis"]["products_worked_on"], 2)
        detail = {row["trial"]: row for row in result["details"]}
        self.assertIn("RICE-TRIAL-01", detail)
        self.assertEqual(detail["RICE-TRIAL-01"]["cooking_runs_in_period"], 1)
        self.assertEqual(detail["RICE-TRIAL-01"]["latest_run_date"], "2026-09-10")

    def test_charts_group_by_developer_product_status_and_activity_period(self):
        result = self.build_dashboard_metrics(
            self.trials,
            self.runs,
            "2026-09-01",
            "2026-09-30",
        )
        charts = result["charts"]

        self.assertEqual(
            charts["trials_by_developer"],
            [
                {"label": "chef.b@example.com", "value": 1},
            ],
        )
        self.assertEqual(
            charts["cooking_runs_by_developer"],
            [
                {"label": "chef.a@example.com", "value": 2},
                {"label": "chef.b@example.com", "value": 2},
            ],
        )
        self.assertEqual(
            charts["product_status"],
            [
                {"label": "Approved", "value": 1},
                {"label": "Under Development", "value": 2},
            ],
        )
        self.assertEqual(charts["activity_granularity"], "day")
        periods = {row["period"]: row for row in charts["development_activity"]}
        self.assertEqual(periods["2026-09-05"]["final_approved"], 1)
        self.assertEqual(periods["2026-09-07"]["trials"], 1)

    def test_new_development_trial_keeps_product_under_development_even_with_old_final(self):
        trials = list(self.trials) + [
            {
                "name": "SOUP-TRIAL-03",
                "product_proposal": "SOUP-01",
                "product_name": "Soup",
                "trial_no": 3,
                "trial_title": "Trial 3",
                "status": "Draft",
                "is_final_trial": 0,
                "posting_date": "2026-09-20",
                "approved_on": None,
                "trial_user": "chef.a@example.com",
            }
        ]

        result = self.build_dashboard_metrics(
            trials,
            self.runs,
            "2026-09-01",
            "2026-09-30",
        )

        self.assertEqual(result["kpis"]["under_development"], 3)
        self.assertEqual(
            result["charts"]["product_status"],
            [
                {"label": "Approved", "value": 0},
                {"label": "Under Development", "value": 3},
            ],
        )

    def test_long_range_uses_month_granularity(self):
        result = self.build_dashboard_metrics(
            self.trials,
            self.runs,
            "2026-07-01",
            "2026-09-30",
        )
        self.assertEqual(result["charts"]["activity_granularity"], "month")
        periods = {row["period"]: row for row in result["charts"]["development_activity"]}
        self.assertEqual(periods["2026-09"]["trials"], 1)

    def test_status_and_product_filters_are_applied(self):
        result = self.build_dashboard_metrics(
            self.trials,
            self.runs,
            "2026-09-01",
            "2026-09-30",
            product_proposal="PASTA-01",
            status="Draft",
        )
        self.assertEqual(result["kpis"]["products_worked_on"], 1)
        self.assertEqual(result["kpis"]["trials"], 1)
        self.assertEqual(result["kpis"]["cooking_runs"], 1)
        self.assertEqual(result["kpis"]["final_approved"], 0)
        self.assertEqual(result["kpis"]["under_development"], 1)

    def test_trials_to_approval_uses_full_product_history(self):
        result = self.build_dashboard_metrics(
            self.trials,
            self.runs,
            "2026-09-01",
            "2026-09-30",
        )
        self.assertEqual(
            result["charts"]["trials_to_approval"],
            [{"label": "Soup", "value": 2, "product_proposal": "SOUP-01"}],
        )


if __name__ == "__main__":
    unittest.main()
