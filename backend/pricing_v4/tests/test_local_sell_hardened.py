import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from rest_framework import serializers

from pricing_v4.models import LocalSellRate, ProductCode
from pricing_v4.serializers import LocalSellRateSerializer
from pricing_v4.services.pricing_domain_service import PricingDomainService

class LocalSellHardenedTests(TestCase):
    def setUp(self):
        # Use get_or_create to avoid unique ID conflicts if tests run repeatedly
        self.pc_export, _ = ProductCode.objects.get_or_create(
            id=1900,
            defaults={
                "code": f"EXPORT-HARD-{uuid.uuid4().hex[:4]}",
                "description": "Export Product",
                "category": "DOCUMENTATION",
                "domain": "EXPORT",
                "is_gst_applicable": True,
                "gst_treatment": "ZERO_RATED",
                "gl_revenue_code": "REV-H",
                "gl_cost_code": "COST-H"
            }
        )
        self.today = date.today()
        self.v_from = self.today
        self.v_to = self.today + timedelta(days=30)

    def test_model_clean_blocks_overlap(self):
        """Direct model clean blocks overlap."""
        LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.v_from,
            valid_until=self.v_to
        )

        rate2 = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("110.00"),
            valid_from=self.v_from + timedelta(days=5),
            valid_until=self.v_to + timedelta(days=5)
        )
        with self.assertRaises(ValidationError):
            rate2.full_clean()

    def test_serializer_blocks_overlap(self):
        """Serializer validate blocks overlap through model hardening."""
        LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.v_from,
            valid_until=self.v_to
        )

        data = {
            'product_code': self.pc_export.id,
            'location': 'POM',
            'direction': 'EXPORT',
            'payment_term': 'ANY',
            'currency': 'PGK',
            'rate_type': 'FIXED',
            'amount': '110.00',
            'valid_from': self.v_from + timedelta(days=5),
            'valid_until': self.v_to + timedelta(days=5),
        }
        serializer = LocalSellRateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        # Check that errors exist
        self.assertTrue(len(serializer.errors) > 0)

    def test_safe_save_helper_blocks_overlap(self):
        """PricingDomainService.save_rate blocks overlap."""
        LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.v_from,
            valid_until=self.v_to
        )

        rate2 = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("110.00"),
            valid_from=self.v_from + timedelta(days=5),
            valid_until=self.v_to + timedelta(days=5)
        )
        with self.assertRaises(ValidationError):
            PricingDomainService.save_rate(rate2)

    def test_safe_update_or_create_helper_blocks_overlap(self):
        """PricingDomainService.update_or_create_rate blocks overlap."""
        LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.v_from,
            valid_until=self.v_to
        )

        lookup = {
            'product_code': self.pc_export,
            'location': 'POM',
            'direction': 'EXPORT',
            'payment_term': 'ANY',
            'currency': 'PGK',
            'valid_from': self.v_from + timedelta(days=1), # Different start, so DoesNotExist
        }
        defaults = {
            'amount': Decimal("120.00"),
            'valid_until': self.v_to,
        }
        
        with self.assertRaises(ValidationError):
            # This should try to CREATE but fail on full_clean() due to overlap
            PricingDomainService.update_or_create_rate(LocalSellRate, lookup, defaults)
