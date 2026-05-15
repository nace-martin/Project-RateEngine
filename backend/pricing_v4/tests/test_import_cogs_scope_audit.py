from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.engine.import_engine import ImportPricingEngine, PaymentTerm, ServiceScope
from pricing_v4.models import Agent, ImportCOGS, LocalCOGSRate, LocalSellRate, ProductCode
from pricing_v4.services.import_cogs_scope import ImportCOGSScope, classify_import_cogs_scope
from pricing_v4.services.rate_selector import RateNotFoundError, RateSelectionContext, select_import_cogs_rate


class ImportCOGSScopeClassificationTests(TestCase):
    def test_classifies_lane_origin_destination_and_unknown_without_db_lookup(self):
        cases = [
            (_product("IMP-FRT-AIR", "Import Air Freight", "FREIGHT"), ImportCOGSScope.LANE),
            (_product("IMP-DOC-ORIGIN", "Import Documentation Fee Origin", "DOCUMENTATION"), ImportCOGSScope.ORIGIN),
            (_product("IMP-AWB-ORIGIN", "Origin AWB Fee", "DOCUMENTATION"), ImportCOGSScope.ORIGIN),
            (_product("IMP-SCREEN-ORIGIN", "Origin X-Ray Screening", "SCREENING"), ImportCOGSScope.ORIGIN),
            (_product("IMP-CLEAR", "Customs Clearance", "CLEARANCE"), ImportCOGSScope.DESTINATION),
            (_product("IMP-CARTAGE-DEST", "Delivery Cartage", "CARTAGE"), ImportCOGSScope.DESTINATION),
            (_product("IMP-MISC", "Import Miscellaneous", "REGULATORY"), ImportCOGSScope.UNKNOWN),
        ]

        for product, expected_scope in cases:
            with self.subTest(product=product.code):
                self.assertEqual(classify_import_cogs_scope(product), expected_scope)


class ImportCOGSLaneLookupRegressionTests(TestCase):
    def setUp(self):
        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)
        self.agent = Agent.objects.create(code="EFM-AU", name="EFM Australia", country_code="AU", agent_type="ORIGIN")
        self.freight = _create_product(2001, "IMP-FRT-AIR", "Import Air Freight", "FREIGHT", "KG")

    def test_lane_freight_lookup_is_resolved_by_origin_and_destination(self):
        bne_pom = self._create_import_cogs("BNE", "POM", Decimal("5.00"))
        syd_pom = self._create_import_cogs("SYD", "POM", Decimal("6.00"))

        result = select_import_cogs_rate(
            RateSelectionContext(
                product_code_id=self.freight.id,
                quote_date=date.today(),
                origin_airport="BNE",
                destination_airport="POM",
                currency="AUD",
                agent_id=self.agent.id,
            )
        )

        self.assertEqual(result.record.id, bne_pom.id)
        self.assertNotEqual(result.record.id, syd_pom.id)

    def test_lane_freight_does_not_fallback_to_a_different_destination(self):
        self._create_import_cogs("BNE", "POM", Decimal("5.00"))

        with self.assertRaises(RateNotFoundError):
            select_import_cogs_rate(
                RateSelectionContext(
                    product_code_id=self.freight.id,
                    quote_date=date.today(),
                    origin_airport="BNE",
                    destination_airport="LAE",
                    currency="AUD",
                    agent_id=self.agent.id,
                )
            )

    def test_missing_lane_buy_data_still_reports_not_found(self):
        with self.assertRaises(RateNotFoundError):
            select_import_cogs_rate(
                RateSelectionContext(
                    product_code_id=self.freight.id,
                    quote_date=date.today(),
                    origin_airport="BNE",
                    destination_airport="POM",
                    currency="AUD",
                    agent_id=self.agent.id,
                )
            )

    def _create_import_cogs(self, origin, destination, rate):
        return ImportCOGS.objects.create(
            product_code=self.freight,
            origin_airport=origin,
            destination_airport=destination,
            agent=self.agent,
            currency="AUD",
            rate_per_kg=rate,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )


