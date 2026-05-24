from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Country, Currency
from core.tests.helpers import create_location
from parties.models import Company, Contact
from pricing_v4.models import Agent, Carrier, DomesticCOGS, DomesticSellRate, ImportCOGS, ProductCode, Surcharge
from services.models import ServiceComponent


class QuoteComputeSelectorValidationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="selector-validation",
            password="testpass123",
            role="manager",
        )
        self.client.force_authenticate(self.user)

        aud = Currency.objects.create(code="AUD", name="Australian Dollar", minor_units=2)
        pgk = Currency.objects.create(code="PGK", name="Papua New Guinean Kina", minor_units=2)
        au = Country.objects.create(code="AU", name="Australia", currency=aud)
        pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=pgk)

        self.origin = create_location(code="SYD", name="Sydney", country=au, is_active=True)
        self.destination = create_location(code="POM", name="Port Moresby", country=pg, is_active=True)
        self.domestic_origin = create_location(code="POM", name="Port Moresby Domestic", country=pg, is_active=True)
        self.domestic_destination = create_location(code="LAE", name="Lae", country=pg, is_active=True)
        self.customer = Company.objects.create(name="Selector Customer", company_type="CUSTOMER", is_customer=True)
        self.contact = Contact.objects.create(
            company=self.customer,
            first_name="Sel",
            last_name="Ector",
            email="selector@example.com",
        )
        self.agent_a = Agent.objects.create(
            code="VAL-AG-A",
            name="Validation Agent A",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.agent_b = Agent.objects.create(
            code="VAL-AG-B",
            name="Validation Agent B",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.domestic_agent = Agent.objects.create(
            code="VAL-DOM-AG",
            name="Domestic Validation Agent",
            country_code="PG",
            agent_type="ORIGIN",
        )
        self.domestic_carrier = Carrier.objects.create(
            code="VAL-PX",
            name="Validation Air Niugini",
            carrier_type="AIRLINE",
        )
        self.freight_pc = ProductCode.objects.create(
            id=2660,
            code="IMP-FRT-VALIDATION",
            description="Import Freight Validation",
            domain="IMPORT",
            category="FREIGHT",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="KG",
        )
        ServiceComponent.objects.create(
            code="IMP-FRT-VALIDATION",
            description="Import Freight Validation",
            mode="AIR",
            leg="MAIN",
            category="TRANSPORT",
            unit="KG",
            audience="BOTH",
        )
        self.domestic_freight_pc = ProductCode.objects.create(
            id=3660,
            code="DOM-FRT-AIR",
            description="Domestic Air Freight",
            domain="DOMESTIC",
            category="FREIGHT",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="KG",
        )
        ServiceComponent.objects.create(
            code="DOM-FRT-AIR",
            description="Domestic Air Freight",
            mode="AIR",
            leg="MAIN",
            category="TRANSPORT",
            unit="KG",
            audience="BOTH",
        )
        self.domestic_product_codes = {}
        for product_id, code, description, category, unit in [
            (3661, "DOM-AWB", "AWB Fee", "DOCUMENTATION", "SHIPMENT"),
            (3662, "DOM-DOC", "Documentation Fee", "DOCUMENTATION", "SHIPMENT"),
            (3663, "DOM-TERMINAL", "Terminal Fee", "HANDLING", "SHIPMENT"),
            (3664, "DOM-SECURITY", "Security Surcharge", "SCREENING", "KG"),
            (3665, "DOM-FSC", "Fuel Surcharge", "SURCHARGE", "KG"),
        ]:
            self.domestic_product_codes[code] = ProductCode.objects.create(
                id=product_id,
                code=code,
                description=description,
                domain="DOMESTIC",
                category=category,
                is_gst_applicable=True,
                gst_rate=Decimal("0.10"),
                gl_revenue_code="4100",
                gl_cost_code="5100",
                default_unit="KG" if unit == "KG" else "SHIPMENT",
            )
            ServiceComponent.objects.create(
                code=code,
                description=description,
                mode="AIR",
                leg="ORIGIN",
                category="DOCUMENTATION" if code in {"DOM-AWB", "DOM-DOC"} else "ACCESSORIAL",
                unit=unit,
                audience="BOTH",
            )
        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)

    def _payload(self, **overrides):
        payload = {
            "customer_id": str(self.customer.id),
            "contact_id": str(self.contact.id),
            "mode": "AIR",
            "service_scope": "A2A",
            "origin_location_id": str(self.origin.id),
            "destination_location_id": str(self.destination.id),
            "incoterm": "EXW",
            "payment_term": "COLLECT",
            "dimensions": [
                {
                    "pieces": 1,
                    "length_cm": "10",
                    "width_cm": "10",
                    "height_cm": "10",
                    "gross_weight_kg": "25",
                    "package_type": "Box",
                }
            ],
        }
        payload.update(overrides)
        return payload

    def _domestic_payload(self, **overrides):
        payload = self._payload(
            service_scope="D2D",
            origin_location_id=str(self.domestic_origin.id),
            destination_location_id=str(self.domestic_destination.id),
            incoterm="DAP",
            payment_term="PREPAID",
        )
        payload.update(overrides)
        return payload

    def _seed_domestic_sell(self):
        return DomesticSellRate.objects.create(
            product_code=self.domestic_freight_pc,
            origin_zone="POM",
            destination_zone="LAE",
            currency="PGK",
            rate_per_kg=Decimal("9.00"),
            min_charge=Decimal("120.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

    def _seed_domestic_cogs(self, *, agent=None, carrier=None, rate="7.00"):
        return DomesticCOGS.objects.create(
            product_code=self.domestic_freight_pc,
            origin_zone="POM",
            destination_zone="LAE",
            agent=agent,
            carrier=carrier,
            currency="PGK",
            rate_per_kg=Decimal(rate),
            min_charge=Decimal("100.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

    def _seed_domestic_surcharge(
        self,
        *,
        code: str,
        rate_side: str,
        rate_type: str,
        amount: str,
        min_charge: str | None = None,
    ):
        return Surcharge.objects.create(
            product_code=self.domestic_product_codes[code],
            service_type="DOMESTIC_AIR",
            rate_side=rate_side,
            rate_type=rate_type,
            amount=Decimal(amount),
            min_charge=Decimal(min_charge) if min_charge else None,
            currency="PGK",
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_active=True,
        )

    def test_quote_compute_requires_buy_currency_when_import_cogs_are_multicurrency(self):
        for currency, amount in [("AUD", "4.80"), ("PGK", "12.50")]:
            ImportCOGS.objects.create(
                product_code=self.freight_pc,
                origin_airport="SYD",
                destination_airport="POM",
                agent=self.agent_a,
                currency=currency,
                rate_per_kg=Decimal(amount),
                valid_from=self.valid_from,
                valid_until=self.valid_until,
            )

        response = self.client.post("/api/v3/quotes/compute/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "RATE_SELECTION_MISSING_DIMENSION")
        self.assertEqual(response.data["component"], "FREIGHT")
        self.assertEqual(response.data["missing_dimensions"], ["buy_currency"])
        self.assertEqual(response.data["resolved_dimensions"]["agent_id"], self.agent_a.id)
        self.assertIsNone(response.data["resolved_dimensions"]["buy_currency"])

    def test_domestic_quote_with_one_matching_cogs_rate_succeeds(self):
        selected = self._seed_domestic_cogs(carrier=self.domestic_carrier, rate="7.00")
        self._seed_domestic_sell()

        response = self.client.post("/api/v3/quotes/compute/", self._domestic_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["latest_version"]["payload_json"]["resolved_dimensions"]["carrier_id"],
            self.domestic_carrier.id,
        )
        line = response.data["latest_version"]["lines"][0]
        self.assertEqual(line["cost_source"], f"DomesticCOGS #{selected.pk}")

    def test_domestic_quote_with_multiple_cogs_rates_requires_counterparty(self):
        self._seed_domestic_cogs(carrier=self.domestic_carrier, rate="7.00")
        self._seed_domestic_cogs(agent=self.domestic_agent, rate="8.00")
        self._seed_domestic_sell()

        response = self.client.post("/api/v3/quotes/compute/", self._domestic_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Multiple Domestic COGS rates matched", response.data["detail"])
        self.assertEqual(response.data["component"], "FREIGHT")
        self.assertEqual(response.data["missing_dimensions"], ["agent_id", "carrier_id"])
        self.assertEqual(response.data["conflicting_rows"][0]["currency"], "PGK")

    def test_domestic_quote_with_selected_counterparty_resolves(self):
        self._seed_domestic_cogs(carrier=self.domestic_carrier, rate="7.00")
        selected = self._seed_domestic_cogs(agent=self.domestic_agent, rate="8.00")
        self._seed_domestic_sell()

        response = self.client.post(
            "/api/v3/quotes/compute/",
            self._domestic_payload(agent_id=self.domestic_agent.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        line = response.data["latest_version"]["lines"][0]
        self.assertEqual(line["cost_source"], f"DomesticCOGS #{selected.pk}")
        self.assertEqual(line["cost_pgk"], "200.00")

    def test_domestic_quote_with_selected_carrier_resolves_when_multiple_cogs_match(self):
        selected = self._seed_domestic_cogs(carrier=self.domestic_carrier, rate="7.00")
        self._seed_domestic_cogs(agent=self.domestic_agent, rate="8.00")
        self._seed_domestic_sell()

        response = self.client.post(
            "/api/v3/quotes/compute/",
            self._domestic_payload(carrier_id=self.domestic_carrier.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        line = response.data["latest_version"]["lines"][0]
        self.assertEqual(line["cost_source"], f"DomesticCOGS #{selected.pk}")
        self.assertEqual(line["cost_pgk"], "175.00")

    def test_domestic_quote_includes_standard_domestic_air_surcharges(self):
        selected = DomesticCOGS.objects.create(
            product_code=self.domestic_freight_pc,
            origin_zone="POM",
            destination_zone="LAE",
            agent=self.domestic_agent,
            currency="PGK",
            rate_per_kg=Decimal("6.10"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        DomesticSellRate.objects.create(
            product_code=self.domestic_freight_pc,
            origin_zone="POM",
            destination_zone="LAE",
            currency="PGK",
            rate_per_kg=Decimal("7.30"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        self._seed_domestic_surcharge(code="DOM-DOC", rate_side="COGS", rate_type="FLAT", amount="35.00")
        self._seed_domestic_surcharge(code="DOM-TERMINAL", rate_side="COGS", rate_type="FLAT", amount="35.00")
        self._seed_domestic_surcharge(
            code="DOM-SECURITY",
            rate_side="COGS",
            rate_type="PER_KG",
            amount="0.20",
            min_charge="5.00",
        )
        self._seed_domestic_surcharge(code="DOM-FSC", rate_side="COGS", rate_type="PER_KG", amount="0.50")
        self._seed_domestic_surcharge(code="DOM-AWB", rate_side="SELL", rate_type="FLAT", amount="70.00")
        self._seed_domestic_surcharge(
            code="DOM-SECURITY",
            rate_side="SELL",
            rate_type="PER_KG",
            amount="0.20",
            min_charge="5.00",
        )
        self._seed_domestic_surcharge(code="DOM-FSC", rate_side="SELL", rate_type="PER_KG", amount="0.70")

        payload = self._domestic_payload(
            dimensions=[
                {
                    "pieces": 1,
                    "length_cm": "10",
                    "width_cm": "10",
                    "height_cm": "10",
                    "gross_weight_kg": "10",
                    "package_type": "Box",
                }
            ],
        )
        response = self.client.post("/api/v3/quotes/compute/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        lines = {
            line["service_component"]["code"]: line
            for line in response.data["latest_version"]["lines"]
        }

        self.assertEqual(lines["DOM-FRT-AIR"]["cost_source"], f"DomesticCOGS #{selected.pk}")
        self.assertEqual(lines["DOM-FRT-AIR"]["cost_pgk"], "61.00")
        self.assertEqual(lines["DOM-FRT-AIR"]["sell_pgk"], "73.00")
        self.assertEqual(lines["DOM-AWB"]["sell_pgk"], "70.00")
        self.assertEqual(lines["DOM-AWB"]["cost_pgk"], "0.00")
        self.assertEqual(lines["DOM-DOC"]["cost_pgk"], "35.00")
        self.assertEqual(lines["DOM-DOC"]["sell_pgk"], "0.00")
        self.assertEqual(lines["DOM-TERMINAL"]["cost_pgk"], "35.00")
        self.assertEqual(lines["DOM-TERMINAL"]["sell_pgk"], "0.00")
        self.assertEqual(lines["DOM-SECURITY"]["cost_pgk"], "5.00")
        self.assertEqual(lines["DOM-SECURITY"]["sell_pgk"], "5.00")
        self.assertEqual(lines["DOM-FSC"]["cost_pgk"], "5.00")
        self.assertEqual(lines["DOM-FSC"]["sell_pgk"], "7.00")

        totals = response.data["latest_version"]["totals"]
        self.assertEqual(totals["total_cost_pgk"], "141.00")
        self.assertEqual(totals["total_sell_pgk"], "155.00")
        self.assertEqual(totals["total_sell_pgk_incl_gst"], "170.50")

    def test_quote_compute_requires_agent_when_counterparty_specific_import_cogs_exist(self):
        for agent in [self.agent_a, self.agent_b]:
            ImportCOGS.objects.create(
                product_code=self.freight_pc,
                origin_airport="SYD",
                destination_airport="POM",
                agent=agent,
                currency="AUD",
                rate_per_kg=Decimal("4.80"),
                valid_from=self.valid_from,
                valid_until=self.valid_until,
            )

        response = self.client.post("/api/v3/quotes/compute/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "RATE_SELECTION_MISSING_DIMENSION")
        self.assertEqual(response.data["component"], "FREIGHT")
        self.assertEqual(response.data["missing_dimensions"], ["agent_id"])
        self.assertEqual(response.data["resolved_dimensions"]["buy_currency"], "AUD")
        self.assertIsNone(response.data["resolved_dimensions"]["agent_id"])

    def test_quote_compute_allows_component_level_resolution_when_global_path_is_not_shared(self):
        origin_pc = ProductCode.objects.create(
            id=2661,
            code="IMP-ORG-HNDL-VAL",
            description="Import Origin Validation",
            domain="IMPORT",
            category="HANDLING",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        destination_pc = ProductCode.objects.create(
            id=2662,
            code="IMP-CTG-DST-VAL",
            description="Import Destination Validation",
            domain="IMPORT",
            category="CARTAGE",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        ServiceComponent.objects.create(
            code="IMP-ORG-HNDL-VAL",
            description="Import Origin Validation",
            mode="AIR",
            leg="ORIGIN",
            category="ACCESSORIAL",
            unit="SHIPMENT",
            audience="BOTH",
        )
        ServiceComponent.objects.create(
            code="IMP-CTG-DST-VAL",
            description="Import Destination Validation",
            mode="AIR",
            leg="DESTINATION",
            category="ACCESSORIAL",
            unit="SHIPMENT",
            audience="BOTH",
        )

        ImportCOGS.objects.create(
            product_code=self.freight_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent_a,
            currency="AUD",
            rate_per_kg=Decimal("4.80"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        ImportCOGS.objects.create(
            product_code=origin_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent_a,
            currency="AUD",
            rate_per_shipment=Decimal("60.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        ImportCOGS.objects.create(
            product_code=destination_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=self.agent_b,
            currency="AUD",
            rate_per_shipment=Decimal("95.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        response = self.client.post(
            "/api/v3/quotes/compute/",
            self._payload(service_scope="D2D"),
            format="json",
        )

        self.assertNotEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotEqual(response.data.get("error_code"), "RATE_RESOLUTION_MISSING_COVERAGE")

    def test_import_quote_resolves_different_counterparty_types_for_different_legs(self):
        carrier_c = Carrier.objects.create(code="VAL-CX", name="Carrier CX", carrier_type="AIRLINE")
        agent_c = Agent.objects.create(code="VAL-AG-C", name="Agent CX", country_code="AU", agent_type="ORIGIN")

        # Freight component uses carrier
        ImportCOGS.objects.create(
            product_code=self.freight_pc,
            origin_airport="SYD",
            destination_airport="POM",
            carrier=carrier_c,
            currency="AUD",
            rate_per_kg=Decimal("5.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # Origin-local component uses agent
        origin_pc = ProductCode.objects.create(
            id=2671,
            code="IMP-AWB-ORIGIN-TEST",
            description="AWB Fee Origin",
            domain="IMPORT",
            category="DOCUMENTATION",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        ServiceComponent.objects.create(
            code="IMP-AWB-ORIGIN-TEST",
            description="AWB Fee Origin Test",
            mode="AIR",
            leg="ORIGIN",
            category="DOCUMENTATION",
            unit="SHIPMENT",
            audience="BOTH",
        )
        ImportCOGS.objects.create(
            product_code=origin_pc,
            origin_airport="SYD",
            destination_airport=None,
            agent=agent_c,
            currency="AUD",
            rate_per_shipment=Decimal("30.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # D2A service scope requires both FREIGHT and ORIGIN_LOCAL
        response = self.client.post(
            "/api/v3/quotes/compute/",
            self._payload(service_scope="D2A"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        res_dims = response.data["latest_version"]["payload_json"]["resolved_dimensions"]
        self.assertEqual(res_dims["carrier_id"], carrier_c.id)
        self.assertEqual(res_dims["agent_id"], agent_c.id)

    def test_import_quote_resolves_null_destination_airport_rows(self):
        agent_c = Agent.objects.create(code="VAL-AG-D", name="Agent D", country_code="AU", agent_type="ORIGIN")

        # Freight component uses agent_c
        ImportCOGS.objects.create(
            product_code=self.freight_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=agent_c,
            currency="AUD",
            rate_per_kg=Decimal("5.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # Origin-local component uses agent_c and destination_airport=None
        origin_pc = ProductCode.objects.create(
            id=2672,
            code="IMP-DOC-ORIGIN-TEST",
            description="Doc Fee Origin",
            domain="IMPORT",
            category="DOCUMENTATION",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        ServiceComponent.objects.create(
            code="IMP-DOC-ORIGIN-TEST",
            description="Doc Fee Origin Test",
            mode="AIR",
            leg="ORIGIN",
            category="DOCUMENTATION",
            unit="SHIPMENT",
            audience="BOTH",
        )
        ImportCOGS.objects.create(
            product_code=origin_pc,
            origin_airport="SYD",
            destination_airport=None,
            agent=agent_c,
            currency="AUD",
            rate_per_shipment=Decimal("25.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # D2A service scope requires both FREIGHT and ORIGIN_LOCAL
        response = self.client.post(
            "/api/v3/quotes/compute/",
            self._payload(service_scope="D2A"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        lines = response.data["latest_version"]["lines"]
        origin_lines = [l for l in lines if l["service_component"]["code"] == "IMP-DOC-ORIGIN-TEST"]
        self.assertEqual(len(origin_lines), 1)
        self.assertEqual(float(origin_lines[0]["cost_fcy"]), 25.0)
        self.assertEqual(origin_lines[0]["cost_fcy_currency"], "AUD")

    def test_bne_origin_local_seeded_rates_integration(self):
        from core.models import Location
        bne_loc = Location.objects.filter(code="BNE").first()
        if not bne_loc:
            from core.models import Country
            au_country = Country.objects.get(code="AU")
            bne_loc = create_location(code="BNE", name="Brisbane", country=au_country, is_active=True)

        # Seed freight COGS for BNE -> POM
        carrier = Carrier.objects.create(
            code="BNE-CX",
            name="BNE Carrier",
            carrier_type="AIRLINE",
        )
        ImportCOGS.objects.create(
            product_code=self.freight_pc,
            origin_airport="BNE",
            destination_airport="POM",
            carrier=carrier,
            currency="AUD",
            rate_per_kg=Decimal("5.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # Seed ProductCode, ServiceComponent, and COGS rate for IMP-DOC-ORIGIN
        doc_origin_pc = ProductCode.objects.create(
            id=2010,
            code="IMP-DOC-ORIGIN",
            description="Import Documentation Fee Origin",
            domain="IMPORT",
            category="DOCUMENTATION",
            is_gst_applicable=True,
            gst_rate=Decimal("0.10"),
            gl_revenue_code="4100",
            gl_cost_code="5100",
            default_unit="SHIPMENT",
        )
        ServiceComponent.objects.create(
            code="IMP-DOC-ORIGIN",
            description="Import Documentation Fee Origin",
            mode="AIR",
            leg="ORIGIN",
            category="DOCUMENTATION",
            unit="SHIPMENT",
            audience="BOTH",
        )
        ImportCOGS.objects.create(
            product_code=doc_origin_pc,
            origin_airport="BNE",
            destination_airport=None,
            agent=self.agent_a,
            currency="AUD",
            rate_per_shipment=Decimal("20.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        payload = self._payload(
            origin_location_id=str(bne_loc.id),
            destination_location_id=str(self.destination.id),
            service_scope="D2A",
        )

        response = self.client.post("/api/v3/quotes/compute/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        lines = response.data["latest_version"]["lines"]
        
        freight_lines = [l for l in lines if l["service_component"]["leg"] == "MAIN"]
        origin_lines = [l for l in lines if l["service_component"]["leg"] == "ORIGIN"]
        
        self.assertTrue(len(freight_lines) > 0)
        self.assertTrue(len(origin_lines) > 0)

    def test_bne_pom_import_100kg_regression(self):
        from core.models import Location, FxSnapshot, Policy
        from django.utils import timezone
        from pricing_v4.models import LocalCOGSRate, LocalSellRate

        # 1. Ensure BNE location exists
        bne_loc = Location.objects.filter(code="BNE").first()
        if not bne_loc:
            from core.models import Country
            au_country = Country.objects.get(code="AU")
            bne_loc = create_location(code="BNE", name="Brisbane", country=au_country, is_active=True)

        # 2. Seed FxSnapshot and Policy
        FxSnapshot.objects.all().delete()
        FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="BSP",
            rates={"AUD": {"tt_buy": "0.3218", "tt_sell": "0.30571"}},
            caf_percent=Decimal("0.05"),
        )
        Policy.objects.all().delete()
        Policy.objects.create(
            name="Test Policy",
            caf_import_pct=Decimal("0.05"),
            caf_export_pct=Decimal("0.10"),
            margin_pct=Decimal("0.20"),
            effective_from=timezone.now().date(),
            effective_to=(timezone.now() + timedelta(days=30)).date(),
            is_active=True,
        )

        # 3. Create ProductCodes and ServiceComponents for IMP accessorials/freight/destination
        pcs_data = [
            (2001, "IMP-FRT-AIR", "Import Air Freight", "FREIGHT", "KG", "MAIN", "TRANSPORT"),
            (2050, "IMP-PICKUP", "Pick Up", "ACCESSORIAL", "SHIPMENT", "ORIGIN", "ACCESSORIAL"),
            (2060, "IMP-FSC-PICKUP", "FSC Pick Up", "SURCHARGE", "SHIPMENT", "ORIGIN", "ACCESSORIAL"),
            (2040, "IMP-SCREEN-ORIGIN", "X-Ray Screening Fee", "ACCESSORIAL", "SHIPMENT", "ORIGIN", "ACCESSORIAL"),
            (2030, "IMP-CTO-ORIGIN", "CTO Fee", "ACCESSORIAL", "SHIPMENT", "ORIGIN", "ACCESSORIAL"),
            (2010, "IMP-DOC-ORIGIN", "Export Document Fee", "DOCUMENTATION", "SHIPMENT", "ORIGIN", "DOCUMENTATION"),
            (2012, "IMP-AGENCY-ORIGIN", "Export Agency Fee", "ACCESSORIAL", "SHIPMENT", "ORIGIN", "ACCESSORIAL"),
            (2011, "IMP-AWB-ORIGIN", "Origin AWB Fee", "DOCUMENTATION", "SHIPMENT", "ORIGIN", "DOCUMENTATION"),
            # Destination ProductCodes
            (2020, "IMP-CLEAR", "Customs Clearance", "CLEARANCE", "SHIPMENT", "DESTINATION", "ACCESSORIAL"),
            (2021, "IMP-AGENCY-DEST", "Agency Fee Destination", "ACCESSORIAL", "SHIPMENT", "DESTINATION", "ACCESSORIAL"),
            (2022, "IMP-DOC-DEST", "Documentation Fee Destination", "DOCUMENTATION", "SHIPMENT", "DESTINATION", "ACCESSORIAL"),
            (2070, "IMP-HANDLING-DEST", "Handling Fee Destination", "ACCESSORIAL", "SHIPMENT", "DESTINATION", "ACCESSORIAL"),
            (2071, "IMP-LOADING-DEST", "Loading Fee Destination", "ACCESSORIAL", "SHIPMENT", "DESTINATION", "ACCESSORIAL"),
            (2072, "IMP-CARTAGE-DEST", "Cartage Destination", "CARTAGE", "SHIPMENT", "DESTINATION", "ACCESSORIAL"),
            (2080, "IMP-FSC-CARTAGE-DEST", "Fuel Surcharge Destination", "SURCHARGE", "SHIPMENT", "DESTINATION", "ACCESSORIAL"),
        ]

        pcs = {}
        for pid, code, desc, cat, unit, leg, sc_cat in pcs_data:
            ProductCode.objects.filter(id=pid).delete()
            ProductCode.objects.filter(code=code).delete()
            ServiceComponent.objects.filter(code=code).delete()

            pcs[code] = ProductCode.objects.create(
                id=pid,
                code=code,
                description=desc,
                domain="IMPORT",
                category=cat,
                is_gst_applicable=True,
                gst_rate=Decimal("0.10"),
                gl_revenue_code="4100",
                gl_cost_code="5100",
                default_unit=unit,
            )
            ServiceComponent.objects.create(
                code=code,
                description=desc,
                mode="AIR",
                leg=leg,
                category=sc_cat,
                unit=unit,
                audience="BOTH",
            )

        # 4. Seed ImportCOGS rates matching standard seed card for BNE
        # Freight BNE -> POM
        carrier = Carrier.objects.create(
            code="VAL-PX-FRT",
            name="Air Niugini Freight",
            carrier_type="AIRLINE",
        )
        ImportCOGS.objects.create(
            product_code=pcs["IMP-FRT-AIR"],
            origin_airport="BNE",
            destination_airport="POM",
            carrier=carrier,
            scope="LANE",
            currency="AUD",
            min_charge=Decimal("350.00"),
            weight_breaks=[
                {"min_kg": 0, "rate": "7.50"},
                {"min_kg": 45, "rate": "7.35"},
                {"min_kg": 100, "rate": "7.00"},
                {"min_kg": 250, "rate": "6.75"},
                {"min_kg": 500, "rate": "6.45"},
                {"min_kg": 1000, "rate": "6.10"},
            ],
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # Pick Up BNE -> None
        ImportCOGS.objects.create(
            product_code=pcs["IMP-PICKUP"],
            origin_airport="BNE",
            destination_airport=None,
            agent=self.agent_a,
            scope="ORIGIN",
            currency="AUD",
            min_charge=Decimal("85.00"),
            rate_per_kg=Decimal("0.26"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # FSC Pick Up BNE -> None
        ImportCOGS.objects.create(
            product_code=pcs["IMP-FSC-PICKUP"],
            origin_airport="BNE",
            destination_airport=None,
            agent=self.agent_a,
            scope="ORIGIN",
            currency="AUD",
            percent_rate=Decimal("20.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # X-Ray Screening BNE -> None
        ImportCOGS.objects.create(
            product_code=pcs["IMP-SCREEN-ORIGIN"],
            origin_airport="BNE",
            destination_airport=None,
            agent=self.agent_a,
            scope="ORIGIN",
            currency="AUD",
            min_charge=Decimal("70.00"),
            rate_per_kg=Decimal("0.382"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # CTO Fee BNE -> None
        ImportCOGS.objects.create(
            product_code=pcs["IMP-CTO-ORIGIN"],
            origin_airport="BNE",
            destination_airport=None,
            agent=self.agent_a,
            scope="ORIGIN",
            currency="AUD",
            rate_per_shipment=Decimal("30.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # Export Document Fee BNE -> None
        ImportCOGS.objects.create(
            product_code=pcs["IMP-DOC-ORIGIN"],
            origin_airport="BNE",
            destination_airport=None,
            agent=self.agent_a,
            scope="ORIGIN",
            currency="AUD",
            rate_per_shipment=Decimal("82.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # Export Agency Fee BNE -> None
        ImportCOGS.objects.create(
            product_code=pcs["IMP-AGENCY-ORIGIN"],
            origin_airport="BNE",
            destination_airport=None,
            agent=self.agent_a,
            scope="ORIGIN",
            currency="AUD",
            rate_per_shipment=Decimal("175.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # Origin AWB Fee BNE -> None
        ImportCOGS.objects.create(
            product_code=pcs["IMP-AWB-ORIGIN"],
            origin_airport="BNE",
            destination_airport=None,
            agent=self.agent_a,
            scope="ORIGIN",
            currency="AUD",
            rate_per_shipment=Decimal("30.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        # Create EFM PNG Agent
        efm_pg, _ = Agent.objects.get_or_create(
            code='EFM-PG',
            defaults={
                'name': 'EFM PNG',
                'country_code': 'PG',
                'agent_type': 'DESTINATION'
            }
        )

        # Seed Destination Local Charges in LocalCOGSRate & LocalSellRate
        dest_codes = ["IMP-CLEAR", "IMP-AGENCY-DEST", "IMP-DOC-DEST", "IMP-HANDLING-DEST", "IMP-LOADING-DEST", "IMP-CARTAGE-DEST", "IMP-FSC-CARTAGE-DEST"]
        for code in dest_codes:
            LocalCOGSRate.objects.create(
                product_code=pcs[code],
                location="POM",
                direction="IMPORT",
                scope="DESTINATION",
                agent=efm_pg,
                currency="PGK",
                rate_type="FLAT",
                amount=Decimal("50.00"),
                valid_from=self.valid_from,
                valid_until=self.valid_until,
            )
            LocalSellRate.objects.create(
                product_code=pcs[code],
                location="POM",
                direction="IMPORT",
                payment_term="ANY",
                scope="DESTINATION",
                currency="PGK",
                rate_type="FLAT",
                amount=Decimal("60.00"),
                valid_from=self.valid_from,
                valid_until=self.valid_until,
            )

        # 5. Build D2D, COLLECT, 100kg Import Quote Payload
        payload = self._payload(
            origin_location_id=str(bne_loc.id),
            destination_location_id=str(self.destination.id),
            service_scope="D2D",
            incoterm="D2D",
            payment_term="COLLECT",
            buy_currency="AUD",
            dimensions=[
                {
                    "pieces": 1,
                    "length_cm": "10",
                    "width_cm": "10",
                    "height_cm": "10",
                    "gross_weight_kg": "100",
                    "package_type": "Pallet",
                }
            ],
        )

        # 6. Request computation
        response = self.client.post("/api/v3/quotes/compute/", payload, format="json")

        # 7. Assertions
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(response.data["quote_result"]["spot_required"])
        self.assertEqual(response.data["quote_result"]["missing_components"], [])
        self.assertNotEqual(response.data["status"], "INCOMPLETE")
        self.assertNotEqual(response.data["latest_version"]["status"], "INCOMPLETE")

        # Verify that all component amounts match expected BUY values in AUD
        lines = response.data["latest_version"]["lines"]
        returned_product_codes = {line["product_code"] for line in lines}
        expected_existing_codes = {
            "IMP-FRT-AIR",
            "IMP-PICKUP",
            "IMP-SCREEN-ORIGIN",
            "IMP-CTO-ORIGIN",
            "IMP-DOC-ORIGIN",
            "IMP-AGENCY-ORIGIN",
            "IMP-AWB-ORIGIN",
        }
        self.assertTrue(expected_existing_codes.issubset(returned_product_codes))

        def get_line_buy(prod_code):
            for l in lines:
                if l["product_code"] == prod_code:
                    return Decimal(str(l["cost_fcy"] if l["cost_fcy"] is not None else l["cost_pgk"]))
            return None

        # Air Freight: 100kg * 7.00 = 700.00
        self.assertEqual(get_line_buy("IMP-FRT-AIR"), Decimal("700.00"))
        # Pick Up: min applies = 85.00
        self.assertEqual(get_line_buy("IMP-PICKUP"), Decimal("85.00"))
        # X-Ray Screening: min applies = 70.00
        self.assertEqual(get_line_buy("IMP-SCREEN-ORIGIN"), Decimal("70.00"))
        # CTO Fee: 30.00
        self.assertEqual(get_line_buy("IMP-CTO-ORIGIN"), Decimal("30.00"))
        # Export Document Fee: 82.00
        self.assertEqual(get_line_buy("IMP-DOC-ORIGIN"), Decimal("82.00"))
        # Export Agency Fee: 175.00
        self.assertEqual(get_line_buy("IMP-AGENCY-ORIGIN"), Decimal("175.00"))
        # Origin AWB Fee: 30.00
        self.assertEqual(get_line_buy("IMP-AWB-ORIGIN"), Decimal("30.00"))

        # Verify FX details match snapshot rate and CAF
        fx_applied = response.data["quote_result"]["fx_applied"]
        self.assertTrue(fx_applied["applied"])
        self.assertEqual(fx_applied["from_currency"], "AUD")
        self.assertEqual(fx_applied["to_currency"], "PGK")
        self.assertEqual(Decimal(str(fx_applied["base_rate"])), Decimal("0.3218"))
        self.assertEqual(Decimal(str(fx_applied["effective_fx_after_caf"])), Decimal("0.30571"))
