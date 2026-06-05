import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError

from pricing_v4.models import (
    ProductCode, Carrier, Agent,
    LocalCOGSRate, ExportSellRate, ExportCOGS,
    ImportCOGS,
    DomesticSellRate, Surcharge
)
from pricing_v4.services.pricing_domain_service import PricingDomainService

class FreightOverlapTests(TestCase):
    def setUp(self):
        # Create standard entities
        self.pc_export = ProductCode.objects.create(
            id=1991, code=f"EXP-{uuid.uuid4().hex[:4]}", description="Export PC",
            category="FREIGHT", domain="EXPORT", is_gst_applicable=True
        )
        self.pc_import = ProductCode.objects.create(
            id=2991, code=f"IMP-{uuid.uuid4().hex[:4]}", description="Import PC",
            category="FREIGHT", domain="IMPORT", is_gst_applicable=True
        )
        self.pc_domestic = ProductCode.objects.create(
            id=3991, code=f"DOM-{uuid.uuid4().hex[:4]}", description="Domestic PC",
            category="FREIGHT", domain="DOMESTIC", is_gst_applicable=True
        )
        self.carrier = Carrier.objects.create(code=f"C-{uuid.uuid4().hex[:2]}", name="Carrier")
        self.agent = Agent.objects.create(code=f"A-{uuid.uuid4().hex[:2]}", name="Agent", country_code="PG")
        self.today = date.today()

    def test_export_sell_overlap_blocked(self):
        """Model full_clean() blocks overlap in ExportSellRate."""
        ExportSellRate.objects.create(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("10.00"),
            valid_from=self.today, valid_until=self.today + timedelta(days=30)
        )
        
        overlapping = ExportSellRate(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("12.00"),
            valid_from=self.today + timedelta(days=10),
            valid_until=self.today + timedelta(days=20)
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_export_cogs_overlap_blocked(self):
        """PricingDomainService blocks overlap in ExportCOGS."""
        PricingDomainService.save_rate(ExportCOGS(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("5.00"),
            carrier=self.carrier,
            valid_from=self.today, valid_until=self.today + timedelta(days=30)
        ))
        
        overlapping = ExportCOGS(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("6.00"),
            carrier=self.carrier,
            valid_from=self.today + timedelta(days=5),
            valid_until=self.today + timedelta(days=15)
        )
        with self.assertRaises(ValidationError):
            PricingDomainService.save_rate(overlapping)

    def test_domestic_sell_overlap_blocked(self):
        """Model full_clean() blocks overlap in DomesticSellRate."""
        DomesticSellRate.objects.create(
            product_code=self.pc_domestic,
            origin_zone="POM", destination_zone="LAE",
            currency="PGK", rate_per_kg=Decimal("8.00"),
            valid_from=self.today, valid_until=self.today + timedelta(days=30)
        )
        
        overlapping = DomesticSellRate(
            product_code=self.pc_domestic,
            origin_zone="POM", destination_zone="LAE",
            currency="PGK", rate_per_kg=Decimal("9.00"),
            valid_from=self.today + timedelta(days=5),
            valid_until=self.today + timedelta(days=15)
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_import_cogs_overlap_blocked(self):
        """Model full_clean() blocks overlap in ImportCOGS."""
        ImportCOGS.objects.create(
            product_code=self.pc_import,
            origin_airport="SIN", destination_airport="POM",
            currency="USD", rate_per_kg=Decimal("2.00"),
            agent=self.agent,
            valid_from=self.today, valid_until=self.today + timedelta(days=365)
        )
        
        overlapping = ImportCOGS(
            product_code=self.pc_import,
            origin_airport="SIN", destination_airport="POM",
            currency="USD", rate_per_kg=Decimal("2.10"),
            agent=self.agent,
            valid_from=self.today + timedelta(days=100),
            valid_until=self.today + timedelta(days=200)
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_local_cogs_overlap_blocked(self):
        """Model full_clean() blocks overlap in LocalCOGSRate."""
        LocalCOGSRate.objects.create(
            product_code=self.pc_export, # Documentation
            location="POM", direction="EXPORT",
            currency="PGK", amount=Decimal("20.00"),
            agent=self.agent,
            valid_from=self.today, valid_until=self.today + timedelta(days=365)
        )
        
        overlapping = LocalCOGSRate(
            product_code=self.pc_export,
            location="POM", direction="EXPORT",
            currency="PGK", amount=Decimal("25.00"),
            agent=self.agent,
            valid_from=self.today + timedelta(days=10),
            valid_until=self.today + timedelta(days=20)
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_surcharge_overlap_blocked(self):
        """Model full_clean() blocks overlap in Surcharge."""
        Surcharge.objects.create(
            product_code=self.pc_export,
            currency="PGK", amount=Decimal("50.00"),
            valid_from=self.today, valid_until=self.today + timedelta(days=365)
        )
        
        overlapping = Surcharge(
            product_code=self.pc_export,
            currency="PGK", amount=Decimal("55.00"),
            valid_from=self.today + timedelta(days=10),
            valid_until=self.today + timedelta(days=20)
        )
        with self.assertRaises(ValidationError):
            overlapping.full_clean()

    def test_rollover_continuity_allowed(self):
        """Sequential non-overlapping rows are allowed via service."""
        PricingDomainService.save_rate(ExportSellRate(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("10.00"),
            valid_from=date(2025, 1, 1), valid_until=date(2025, 12, 31)
        ))
        
        rollover = ExportSellRate(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("11.00"),
            valid_from=date(2026, 1, 1),
            valid_until=date(2026, 12, 31)
        )
        # Should not raise
        PricingDomainService.save_rate(rollover)

    def test_update_excludes_self(self):
        """Updating a row doesn't conflict with itself via service."""
        rate = PricingDomainService.save_rate(ExportSellRate(
            product_code=self.pc_export,
            origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("10.00"),
            valid_from=self.today, valid_until=self.today + timedelta(days=30)
        ))
        
        rate.rate_per_kg = Decimal("11.00")
        # Should not raise
        PricingDomainService.save_rate(rate)
