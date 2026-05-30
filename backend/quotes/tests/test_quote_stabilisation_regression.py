# backend/quotes/tests/test_quote_stabilisation_regression.py

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Country, Currency
from core.tests.helpers import create_location
from parties.models import Company, Contact
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
from services.models import ServiceComponent
from pricing_v4.tests.test_export_engine import seed_all_export_product_codes


class CoreQuoteStabilisationRegressionTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="regression-runner",
            password="testpass123",
            role="manager",
        )
        self.client.force_authenticate(self.user)

        # 1. Currencies & Countries
        self.aud = Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar", "minor_units": 2})[0]
        self.pgk = Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinean Kina", "minor_units": 2})[0]
        self.usd = Currency.objects.get_or_create(code="USD", defaults={"name": "United States Dollar", "minor_units": 2})[0]
        self.sgd = Currency.objects.get_or_create(code="SGD", defaults={"name": "Singapore Dollar", "minor_units": 2})[0]

        self.au = Country.objects.get_or_create(code="AU", defaults={"name": "Australia", "currency": self.aud})[0]
        self.pg = Country.objects.get_or_create(code="PG", defaults={"name": "Papua New Guinea", "currency": self.pgk})[0]
        self.sg = Country.objects.get_or_create(code="SG", defaults={"name": "Singapore", "currency": self.sgd})[0]

        # 2. Locations
        self.bne = create_location(code="BNE", name="Brisbane", country=self.au, is_active=True)
        self.pom = create_location(code="POM", name="Port Moresby", country=self.pg, is_active=True)
        self.lae = create_location(code="LAE", name="Lae", country=self.pg, is_active=True)
        self.syd = create_location(code="SYD", name="Sydney", country=self.au, is_active=True)
        self.sin = create_location(code="SIN", name="Singapore", country=self.sg, is_active=True)

        # 3. Parties
        self.customer = Company.objects.create(name="Regression Customer", company_type="CUSTOMER", is_customer=True)
        self.contact = Contact.objects.create(
            company=self.customer,
            first_name="Reg",
            last_name="Gression",
            email="regression@example.com",
        )
        
        self.agent_bne = Agent.objects.create(
            code="REG-AG-BNE",
            name="BNE Agent",
            country_code="AU",
            agent_type="ORIGIN",
        )
        self.agent_pom = Agent.objects.create(
            code="REG-AG-POM",
            name="POM Agent",
            country_code="PG",
            agent_type="DESTINATION",
        )

        self.carrier_px = Carrier.objects.create(
            code="REG-PX",
            name="Air Niugini",
            carrier_type="AIRLINE",
        )

        # 4. Product Codes
        self.imp_freight_pc = ProductCode.objects.get_or_create(
            id=5001,
            defaults={
                "code": "IMP-FRT-AIR",
                "description": "Import Air Freight",
                "domain": "IMPORT",
                "category": "FREIGHT",
                "is_gst_applicable": True,
                "gst_rate": Decimal("0.10"),
                "gl_revenue_code": "4100",
                "gl_cost_code": "5100",
                "default_unit": "KG",
            }
        )[0]

        self.imp_origin_pc = ProductCode.objects.get_or_create(
            id=5002,
            defaults={
                "code": "IMP-ORIGIN-HANDLING",
                "description": "Import Origin Handling",
                "domain": "IMPORT",
                "category": "HANDLING",
                "is_gst_applicable": False,
                "gl_revenue_code": "4100",
                "gl_cost_code": "5100",
                "default_unit": "SHIPMENT",
            }
        )[0]

        self.imp_dest_pc = ProductCode.objects.get_or_create(
            id=5003,
            defaults={
                "code": "IMP-CARTAGE-DEST",
                "description": "Import Destination Delivery",
                "domain": "IMPORT",
                "category": "CARTAGE",
                "is_gst_applicable": True,
                "gst_rate": Decimal("0.10"),
                "gl_revenue_code": "4100",
                "gl_cost_code": "5100",
                "default_unit": "SHIPMENT",
            }
        )[0]

        # Seed all export product codes dynamically using the helper to satisfy ExportPricingEngine requirements
        seed_all_export_product_codes()
        self.exp_freight_pc = ProductCode.objects.get(code="EXP-FRT-AIR")
        self.exp_origin_pc = ProductCode.objects.get(code="EXP-DOC")
        self.exp_dest_pc = ProductCode.objects.get(code="EXP-CLEAR-DEST")

        self.dom_freight_pc = ProductCode.objects.get_or_create(
            id=5007,
            defaults={
                "code": "DOM-FRT-AIR",
                "description": "Domestic Air Freight",
                "domain": "DOMESTIC",
                "category": "FREIGHT",
                "is_gst_applicable": True,
                "gst_rate": Decimal("0.10"),
                "gl_revenue_code": "4100",
                "gl_cost_code": "5100",
                "default_unit": "KG",
            }
        )[0]

        # 5. Service Components
        ServiceComponent.objects.get_or_create(
            code="IMP-FRT-AIR",
            defaults={"description": "Import Air Freight", "mode": "AIR", "leg": "MAIN", "category": "TRANSPORT", "unit": "KG", "audience": "BOTH"}
        )
        ServiceComponent.objects.get_or_create(
            code="IMP-ORIGIN-HANDLING",
            defaults={"description": "Import Origin Handling", "mode": "AIR", "leg": "ORIGIN", "category": "ACCESSORIAL", "unit": "SHIPMENT", "audience": "BOTH"}
        )
        ServiceComponent.objects.get_or_create(
            code="IMP-CARTAGE-DEST",
            defaults={"description": "Import Destination Delivery", "mode": "AIR", "leg": "DESTINATION", "category": "CARTAGE", "unit": "SHIPMENT", "audience": "BOTH"}
        )
        ServiceComponent.objects.get_or_create(
            code="EXP-FRT-AIR",
            defaults={"description": "Export Air Freight", "mode": "AIR", "leg": "MAIN", "category": "TRANSPORT", "unit": "KG", "audience": "BOTH"}
        )
        ServiceComponent.objects.get_or_create(
            code="EXP-DOC",
            defaults={"description": "Export Documentation", "mode": "AIR", "leg": "ORIGIN", "category": "DOCUMENTATION", "unit": "SHIPMENT", "audience": "BOTH"}
        )
        ServiceComponent.objects.get_or_create(
            code="EXP-CLEAR-DEST",
            defaults={"description": "Export Dest Clearance", "mode": "AIR", "leg": "DESTINATION", "category": "ACCESSORIAL", "unit": "SHIPMENT", "audience": "BOTH"}
        )
        ServiceComponent.objects.get_or_create(
            code="DOM-FRT-AIR",
            defaults={"description": "Domestic Air Freight", "mode": "AIR", "leg": "MAIN", "category": "TRANSPORT", "unit": "KG", "audience": "BOTH"}
        )

        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)

    def _payload(self, origin, destination, scope, payment_term, incoterm, **overrides):
        payload = {
            "customer_id": str(self.customer.id),
            "contact_id": str(self.contact.id),
            "mode": "AIR",
            "service_scope": scope,
            "origin_location_id": str(origin.id),
            "destination_location_id": str(destination.id),
            "incoterm": incoterm,
            "payment_term": payment_term,
            "dimensions": [
                {
                    "pieces": 1,
                    "length_cm": "10",
                    "width_cm": "10",
                    "height_cm": "10",
                    "gross_weight_kg": "20",
                    "package_type": "Box",
                }
            ],
            "commodity_code": "GCR",
        }
        payload.update(overrides)
        return payload

    # =========================================================================
    # Scenario 1: Import COLLECT BNE → POM D2D with complete rates
    # =========================================================================
    def test_import_collect_complete_rates_standard_quote(self):
        # 1. Freight: BNE → POM ImportCOGS / ImportSellRate
        ImportCOGS.objects.create(
            product_code=self.imp_freight_pc, origin_airport="BNE", destination_airport="POM",
            agent=self.agent_bne, currency="AUD", rate_per_kg=Decimal("4.50"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        ImportSellRate.objects.create(
            product_code=self.imp_freight_pc, origin_airport="BNE", destination_airport="POM",
            currency="PGK", rate_per_kg=Decimal("12.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        # 2. Origin Local: BNE-side local import rates
        LocalCOGSRate.objects.create(
            product_code=self.imp_origin_pc, location="BNE", direction="IMPORT",
            agent=self.agent_bne, currency="AUD", rate_type="FIXED", amount=Decimal("50.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.imp_origin_pc, location="BNE", direction="IMPORT",
            payment_term="COLLECT", currency="PGK", rate_type="FIXED", amount=Decimal("150.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        # 3. Destination Local: POM-side local import rates
        LocalCOGSRate.objects.create(
            product_code=self.imp_dest_pc, location="POM", direction="IMPORT",
            agent=self.agent_pom, currency="PGK", rate_type="FIXED", amount=Decimal("70.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.imp_dest_pc, location="POM", direction="IMPORT",
            payment_term="COLLECT", currency="PGK", rate_type="FIXED", amount=Decimal("200.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        # Evaluate Trigger first
        eval_payload = {
            "origin_country": "AU", "destination_country": "PG",
            "origin_airport": "BNE", "destination_airport": "POM",
            "service_scope": "D2D", "payment_term": "COLLECT",
            "commodity": "GCR",
            "agent_id": self.agent_bne.id, "buy_currency": "AUD"
        }
        eval_res = self.client.post("/api/v3/spot/evaluate-trigger/", eval_payload, format="json")
        self.assertEqual(eval_res.status_code, status.HTTP_200_OK)
        self.assertFalse(eval_res.json()["is_spot_required"])

        # Create Standard Quote
        payload = self._payload(self.bne, self.pom, "D2D", "COLLECT", "EXW", agent_id=self.agent_bne.id, buy_currency="AUD")
        res = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "DRAFT")

    # =========================================================================
    # Scenario 2: Import COLLECT BNE → POM D2D missing origin local
    # =========================================================================
    def test_import_collect_missing_origin_local_triggers_spot(self):
        # Seed freight and destination locals, omit origin locals
        ImportCOGS.objects.create(
            product_code=self.imp_freight_pc, origin_airport="BNE", destination_airport="POM",
            agent=self.agent_bne, currency="AUD", rate_per_kg=Decimal("4.50"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        ImportSellRate.objects.create(
            product_code=self.imp_freight_pc, origin_airport="BNE", destination_airport="POM",
            currency="PGK", rate_per_kg=Decimal("12.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalCOGSRate.objects.create(
            product_code=self.imp_dest_pc, location="POM", direction="IMPORT",
            agent=self.agent_pom, currency="PGK", rate_type="FIXED", amount=Decimal("70.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.imp_dest_pc, location="POM", direction="IMPORT",
            payment_term="COLLECT", currency="PGK", rate_type="FIXED", amount=Decimal("200.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        eval_payload = {
            "origin_country": "AU", "destination_country": "PG",
            "origin_airport": "BNE", "destination_airport": "POM",
            "service_scope": "D2D", "payment_term": "COLLECT",
            "commodity": "GCR",
            "agent_id": self.agent_bne.id, "buy_currency": "AUD"
        }
        eval_res = self.client.post("/api/v3/spot/evaluate-trigger/", eval_payload, format="json")
        self.assertEqual(eval_res.status_code, status.HTTP_200_OK)
        res_json = eval_res.json()
        self.assertTrue(res_json["is_spot_required"])
        self.assertEqual(res_json["trigger"]["missing_components"], ["ORIGIN_LOCAL"])

    # =========================================================================
    # Scenario 3: Import COLLECT BNE → POM D2D missing freight
    # =========================================================================
    def test_import_collect_missing_freight_triggers_spot(self):
        # Seed origin and destination locals, omit BNE → POM freight rates
        LocalCOGSRate.objects.create(
            product_code=self.imp_origin_pc, location="BNE", direction="IMPORT",
            agent=self.agent_bne, currency="AUD", rate_type="FIXED", amount=Decimal("50.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.imp_origin_pc, location="BNE", direction="IMPORT",
            payment_term="COLLECT", currency="PGK", rate_type="FIXED", amount=Decimal("150.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalCOGSRate.objects.create(
            product_code=self.imp_dest_pc, location="POM", direction="IMPORT",
            agent=self.agent_pom, currency="PGK", rate_type="FIXED", amount=Decimal("70.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.imp_dest_pc, location="POM", direction="IMPORT",
            payment_term="COLLECT", currency="PGK", rate_type="FIXED", amount=Decimal("200.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        eval_payload = {
            "origin_country": "AU", "destination_country": "PG",
            "origin_airport": "BNE", "destination_airport": "POM",
            "service_scope": "D2D", "payment_term": "COLLECT",
            "commodity": "GCR",
            "agent_id": self.agent_bne.id, "buy_currency": "AUD"
        }
        eval_res = self.client.post("/api/v3/spot/evaluate-trigger/", eval_payload, format="json")
        self.assertEqual(eval_res.status_code, status.HTTP_200_OK)
        res_json = eval_res.json()
        self.assertTrue(res_json["is_spot_required"])
        self.assertEqual(res_json["trigger"]["missing_components"], ["FREIGHT"])

    # =========================================================================
    # Scenario 4: Export PREPAID POM → BNE D2D with complete rates
    # =========================================================================
    def test_export_prepaid_complete_rates_standard_quote(self):
        # 1. Freight: POM → BNE ExportCOGS / ExportSellRate
        ExportCOGS.objects.create(
            product_code=self.exp_freight_pc, origin_airport="POM", destination_airport="BNE",
            agent=self.agent_bne, currency="USD", rate_per_kg=Decimal("3.50"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        ExportSellRate.objects.create(
            product_code=self.exp_freight_pc, origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("15.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        # 2. Origin Local: POM-side local export rates
        LocalCOGSRate.objects.create(
            product_code=self.exp_origin_pc, location="POM", direction="EXPORT",
            agent=self.agent_pom, currency="PGK", rate_type="FIXED", amount=Decimal("40.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.exp_origin_pc, location="POM", direction="EXPORT",
            payment_term="PREPAID", currency="PGK", rate_type="FIXED", amount=Decimal("100.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        # 3. Destination Local: BNE-side local export rates
        LocalCOGSRate.objects.create(
            product_code=self.exp_dest_pc, location="BNE", direction="EXPORT",
            agent=self.agent_bne, currency="AUD", rate_type="FIXED", amount=Decimal("60.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.exp_dest_pc, location="BNE", direction="EXPORT",
            payment_term="PREPAID", currency="PGK", rate_type="FIXED", amount=Decimal("180.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        eval_payload = {
            "origin_country": "PG", "destination_country": "AU",
            "origin_airport": "POM", "destination_airport": "BNE",
            "service_scope": "D2D", "payment_term": "PREPAID",
            "commodity": "GCR",
            "agent_id": self.agent_bne.id, "buy_currency": "USD"
        }
        eval_res = self.client.post("/api/v3/spot/evaluate-trigger/", eval_payload, format="json")
        self.assertEqual(eval_res.status_code, status.HTTP_200_OK)
        self.assertFalse(eval_res.json()["is_spot_required"])

        # Create Standard Quote
        payload = self._payload(self.pom, self.bne, "D2D", "PREPAID", "EXW", agent_id=self.agent_bne.id, buy_currency="USD")
        res = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "DRAFT")

    # =========================================================================
    # Scenario 5: Export PREPAID POM → BNE D2D missing destination local
    # =========================================================================
    def test_export_prepaid_missing_destination_local_triggers_spot(self):
        # Seed POM → BNE freight and POM origin locals, omit BNE destination local rates
        ExportCOGS.objects.create(
            product_code=self.exp_freight_pc, origin_airport="POM", destination_airport="BNE",
            agent=self.agent_bne, currency="USD", rate_per_kg=Decimal("3.50"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        ExportSellRate.objects.create(
            product_code=self.exp_freight_pc, origin_airport="POM", destination_airport="BNE",
            currency="PGK", rate_per_kg=Decimal("15.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalCOGSRate.objects.create(
            product_code=self.exp_origin_pc, location="POM", direction="EXPORT",
            agent=self.agent_pom, currency="PGK", rate_type="FIXED", amount=Decimal("40.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        LocalSellRate.objects.create(
            product_code=self.exp_origin_pc, location="POM", direction="EXPORT",
            payment_term="PREPAID", currency="PGK", rate_type="FIXED", amount=Decimal("100.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        eval_payload = {
            "origin_country": "PG", "destination_country": "AU",
            "origin_airport": "POM", "destination_airport": "BNE",
            "service_scope": "D2D", "payment_term": "PREPAID",
            "commodity": "GCR",
            "agent_id": self.agent_bne.id, "buy_currency": "USD"
        }
        eval_res = self.client.post("/api/v3/spot/evaluate-trigger/", eval_payload, format="json")
        self.assertEqual(eval_res.status_code, status.HTTP_200_OK)
        res_json = eval_res.json()
        self.assertTrue(res_json["is_spot_required"])
        self.assertEqual(res_json["trigger"]["missing_components"], ["DESTINATION_LOCAL"])

    # =========================================================================
    # Scenario 6: Domestic POM → LAE A2A with complete freight
    # =========================================================================
    def test_domestic_complete_freight_standard_quote(self):
        DomesticCOGS.objects.create(
            product_code=self.dom_freight_pc, origin_zone="POM", destination_zone="LAE",
            carrier=self.carrier_px, currency="PGK", rate_per_kg=Decimal("5.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )
        DomesticSellRate.objects.create(
            product_code=self.dom_freight_pc, origin_zone="POM", destination_zone="LAE",
            currency="PGK", rate_per_kg=Decimal("8.00"),
            valid_from=self.valid_from, valid_until=self.valid_until
        )

        eval_payload = {
            "origin_country": "PG", "destination_country": "PG",
            "origin_airport": "POM", "destination_airport": "LAE",
            "service_scope": "A2A", "payment_term": "PREPAID",
            "commodity": "GCR",
            "carrier_id": self.carrier_px.id, "buy_currency": "PGK"
        }
        eval_res = self.client.post("/api/v3/spot/evaluate-trigger/", eval_payload, format="json")
        self.assertEqual(eval_res.status_code, status.HTTP_200_OK)
        self.assertFalse(eval_res.json()["is_spot_required"])

        # Create Standard Quote
        payload = self._payload(self.pom, self.lae, "A2A", "PREPAID", "EXW", carrier_id=self.carrier_px.id, buy_currency="PGK")
        res = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "DRAFT")

    # =========================================================================
    # Scenario 7: Unsupported non-PNG route rejection
    # =========================================================================
    def test_unsupported_non_png_route_rejected(self):
        payload = self._payload(self.syd, self.sin, "A2A", "PREPAID", "EXW")
        res = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not involving PNG", res.data["detail"])

        eval_payload = {
            "origin_country": "AU", "destination_country": "SG",
            "origin_airport": "SYD", "destination_airport": "SIN",
            "service_scope": "A2A", "payment_term": "PREPAID",
            "commodity": "GCR",
        }
        eval_res = self.client.post("/api/v3/spot/validate-scope/", eval_payload, format="json")
        self.assertEqual(eval_res.status_code, status.HTTP_200_OK)
        self.assertFalse(eval_res.json()["is_valid"])

    # =========================================================================
    # Scenario 8: Payment term and direction currency resolution matrix
    # =========================================================================
    def test_payment_term_currency_matrix(self):
        # We test determine_quote_currency via direct API computation
        # IMPORT + COLLECT => PGK
        # IMPORT + PREPAID (from AU) => AUD
        # IMPORT + PREPAID (non-AU) => USD
        # EXPORT + PREPAID => PGK
        # EXPORT + COLLECT (to AU) => AUD
        # EXPORT + COLLECT (non-AU) => USD
        # DOMESTIC => PGK
        from quotes.currency_rules import determine_quote_currency
        self.assertEqual(determine_quote_currency("IMPORT", "COLLECT", "AU", "PG"), "PGK")
        self.assertEqual(determine_quote_currency("IMPORT", "PREPAID", "AU", "PG"), "AUD")
        self.assertEqual(determine_quote_currency("IMPORT", "PREPAID", "SG", "PG"), "USD")
        self.assertEqual(determine_quote_currency("EXPORT", "PREPAID", "PG", "AU"), "PGK")
        self.assertEqual(determine_quote_currency("EXPORT", "COLLECT", "PG", "AU"), "AUD")
        self.assertEqual(determine_quote_currency("EXPORT", "COLLECT", "PG", "SG"), "USD")
        self.assertEqual(determine_quote_currency("DOMESTIC", "PREPAID", "PG", "PG"), "PGK")
        self.assertEqual(determine_quote_currency("DOMESTIC", "COLLECT", "PG", "PG"), "PGK")
