import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.core.management import call_command
from django.test import TestCase
from io import StringIO

from pricing_v4.models import LocalSellRate, ProductCode
from pricing_v4.services.rate_selector import RateSelectionContext, select_local_sell_rate

class LocalSellCleanupTests(TestCase):
    def setUp(self):
        # Use unique code and valid ID (1xxx for EXPORT)
        # We'll use a high range to avoid conflicts with real data if any exists in test DB
        unique_id = 1999 
        unique_code = f"TEST-LC-{uuid.uuid4().hex[:8]}"
        
        # In case 1999 is taken, we'll try to find a free one
        while ProductCode.objects.filter(id=unique_id).exists():
            unique_id -= 1

        self.pc = ProductCode.objects.create(
            id=unique_id,
            code=unique_code,
            description="Test Local",
            category="DOCUMENTATION",
            domain="EXPORT",
            is_gst_applicable=True,
            gst_treatment="ZERO_RATED",
            gl_revenue_code="REV-123",
            gl_cost_code="COST-123"
        )
        self.today = date.today()
        self.valid_from = self.today - timedelta(days=10)
        self.valid_until = self.today + timedelta(days=30)

    def test_planner_identifies_redundant_row(self):
        # Create ANY row
        any_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Create identical PREPAID row
        spec_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        out = StringIO()
        call_command('plan_local_sell_redundancy_cleanup', stdout=out)
        output = out.getvalue()

        self.assertIn("safe_to_delete_specific_term:        1", output)
        self.assertIn("DRY RUN", output)
        # Verify not deleted yet
        self.assertTrue(LocalSellRate.objects.filter(id=spec_rate.id).exists())

    def test_planner_applies_deletion(self):
        any_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        spec_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        out = StringIO()
        call_command('plan_local_sell_redundancy_cleanup', '--apply', stdout=out)
        
        self.assertFalse(LocalSellRate.objects.filter(id=spec_rate.id).exists())
        self.assertTrue(LocalSellRate.objects.filter(id=any_rate.id).exists())

    def test_planner_keeps_differing_amount(self):
        any_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        spec_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK",
            amount=Decimal("150.00"), # Differs
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        out = StringIO()
        call_command('plan_local_sell_redundancy_cleanup', stdout=out)
        output = out.getvalue()

        self.assertIn("keep_specific_term_differs_from_any: 1", output)
        self.assertIn("safe_to_delete_specific_term:        0", output)

    def test_planner_protects_historical_rows(self):
        # ANY row in the future
        any_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.today + timedelta(days=1),
            valid_until=self.today + timedelta(days=10)
        )
        # SPEC row in the past (historical_only means no overlap with ANY)
        spec_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.today - timedelta(days=10),
            valid_until=self.today - timedelta(days=1)
        )

        out = StringIO()
        call_command('plan_local_sell_redundancy_cleanup', stdout=out)
        output = out.getvalue()

        self.assertIn("historical_only:                     1", output)

    def test_selector_warns_on_differing_overlap(self):
        # Create ANY row
        any_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        # Create differing PREPAID row
        spec_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK",
            amount=Decimal("150.00"), # Differing value
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        context = RateSelectionContext(
            product_code_id=self.pc.id,
            quote_date=self.today,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK"
        )

        with self.assertLogs('pricing_v4.services.rate_selector', level='WARNING') as cm:
            result = select_local_sell_rate(context)
            self.assertEqual(result.record.id, spec_rate.id)
            self.assertTrue(any("REDUNDANCY_CONFLICT" in output for output in cm.output))
            self.assertTrue(any("amount" in output for output in cm.output))

    def test_selector_prefers_specific_override(self):
        # Ensure preference logic is not broken
        any_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="ANY",
            currency="PGK",
            amount=Decimal("100.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )
        spec_rate = LocalSellRate.objects.create(
            product_code=self.pc,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK",
            amount=Decimal("150.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until
        )

        context = RateSelectionContext(
            product_code_id=self.pc.id,
            quote_date=self.today,
            location="POM",
            direction="EXPORT",
            payment_term="PREPAID",
            currency="PGK"
        )
        
        result = select_local_sell_rate(context)
        self.assertEqual(result.record.id, spec_rate.id)
        self.assertEqual(result.record.amount, Decimal("150.00"))
