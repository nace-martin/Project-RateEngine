import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError

from pricing_v4.models import (
    ProductCode, Carrier, Agent,
    LocalCOGSRate, LocalSellRate,
    ExportSellRate, ExportCOGS,
    ImportSellRate, ImportCOGS,
    DomesticSellRate, DomesticCOGS,
    Surcharge
)
from pricing_v4.services.pricing_domain_service import PricingDomainService
from pricing_v4.tests.validated_factories import (
    create_validated_export_sell,
    create_validated_export_cogs,
    create_validated_domestic_sell,
    create_validated_import_cogs,
    create_validated_local_cogs,
    create_validated_surcharge,
    get_or_create_test_product
)

class FreightOverlapTests(TestCase):
    def setUp(self):
        # Create standard entities using helpers
        # Ensure categories match the tables
        self.pc_export = get_or_create_test_product(1991, f"EXP-{uuid.uuid4().hex[:4]}", "EXPORT", category="FREIGHT")
        self.pc_import = get_or_create_test_product(2991, f"IMP-{uuid.uuid4().hex[:4]}", "IMPORT", category="FREIGHT")
        self.pc_domestic = get_or_create_test_product(3991, f"DOM-{uuid.uuid4().hex[:4]}", "DOMESTIC", category="FREIGHT")
        
        # Local category for LocalCOGSRate
        self.pc_local = get_or_create_test_product(1992, f"LOC-{uuid.uuid4().hex[:4]}", "EXPORT", category="DOCUMENTATION")

        self.carrier = Carrier.objects.create(code=f"C-{uuid.uuid4().hex[:2]}", name="Carrier")
        self.agent = Agent.objects.create(code=f"A-{uuid.uuid4().hex[:2]}", name="Agent", country_code="PG")
        self.today = date.today()

    def test_export_sell_overlap_blocked(self):
        """Model full_clean() blocks overlap in ExportSellRate via validated helper."""
        create_validated_export_sell(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("10.00"),
            valid_from=self.today, valid_until=self.today + timedelta(days=30)
        )
        
        with self.assertRaises(ValidationError):
            create_validated_export_sell(
                product_code=self.pc_export,
                origin_airport="POM", destination_airport="BNE",
                currency="PGK", rate_per_kg=Decimal("12.00"),
                valid_from=self.today + timedelta(days=10),
                valid_until=self.today + timedelta(days=20)
            )

    def test_export_cogs_overlap_blocked(self):
        """PricingDomainService (via helper) blocks overlap in ExportCOGS."""
        create_validated_export_cogs(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("5.00"),
            carrier=self.carrier,
            valid_from=self.today, valid_until=self.today + timedelta(days=30)
        )
        
        with self.assertRaises(ValidationError):
            create_validated_export_cogs(
                product_code=self.pc_export,
                origin_airport="POM", destination_airport="BNE",
                currency="PGK", rate_per_kg=Decimal("6.00"),
                carrier=self.carrier,
                valid_from=self.today + timedelta(days=5),
                valid_until=self.today + timedelta(days=15)
            )

    def test_domestic_sell_overlap_blocked(self):
        """Model full_clean() blocks overlap in DomesticSellRate."""
        create_validated_domestic_sell(
            product_code=self.pc_domestic,
            origin_zone="POM", destination_zone="LAE",
            currency="PGK", rate_per_kg=Decimal("8.00"),
            valid_from=self.today, valid_until=self.today + timedelta(days=30)
        )
        
        with self.assertRaises(ValidationError):
            create_validated_domestic_sell(
                product_code=self.pc_domestic,
                origin_zone="POM", destination_zone="LAE",
                currency="PGK", rate_per_kg=Decimal("9.00"),
                valid_from=self.today + timedelta(days=5),
                valid_until=self.today + timedelta(days=15)
            )

    def test_import_cogs_overlap_blocked(self):
        """Model full_clean() blocks overlap in ImportCOGS."""
        create_validated_import_cogs(
            product_code=self.pc_import,
            origin_airport="SIN", destination_airport="POM",
            currency="USD", rate_per_kg=Decimal("2.00"),
            agent=self.agent,
            valid_from=self.today, valid_until=self.today + timedelta(days=365)
        )
        
        with self.assertRaises(ValidationError):
            create_validated_import_cogs(
                product_code=self.pc_import,
                origin_airport="SIN", destination_airport="POM",
                currency="USD", rate_per_kg=Decimal("2.10"),
                agent=self.agent,
                valid_from=self.today + timedelta(days=100),
                valid_until=self.today + timedelta(days=200)
            )

    def test_local_cogs_overlap_blocked(self):
        """Model full_clean() blocks overlap in LocalCOGSRate."""
        create_validated_local_cogs(
            product_code=self.pc_local,
            location="POM", direction="EXPORT",
            currency="PGK", amount=Decimal("20.00"),
            agent=self.agent,
            valid_from=self.today, valid_until=self.today + timedelta(days=365)
        )
        
        with self.assertRaises(ValidationError):
            create_validated_local_cogs(
                product_code=self.pc_local,
                location="POM", direction="EXPORT",
                currency="PGK", amount=Decimal("25.00"),
                agent=self.agent,
                valid_from=self.today + timedelta(days=10),
                valid_until=self.today + timedelta(days=20)
            )

    def test_surcharge_overlap_blocked(self):
        """Model full_clean() blocks overlap in Surcharge."""
        create_validated_surcharge(
            product_code=self.pc_export,
            service_type="EXPORT_AIR",
            rate_side="COGS",
            currency="PGK", amount=Decimal("50.00"),
            rate_type="FLAT",
            valid_from=self.today, valid_until=self.today + timedelta(days=365)
        )
        
        with self.assertRaises(ValidationError):
            create_validated_surcharge(
                product_code=self.pc_export,
                service_type="EXPORT_AIR",
                rate_side="COGS",
                currency="PGK", amount=Decimal("55.00"),
                rate_type="FLAT",
                valid_from=self.today + timedelta(days=10),
                valid_until=self.today + timedelta(days=20)
            )

    def test_rollover_continuity_allowed(self):
        """Sequential non-overlapping rows are allowed via service."""
        create_validated_export_sell(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("10.00"),
            valid_from=date(2025, 1, 1), valid_until=date(2025, 12, 31)
        )
        
        # This should succeed
        create_validated_export_sell(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("11.00"),
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31)
        )

    def test_update_excludes_self(self):
        """Updating a row doesn't conflict with itself via service."""
        rate = create_validated_export_sell(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("10.00"),
            valid_from=self.today, valid_until=self.today + timedelta(days=30)
        )
        
        rate.rate_per_kg = Decimal("11.00")
        # Should not raise
        PricingDomainService.save_rate(rate)
