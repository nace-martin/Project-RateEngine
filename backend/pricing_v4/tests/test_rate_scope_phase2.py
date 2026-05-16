from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.engine.domestic_engine import DomesticPricingEngine
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm as ExportPaymentTerm
from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.models import (
    Agent,
    Carrier,
    DomesticCOGS,
    DomesticSellRate,
    ExportCOGS,
    ExportSellRate,
    ImportCOGS,
    ImportSellRate,
    LocalCOGSRate,
    LocalSellRate,
    ProductCode,
)
from pricing_v4.services.rate_selector import (
    RateAmbiguityError,
    RateSelectionContext,
    select_export_sell_rate,
)


class Phase2QuoteOutputRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.valid_from = date.today() - timedelta(days=30)
        cls.valid_until = date.today() + timedelta(days=365)
        cls.agent = Agent.objects.create(
            code="P2-AG",
            name="Phase 2 Agent",
            country_code="PG",
            agent_type="ORIGIN",
        )
        cls.import_agent = Agent.objects.create(
            code="P2-AU",
            name="Phase 2 Australia Agent",
            country_code="AU",
            agent_type="ORIGIN",
        )
        cls.carrier = Carrier.objects.create(code="P2-PX", name="Phase 2 Carrier", carrier_type="AIRLINE")

        cls.imp_clear = _product(9201, "IMP-CLEAR", "Import Customs Clearance", "IMPORT", "CLEARANCE")
        cls.imp_cartage = _product(9202, "IMP-CARTAGE-DEST", "Destination Cartage", "IMPORT", "CARTAGE")
        cls.exp_freight = _product(9101, "EXP-FRT-AIR", "Export Air Freight", "EXPORT", "FREIGHT", "KG")
        cls.dom_freight = _product(9301, "DOM-FRT-AIR", "Domestic Air Freight", "DOMESTIC", "FREIGHT", "KG")

        LocalCOGSRate.objects.create(
            product_code=cls.imp_clear,
            location="POM",
            direction="IMPORT",
            agent=cls.import_agent,
            currency="PGK",
            rate_type="FIXED",
            amount=Decimal("350.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )
        LocalSellRate.objects.create(
            product_code=cls.imp_clear,
            location="POM",
            direction="IMPORT",
            payment_term="COLLECT",
            currency="PGK",
            rate_type="FIXED",
            amount=Decimal("500.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )
        LocalSellRate.objects.create(
            product_code=cls.imp_clear,
            location="POM",
            direction="IMPORT",
            payment_term="PREPAID",
            currency="USD",
            rate_type="FIXED",
            amount=Decimal("180.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )
        LocalCOGSRate.objects.create(
            product_code=cls.imp_cartage,
            location="POM",
            direction="IMPORT",
            agent=cls.import_agent,
            currency="PGK",
            rate_type="FIXED",
            amount=Decimal("150.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )
        LocalSellRate.objects.create(
            product_code=cls.imp_cartage,
            location="POM",
            direction="IMPORT",
            payment_term="COLLECT",
            currency="PGK",
            rate_type="FIXED",
            amount=Decimal("200.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )
        LocalSellRate.objects.create(
            product_code=cls.imp_cartage,
            location="POM",
            direction="IMPORT",
            payment_term="PREPAID",
            currency="USD",
            rate_type="FIXED",
            amount=Decimal("70.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )

        ExportCOGS.objects.create(
            product_code=cls.exp_freight,
            origin_airport="POM",
            destination_airport="BNE",
            carrier=cls.carrier,
            currency="PGK",
            rate_per_kg=Decimal("6.00"),
            min_charge=Decimal("100.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )
        ExportSellRate.objects.create(
            product_code=cls.exp_freight,
            origin_airport="POM",
            destination_airport="BNE",
            currency="USD",
            rate_per_kg=Decimal("4.00"),
            min_charge=Decimal("80.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )

        DomesticCOGS.objects.create(
            product_code=cls.dom_freight,
            origin_zone="POM",
            destination_zone="LAE",
            carrier=cls.carrier,
            currency="PGK",
            rate_per_kg=Decimal("6.50"),
            min_charge=Decimal("100.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )
        DomesticSellRate.objects.create(
            product_code=cls.dom_freight,
            origin_zone="POM",
            destination_zone="LAE",
            currency="PGK",
            rate_per_kg=Decimal("8.00"),
            min_charge=Decimal("120.00"),
            valid_from=cls.valid_from,
            valid_until=cls.valid_until,
        )

    def test_import_air_a2d_bne_pom_collect_quote_output_is_stable(self):
        result = ImportPricingEngine(
            quote_date=date.today(),
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("50"),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.A2D,
        ).calculate_quote()

        self.assertEqual(result.quote_currency, "PGK")
        self.assertEqual(result.total_cost_pgk, Decimal("500.00"))
        self.assertEqual(result.total_sell_pgk, Decimal("700.00"))
        self.assertEqual([line.product_code for line in result.destination_lines], ["IMP-CLEAR", "IMP-CARTAGE-DEST"])

    def test_import_air_a2d_bne_pom_prepaid_quote_output_is_stable(self):
        result = ImportPricingEngine(
            quote_date=date.today(),
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("50"),
            payment_term=PaymentTerm.PREPAID,
            service_scope=ServiceScope.A2D,
            tt_sell=Decimal("0.40"),
            caf_rate=Decimal("0.00"),
        ).calculate_quote()

        self.assertEqual(result.quote_currency, "USD")
        self.assertEqual(result.total_cost_pgk, Decimal("500.00"))
        self.assertEqual([line.sell_currency for line in result.destination_lines], ["USD", "USD"])
        self.assertEqual([line.sell_amount for line in result.destination_lines], [Decimal("180.00"), Decimal("70.00")])
        self.assertEqual([line.product_code for line in result.destination_lines], ["IMP-CLEAR", "IMP-CARTAGE-DEST"])

    def test_export_air_pom_bne_quote_output_is_stable(self):
        result = ExportPricingEngine(
            quote_date=date.today(),
            origin="POM",
            destination="BNE",
            chargeable_weight_kg=Decimal("50"),
            payment_term=ExportPaymentTerm.PREPAID,
            tt_sell=Decimal("2.50"),
            caf_rate=Decimal("0.00"),
            destination_currency="USD",
        ).calculate_quote([self.exp_freight.id])

        self.assertEqual(result.total_cost_pgk, Decimal("300.00"))
        self.assertEqual(result.lines[0].sell_currency, "USD")
        self.assertEqual(result.lines[0].sell_amount, Decimal("200.00"))
        self.assertEqual([line.product_code for line in result.lines], ["EXP-FRT-AIR"])

    def test_domestic_air_pom_lae_quote_output_is_stable(self):
        result = DomesticPricingEngine(
            cogs_origin="POM",
            destination="LAE",
            weight_kg=50,
            service_scope="A2A",
        ).calculate_quote()

        self.assertEqual(result.total_cost_pgk, Decimal("325.00"))
        self.assertEqual(result.total_sell_pgk, Decimal("400.00"))
        self.assertEqual([line.product_code for line in result.line_items], ["DOM-FRT-AIR"])

    def test_missing_domestic_buy_data_returns_missing_placeholder_not_exception(self):
        result = DomesticPricingEngine(
            cogs_origin="POM",
            destination="WEW",
            weight_kg=50,
            service_scope="A2A",
        ).calculate_quote()

        missing_lines = [line for line in result.line_items if line.is_rate_missing]
        self.assertEqual(len(missing_lines), 1)
        self.assertFalse(missing_lines[0].included_in_total)
        self.assertIn("Rate missing for DOM-FRT-AIR", missing_lines[0].notes)


class Phase2ScopePersistenceTests(TestCase):
    def test_rate_tables_have_nullable_transition_scope_field(self):
        for model_cls in [
            ExportCOGS,
            ExportSellRate,
            ImportCOGS,
            ImportSellRate,
            DomesticCOGS,
            DomesticSellRate,
            LocalCOGSRate,
            LocalSellRate,
        ]:
            with self.subTest(model=model_cls.__name__):
                field = model_cls._meta.get_field("scope")
                self.assertTrue(field.null)
                self.assertTrue(field.blank)
                self.assertEqual({choice[0] for choice in field.choices}, {"LANE", "ORIGIN", "DESTINATION", "LOCAL", "UNKNOWN"})

    def test_audit_reports_explicit_scope_computed_scope_and_mismatches(self):
        product = _product(9401, "EXP-FRT-AIR", "Export Air Freight", "EXPORT", "FREIGHT", "KG")
        ExportSellRate.objects.create(
            product_code=product,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            rate_per_kg=Decimal("5.00"),
            valid_from=date.today() - timedelta(days=1),
            valid_until=date.today() + timedelta(days=30),
            scope="ORIGIN",
        )
        out = StringIO()

        call_command("audit_pricing_rate_scope", stdout=out)

        report = out.getvalue()
        self.assertIn("explicit_scope=ORIGIN", report)
        self.assertIn("computed_scope=LANE", report)
        self.assertIn("Scope mismatches:", report)
        self.assertIn("EXP-FRT-AIR", report)

    def test_selector_keeps_ambiguity_deterministic_with_scoped_rows(self):
        product = _product(9402, "EXP-FRT-AMB", "Export Air Freight", "EXPORT", "FREIGHT", "KG")
        valid_from = date.today() - timedelta(days=1)
        valid_until = date.today() + timedelta(days=30)
        for currency in ["PGK", "USD"]:
            ExportSellRate.objects.create(
                product_code=product,
                origin_airport="POM",
                destination_airport="BNE",
                currency=currency,
                rate_per_kg=Decimal("5.00"),
                valid_from=valid_from,
                valid_until=valid_until,
                scope="LANE",
            )

        with self.assertRaises(RateAmbiguityError):
            select_export_sell_rate(
                RateSelectionContext(
                    product_code_id=product.id,
                    quote_date=date.today(),
                    origin_airport="POM",
                    destination_airport="BNE",
                )
            )

    def test_selector_scope_preference_is_applied_after_route_filters(self):
        product = _product(9403, "EXP-FRT-SCOPED", "Export Air Freight", "EXPORT", "FREIGHT", "KG")
        valid_from = date.today() - timedelta(days=1)
        valid_until = date.today() + timedelta(days=30)
        scoped_other_lane = ExportSellRate.objects.create(
            product_code=product,
            origin_airport="POM",
            destination_airport="SYD",
            currency="PGK",
            rate_per_kg=Decimal("9.00"),
            valid_from=valid_from,
            valid_until=valid_until,
            scope="LANE",
        )
        legacy_requested_lane = ExportSellRate.objects.create(
            product_code=product,
            origin_airport="POM",
            destination_airport="BNE",
            currency="PGK",
            rate_per_kg=Decimal("5.00"),
            valid_from=valid_from,
            valid_until=valid_until,
        )

        result = select_export_sell_rate(
            RateSelectionContext(
                product_code_id=product.id,
                quote_date=date.today(),
                origin_airport="POM",
                destination_airport="BNE",
                currency="PGK",
                metadata={"rate_scope": "LANE"},
            )
        )

        self.assertEqual(result.record.id, legacy_requested_lane.id)
        self.assertNotEqual(result.record.id, scoped_other_lane.id)


def _product(id, code, description, domain, category, default_unit="SHIPMENT"):
    return ProductCode.objects.create(
        id=id,
        code=code,
        description=description,
        domain=domain,
        category=category,
        is_gst_applicable=True,
        gst_treatment="STANDARD",
        gst_rate=Decimal("0.10"),
        gl_revenue_code="4000",
        gl_cost_code="5000",
        default_unit=default_unit,
    )
