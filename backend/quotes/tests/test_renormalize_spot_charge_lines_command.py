from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from parties.models import Company
from pricing_v4.models import ChargeAlias, ProductCode
from quotes.models import Quote
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB


class RenormalizeSpotChargeLinesCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.product_code = ProductCode.objects.create(
            id=1091,
            code="EXP-RENORM-HANDLING",
            description="Export Renormalized Handling",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        cls.alt_product_code = ProductCode.objects.create(
            id=1092,
            code="EXP-RENORM-ALT",
            description="Export Renormalized Alternative",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def test_dry_run_makes_no_changes(self):
        alias = self._create_alias("Terminal Handling", self.product_code)
        line = self._create_line(source_label="Terminal Handling")

        stdout = StringIO()
        call_command("renormalize_spot_charge_lines", "--dry-run", stdout=stdout)

        line.refresh_from_db()
        self.assertEqual(line.normalization_status, SPEChargeLineDB.NormalizationStatus.UNMAPPED)
        self.assertIsNone(line.matched_alias)
        self.assertIsNone(line.resolved_product_code)
        self.assertIn("- Would update: 1", stdout.getvalue())
        self.assertEqual(alias.alias_text, "Terminal Handling")

    def test_unmapped_line_becomes_matched_after_alias_exists(self):
        alias = self._create_alias("Terminal Handling", self.product_code)
        line = self._create_line(source_label="Terminal Handling")

        stdout = StringIO()
        call_command("renormalize_spot_charge_lines", stdout=stdout)

        line.refresh_from_db()
        self.assertEqual(line.source_label, "Terminal Handling")
        self.assertEqual(line.normalized_label, "terminal handling")
        self.assertEqual(line.normalization_status, SPEChargeLineDB.NormalizationStatus.MATCHED)
        self.assertEqual(line.normalization_method, SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS)
        self.assertEqual(line.matched_alias, alias)
        self.assertEqual(line.resolved_product_code, self.product_code)
        self.assertIn("- Updated: 1", stdout.getvalue())

    def test_manual_resolved_line_is_skipped(self):
        self._create_alias("Terminal Handling", self.product_code)
        line = self._create_line(
            source_label="Terminal Handling",
            manual_resolution_status=SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
            manual_resolved_product_code=self.alt_product_code,
        )

        stdout = StringIO()
        call_command("renormalize_spot_charge_lines", stdout=stdout)

        line.refresh_from_db()
        self.assertEqual(line.normalization_status, SPEChargeLineDB.NormalizationStatus.UNMAPPED)
        self.assertEqual(line.manual_resolved_product_code, self.alt_product_code)
        self.assertIsNone(line.resolved_product_code)
        self.assertIn("- Skipped due to manual resolution: 1", stdout.getvalue())

    def test_ambiguous_result_does_not_set_product_code(self):
        self._create_alias("Terminal Handling", self.product_code)
        self._create_alias("Terminal Handling", self.alt_product_code)
        line = self._create_line(source_label="Terminal Handling")

        stdout = StringIO()
        call_command("renormalize_spot_charge_lines", stdout=stdout)

        line.refresh_from_db()
        self.assertEqual(line.normalization_status, SPEChargeLineDB.NormalizationStatus.AMBIGUOUS)
        self.assertEqual(line.normalization_method, SPEChargeLineDB.NormalizationMethod.EXACT_ALIAS)
        self.assertIsNone(line.matched_alias)
        self.assertIsNone(line.resolved_product_code)
        self.assertIn("- Ambiguous: 1", stdout.getvalue())

    def test_finalized_quote_lines_are_skipped_unless_explicitly_allowed(self):
        self._create_alias("Terminal Handling", self.product_code)
        quote = Quote.objects.create(
            customer=Company.objects.create(name="Renormalize Customer", company_type="CUSTOMER"),
            status=Quote.Status.FINALIZED,
        )
        line = self._create_line(
            source_label="Terminal Handling",
            envelope=self._create_envelope(quote=quote),
        )

        stdout = StringIO()
        call_command("renormalize_spot_charge_lines", stdout=stdout)

        line.refresh_from_db()
        self.assertEqual(line.normalization_status, SPEChargeLineDB.NormalizationStatus.UNMAPPED)
        self.assertIsNone(line.resolved_product_code)
        self.assertIn("- Skipped finalized quotes: 1", stdout.getvalue())

        call_command("renormalize_spot_charge_lines", "--allow-finalized-quotes", stdout=StringIO())

        line.refresh_from_db()
        self.assertEqual(line.normalization_status, SPEChargeLineDB.NormalizationStatus.MATCHED)
        self.assertEqual(line.resolved_product_code, self.product_code)

    def _create_envelope(self, *, quote=None):
        return SpotPricingEnvelopeDB.objects.create(
            status=SpotPricingEnvelopeDB.Status.DRAFT,
            quote=quote,
            shipment_context_json={
                "origin_country": "PG",
                "destination_country": "AU",
                "origin_code": "POM",
                "destination_code": "BNE",
            },
            conditions_json={},
            spot_trigger_reason_code="TEST",
            spot_trigger_reason_text="Test",
            expires_at=timezone.now() + timedelta(hours=4),
        )

    def _create_line(self, *, source_label, envelope=None, **overrides):
        defaults = {
            "envelope": envelope or self._create_envelope(),
            "code": "ORIGIN_LOCAL_SPOT",
            "description": source_label,
            "amount": "25.00",
            "currency": "PGK",
            "unit": SPEChargeLineDB.Unit.PER_SHIPMENT,
            "bucket": SPEChargeLineDB.Bucket.ORIGIN_CHARGES,
            "source_label": source_label,
            "normalized_label": ChargeAlias.normalize_alias_text_value(source_label),
            "normalization_status": SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            "normalization_method": SPEChargeLineDB.NormalizationMethod.NONE,
            "source_reference": "agent-email",
            "entered_at": timezone.now(),
        }
        defaults.update(overrides)
        return SPEChargeLineDB.objects.create(**defaults)

    def _create_alias(self, alias_text, product_code):
        return ChargeAlias.objects.create(
            alias_text=alias_text,
            normalized_alias_text=ChargeAlias.normalize_alias_text_value(alias_text),
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            product_code=product_code,
            priority=10,
            is_active=True,
            review_status=ChargeAlias.ReviewStatus.APPROVED,
        )
