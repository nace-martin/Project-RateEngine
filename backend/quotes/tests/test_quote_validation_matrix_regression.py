# backend/quotes/tests/test_quote_validation_matrix_regression.py

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from django.test import override_settings

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


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework.authentication.TokenAuthentication",
        ],
        "DEFAULT_THROTTLE_CLASSES": [],
    }
)
class QuoteValidationMatrixRegressionTests(APITestCase):
    """
    Exhaustive regression test suite validating the entire 24-combination matrix
    of Direction x Scope x Payment Term.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="matrix-runner",
            password="testpass123",
            role="manager",
        )
        self.client.force_authenticate(self.user)

        # 1. Currencies & Countries
        self.aud = Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar"})[0]
        self.pgk = Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinean Kina"})[0]
        self.usd = Currency.objects.get_or_create(code="USD", defaults={"name": "United States Dollar"})[0]

        self.au = Country.objects.get_or_create(code="AU", defaults={"name": "Australia", "currency": self.aud})[0]
        self.pg = Country.objects.get_or_create(code="PG", defaults={"name": "Papua New Guinea", "currency": self.pgk})[0]

        # 2. Locations
        self.bne = create_location(code="BNE", name="Brisbane", country=self.au, is_active=True)
        self.pom = create_location(code="POM", name="Port Moresby", country=self.pg, is_active=True)
        self.lae = create_location(code="LAE", name="Lae", country=self.pg, is_active=True)

        # 3. Parties
        self.customer = Company.objects.create(name="Matrix Customer", company_type="CUSTOMER", is_customer=True)
        self.contact = Contact.objects.create(
            company=self.customer,
            first_name="Mat",
            last_name="Rix",
            email="matrix@example.com",
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

        # Seed export product codes and components
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

    def _seed_rates(self, direction, scope, payment_term):
        """Helper to seed all required rates for a given combination so standard quote passes."""
        # 1. Clean existing rates to ensure clean state per scenario run
        ImportCOGS.objects.all().delete()
        ImportSellRate.objects.all().delete()
        ExportCOGS.objects.all().delete()
        ExportSellRate.objects.all().delete()
        DomesticCOGS.objects.all().delete()
        DomesticSellRate.objects.all().delete()
        LocalCOGSRate.objects.all().delete()
        LocalSellRate.objects.all().delete()

        if direction == "DOMESTIC":
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
            return

        if direction == "IMPORT":
            # Freight (Required for A2A, D2A, D2D)
            if scope in ["A2A", "D2A", "D2D"]:
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
            
            # Origin local (Required for D2A, D2D)
            if scope in ["D2A", "D2D"]:
                LocalCOGSRate.objects.create(
                    product_code=self.imp_origin_pc, location="BNE", direction="IMPORT",
                    agent=self.agent_bne, currency="AUD", rate_type="FIXED", amount=Decimal("50.00"),
                    valid_from=self.valid_from, valid_until=self.valid_until
                )
                LocalSellRate.objects.create(
                    product_code=self.imp_origin_pc, location="BNE", direction="IMPORT",
                    payment_term=payment_term, currency="PGK", rate_type="FIXED", amount=Decimal("150.00"),
                    valid_from=self.valid_from, valid_until=self.valid_until
                )

            # Destination local (Required for A2D, D2D)
            if scope in ["A2D", "D2D"]:
                LocalCOGSRate.objects.create(
                    product_code=self.imp_dest_pc, location="POM", direction="IMPORT",
                    agent=self.agent_pom, currency="PGK", rate_type="FIXED", amount=Decimal("70.00"),
                    valid_from=self.valid_from, valid_until=self.valid_until
                )
                LocalSellRate.objects.create(
                    product_code=self.imp_dest_pc, location="POM", direction="IMPORT",
                    payment_term=payment_term, currency="PGK", rate_type="FIXED", amount=Decimal("200.00"),
                    valid_from=self.valid_from, valid_until=self.valid_until
                )

        elif direction == "EXPORT":
            # Freight (Required for A2A, D2A, D2D)
            if scope in ["A2A", "D2A", "D2D"]:
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

            # Origin local (Required for D2A, D2D)
            if scope in ["D2A", "D2D"]:
                LocalCOGSRate.objects.create(
                    product_code=self.exp_origin_pc, location="POM", direction="EXPORT",
                    agent=self.agent_pom, currency="PGK", rate_type="FIXED", amount=Decimal("40.00"),
                    valid_from=self.valid_from, valid_until=self.valid_until
                )
                LocalSellRate.objects.create(
                    product_code=self.exp_origin_pc, location="POM", direction="EXPORT",
                    payment_term=payment_term, currency="PGK", rate_type="FIXED", amount=Decimal("100.00"),
                    valid_from=self.valid_from, valid_until=self.valid_until
                )

            # Destination local (Required for A2D, D2D)
            if scope in ["A2D", "D2D"]:
                LocalCOGSRate.objects.create(
                    product_code=self.exp_dest_pc, location="BNE", direction="EXPORT",
                    agent=self.agent_bne, currency="AUD", rate_type="FIXED", amount=Decimal("60.00"),
                    valid_from=self.valid_from, valid_until=self.valid_until
                )
                LocalSellRate.objects.create(
                    product_code=self.exp_dest_pc, location="BNE", direction="EXPORT",
                    payment_term=payment_term, currency="PGK", rate_type="FIXED", amount=Decimal("180.00"),
                    valid_from=self.valid_from, valid_until=self.valid_until
                )

    def test_24_combination_matrix(self):
        """
        Dynamically run and validate the complete 24-combination matrix.
        Asserts service scope rules, shipment classification, expected SPOT trigger state,
        and missing component correctness.
        """
        directions = ["IMPORT", "EXPORT", "DOMESTIC"]
        scopes = ["A2A", "D2A", "A2D", "D2D"]
        payment_terms = ["PREPAID", "COLLECT"]

        count = 0
        for direction in directions:
            for scope in scopes:
                for payment_term in payment_terms:
                    count += 1
                    
                    # 1. Setup the shipment parameters
                    if direction == "DOMESTIC":
                        origin = self.pom
                        destination = self.lae
                        origin_country = "PG"
                        destination_country = "PG"
                        incoterm = "EXW"
                        carrier_id = self.carrier_px.id
                        agent_id = None
                        buy_currency = "PGK"
                    elif direction == "IMPORT":
                        origin = self.bne
                        destination = self.pom
                        origin_country = "AU"
                        destination_country = "PG"
                        incoterm = "FCA" if scope == "D2A" else "EXW"
                        carrier_id = None
                        agent_id = self.agent_bne.id
                        buy_currency = "AUD"
                    else:  # EXPORT
                        origin = self.pom
                        destination = self.bne
                        origin_country = "PG"
                        destination_country = "AU"
                        incoterm = "FCA" if scope == "D2A" else "DAP" if scope == "D2D" and payment_term == "PREPAID" else "EXW"
                        carrier_id = None
                        agent_id = self.agent_bne.id
                        buy_currency = "USD"

                    # --- PHASE A: All Rates Exist (Standard Quote / SPOT = False) ---
                    self._seed_rates(direction, scope, payment_term)

                    # Trigger evaluation
                    eval_payload = {
                        "origin_country": origin_country,
                        "destination_country": destination_country,
                        "origin_airport": origin.code,
                        "destination_airport": destination.code,
                        "service_scope": scope,
                        "payment_term": payment_term,
                        "commodity": "GCR",
                        "agent_id": agent_id,
                        "carrier_id": carrier_id,
                        "buy_currency": buy_currency
                    }
                    eval_res = self.client.post("/api/v3/spot/evaluate-trigger/", eval_payload, format="json")
                    self.assertEqual(
                        eval_res.status_code, status.HTTP_200_OK,
                        f"Failed trigger evaluation for {direction} {scope} {payment_term}"
                    )
                    self.assertFalse(
                        eval_res.json()["is_spot_required"],
                        f"Spot trigger incorrectly activated when all rates exist for {direction} {scope} {payment_term}"
                    )

                    # Create & Compute standard quote
                    payload = self._payload(
                        origin, destination, scope, payment_term, incoterm,
                        agent_id=agent_id, carrier_id=carrier_id, buy_currency=buy_currency
                    )
                    res = self.client.post("/api/v3/quotes/compute/", payload, format="json")
                    self.assertEqual(
                        res.status_code, status.HTTP_201_CREATED,
                        f"Failed standard quote compute for {direction} {scope} {payment_term}. Detail: {res.data if hasattr(res, 'data') else res}"
                    )
                    self.assertEqual(
                        res.data["status"], "DRAFT",
                        f"Incorrect quote status for standard quote in {direction} {scope} {payment_term}"
                    )

                    # --- PHASE B: Rates are Missing (SPOT = True) ---
                    # Delete all rates so it triggers SPOT
                    ImportCOGS.objects.all().delete()
                    ImportSellRate.objects.all().delete()
                    ExportCOGS.objects.all().delete()
                    ExportSellRate.objects.all().delete()
                    DomesticCOGS.objects.all().delete()
                    DomesticSellRate.objects.all().delete()
                    LocalCOGSRate.objects.all().delete()
                    LocalSellRate.objects.all().delete()

                    eval_res_spot = self.client.post("/api/v3/spot/evaluate-trigger/", eval_payload, format="json")
                    self.assertEqual(eval_res_spot.status_code, status.HTTP_200_OK)
                    spot_data = eval_res_spot.json()
                    
                    self.assertTrue(
                        spot_data["is_spot_required"],
                        f"Spot trigger failed to activate when rates are missing for {direction} {scope} {payment_term}"
                    )

                    # Verify expected missing components based on service scope logic
                    missing = spot_data["trigger"]["missing_components"]
                    if direction == "DOMESTIC":
                        self.assertEqual(missing, ["FREIGHT"])
                    elif scope == "A2A":
                        self.assertEqual(missing, ["FREIGHT"])
                    elif scope == "D2A":
                        self.assertEqual(set(missing), {"ORIGIN_LOCAL", "FREIGHT"})
                    elif scope == "A2D":
                        self.assertEqual(missing, ["DESTINATION_LOCAL"])
                    elif scope == "D2D":
                        self.assertEqual(set(missing), {"ORIGIN_LOCAL", "FREIGHT", "DESTINATION_LOCAL"})

        self.assertEqual(count, 24, "Did not execute exactly 24 matrix combinations.")
