import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRINT_FORMAT = (
    ROOT
    / "rnd/print_format/product_proposal_trial_latest_run"
    / "product_proposal_trial_latest_run.json"
)
TRIAL_PY = ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.py"
TRIAL_JS = ROOT / "rnd/doctype/product_proposal_trial/product_proposal_trial.js"
LEGACY_TEMPLATE = ROOT / "rnd/templates/trial_run_cooking_sheet.html"


class TestRNDTrialLatestRunPrintFormatSource(unittest.TestCase):
    def test_standard_print_format_exists_for_product_proposal_trial(self):
        self.assertTrue(PRINT_FORMAT.exists())
        data = json.loads(PRINT_FORMAT.read_text())
        self.assertEqual(data["doc_type"], "Product Proposal Trial")
        self.assertEqual(data["name"], "Product Proposal Trial - Latest Run")
        self.assertEqual(data["custom_format"], 1)
        self.assertEqual(data["standard"], "Yes")
        self.assertEqual(data["print_format_type"], "Jinja")

    def test_print_format_uses_latest_run_and_orders_sections(self):
        data = json.loads(PRINT_FORMAT.read_text())
        html = data["html"]
        css = data["css"]

        self.assertIn("doc.get_latest_run_cooking_sheet()", html)
        self.assertLess(html.index("Solid / Liquid"), html.index("Materials"))
        self.assertIn("print-header", html)
        self.assertIn("table-bordered", html)
        self.assertIn("print-header", css)
        self.assertIn("page-break-inside: avoid", css)

    def test_latest_run_helper_is_exposed_on_trial_document(self):
        source = TRIAL_PY.read_text()
        self.assertIn("def get_latest_run_cooking_sheet(self):", source)
        self.assertIn("max(", source)
        self.assertIn("row.run_no", source)
        self.assertIn("get_trial_run_cooking_sheet(", source)

    def test_existing_run_specific_print_is_preserved(self):
        source = TRIAL_JS.read_text()
        self.assertIn("Print Cooking Sheet", source)
        self.assertIn("run_no: values.run_no", source)

    def test_legacy_cooking_sheet_also_places_solid_liquid_before_materials(self):
        html = LEGACY_TEMPLATE.read_text()
        self.assertLess(html.index("Solid / Liquid"), html.index("Materials"))


if __name__ == "__main__":
    unittest.main()
