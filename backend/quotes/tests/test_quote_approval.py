from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from core.commodity import COMMODITY_CODE_AVI
from pricing_v4.models import CommodityApprovalRule
from quotes.approval import QuoteApprovalPolicy
from quotes.models import Quote


class QuoteApprovalPolicyTests(TestCase):
    def test_matching_db_rule_requires_manager_approval(self):
        CommodityApprovalRule.objects.create(
            shipment_type=Quote.ShipmentType.IMPORT,
            service_scope="A2D",
            commodity_code=COMMODITY_CODE_AVI,
            requires_manager_approval=True,
            effective_from=timezone.now().date() - timedelta(days=1),
        )

        decision = QuoteApprovalPolicy.evaluate(
            shipment_type=Quote.ShipmentType.IMPORT,
            service_scope="A2D",
            commodity_code=COMMODITY_CODE_AVI,
            total_cost_pgk=Decimal("100.00"),
            total_sell_pgk=Decimal("140.00"),
        )

        self.assertTrue(decision.approval_required)
        self.assertEqual(decision.margin_percent, Decimal("28.57"))
        self.assertIn("Live Animals requires manager approval.", decision.reason)

    def test_margin_threshold_rule_requires_approval_when_below_threshold(self):
        CommodityApprovalRule.objects.create(
            shipment_type=Quote.ShipmentType.EXPORT,
            service_scope=None,
            commodity_code=COMMODITY_CODE_AVI,
            requires_manager_approval=False,
            margin_below_pct=Decimal("20.00"),
            effective_from=timezone.now().date() - timedelta(days=1),
        )

        decision = QuoteApprovalPolicy.evaluate(
            shipment_type=Quote.ShipmentType.EXPORT,
            service_scope="D2A",
            commodity_code=COMMODITY_CODE_AVI,
            total_cost_pgk=Decimal("90.00"),
            total_sell_pgk=Decimal("100.00"),
        )

        self.assertTrue(decision.approval_required)
        self.assertIn("Margin 10.00% is below the 20.00% threshold for Live Animals.", decision.reason)

    @override_settings(
        STANDARD_QUOTE_APPROVAL_POLICY={
            'special_cargo_requires_approval': True,
            'approval_required_commodities': ['AVI'],
            'margin_below_pct': Decimal("12.50"),
        }
    )
    def test_db_rule_can_explicitly_override_fallback_special_cargo_approval(self):
        CommodityApprovalRule.objects.create(
            shipment_type=Quote.ShipmentType.EXPORT,
            service_scope="D2A",
            commodity_code=COMMODITY_CODE_AVI,
            requires_manager_approval=False,
            effective_from=timezone.now().date() - timedelta(days=1),
        )

        decision = QuoteApprovalPolicy.evaluate(
            shipment_type=Quote.ShipmentType.EXPORT,
            service_scope="D2A",
            commodity_code=COMMODITY_CODE_AVI,
            total_cost_pgk=Decimal("80.00"),
            total_sell_pgk=Decimal("100.00"),
        )

        self.assertFalse(decision.approval_required)
        self.assertEqual(decision.reason, "")

    @override_settings(
        STANDARD_QUOTE_APPROVAL_POLICY={
            'special_cargo_requires_approval': True,
            'approval_required_commodities': ['AVI'],
            'margin_below_pct': Decimal("12.50"),
        }
    )
    def test_fallback_policy_applies_when_no_db_rule_matches(self):
        decision = QuoteApprovalPolicy.evaluate(
            shipment_type=Quote.ShipmentType.EXPORT,
            service_scope="D2A",
            commodity_code=COMMODITY_CODE_AVI,
            total_cost_pgk=Decimal("80.00"),
            total_sell_pgk=Decimal("100.00"),
        )

        self.assertTrue(decision.approval_required)
        self.assertIn("Live Animals requires manager approval.", decision.reason)
        self.assertNotIn("Margin", decision.reason)
