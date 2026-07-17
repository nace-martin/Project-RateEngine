import json
import os
from django.test import SimpleTestCase
from pydantic import ValidationError
from quotes.contracts.draft_quote_contract import (
    DraftQuoteSchema, DraftChargeSchema, IgnoredItemSchema,
    DraftQuoteResolveSchema, DraftQuoteResolveResponseSchema
)



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

        self.resolve_fixture_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "draft_quote_contract",
            "hard_case_resolve_submission.json"
        )
        with open(self.resolve_fixture_path, "r") as f:
            self.resolve_raw_data = json.load(f)

    def test_mock_payload_validates_successfully(self):
        """Verify the hard-case mock payload successfully validates against the contract schema."""
        schema = DraftQuoteSchema(**self.raw_data)
        self.assertEqual(schema.contract_version, "1.0.0")
        self.assertEqual(len(schema.suggested_charges), 5)
        self.assertEqual(len(schema.commercial_terms), 4)
        self.assertEqual(len(schema.unclassified_items), 1)
        self.assertEqual(len(schema.ignored_items), 1)
        self.assertEqual(schema.shipment_context["direction"], "IMPORT")

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

    def test_workflow_validation_data_adequacy(self):
        """Confirm hard-case fixture contains enough correction_actions / similarity_group_id / review_queue data for workflow validation."""
        schema = DraftQuoteSchema(**self.raw_data)
        
        # Verify review queue contains items requiring manual actions
        self.assertTrue(len(schema.review_queue) >= 3)
        review_types = {item.get("type") for item in schema.review_queue}
        self.assertIn("charge_needs_review", review_types)
        self.assertIn("unclassified_item", review_types)
        
        # Verify correction actions are mapped for those items
        self.assertTrue(len(schema.correction_actions) >= 3)
        action_types = {action.get("action_type") for action in schema.correction_actions}
        self.assertIn("RESOLVE_PRODUCT_CODE", action_types)
        self.assertIn("CONFIRM_INHERITED_CURRENCY", action_types)
        self.assertIn("CLASSIFY_ITEM", action_types)

        # Verify similarity group exists on the two target review charges
        charges_with_group = [
            c for c in schema.suggested_charges if c.similarity_group_id == "sim-surcharges"
        ]
        self.assertEqual(len(charges_with_group), 2)

    def test_mock_resolve_payload_validates_successfully(self):
        """Verify that the hard-case resolve submission payload validates against DraftQuoteResolveSchema."""
        schema = DraftQuoteResolveSchema(**self.resolve_raw_data)
        self.assertEqual(str(schema.idempotency_key), "8e9b2520-22c5-4309-88cc-51e6b3648612")
        self.assertEqual(len(schema.decisions), 6)
        
        decisions_by_type = {d.type: d for d in schema.decisions}
        self.assertIn("accept_suggestion", decisions_by_type)
        self.assertIn("map_to_product_code", decisions_by_type)
        self.assertIn("request_product_code", decisions_by_type)
        self.assertIn("ignore", decisions_by_type)
        self.assertIn("edit_charge", decisions_by_type)
        self.assertIn("classify_unclassified", decisions_by_type)

    def test_resolve_validation_rules_reject_invalid_payloads(self):
        """Verify resolve validation schema rejects invalid decision type or details."""
        # 1. Invalid decision type
        bad_type_data = json.loads(json.dumps(self.resolve_raw_data))
        bad_type_data["decisions"][0]["type"] = "delete_everything"
        with self.assertRaises(ValidationError):
            DraftQuoteResolveSchema(**bad_type_data)

        # 2. Ignore decision missing required 'reason'
        bad_ignore_data = json.loads(json.dumps(self.resolve_raw_data))
        ignore_decision = next(d for d in bad_ignore_data["decisions"] if d["type"] == "ignore")
        ignore_decision["details"]["reason"] = "   "
        with self.assertRaises(ValidationError):
            DraftQuoteResolveSchema(**bad_ignore_data)

        # 3. Edit charge missing original/updated values fields
        bad_edit_data = json.loads(json.dumps(self.resolve_raw_data))
        edit_decision = next(d for d in bad_edit_data["decisions"] if d["type"] == "edit_charge")
        edit_decision["details"]["updated_values"] = {}
        with self.assertRaises(ValidationError):
            DraftQuoteResolveSchema(**bad_edit_data)

    def test_resolve_response_payload_validation(self):
        """Verify DraftQuoteResolveResponseSchema correctly validates a valid response payload."""
        response_payload = {
            "status": "accepted",
            "idempotency_key": "8e9b2520-22c5-4309-88cc-51e6b3648612",
            "applied_decisions": [
                {
                    "decision_id": "dec-001",
                    "target_id": "chg-001",
                    "type": "accept_suggestion",
                    "status": "applied",
                    "message": "Suggestion applied successfully"
                }
            ],
            "rejected_decisions": [],
            "validation_errors": [],
            "unresolved_items_remaining": 0,
            "envelope_id": "8e9b2520-22c5-4309-88cc-51e6b3648612",
            "message": "Resolution applied"
        }
        schema = DraftQuoteResolveResponseSchema(**response_payload)
        self.assertEqual(schema.status, "accepted")
        self.assertEqual(str(schema.idempotency_key), "8e9b2520-22c5-4309-88cc-51e6b3648612")
        self.assertEqual(str(schema.envelope_id), "8e9b2520-22c5-4309-88cc-51e6b3648612")
        self.assertEqual(len(schema.applied_decisions), 1)

    def test_resolve_response_rejects_invalid_status(self):
        """Verify DraftQuoteResolveResponseSchema raises ValidationError on invalid status."""
        response_payload = {
            "status": "fully_verified_by_operator",  # invalid status
            "idempotency_key": "8e9b2520-22c5-4309-88cc-51e6b3648612",
            "applied_decisions": [],
            "rejected_decisions": [],
            "validation_errors": [],
            "message": "Resolution applied"
        }
        with self.assertRaises(ValidationError):
            DraftQuoteResolveResponseSchema(**response_payload)



