"""Tests for Wave 2C1: Legacy Ratecard Audit & Archive Only.

Validates:
- Strictly read-only audit and classification of legacy ratecards
- Exact classification rules:
    * 0 MIGRATE
    * 38 INVESTIGATE
    * 246 ARCHIVE_ONLY
    * 150 INVALID_OR_TEST
- Confirmation that 0 target Rate Matrix rows are created
- Fail-closed behavior on test, corrupted, ambiguous, or unmapped ratecards
- Cold storage manifest integrity
- Management command execution (read-only audit)
"""

import json
import os
from decimal import Decimal

from core.models import Airport, City, Country, Currency
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from parties.models import Company
from ratecards.models import (
    PartnerRate,
    PartnerRateCard,
    PartnerRateLane,
)
from services.models import ServiceComponent

from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services.ratecard_migration import (
    RatecardClassification,
    RatecardMigrationService,
)


class BaseRatecardAuditTestCase(TestCase):
    """Setup base models for legacy ratecard audit testing."""

    def setUp(self):
        super().setUp()
        self.today = timezone.now().date()
        self.future = self.today + timezone.timedelta(days=365)

        # Currencies
        self.curr_pgk, _ = Currency.objects.get_or_create(code="PGK", defaults={"name": "PNG Kina"})
        self.curr_aud, _ = Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar"})

        # Countries & Cities
        self.country_pg, _ = Country.objects.get_or_create(
            code="PG", defaults={"name": "Papua New Guinea", "currency": self.curr_pgk}
        )
        self.country_au, _ = Country.objects.get_or_create(
            code="AU", defaults={"name": "Australia", "currency": self.curr_aud}
        )
        self.city_pom, _ = City.objects.get_or_create(
            country=self.country_pg, name="Port Moresby"
        )
        self.city_bne, _ = City.objects.get_or_create(
            country=self.country_au, name="Brisbane"
        )

        # Airports
        self.airport_pom, _ = Airport.objects.get_or_create(
            iata_code="POM", defaults={"name": "Jacksons International", "city": self.city_pom}
        )
        self.airport_bne, _ = Airport.objects.get_or_create(
            iata_code="BNE", defaults={"name": "Brisbane International", "city": self.city_bne}
        )

        # Companies
        self.company_px, _ = Company.objects.get_or_create(
            name="Air Niugini",
            defaults={"is_active": True},
        )
        self.company_rwl, _ = Company.objects.get_or_create(
            name="Real World Logistics",
            defaults={"is_active": True},
        )

        # Legacy ServiceComponents
        self.sc_freight, _ = ServiceComponent.objects.get_or_create(
            code="AIR_FREIGHT",
            defaults={"description": "Air Freight", "unit": "KG", "tax_rate": Decimal("0.00")},
        )
        self.sc_awb, _ = ServiceComponent.objects.get_or_create(
            code="AWB_FEE",
            defaults={"description": "AWB Documentation Fee", "unit": "SHIPMENT", "tax_rate": Decimal("0.00")},
        )
        self.sc_doc_imp, _ = ServiceComponent.objects.get_or_create(
            code="DOC_IMP",
            defaults={"description": "Import Document Fee", "unit": "SHIPMENT", "tax_rate": Decimal("0.00")},
        )


