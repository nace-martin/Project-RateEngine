
from django.test import TestCase
from unittest.mock import MagicMock, patch
from decimal import Decimal
from quotes.spot_services import ReplyAnalysisService
from quotes.ai_intake_schemas import SpotChargeLine
from quotes.ai_intake_service import AIRateIntakePipelineResult
from quotes.reply_schemas import AssertionStatus, AssertionCategory
from quotes.spot_schemas import SPEChargeLine
from django.utils import timezone

class CurrencyFallbackTest(TestCase):
    @patch('quotes.ai_intake_service.parse_rate_quote_text')
    @patch('quotes.ai_intake_service.get_gemini_client')
    def test_quote_currency_fallback(self, mock_get_client, mock_parse):
        """
        Verify that if AI returns a global quote_currency, it falls back to lines
        missing currency_code.
        """
        # Setup Mocks
        mock_get_client.return_value = MagicMock()
        
        # Mock AI Response: Global SGD, Line missing currency
        mock_parse.return_value = AIRateIntakePipelineResult(
            success=True,
            quote_currency="SGD",
            lines=[
                SpotChargeLine(
                    bucket="ORIGIN",
                    description="Terminal Fee",
                    amount=Decimal("35.00"),
                    unit_basis="PER_SHIPMENT",
                    currency=None # MISSING CURRENCY
                )
            ],
            raw_text_length=100
        )
        
        # Call Service
        confirmations = ReplyAnalysisService.analyze_with_ai(
            raw_text="Test Quote in SGD",
            shipment_context={}
        )
        
        # Verify Assertions
        assertions = confirmations.assertions
        
        # 1. Check for Global Currency Assertion
        currency_assertion = next((a for a in assertions if a.category == AssertionCategory.CURRENCY), None)
        self.assertIsNotNone(currency_assertion, "Should create global CURRENCY assertion")
        self.assertEqual(currency_assertion.rate_currency, "SGD")
        
        # 2. Check Line Item Fallback
        line_assertion = next((a for a in assertions if a.text == "Terminal Fee"), None)
        self.assertIsNotNone(line_assertion)
        self.assertEqual(line_assertion.rate_currency, "SGD", "Should fallback to quote_currency")
        
        # 3. Check Summary Validation
        self.assertTrue(confirmations.summary.has_currency, "Summary should be valid for currency")
        
        # 4. Check Warnings
        # Should NOT have "MISSING: Rate currency is required"
        currency_warnings = [w for w in confirmations.warnings if "Rate currency is required" in w]
        self.assertEqual(len(currency_warnings), 0, "Should not warn about missing currency")

    def test_spot_charge_line_coerces_null_rule_meta(self):
        line = SpotChargeLine(
            bucket="FREIGHT",
            description="Airfreight",
            rate_per_unit=Decimal("5.00"),
            currency="USD",
            unit_basis="PER_KG",
            rule_meta=None,
        )

        self.assertEqual(line.rule_meta, {})

    def test_spe_charge_line_accepts_extended_supported_currency(self):
        line = SPEChargeLine(
            code="DESTINATION_LOCAL",
            description="Destination handling",
            amount=Decimal("42.00"),
            currency="EUR",
            unit="flat",
            bucket="destination_charges",
            source_reference="Agent quote",
            entered_by_user_id="tester",
            entered_at=timezone.now(),
        )

        self.assertEqual(line.currency, "EUR")

