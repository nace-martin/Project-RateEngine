from django.test import TestCase
from django.core.management import call_command
from quotes.spot_models import SpotPricingEnvelopeDB, ExpectedChargeTemplate
from quotes.services.spot_template_validation import validate_envelope_charges


class SpotTemplateValidationFixturesTests(TestCase):
    def test_seeding_fixtures_and_idempotency(self):
        # 1. Run the seed command for the first time
        call_command("seed_spot_template_validation_fixtures")

        # 2. Verify seeded templates exist
        templates = ExpectedChargeTemplate.objects.filter(name__startswith="QA ")
        self.assertEqual(templates.count(), 3)

        # 3. Verify seeded envelopes exist
        envelopes = SpotPricingEnvelopeDB.objects.filter(spot_trigger_reason_code__startswith="QA_SEED_")
        self.assertEqual(envelopes.count(), 4)

        # 4. Verify validation states and specific findings
        # Scenario 1: Passed
        spe_passed = SpotPricingEnvelopeDB.objects.get(spot_trigger_reason_code="QA_SEED_PASSED")
        result_passed = validate_envelope_charges(spe_passed)
        self.assertEqual(result_passed["status"], "passed")
        self.assertEqual(len(result_passed["findings"]), 0)

        # Scenario 2: Warnings (expected_charge_missing, unexpected_charge_present)
        spe_warnings = SpotPricingEnvelopeDB.objects.get(spot_trigger_reason_code="QA_SEED_WARNINGS")
        result_warnings = validate_envelope_charges(spe_warnings)
        self.assertEqual(result_warnings["status"], "warnings")
        finding_codes = {f["code"] for f in result_warnings["findings"]}
        self.assertIn("expected_charge_missing", finding_codes)
        self.assertIn("unexpected_charge_present", finding_codes)

        # Scenario 3: Review (basis mismatch, duplicate charge family, conditional charge present)
        spe_review = SpotPricingEnvelopeDB.objects.get(spot_trigger_reason_code="QA_SEED_REVIEW")
        result_review = validate_envelope_charges(spe_review)
        self.assertEqual(result_review["status"], "review")
        finding_codes_review = {f["code"] for f in result_review["findings"]}
        self.assertIn("expected_basis_mismatch", finding_codes_review)
        self.assertIn("duplicate_charge_family", finding_codes_review)
        self.assertIn("conditional_charge_present", finding_codes_review)

        # Scenario 4: Template Not Found
        spe_not_found = SpotPricingEnvelopeDB.objects.get(spot_trigger_reason_code="QA_SEED_NO_TEMPLATE")
        result_not_found = validate_envelope_charges(spe_not_found)
        self.assertEqual(result_not_found["status"], "review")
        self.assertEqual(result_not_found["findings"][0]["code"], "template_not_found")

        # 5. Run the seed command a second time to verify idempotency
        call_command("seed_spot_template_validation_fixtures")

        # Confirm count hasn't doubled
        self.assertEqual(ExpectedChargeTemplate.objects.filter(name__startswith="QA ").count(), 3)
        self.assertEqual(SpotPricingEnvelopeDB.objects.filter(spot_trigger_reason_code__startswith="QA_SEED_").count(), 4)