class AuditImportCOGSScopeCommandTests(TestCase):
    def setUp(self):
        self.valid_from = date(2025, 1, 1)
        self.valid_until = date(2026, 12, 31)
        self.agent = Agent.objects.create(code="EFM-AU", name="EFM Australia", country_code="AU", agent_type="ORIGIN")
        self.doc_origin = _create_product(2010, "IMP-DOC-ORIGIN", "Import Documentation Fee Origin", "DOCUMENTATION")
        self.unknown = _create_product(2098, "IMP-MISC", "Import Miscellaneous", "REGULATORY")

    def test_audit_reports_duplicate_non_lane_unknown_and_orphan_candidates_without_changes(self):
        self._create_import_cogs(self.doc_origin, "BNE", "POM", Decimal("80.00"))
        self._create_import_cogs(self.doc_origin, "BNE", "LAE", Decimal("80.00"))
        self._create_import_cogs(self.doc_origin, "SYD", "POM", Decimal("80.00"))
        self._create_import_cogs(self.unknown, "BNE", "POM", Decimal("12.00"))
        before_ids = list(ImportCOGS.objects.values_list("id", flat=True).order_by("id"))
        out = StringIO()

        call_command("audit_import_cogs_scope", stdout=out)

        self.assertEqual(list(ImportCOGS.objects.values_list("id", flat=True).order_by("id")), before_ids)
        report = out.getvalue()
        self.assertIn("No rows were changed.", report)
        self.assertIn("Likely duplicate non-lane rows:", report)
        self.assertIn("IMP-DOC-ORIGIN", report)
        self.assertIn("destinations=LAE, POM", report)
        self.assertIn("UNKNOWN scope rows:", report)
        self.assertIn("IMP-MISC", report)
        self.assertIn("missing_destinations=LAE", report)

    def _create_import_cogs(self, product_code, origin, destination, amount):
        return ImportCOGS.objects.create(
            product_code=product_code,
            origin_airport=origin,
            destination_airport=destination,
            agent=self.agent,
            currency="AUD",
            rate_per_shipment=amount,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )


