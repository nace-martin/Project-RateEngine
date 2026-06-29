# backend/quotes/tests/test_crm_resilience.py

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Country, Currency
from core.tests.helpers import create_location
from parties.models import Company, Contact
from pricing_v4.models import Carrier, DomesticCOGS, DomesticSellRate, ProductCode
from services.models import ServiceComponent
from quotes.models import Quote


@override_settings(RBAC_ALLOW_LEGACY_SCOPE_FALLBACK_FOR_TESTS=True)
class CRMResilienceTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="crm-resilience",
            password="testpass123",
            role="manager",
        )
        self.client.force_authenticate(self.user)

        pgk = Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinean Kina", "minor_units": 2})[0]
        pg = Country.objects.get_or_create(code="PG", defaults={"name": "Papua New Guinea", "currency": pgk})[0]

        self.origin = create_location(code="POM", name="Port Moresby", country=pg, is_active=True)
        self.destination = create_location(code="LAE", name="Lae", country=pg, is_active=True)
        self.customer = Company.objects.create(name="CRM Customer", company_type="CUSTOMER", is_customer=True)
        self.contact = Contact.objects.create(
            company=self.customer,
            first_name="Crm",
            last_name="Resilient",
            email="crm@example.com",
        )

        self.carrier = Carrier.objects.create(
            code="CRM-PX",
            name="CRM Carrier",
            carrier_type="AIRLINE",
        )

        self.freight_pc = ProductCode.objects.get_or_create(
            id=6001,
            defaults={
                "code": "DOM-FRT-AIR",
                "description": "Domestic Air Freight CRM",
                "domain": "DOMESTIC",
                "category": "FREIGHT",
                "is_gst_applicable": True,
                "gst_rate": Decimal("0.10"),
                "gl_revenue_code": "4100",
                "gl_cost_code": "5100",
                "default_unit": "KG",
            }
        )[0]

        ServiceComponent.objects.get_or_create(
            code="DOM-FRT-AIR",
            defaults={
                "description": "Domestic Air Freight CRM",
                "mode": "AIR",
                "leg": "MAIN",
                "category": "TRANSPORT",
                "unit": "KG",
                "audience": "BOTH",
            }
        )

        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)

        # Seed freight rates so standard quote can compute successfully
        DomesticCOGS.objects.create(
            product_code=self.freight_pc,
            origin_zone="POM",
            destination_zone="LAE",
            carrier=self.carrier,
            currency="PGK",
            rate_per_kg=Decimal("6.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )
        DomesticSellRate.objects.create(
            product_code=self.freight_pc,
            origin_zone="POM",
            destination_zone="LAE",
            currency="PGK",
            rate_per_kg=Decimal("9.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

    def _payload(self):
        return {
            "customer_id": str(self.customer.id),
            "contact_id": str(self.contact.id),
            "mode": "AIR",
            "service_scope": "A2A",
            "origin_location_id": str(self.origin.id),
            "destination_location_id": str(self.destination.id),
            "incoterm": "EXW",
            "payment_term": "PREPAID",
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
            "commodity_code": "GCR",
        }

    @patch("quotes.views.calculation.resolve_quote_opportunity")
    @patch("quotes.views.calculation.logger")
    def test_quote_creation_succeeds_when_crm_opportunity_resolution_fails(self, mock_logger, mock_resolve):
        # Mock opportunity resolution to raise an exception
        mock_resolve.side_effect = RuntimeError("Simulated Opportunity DB Failure")

        response = self.client.post("/api/v3/quotes/compute/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "DRAFT")
        self.assertIsNone(response.data["opportunity"])

        # Assert the exception was logged
        mock_logger.exception.assert_called()
        log_msg = mock_logger.exception.call_args[0][0]
        self.assertIn("CRM opportunity resolution failed during quote creation", log_msg)

    @patch("quotes.views.calculation.create_auto_quote_opportunity_interaction")
    @patch("quotes.views.calculation.logger")
    def test_quote_creation_succeeds_when_crm_interaction_auto_creation_fails(self, mock_logger, mock_create):
        # Mock auto interaction creation to raise an exception
        mock_create.side_effect = ValueError("Simulated Interaction Validation Error")

        # Mock resolve_quote_opportunity to return a dummy opportunity and opportunity_was_auto_created = True
        from crm.models import Opportunity
        dummy_opportunity = Opportunity.objects.create(
            company=self.customer,
            title="POM to LAE CRM opportunity",
            service_type="AIR",
            direction="DOMESTIC",
            scope="A2A",
        )

        with patch("quotes.views.calculation.resolve_quote_opportunity", return_value=(dummy_opportunity, True)):
            response = self.client.post("/api/v3/quotes/compute/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "DRAFT")
        self.assertEqual(str(response.data["opportunity"]), str(dummy_opportunity.id))

        # Assert the exception was logged
        mock_logger.exception.assert_called()
        log_msg = mock_logger.exception.call_args[0][0]
        self.assertIn("CRM opportunity interaction auto-creation failed", log_msg)

    @patch("quotes.signals.logger")
    def test_quote_status_transition_succeeds_when_crm_sync_fails(self, mock_logger):
        from crm.models import Opportunity
        opportunity = Opportunity.objects.create(
            company=self.customer,
            title="Transition opportunity",
            service_type="AIR",
            direction="DOMESTIC",
            scope="A2A",
        )
        # Create a Quote in DRAFT status
        quote = Quote.objects.create(
            customer=self.customer,
            contact=self.contact,
            mode="AIR",
            shipment_type="DOMESTIC",
            incoterm="EXW",
            payment_term="PREPAID",
            service_scope="A2A",
            status="DRAFT",
            created_by=self.user,
            opportunity=opportunity,
        )

        # Transition status to FINALIZED while post-save CRM sync raises an exception
        with patch("quotes.signals._sync_crm_for_quote_event", side_effect=RuntimeError("Simulated Post-Save CRM Event Sync Failure")) as mock_sync:
            transition_payload = {
                "action": "finalize",
            }
            response = self.client.post(
                f"/api/v3/quotes/{quote.id}/transition/",
                transition_payload,
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "FINALIZED")

        # Now test that the internal post-save signal try-except catch works when NOT mocked from the outside
        with patch("crm.services.create_quote_system_interaction", side_effect=ValueError("Sync Database Down")):
            # Reset transition to SENT
            sent_payload = {
                "action": "send",
            }
            res_sent = self.client.post(
                f"/api/v3/quotes/{quote.id}/transition/",
                sent_payload,
                format="json",
            )
            # Should transition successfully despite CRM post-save interaction logging raising ValueError
            self.assertEqual(res_sent.status_code, status.HTTP_200_OK)
            self.assertEqual(res_sent.data["status"], "SENT")
            
            # Assert the exception was cleanly logged
            mock_logger.exception.assert_called()
            log_msg = mock_logger.exception.call_args[0][0]
            self.assertIn("CRM event synchronization failed", log_msg)
