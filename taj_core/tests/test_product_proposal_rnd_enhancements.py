import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from taj_core.rnd.doctype.product_proposal.product_proposal import ProductProposal
from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
    ProductProposalTrial,
    _is_sensory_window_active,
)
from taj_core.rnd.doctype.sensory_feedback.sensory_feedback import SensoryFeedback


def _load_app_json(*parts):
    path = Path(frappe.get_app_path("taj_core", *parts))
    return json.loads(path.read_text())


class TestProductProposalRNDEnhancements(unittest.TestCase):
    def test_customer_sample_token_is_generated_once(self):
        row = frappe._dict(evaluation_token="")
        fake = SimpleNamespace(customer_samples=[row])
        fake.get = lambda fieldname: getattr(fake, fieldname, None)

        ProductProposal.set_customer_sample_tokens(fake)
        first = row.evaluation_token

        self.assertTrue(first)

        ProductProposal.set_customer_sample_tokens(fake)
        self.assertEqual(row.evaluation_token, first)

    def test_customer_sample_trial_must_belong_to_parent(self):
        row = frappe._dict(
            {
                "customer": "CUST-1",
                "trial_document": "TRIAL-OTHER",
                "sample_qty": 1,
                "uom": "Nos",
            }
        )
        fake = SimpleNamespace(
            name="PP-1",
            customer_samples=[row],
        )
        fake.get = lambda fieldname: getattr(fake, fieldname, None)

        module = "taj_core.rnd.doctype.product_proposal.product_proposal"

        with patch(
            f"{module}.frappe.db.get_value",
            return_value="PP-2",
        ):
            with self.assertRaises(frappe.ValidationError):
                ProductProposal.validate_customer_samples(fake)

    def test_customer_sample_run_must_belong_to_selected_trial(self):
        row = frappe._dict(
            customer="CUST-1",
            trial_document="TRIAL-1",
            trial_run_no=2,
            sample_qty=1,
            uom="Nos",
        )
        fake = SimpleNamespace(name="PP-1", customer_samples=[row])
        fake.get = lambda fieldname: getattr(fake, fieldname, None)
        module = "taj_core.rnd.doctype.product_proposal.product_proposal"

        with patch(f"{module}.frappe.db.get_value", return_value="PP-1"), patch(
            f"{module}.frappe.db.exists", return_value=False
        ):
            with self.assertRaises(frappe.ValidationError):
                ProductProposal.validate_customer_samples(fake)

    def test_customer_sample_qty_must_be_positive(self):
        row = frappe._dict(
            {
                "customer": "CUST-1",
                "trial_document": "TRIAL-1",
                "sample_qty": 0,
                "uom": "Nos",
            }
        )
        fake = SimpleNamespace(
            name="PP-1",
            customer_samples=[row],
        )
        fake.get = lambda fieldname: getattr(fake, fieldname, None)

        with self.assertRaises(frappe.ValidationError):
            ProductProposal.validate_customer_samples(fake)

    def test_customer_sample_fields_can_be_updated_after_submit(self):
        data = _load_app_json(
            "rnd",
            "doctype",
            "product_proposal_sample",
            "product_proposal_sample.json",
        )
        fields = {row["fieldname"]: row for row in data["fields"]}

        for fieldname in (
            "customer",
            "trial_document",
            "sample_date",
            "sample_qty",
            "uom",
            "interest_status",
            "notes",
        ):
            self.assertEqual(fields[fieldname].get("allow_on_submit"), 1)

    def test_sample_token_context_overrides_forged_feedback_values(self):
        fake = frappe._dict(
            {
                "sample_token": "secure-token",
                "item": "FORGED-PP",
                "trial_document": "FORGED-TRIAL",
                "customer": "FORGED-CUSTOMER",
                "your_name": "FORGED NAME",
            }
        )

        context = frappe._dict(
            {
                "product_proposal": "PP-1",
                "trial_document": "PP-1-TRIAL-01",
                "customer": "CUST-1",
                "customer_name": "Customer One",
            }
        )

        resolver = (
            "taj_core.rnd.web_form.sensory_rating.sensory_rating."
            "resolve_sample_evaluation_context"
        )

        with patch(resolver, return_value=context):
            SensoryFeedback.apply_sample_context(fake)

        self.assertEqual(fake.item, "PP-1")
        self.assertEqual(fake.trial_document, "PP-1-TRIAL-01")
        self.assertEqual(fake.customer, "CUST-1")
        self.assertEqual(fake.your_name, "Customer One")

    def test_sample_token_context_is_not_applied_without_token(self):
        fake = frappe._dict(
            {
                "sample_token": "",
                "item": "PP-1",
                "trial_document": "PP-1-TRIAL-01",
                "customer": None,
            }
        )

        SensoryFeedback.apply_sample_context(fake)

        self.assertEqual(fake.item, "PP-1")
        self.assertEqual(fake.trial_document, "PP-1-TRIAL-01")

    def test_sensory_feedback_normalizes_literal_today(self):
        fake = frappe._dict(evaluation_date="Today")
        module = "taj_core.rnd.doctype.sensory_feedback.sensory_feedback"

        with patch(f"{module}.today", return_value="2026-09-09"):
            SensoryFeedback.set_evaluation_date_default(fake)

        self.assertEqual(fake.evaluation_date, "2026-09-09")

    def test_sensory_defaults_to_three_month_window(self):
        fake = frappe._dict(
            {
                "enable_sensory_rating": 1,
                "sensory_from_date": None,
                "sensory_until_date": None,
            }
        )

        module = (
            "taj_core.rnd.doctype.product_proposal_trial."
            "product_proposal_trial"
        )

        with patch(f"{module}.today", return_value="2026-09-08"):
            ProductProposalTrial.set_sensory_availability_defaults(fake)

        self.assertEqual(
            frappe.utils.getdate(fake.sensory_from_date),
            frappe.utils.getdate("2026-09-08"),
        )
        self.assertEqual(
            frappe.utils.getdate(fake.sensory_until_date),
            frappe.utils.getdate("2026-12-08"),
        )

    def test_sensory_until_cannot_precede_from(self):
        fake = frappe._dict(
            {
                "enable_sensory_rating": 1,
                "sensory_from_date": "2026-09-10",
                "sensory_until_date": "2026-09-09",
            }
        )

        with self.assertRaises(frappe.ValidationError):
            ProductProposalTrial.validate_sensory_availability(fake)

    def test_sensory_window_active_only_inside_enabled_period(self):
        self.assertTrue(
            _is_sensory_window_active(
                1,
                "2026-09-01",
                "2026-09-30",
                "2026-09-08",
            )
        )
        self.assertFalse(
            _is_sensory_window_active(
                0,
                "2026-09-01",
                "2026-09-30",
                "2026-09-08",
            )
        )
        self.assertFalse(
            _is_sensory_window_active(
                1,
                "2026-10-01",
                "2026-12-31",
                "2026-09-08",
            )
        )
        self.assertFalse(
            _is_sensory_window_active(
                1,
                "2026-06-01",
                "2026-08-31",
                "2026-09-08",
            )
        )

    def test_sensory_web_form_uses_bounded_non_link_picker_fields(self):
        data = _load_app_json(
            "rnd",
            "web_form",
            "sensory_rating",
            "sensory_rating.json",
        )
        fields = {row["fieldname"]: row for row in data["web_form_fields"]}

        self.assertEqual(fields["trial_document"]["fieldtype"], "Select")
        self.assertNotIn("item", fields)
        self.assertEqual(fields["customer"]["fieldtype"], "Data")

    def test_cancelled_product_proposal_is_not_available_for_sensory(self):
        module = (
            "taj_core.rnd.web_form.sensory_rating.sensory_rating"
        )

        with patch(
            f"{module}.frappe.db.get_value",
            return_value=frappe._dict(
                product_name="Cancelled Product",
                docstatus=2,
            ),
        ):
            from taj_core.rnd.web_form.sensory_rating.sensory_rating import (
                _get_product_proposal_evaluation_context,
            )

            with self.assertRaises(frappe.ValidationError):
                _get_product_proposal_evaluation_context("PP-CANCELLED")

    def test_sensory_web_form_sample_path_hides_redundant_identity(self):
        js_path = Path(
            frappe.get_app_path(
                "taj_core",
                "rnd",
                "web_form",
                "sensory_rating",
                "sensory_rating.js",
            )
        )
        source = js_path.read_text()

        self.assertIn("row.product_name", source)
        self.assertIn(
            "set_df_property('your_name', 'reqd', 0)",
            source,
        )
        self.assertIn(
            "set_df_property('your_name', 'hidden', 1)",
            source,
        )


    def test_cooking_run_defaults_only_assign_number_and_date(self):
        row = frappe._dict(
            run_no=0,
            run_date=None,
            required_qty=100,
            produced_qty=92,
            notes="",
        )
        fake = frappe._dict(
            cooking_runs=[row],
            is_final_trial=0,
            status="Draft",
        )
        fake.get = lambda fieldname: getattr(fake, fieldname, None)

        ProductProposalTrial.set_cooking_run_defaults(fake)

        self.assertEqual(row.run_no, 1)
        self.assertTrue(row.run_date)
        self.assertNotIn("purpose", row)
        self.assertNotIn("yield_percent", row)

    def test_existing_cooking_run_cannot_be_deleted(self):
        old_row = frappe._dict(
            name="RUN-ROW-1", run_no=1, run_date="2026-09-09",
            required_qty=100, produced_qty=95, notes="",
        )
        old_doc = frappe._dict(cooking_runs=[old_row])
        fake = frappe._dict(
            cooking_runs=[], is_final_trial=0, status="Draft"
        )
        fake.get = lambda fieldname: getattr(fake, fieldname, None)
        fake.get_doc_before_save = lambda: old_doc

        with self.assertRaises(frappe.ValidationError):
            ProductProposalTrial.validate_cooking_runs(fake)

    def test_final_approved_trial_allows_new_same_recipe_cooking_run(self):
        new_run = frappe._dict(
            name=None,
            run_no=1,
            run_date="2026-09-09",
            required_qty=10,
            produced_qty=0,
            notes="",
        )
        fake = frappe._dict(
            cooking_runs=[new_run],
            is_final_trial=1,
            status="Approved",
        )
        fake.get = lambda fieldname: getattr(fake, fieldname, None)
        fake.get_doc_before_save = lambda: frappe._dict(cooking_runs=[])

        ProductProposalTrial.validate_cooking_runs(fake)

    def test_trial_run_cooking_sheet_scales_without_mutating_trial(self):
        from taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial import (
            get_trial_run_cooking_sheet,
        )

        item = frappe._dict(item_code="ITEM-1", item_name="Item 1", uom="Kg", qty=40)
        solid = frappe._dict(
            component_type="Solid 1",
            component_name="Meat",
            size="2*2",
            weight=10,
            total_weight_cook=200,
            salt=0,
            brix=0,
            ph=6.2,
            viscosity=0,
            spindel_type="",
            rpm=0,
            temperature=5,
        )
        run = frappe._dict(
            run_no=2, run_date="2026-09-09",
            required_qty=50, produced_qty=48, notes=""
        )
        trial = frappe._dict(
            name="TRIAL-1", trial_no=1, trial_title="Trial 1",
            product_proposal="PP-1", planned_cooking_qty=100,
            items=[item], solid_liquid=[solid], cooking_runs=[run],
        )
        trial.get = lambda fieldname: getattr(trial, fieldname, None)
        trial.check_permission = lambda permission: None

        module = "taj_core.rnd.doctype.product_proposal_trial.product_proposal_trial"
        with patch(f"{module}.frappe.get_doc", return_value=trial), patch(
            f"{module}.frappe.db.get_value",
            return_value=frappe._dict(product_name="Product One"),
        ):
            sheet = get_trial_run_cooking_sheet("TRIAL-1", 2)

        self.assertAlmostEqual(sheet["items"][0].required_qty, 20)
        self.assertAlmostEqual(sheet["solid_liquid"][0].total_weight_cook, 100)
        self.assertEqual(item.qty, 40)
        self.assertEqual(solid.total_weight_cook, 200)

    def test_trial_label_6x4_print_format_source(self):
        data = _load_app_json(
            "rnd",
            "print_format",
            "product_proposal_trial_label_6x4",
            "product_proposal_trial_label_6x4.json",
        )

        self.assertEqual(data["name"], "Product Proposal Trial Label 6x4")
        self.assertEqual(data["doc_type"], "Product Proposal Trial")
        self.assertIn("size: 6cm 4cm", data["css"])
        self.assertIn("R&amp;D TRIAL - NOT FOR SALE", data["html"])
        self.assertIn("doc.trial_title", data["html"])
        self.assertIn("doc.trial_no", data["html"])
        self.assertIn("doc.posting_date", data["html"])

    def test_non_token_feedback_always_requires_server_trial_authorization(self):
        fake = frappe._dict(
            {
                "sample_token": "",
                "trial_document": "PP-1-TRIAL-01",
            }
        )

        resolver = (
            "taj_core.rnd.web_form.sensory_rating.sensory_rating."
            "get_trial_evaluation_context"
        )

        with patch(
            resolver,
            side_effect=frappe.PermissionError,
        ):
            with self.assertRaises(frappe.PermissionError):
                SensoryFeedback.validate_public_sensory_availability(fake)