class ImportCOGSQuoteSnapshotRegressionTests(TestCase):
    def setUp(self):
        self.valid_from = date.today() - timedelta(days=30)
        self.valid_until = date.today() + timedelta(days=365)
        self.origin_agent = Agent.objects.create(code="EFM-AU", name="EFM Australia", country_code="AU", agent_type="ORIGIN")
        self.destination_agent = Agent.objects.create(code="EFM-PG", name="EFM PNG", country_code="PG", agent_type="DESTINATION")
        self.products = {
            "IMP-FRT-AIR": _create_product(2001, "IMP-FRT-AIR", "Import Air Freight", "FREIGHT", "KG"),
            "IMP-DOC-ORIGIN": _create_product(2010, "IMP-DOC-ORIGIN", "Import Documentation Fee Origin", "DOCUMENTATION"),
            "IMP-AWB-ORIGIN": _create_product(2011, "IMP-AWB-ORIGIN", "Origin AWB Fee", "DOCUMENTATION"),
            "IMP-AGENCY-ORIGIN": _create_product(2012, "IMP-AGENCY-ORIGIN", "Import Agency Fee Origin", "AGENCY"),
            "IMP-CLEAR": _create_product(2020, "IMP-CLEAR", "Customs Clearance", "CLEARANCE"),
            "IMP-AGENCY-DEST": _create_product(2021, "IMP-AGENCY-DEST", "Destination Agency Fee", "AGENCY"),
            "IMP-DOC-DEST": _create_product(2022, "IMP-DOC-DEST", "Destination Documentation Fee", "DOCUMENTATION"),
            "IMP-CTO-ORIGIN": _create_product(2030, "IMP-CTO-ORIGIN", "Origin CTO Fee", "HANDLING", "KG"),
            "IMP-SCREEN-ORIGIN": _create_product(2040, "IMP-SCREEN-ORIGIN", "Origin X-Ray Screening", "SCREENING", "KG"),
            "IMP-PICKUP": _create_product(2050, "IMP-PICKUP", "Origin Pickup", "CARTAGE", "KG"),
            "IMP-FSC-PICKUP": _create_product(2060, "IMP-FSC-PICKUP", "Origin Pickup FSC", "SURCHARGE", "PERCENT"),
            "IMP-HANDLING-DEST": _create_product(2070, "IMP-HANDLING-DEST", "Destination Handling", "HANDLING", "KG"),
            "IMP-LOADING-DEST": _create_product(2071, "IMP-LOADING-DEST", "Destination Loading Fee", "HANDLING"),
            "IMP-CARTAGE-DEST": _create_product(2072, "IMP-CARTAGE-DEST", "Delivery Cartage", "CARTAGE"),
            "IMP-FSC-CARTAGE-DEST": _create_product(2080, "IMP-FSC-CARTAGE-DEST", "Delivery FSC", "SURCHARGE", "PERCENT"),
        }
        self.products["IMP-FSC-PICKUP"].percent_of_product_code = self.products["IMP-PICKUP"]
        self.products["IMP-FSC-PICKUP"].save(update_fields=["percent_of_product_code"])
        self.products["IMP-FSC-CARTAGE-DEST"].percent_of_product_code = self.products["IMP-CARTAGE-DEST"]
        self.products["IMP-FSC-CARTAGE-DEST"].save(update_fields=["percent_of_product_code"])
        self._seed_import_origin_cogs()
        self._seed_destination_local_rates()

    def test_quote_json_snapshot_is_identical_after_scope_audit_helpers_run(self):
        before = self._quote_snapshot()
        out = StringIO()

        for row in ImportCOGS.objects.select_related("product_code"):
            classify_import_cogs_scope(row)
        call_command("audit_import_cogs_scope", stdout=out)
        after = self._quote_snapshot()

        self.assertEqual(after, before)
        self.assertEqual(before["origin"], "BNE")
        self.assertEqual(before["destination"], "POM")
        self.assertEqual(before["service_scope"], "D2D")
        self.assertEqual(before["line_codes"], [
            "IMP-FRT-AIR",
            "IMP-DOC-ORIGIN",
            "IMP-AWB-ORIGIN",
            "IMP-AGENCY-ORIGIN",
            "IMP-CLEAR",
            "IMP-AGENCY-DEST",
            "IMP-DOC-DEST",
            "IMP-CTO-ORIGIN",
            "IMP-SCREEN-ORIGIN",
            "IMP-PICKUP",
            "IMP-FSC-PICKUP",
            "IMP-HANDLING-DEST",
            "IMP-LOADING-DEST",
            "IMP-CARTAGE-DEST",
            "IMP-FSC-CARTAGE-DEST",
        ])
        self.assertFalse(any(line["is_rate_missing"] for line in before["line_items"]))

    def _quote_snapshot(self):
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("125"),
            payment_term=PaymentTerm.COLLECT,
            service_scope=ServiceScope.D2D,
        )
        result = _stable_json(engine.calculate_quote())
        return {
            "origin": result["origin"],
            "destination": result["destination"],
            "service_scope": result["service_scope"],
            "total_cost_pgk": result["total_cost_pgk"],
            "total_sell_pgk": result["total_sell_pgk"],
            "total_sell_incl_gst": result["total_sell_incl_gst"],
            "line_codes": [line["product_code"] for line in result["line_items"]],
            "line_items": result["line_items"],
        }

    def _seed_import_origin_cogs(self):
        rows = [
            ("IMP-FRT-AIR", {"rate_per_kg": Decimal("6.75"), "min_charge": Decimal("330.00")}),
            ("IMP-DOC-ORIGIN", {"rate_per_shipment": Decimal("80.00")}),
            ("IMP-AWB-ORIGIN", {"rate_per_shipment": Decimal("25.00")}),
            ("IMP-AGENCY-ORIGIN", {"rate_per_shipment": Decimal("175.00")}),
            ("IMP-CTO-ORIGIN", {"rate_per_kg": Decimal("0.30"), "min_charge": Decimal("30.00")}),
            ("IMP-SCREEN-ORIGIN", {"rate_per_kg": Decimal("0.36"), "min_charge": Decimal("70.00")}),
            ("IMP-PICKUP", {"rate_per_kg": Decimal("0.26"), "min_charge": Decimal("85.00")}),
            ("IMP-FSC-PICKUP", {"percent_rate": Decimal("20.00")}),
        ]
        for code, values in rows:
            ImportCOGS.objects.create(
                product_code=self.products[code],
                origin_airport="BNE",
                destination_airport="POM",
                agent=self.origin_agent,
                currency="AUD",
                valid_from=self.valid_from,
                valid_until=self.valid_until,
                **values,
            )

    def _seed_destination_local_rates(self):
        rows = [
            ("IMP-CLEAR", {"amount": Decimal("300.00"), "rate_type": "FIXED"}),
            ("IMP-AGENCY-DEST", {"amount": Decimal("50.00"), "rate_type": "FIXED"}),
            ("IMP-DOC-DEST", {"amount": Decimal("50.00"), "rate_type": "FIXED"}),
            ("IMP-HANDLING-DEST", {"amount": Decimal("0.05"), "rate_type": "PER_KG", "min_charge": Decimal("50.00")}),
            ("IMP-LOADING-DEST", {"amount": Decimal("50.00"), "rate_type": "FIXED"}),
            ("IMP-CARTAGE-DEST", {"amount": Decimal("0.00"), "rate_type": "FIXED"}),
            ("IMP-FSC-CARTAGE-DEST", {"amount": Decimal("0.00"), "rate_type": "PERCENT"}),
        ]
        for code, values in rows:
            LocalCOGSRate.objects.create(
                product_code=self.products[code],
                location="POM",
                direction="IMPORT",
                agent=self.destination_agent,
                currency="PGK",
                valid_from=self.valid_from,
                valid_until=self.valid_until,
                **values,
            )
            LocalSellRate.objects.create(
                product_code=self.products[code],
                location="POM",
                direction="IMPORT",
                payment_term="COLLECT",
                currency="PGK",
                valid_from=self.valid_from,
                valid_until=self.valid_until,
                **values,
            )


def _create_product(id, code, description, category, default_unit="SHIPMENT"):
    return ProductCode.objects.create(
        id=id,
        code=code,
        description=description,
        domain="IMPORT",
        category=category,
        is_gst_applicable=True,
        gst_treatment="STANDARD",
        gst_rate=Decimal("0.10"),
        gl_revenue_code="4000",
        gl_cost_code="5000",
        default_unit=default_unit,
    )


def _product(code, description, category):
    return ProductCode(code=code, description=description, category=category, domain="IMPORT")


def _stable_json(value):
    if is_dataclass(value):
        return _stable_json(asdict(value))
    if isinstance(value, dict):
        return {key: _stable_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stable_json(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
