import importlib
import json
from pathlib import Path

from frappe.tests.utils import FrappeTestCase


PACKAGE_ROOT = Path(__file__).resolve().parents[1]

PATCH_PATH = (
    PACKAGE_ROOT
    / "patches"
    / "2026_09_13_cleanup_legacy_product_proposal_report_settings.py"
)

SERVICE_PATH = (
    PACKAGE_ROOT
    / "services"
    / "item_uom.py"
)


class TestRNDFinalization(FrappeTestCase):

    def test_cleanup_patch_removes_only_legacy_report_settings(self):
        self.assertTrue(
            PATCH_PATH.exists(),
            "Legacy Product Proposal Report cleanup patch is missing",
        )

        module = importlib.import_module(
            "taj_core.patches."
            "2026_09_13_cleanup_legacy_product_proposal_report_settings"
        )

        original = {
            "last_view": "List",
            "List": {
                "filters": [],
                "sort_by": "modified",
            },
            "GridView": {
                "Product Proposal Raw Material": [
                    {"fieldname": "item_code", "columns": 1}
                ]
            },
            "Report": {
                "fields": [
                    ["name", "Product Proposal"],
                    [
                        "planned_cooking_qty",
                        "Product Proposal Trial Cooking",
                    ],
                ],
                "filters": [
                    [
                        "Product Proposal Trial Cooking",
                        "planned_cooking_qty",
                        "is",
                        "set",
                        False,
                    ]
                ],
            },
        }

        cleaned, changed = module.clean_user_settings(
            json.dumps(original)
        )

        self.assertTrue(changed)

        result = json.loads(cleaned)

        self.assertNotIn("Report", result)
        self.assertEqual(
            result["List"],
            original["List"],
        )
        self.assertEqual(
            result["GridView"],
            original["GridView"],
        )

    def test_uom_validation_message_mentions_global_conversion(self):
        source = SERVICE_PATH.read_text()

        self.assertIn(
            "same-category UOM Conversion Factor",
            source,
        )
