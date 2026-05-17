import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError

from pricing_v4.models import LocalSellRate, ProductCode

class LocalSellConstraintsTests(TestCase):
    def setUp(self):
        # Use get_or_create to avoid unique ID conflicts if tests run repeatedly
        self.pc_export, _ = ProductCode.objects.get_or_create(
            id=1900,
            defaults={
                "code": f"EXPORT-PROD-{uuid.uuid4().hex[:4]}",
                "description": "Export Product",
                "category": "DOCUMENTATION",
                "domain": "EXPORT",
                "is_gst_applicable": True,
                "gst_treatment": "ZERO_RATED",
                "gl_revenue_code": "REV-1",
                "gl_cost_code": "COST-1"
            }
        )
        self.today = date.today()

    def test_historical_continuity_allowed(self):
        """Sequential non-overlapping rows for same identity are allowed."""
        v1_from = self.today - timedelta(days=365)
        v1_to = self.today - timedelta(days=1)
        v2_from = self.today
        v2_to = self.today + timedelta(days=364)

        # Row 1: 2025
        rate1 = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=v1_from,
            valid_until=v1_to
        )
        rate1.full_clean()
        rate1.save()

        # Row 2: 2026 (Starts exactly when Row 1 ends)
        rate2 = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("110.00"),
            valid_from=v2_from,
            valid_until=v2_to
        )
        rate2.full_clean()
        rate2.save()
        
        self.assertEqual(LocalSellRate.objects.count(), 2)

    def test_conflicting_overlap_blocked(self):
        """Overlap for identical commercial identity is blocked."""
        v1_from = self.today - timedelta(days=30)
        v1_to = self.today + timedelta(days=30)
        
        # Row 1
        rate1 = LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=v1_from,
            valid_until=v1_to
        )

        # Row 2: Overlaps Row 1 by 1 day
        rate2 = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("110.00"),
            valid_from=v1_to, # Overlap on the end date
            valid_until=v1_to + timedelta(days=30)
        )
        
        with self.assertRaises(ValidationError) as cm:
            rate2.full_clean()
        
        self.assertIn("Overlapping active row exists", str(cm.exception))

    def test_specific_override_allowed_overlap_with_any(self):
        """PREPAID overlap with ANY is allowed (hardening only warns, clean doesn't block)."""
        v_from = self.today
        v_to = self.today + timedelta(days=30)

        # ANY row
        LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=v_from,
            valid_until=v_to
        )

        # PREPAID row (Overlaps exactly)
        rate2 = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK",
            amount=Decimal("150.00"),
            valid_from=v_from,
            valid_until=v_to
        )
        
        # Should pass validation as payment_term differs
        rate2.full_clean()
        rate2.save()
        
        self.assertEqual(LocalSellRate.objects.count(), 2)

    def test_rollover_continuity(self):
        """Rollover creation (end+1) is allowed."""
        v1_from = date(2025, 1, 1)
        v1_to = date(2025, 12, 31)
        v2_from = date(2026, 1, 1)
        v2_to = date(2026, 12, 31)

        LocalSellRate.objects.create(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=v1_from,
            valid_until=v1_to
        )

        rate2 = LocalSellRate(
            product_code=self.pc_export,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=v2_from,
            valid_until=v2_to
        )
        rate2.full_clean()
        rate2.save()
        
        self.assertEqual(LocalSellRate.objects.count(), 2)
