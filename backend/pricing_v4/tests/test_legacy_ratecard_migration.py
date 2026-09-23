"""Tests for Wave 2C1: Legacy Ratecard Migration & Cutover.

Validates:
- Audit and classification of legacy ratecards
- Clean migration to Phase 3 Rate Matrix (RateSheet -> RateLine -> RateApplicability -> RateTier)
- Fail-closed behavior on ambiguous, unmapped, or partial cards
- Strict idempotency of the migration service
- Cold storage manifest validation
- Repointed RatecardListAPIView runtime consumer and RBAC
"""

import json
import os
from decimal import Decimal

from accounts.models import CustomUser
from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Airport, City, Country, Currency
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from parties.models import Company
from parties.party_models import PartyMaster, PartyRole
from ratecards.models import (
    PartnerRate,
    PartnerRateCard,
    PartnerRateLane,
)
from rest_framework import status
from rest_framework.test import APIClient
from services.models import ServiceComponent

from pricing_v4.commercial_models import CommercialProductCode
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

User = get_user_model()


class BaseMigrationTestCase(TestCase):
    """Setup base geographic, party, currency, and component fixtures."""

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

        # GeoLocations
        self.geo_pom, _ = GeoLocation.objects.get_or_create(
            canonical_name="Port Moresby Airport",
            country_code="PG",
            location_type=GeoLocation.LocationType.AIRPORT,
            defaults={"is_active": True},
        )
        GeoLocationIdentifier.objects.get_or_create(
            location=self.geo_pom,
            scheme=GeoLocationIdentifier.Scheme.IATA,
            code="POM",
        )

        self.geo_bne, _ = GeoLocation.objects.get_or_create(
            canonical_name="Brisbane Airport",
            country_code="AU",
            location_type=GeoLocation.LocationType.AIRPORT,
            defaults={"is_active": True},
        )
        GeoLocationIdentifier.objects.get_or_create(
            location=self.geo_bne,
            scheme=GeoLocationIdentifier.Scheme.IATA,
            code="BNE",
        )

        # Companies & Parties
        self.company_px, _ = Company.objects.get_or_create(
            name="Air Niugini",
            defaults={"is_active": True},
        )
        self.party_px, _ = PartyMaster.objects.get_or_create(
            legal_name="Air Niugini",
            country_code="PG",
            defaults={"entity_type": "CARRIER", "is_active": True},
        )
        PartyRole.objects.get_or_create(
            party=self.party_px,
            role_type=PartyRole.RoleType.CARRIER,
            defaults={"is_active": True},
        )

        # Commercial Product Codes
        self.cpc_freight, _ = CommercialProductCode.objects.get_or_create(
            code="EXP-FRT-AIR",
            defaults={
                "name": "Air Freight Export Standard",
                "category": CommercialProductCode.Category.FREIGHT,
                "gst_treatment": CommercialProductCode.GstTreatment.FREIGHT_EXPORT,
                "charge_basis_default": CommercialProductCode.ChargeBasis.PER_KG,
                "is_active": True,
            },
        )
        self.cpc_awb, _ = CommercialProductCode.objects.get_or_create(
            code="EXP-AWB",
            defaults={
                "name": "Air Waybill Fee Export",
                "category": CommercialProductCode.Category.ORIGIN,
                "gst_treatment": CommercialProductCode.GstTreatment.ZERO_RATED,
                "charge_basis_default": CommercialProductCode.ChargeBasis.FLAT,
                "is_active": True,
            },
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


class RatecardClassificationTests(BaseMigrationTestCase):
    """Tests for classification logic of legacy ratecards."""

    def test_classify_test_ratecard_as_invalid(self):
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

        service = RatecardMigrationService(dry_run=True)
        report = service.audit_and_classify()

        self.assertEqual(report.classification_counts[RatecardClassification.INVALID_OR_TEST], 1)
        self.assertEqual(report.parity_counts["invalid"], 1)

    def test_classify_missing_valid_from_as_investigate(self):
        card = PartnerRateCard.objects.create(
            supplier=self.company_px,
            name="EFM POM Export Sell Rates 2025",
            currency_code="PGK",
            rate_type="BUY_RATE",
            valid_from=None,  # Missing valid_from
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

        service = RatecardMigrationService(dry_run=True)
        report = service.audit_and_classify()

        self.assertEqual(report.classification_counts[RatecardClassification.INVESTIGATE], 1)
        self.assertEqual(report.parity_counts["blocked"], 1)

    def test_classify_unmapped_components_as_archive_only(self):
        unmapped_sc, _ = ServiceComponent.objects.get_or_create(
            code="UNMAPPED_FEE",
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

        service = RatecardMigrationService(dry_run=True)
        report = service.audit_and_classify()

        self.assertEqual(report.classification_counts[RatecardClassification.ARCHIVE_ONLY], 1)
        self.assertEqual(report.parity_counts["archive-only"], 1)


class RatecardMigrationExecutionTests(BaseMigrationTestCase):
    """Tests for clean migration execution, parity, and idempotency."""

    def setUp(self):
        super().setUp()
        self.clean_card = PartnerRateCard.objects.create(
            supplier=self.company_px,
            name="Standard Air Niugini Export Buy 2025",
            currency_code="PGK",
            rate_type="BUY_RATE",
            service_level="STANDARD",
            valid_from=self.today,
            valid_until=self.future,
        )
        self.clean_lane = PartnerRateLane.objects.create(
            rate_card=self.clean_card,
            origin_airport=self.airport_pom,
            destination_airport=self.airport_bne,
            direction="EXPORT",
            mode="AIR",
        )
        # Tiered freight rate
        self.freight_rate = PartnerRate.objects.create(
            lane=self.clean_lane,
            service_component=self.sc_freight,
            unit="KG",
            rate_per_kg_fcy=Decimal("5.50"),
            min_charge_fcy=Decimal("50.00"),
            tiering_json={
                "breaks": [
                    {"min_kg": 0, "rate_per_kg": "7.50"},
                    {"min_kg": 45, "rate_per_kg": "6.00"},
                    {"min_kg": 100, "rate_per_kg": "5.50"},
                ]
            },
        )
        # Flat documentation fee
        self.doc_rate = PartnerRate.objects.create(
            lane=self.clean_lane,
            service_component=self.sc_awb,
            unit="SHIPMENT",
            rate_per_shipment_fcy=Decimal("75.00"),
        )

    def test_migration_creates_clean_rate_matrix_with_parity(self):
        service = RatecardMigrationService(dry_run=False)
        report = service.execute_migration()

        # Classification check (2 rates on card)
        self.assertEqual(report.classification_counts[RatecardClassification.MIGRATE], 2)
        self.assertEqual(report.parity_counts["matched"], 2)

        # Target counts
        self.assertEqual(report.target_rows_created["RateSheet"], 1)
        self.assertEqual(report.target_rows_created["RateLine"], 2)
        self.assertEqual(report.target_rows_created["RateApplicability"], 2)
        self.assertEqual(report.target_rows_created["RateTier"], 3)

        # Verify RateSheet
        sheet = RateSheet.objects.get(name=f"Migrated: {self.clean_card.name}")
        self.assertEqual(sheet.rate_type, RateSheet.RateType.BUY)
        self.assertEqual(sheet.currency_code, "PGK")
        self.assertEqual(sheet.valid_from, self.today)
        self.assertEqual(sheet.valid_until, self.future)
        self.assertEqual(sheet.carrier.legal_name, "Air Niugini")

        # Verify Freight RateLine and Applicability
        freight_line = RateLine.objects.get(sheet=sheet, product_code=self.cpc_freight)
        self.assertEqual(freight_line.rate_basis, RateLine.RateBasis.TIERED_WEIGHT)
        self.assertEqual(freight_line.min_charge, Decimal("50.00"))

        app_freight = RateApplicability.objects.get(rate_line=freight_line)
        self.assertEqual(app_freight.origin.identifiers.first().code, "POM")
        self.assertEqual(app_freight.destination.identifiers.first().code, "BNE")
        self.assertEqual(app_freight.direction, "EXPORT")

        # Verify RateTiers
        tiers = list(RateTier.objects.filter(rate_line=freight_line).order_by("min_quantity"))
        self.assertEqual(len(tiers), 3)
        self.assertEqual(tiers[0].min_quantity, Decimal(0))
        self.assertEqual(tiers[0].unit_rate, Decimal("7.50"))
        self.assertEqual(tiers[1].min_quantity, Decimal(45))
        self.assertEqual(tiers[1].unit_rate, Decimal("6.00"))
        self.assertEqual(tiers[2].min_quantity, Decimal(100))
        self.assertEqual(tiers[2].unit_rate, Decimal("5.50"))

        # Verify Flat Fee Line
        awb_line = RateLine.objects.get(sheet=sheet, product_code=self.cpc_awb)
        self.assertEqual(awb_line.rate_basis, RateLine.RateBasis.FLAT)
        self.assertEqual(awb_line.unit_rate, Decimal("75.00"))

    def test_migration_is_strictly_idempotent(self):
        service = RatecardMigrationService(dry_run=False)

        # First run
        report1 = service.execute_migration()
        self.assertEqual(report1.target_rows_created["RateSheet"], 1)
        self.assertEqual(report1.target_rows_created["RateLine"], 2)

        # Second run
        report2 = service.execute_migration()
        self.assertEqual(report2.target_rows_created["RateSheet"], 0)
        self.assertEqual(report2.target_rows_created["RateLine"], 0)
        self.assertEqual(report2.target_rows_created["RateApplicability"], 0)
        self.assertEqual(report2.target_rows_created["RateTier"], 0)

        # Database counts unchanged
        self.assertEqual(RateSheet.objects.count(), 1)
        self.assertEqual(RateLine.objects.count(), 2)
        self.assertEqual(RateApplicability.objects.count(), 2)
        self.assertEqual(RateTier.objects.count(), 3)

    def test_fail_closed_on_partial_card_blocks_migration(self):
        # Add an unmapped component to the card
        unmapped_sc, _ = ServiceComponent.objects.get_or_create(
            code="UNKNOWN_EXTRA_FEE",
            defaults={"description": "Unknown", "unit": "SHIPMENT"},
        )
        PartnerRate.objects.create(
            lane=self.clean_lane,
            service_component=unmapped_sc,
            unit="SHIPMENT",
            rate_per_shipment_fcy=Decimal("20.00"),
        )

        service = RatecardMigrationService(dry_run=False)
        report = service.execute_migration()

        # The card contains an unmapped rate -> must fail closed (all-or-nothing per card, 3 rates on card)
        self.assertEqual(report.classification_counts[RatecardClassification.ARCHIVE_ONLY], 3)
        self.assertEqual(report.target_rows_created["RateSheet"], 0)
        self.assertEqual(RateSheet.objects.count(), 0)
        self.assertEqual(RateLine.objects.count(), 0)


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


class RatecardListAPIViewConsumerTests(BaseMigrationTestCase):
    """Tests for repointed RatecardListAPIView consumer and RBAC."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()

        self.sales = User.objects.create_user(
            username="sales_user",
            email="sales@example.com",
            password="password",
            role=CustomUser.ROLE_SALES,
        )
        self.manager = User.objects.create_user(
            username="manager_user",
            email="manager@example.com",
            password="password",
            role=CustomUser.ROLE_MANAGER,
        )

        # Legacy Card
        self.legacy_card = PartnerRateCard.objects.create(
            supplier=self.company_px,
            name="Legacy Phase 2 Card",
            currency_code="PGK",
            valid_from=self.today,
        )

        # Clean RateSheet
        self.clean_sheet = RateSheet.objects.create(
            name="Phase 3 Clean Air Tariff",
            rate_type=RateSheet.RateType.BUY,
            transport_mode=RateSheet.TransportMode.AIR,
            currency_code="PGK",
            carrier=self.party_px,
            valid_from=self.today,
            is_active=True,
            version=1,
        )

    def test_sales_role_is_forbidden(self):
        self.client.force_authenticate(self.sales)
        response = self.client.get("/api/v3/ratecards/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_role_sees_clean_ratesheet_and_legacy_fallback(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/v3/ratecards/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        items = response.data
        self.assertEqual(len(items), 2)

        # First item should be the clean RateSheet
        clean_item = items[0]
        self.assertEqual(clean_item["id"], str(self.clean_sheet.id))
        self.assertEqual(clean_item["name"], "Phase 3 Clean Air Tariff")
        self.assertEqual(clean_item["file_type"], "RATE_SHEET")
        self.assertEqual(clean_item["supplier_name"], "Air Niugini")

        # Second item should be the legacy PartnerRateCard
        legacy_item = items[1]
        self.assertEqual(legacy_item["id"], str(self.legacy_card.id))
        self.assertEqual(legacy_item["name"], "Legacy Phase 2 Card")
        self.assertEqual(legacy_item["file_type"], "CSV")


class ManagementCommandTests(BaseMigrationTestCase):
    """Tests for the migrate_legacy_ratecards management command."""

    def test_command_audit_only_flag(self):
        call_command("migrate_legacy_ratecards", "--audit-only")
        self.assertEqual(RateSheet.objects.count(), 0)

    def test_command_dry_run_flag(self):
        call_command("migrate_legacy_ratecards", "--dry-run")
        self.assertEqual(RateSheet.objects.count(), 0)
