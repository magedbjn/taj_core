import json
from pathlib import Path
import unittest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class SensoryRatingWebFormRegressionTest(unittest.TestCase):
    def test_evaluation_date_does_not_use_literal_today_doctype_default(self):
        path = PACKAGE_ROOT / "rnd" / "doctype" / "sensory_feedback" / "sensory_feedback.json"
        data = json.loads(path.read_text())
        fields = {field["fieldname"]: field for field in data["fields"]}

        self.assertNotEqual(fields["evaluation_date"].get("default"), "Today")

    def test_evaluation_date_is_server_managed_not_web_form_managed(self):
        json_path = PACKAGE_ROOT / "rnd" / "web_form" / "sensory_rating" / "sensory_rating.json"
        js_path = PACKAGE_ROOT / "rnd" / "web_form" / "sensory_rating" / "sensory_rating.js"
        py_path = PACKAGE_ROOT / "rnd" / "doctype" / "sensory_feedback" / "sensory_feedback.py"

        data = json.loads(json_path.read_text())
        fieldnames = [field.get("fieldname") for field in data["web_form_fields"]]
        self.assertNotIn("evaluation_date", fieldnames)
        self.assertNotIn("set_value('evaluation_date'", js_path.read_text())

        source = py_path.read_text()
        self.assertIn("self.set_evaluation_date_default()", source)
        self.assertIn("self.evaluation_date = today()", source)

    def test_web_form_explains_when_no_trials_are_open(self):
        path = PACKAGE_ROOT / "rnd" / "web_form" / "sensory_rating" / "sensory_rating.js"
        source = path.read_text()

        self.assertIn("No Trials are currently open for Sensory Rating.", source)


if __name__ == "__main__":
    unittest.main()
