import json
import os
from django.test import SimpleTestCase
from pydantic import ValidationError
from quotes.contracts.draft_quote_contract import DraftQuoteSchema, DraftChargeSchema, IgnoredItemSchema



class DraftQuoteContractTests(SimpleTestCase):
    def setUp(self):
        self.fixture_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "draft_quote_contract",
            "hard_case_air_import.json"
        )
        with open(self.fixture_path, "r") as f:
            self.raw_data = json.load(f)

    def test_mock_payload_validates_successfully(self):
        """Verify the hard-case mock payload successfully validates against the contract schema."""
        schema = DraftQuoteSchema(**self.raw_data)
        self.assertEqual(schema.contract_version, "1.0.0")
        self.assertEqual(len(schema.suggested_charges), 5)
        self.assertEqual(len(schema.commercial_terms), 4)
        self.assertEqual(len(schema.unclassified_items), 1)
        self.assertEqual(len(schema.ignored_items), 1)

    def test_every_suggested_charge_has_evidence_with_source_text(self):
        """Verify that every charge in suggested status has evidence and source_text."""
        schema = DraftQuoteSchema(**self.raw_data)
        
        # Charges with status 'suggested' must have evidence.source_text
        for charge in schema.suggested_charges:
            if charge.status == "suggested":
                self.assertIsNotNone(charge.evidence)
                self.assertTrue(len(charge.evidence.source_text) > 0)

        # Let's test that validation fails if a suggested charge is missing evidence
        bad_data = json.loads(json.dumps(self.raw_data))
        bad_data["suggested_charges"][0]["evidence"] = None
        
        with self.assertRaises(ValidationError) as ctx:
            DraftQuoteSchema(**bad_data)
        self.assertIn("Suggested charges must have evidence containing source_text", str(ctx.exception))

    def test_no_system_generated_charge_has_accepted_by_user_status(self):
        """Verify that no suggested charge in the intake mock payload starts as accepted_by_user."""
        schema = DraftQuoteSchema(**self.raw_data)
        for charge in schema.suggested_charges:
            self.assertNotEqual(charge.status, "accepted_by_user")

    def test_needs_review_and_unclassified_items_appear_in_review_queue(self):
        """Verify that needs_review or unclassified charges/items are registered in the review_queue."""
        schema = DraftQuoteSchema(**self.raw_data)
        
        # Gather ids in review queue
        review_ids = {item.get("id") for item in schema.review_queue}
        
        # Verify needs_review charges are in review queue
        for charge in schema.suggested_charges:
            if charge.status == "needs_review":
                self.assertIn(charge.id, review_ids)

        # Verify unclassified items are in review queue
        for item in schema.unclassified_items:
            self.assertIn(item.id, review_ids)

        # Test validation fails if an item is missing from review_queue
        bad_data = json.loads(json.dumps(self.raw_data))
        bad_data["review_queue"] = [
            item for item in bad_data["review_queue"] if item["id"] != "chg-002"
        ]
        with self.assertRaises(ValidationError) as ctx:
            DraftQuoteSchema(**bad_data)
        self.assertIn("requires review but is not in the review_queue", str(ctx.exception))

    def test_unclassified_items_are_not_silently_dropped(self):
        """Verify that unclassified commercial-looking items are preserved in unclassified_items list."""
        schema = DraftQuoteSchema(**self.raw_data)
        self.assertEqual(len(schema.unclassified_items), 1)
        self.assertEqual(schema.unclassified_items[0].id, "unclass-001")
        self.assertEqual(
            schema.unclassified_items[0].raw_text,
            "Possible cartage / transfer charge: SGD 120.00 might apply if transferred to secondary warehouse"
        )

    def test_ignored_items_require_ignored_reason(self):
        """Verify that ignored items must have a non-empty ignored_reason."""
        schema = DraftQuoteSchema(**self.raw_data)
        self.assertEqual(len(schema.ignored_items), 1)
        self.assertEqual(schema.ignored_items[0].ignored_reason, "Standard boilerplate email confidentiality disclaimer")

        # Test validation fails if ignored_reason is empty or missing
        bad_data = json.loads(json.dumps(self.raw_data))
        bad_data["ignored_items"][0]["ignored_reason"] = "   "
        with self.assertRaises(ValidationError) as ctx:
            DraftQuoteSchema(**bad_data)
        self.assertIn("requires a non-empty ignored_reason", str(ctx.exception))

    def test_totals_validation_can_represent_mismatch_without_schema_failure(self):
        """Verify that a totals mismatch (math_balances=False) validates successfully without schema validation failure."""
        schema = DraftQuoteSchema(**self.raw_data)
        self.assertFalse(schema.totals_validation.math_balances)
        self.assertEqual(schema.totals_validation.extracted_total, 1100.00)
        self.assertEqual(schema.totals_validation.calculated_total, 1145.00)
        self.assertEqual(schema.totals_validation.difference, 45.00)

    def test_similarity_group_id_exists_on_related_charges(self):
        """Verify that related charges share similarity_group_id for bulk-editing."""
        schema = DraftQuoteSchema(**self.raw_data)
        
        # Verify similarity group matches on FSC and Security charges
        charges_in_group = [
            c for c in schema.suggested_charges if c.similarity_group_id == "sim-surcharges"
        ]
        self.assertEqual(len(charges_in_group), 2)
        charge_ids = {c.id for c in charges_in_group}
        self.assertIn("chg-002", charge_ids)
        self.assertIn("chg-003", charge_ids)