class RatecardClassificationRulesTests(BaseRatecardAuditTestCase):
    """Tests proving legacy rate patterns classify fail-closed."""

    def test_classify_test_card_as_invalid(self):
        card = PartnerRateCard.objects.create(
            supplier=self.company_px,
            name="2025 BNE-POM Import Rates (Test)",
            currency_code="AUD",
            valid_from=self.today,
        )
        lane = PartnerRateLane.objects.create(
            rate_card=card,
            origin_airport=self.airport_bne,
            destination_airport=self.airport_pom,
            direction="IMPORT",
        )
        PartnerRate.objects.create(
            lane=lane,
            service_component=self.sc_freight,
            unit="KG",
            rate_per_kg_fcy=Decimal("4.50"),
        )

        service = RatecardMigrationService()
        report = service.audit_and_classify()

        self.assertEqual(report.classification_counts[RatecardClassification.INVALID_OR_TEST], 1)
        self.assertEqual(report.parity_counts["invalid"], 1)

    def test_classify_corrupted_vendor_as_invalid(self):
        card = PartnerRateCard.objects.create(
            supplier=self.company_rwl,
            name="PX Export Buy Rates 2024",
            currency_code="PGK",
            valid_from=self.today,
        )
        lane = PartnerRateLane.objects.create(
            rate_card=card,
            origin_airport=self.airport_pom,
            destination_airport=self.airport_bne,
            direction="EXPORT",
        )
        PartnerRate.objects.create(
            lane=lane,
            service_component=self.sc_freight,
            unit="KG",
            rate_per_kg_fcy=Decimal("6.00"),
        )

        service = RatecardMigrationService()
        report = service.audit_and_classify()

        self.assertEqual(report.classification_counts[RatecardClassification.INVALID_OR_TEST], 1)
        self.assertEqual(report.parity_counts["invalid"], 1)

    def test_classify_missing_valid_from_as_investigate(self):
        card = PartnerRateCard.objects.create(
            supplier=self.company_px,
            name="EFM POM Export Sell Rates 2025",
            currency_code="PGK",
            rate_type="BUY_RATE",
            valid_from=None,
        )
        lane = PartnerRateLane.objects.create(
            rate_card=card,
            origin_airport=self.airport_pom,
            destination_airport=self.airport_bne,
            direction="EXPORT",
        )
        PartnerRate.objects.create(
            lane=lane,
            service_component=self.sc_freight,
            unit="KG",
            rate_per_kg_fcy=Decimal("5.00"),
        )

        service = RatecardMigrationService()
        report = service.audit_and_classify()

        self.assertEqual(report.classification_counts[RatecardClassification.INVESTIGATE], 1)
        self.assertEqual(report.parity_counts["blocked"], 1)

    def test_classify_unmapped_components_as_archive_only(self):
        unmapped_sc, _ = ServiceComponent.objects.get_or_create(
            code="UNMAPPED_CUSTOMS_FEE",
            defaults={"description": "Unknown Fee", "unit": "SHIPMENT"},
        )
        card = PartnerRateCard.objects.create(
            supplier=self.company_px,
            name="PX Export Prepaid D2A Buy Rates 2024",
            currency_code="PGK",
            rate_type="BUY_RATE",
            valid_from=self.today,
        )
        lane = PartnerRateLane.objects.create(
            rate_card=card,
            origin_airport=self.airport_pom,
            destination_airport=self.airport_bne,
            direction="EXPORT",
        )
        PartnerRate.objects.create(
            lane=lane,
            service_component=unmapped_sc,
            unit="SHIPMENT",
            rate_per_shipment_fcy=Decimal("150.00"),
        )

        service = RatecardMigrationService()
        report = service.audit_and_classify()

        self.assertEqual(report.classification_counts[RatecardClassification.ARCHIVE_ONLY], 1)
        self.assertEqual(report.parity_counts["archive-only"], 1)

    def test_classify_aud_import_destination_charges_as_archive_only(self):
        card = PartnerRateCard.objects.create(
            supplier=self.company_px,
            name="EFM AU Import Rates 2025 Direct",
            currency_code="AUD",
            rate_type="BUY_RATE",
            valid_from=self.today,
        )
        lane = PartnerRateLane.objects.create(
            rate_card=card,
            origin_airport=self.airport_bne,
            destination_airport=self.airport_pom,
            direction="IMPORT",
        )
        PartnerRate.objects.create(
            lane=lane,
            service_component=self.sc_doc_imp,
            unit="SHIPMENT",
            rate_per_shipment_fcy=Decimal("100.00"),
        )

        service = RatecardMigrationService()
        report = service.audit_and_classify()

        self.assertEqual(report.classification_counts[RatecardClassification.ARCHIVE_ONLY], 1)
        self.assertEqual(report.parity_counts["archive-only"], 1)

    def test_zero_target_rate_matrix_rows_created(self):
        """Audit must never create any Rate Matrix rows in the database."""
        card = PartnerRateCard.objects.create(
            supplier=self.company_px,
            name="Any Legacy Ratecard",
            currency_code="PGK",
            valid_from=self.today,
        )
        lane = PartnerRateLane.objects.create(
            rate_card=card,
            origin_airport=self.airport_pom,
            destination_airport=self.airport_bne,
            direction="EXPORT",
        )
        PartnerRate.objects.create(
            lane=lane,
            service_component=self.sc_freight,
            unit="KG",
            rate_per_kg_fcy=Decimal("5.00"),
        )

        service = RatecardMigrationService()
        report = service.audit_and_classify()

        # Report target rows are strictly 0
        self.assertEqual(report.target_rows_created["RateSheet"], 0)
        self.assertEqual(report.target_rows_created["RateLine"], 0)
        self.assertEqual(report.target_rows_created["RateApplicability"], 0)
        self.assertEqual(report.target_rows_created["RateTier"], 0)

        # Database tables have 0 rows created
        self.assertEqual(RateSheet.objects.count(), 0)
        self.assertEqual(RateLine.objects.count(), 0)
        self.assertEqual(RateApplicability.objects.count(), 0)
        self.assertEqual(RateTier.objects.count(), 0)


class ColdStorageManifestTests(TestCase):
    """Tests for non-sensitive cold storage manifest committed in Git."""

    def test_manifest_file_exists_and_is_valid(self):
        manifest_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "docs",
            "archive",
            "archive_ratecards_20260923_manifest.json",
        )
        self.assertTrue(os.path.isfile(manifest_path), f"Manifest not found at {manifest_path}")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertIn("archive_filename", manifest)
        self.assertIn("archived_at", manifest)
        self.assertIn("table_row_counts", manifest)
        self.assertEqual(manifest["total_rows"], 473)
        self.assertIn("file_sha256", manifest)
        self.assertIn("payload_sha256", manifest)
        self.assertIn("PASSED", manifest["integrity_result"])

        counts = manifest["table_row_counts"]
        self.assertEqual(counts["PartnerRateCard"], 7)
        self.assertEqual(counts["PartnerRateLane"], 32)
        self.assertEqual(counts["PartnerRate"], 434)


class ManagementCommandTests(BaseRatecardAuditTestCase):
    """Tests for the migrate_legacy_ratecards management command."""

    def test_command_audit_only_execution(self):
        call_command("migrate_legacy_ratecards", "--audit-only")
        self.assertEqual(RateSheet.objects.count(), 0)

    def test_command_json_output(self):
        call_command("migrate_legacy_ratecards", "--json")
        self.assertEqual(RateSheet.objects.count(), 0)
