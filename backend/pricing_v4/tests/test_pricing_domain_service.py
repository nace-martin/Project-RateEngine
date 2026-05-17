import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError

from pricing_v4.models import LocalSellRate, ProductCode
from pricing_v4.services.pricing_domain_service import PricingDomainService

class PricingDomainServiceTests(TestCase):
    def setUp(self):
        # Use a unique ID and code
        unique_id = 1999
        while ProductCode.objects.filter(id=unique_id).exists():
            unique_id -= 1

        self.pc_export = ProductCode.objects.create(
            id=unique_id,
            code=f"DOMAIN-TEST-{uuid.uuid4().hex[:4]}",
            description="Test Local",
            category="DOCUMENTATION",
            domain="EXPORT",
            is_gst_applicable=True,
            gst_treatment="ZERO_RATED",
            gl_revenue_code="REV-123",
            gl_cost_code="COST-123"
        )
        self.today = date.today()

    def test_save_rate_enforces_full_clean(self):
        """save_rate must trigger model validation."""
        # Create an invalid rate (wrong domain for EXPORT)
        invalid_rate = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="IMPORT", # Conflict: Export PC with Import direction
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=30)
        )
        
        with self.assertRaises(ValidationError):
            PricingDomainService.save_rate(invalid_rate)

    def test_save_rate_blocks_overlaps_where_enforced(self):
        """save_rate blocks overlaps if the model has a clean() check."""
        PricingDomainService.save_rate(LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.today,
            valid_until=self.today + timedelta(days=30)
        ))

        overlapping = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("110.00"),
            valid_from=self.today + timedelta(days=5),
            valid_until=self.today + timedelta(days=15)
        )
        
        with self.assertRaises(ValidationError):
            PricingDomainService.save_rate(overlapping)

    def test_update_or_create_rate_safety(self):
        """update_or_create_rate must trigger validation."""
        lookup = {
            'product_code': self.pc_export, 
            'location': 'POM', 
            'direction': 'EXPORT', 
            'payment_term': 'ANY', 
            'currency': 'PGK', 
            'valid_from': self.today
        }
        
        # Create initial valid row
        PricingDomainService.update_or_create_rate(
            LocalSellRate,
            lookup_kwargs=lookup,
            defaults={'amount': Decimal("100.00"), 'valid_until': self.today + timedelta(days=30)}
        )

        # Try to update to an invalid state (invalid direction)
        with self.assertRaises(ValidationError):
            PricingDomainService.update_or_create_rate(
                LocalSellRate,
                lookup_kwargs=lookup,
                defaults={'direction': 'IMPORT'}
            )
            
    def test_rollover_continuity_is_preserved(self):
        """Service allows sequential rollover dates."""
        v1_from = date(2025, 1, 1)
        v1_to = date(2025, 12, 31)
        v2_from = date(2026, 1, 1)
        v2_to = date(2026, 12, 31)

        PricingDomainService.save_rate(LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=v1_from,
            valid_until=v1_to
        ))

        # This should succeed
        PricingDomainService.save_rate(LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("105.00"),
            valid_from=v2_from,
            valid_until=v2_to
        ))
        
        self.assertEqual(LocalSellRate.objects.count(), 2)
