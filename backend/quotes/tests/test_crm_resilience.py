# backend/quotes/tests/test_crm_resilience.py

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import Country, Currency
from core.tests.helpers import create_location
from crm.models import Interaction, Opportunity
from parties.models import Company, Contact
from pricing_v4.models import Carrier, DomesticCOGS, DomesticSellRate, ProductCode
from services.models import ServiceComponent
from quotes.models import Quote, QuoteEvent


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

    def test_standard_quote_creation_has_no_crm_side_effects(self):
        response = self.client.post("/api/v3/quotes/compute/", self._payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "DRAFT")
        self.assertIsNone(response.data["opportunity"])
        self.assertEqual(Opportunity.objects.count(), 0)
        self.assertEqual(Interaction.objects.count(), 0)

        quote = Quote.objects.get(id=response.data["id"])
        self.assertEqual(quote.customer, self.customer)
        self.assertEqual(quote.contact, self.contact)
        self.assertEqual(quote.versions.get(version_number=1).lines.count(), 1)
        totals = response.data["latest_version"]["totals"]
        self.assertEqual(totals["total_cost_pgk"], "150.00")
        self.assertEqual(totals["total_sell_pgk"], "225.00")
        self.assertEqual(totals["total_sell_pgk_incl_gst"], "247.50")

    def test_standard_quote_recalculation_has_no_crm_side_effects_or_total_changes(self):
        payload = self._payload()
        created = self.client.post("/api/v3/quotes/compute/", payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        quote = Quote.objects.get(id=created.data["id"])
        first_version = quote.versions.get(version_number=1)
        first_totals = (
            first_version.totals.total_cost_pgk,
            first_version.totals.total_sell_pgk,
            first_version.totals.total_sell_pgk_incl_gst,
            first_version.totals.total_sell_fcy,
            first_version.totals.total_sell_fcy_incl_gst,
            first_version.totals.total_sell_fcy_currency,
        )
        first_line_count = first_version.lines.count()

        payload["quote_id"] = str(quote.id)
        recalculated = self.client.post("/api/v3/quotes/compute/", payload, format="json")

        self.assertEqual(recalculated.status_code, status.HTTP_201_CREATED)
        quote.refresh_from_db()
        self.assertEqual(quote.versions.count(), 2)
        self.assertEqual(quote.customer, self.customer)
        self.assertEqual(quote.contact, self.contact)
        self.assertIsNone(quote.opportunity_id)
        second_version = quote.versions.get(version_number=2)
        self.assertEqual(second_version.lines.count(), first_line_count)
        self.assertEqual(
            (
                second_version.totals.total_cost_pgk,
                second_version.totals.total_sell_pgk,
                second_version.totals.total_sell_pgk_incl_gst,
                second_version.totals.total_sell_fcy,
                second_version.totals.total_sell_fcy_incl_gst,
                second_version.totals.total_sell_fcy_currency,
            ),
            first_totals,
        )
        self.assertEqual(Opportunity.objects.count(), 0)
        self.assertEqual(Interaction.objects.count(), 0)

    def _create_linked_quote(self, title):
        opportunity = Opportunity.objects.create(
            company=self.customer,
            title=title,
            service_type="AIR",
            direction="DOMESTIC",
            scope="A2A",
        )
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
        return quote, opportunity

    def _transition(self, quote, action, expected_status):
        response = self.client.post(
            f"/api/v3/quotes/{quote.id}/transition/",
            {"action": action},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], expected_status)
        quote.refresh_from_db()

    def _assert_event(self, quote, event_type, previous_status, new_status):
        event = quote.events.get(event_type=event_type)
        self.assertEqual(event.quote, quote)
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.metadata["previous_status"], previous_status)
        self.assertEqual(event.metadata["new_status"], new_status)

    def _assert_crm_unchanged(self, quote, opportunity, opportunity_count):
        quote.refresh_from_db()
        opportunity.refresh_from_db()
        self.assertEqual(quote.opportunity_id, opportunity.id)
        self.assertEqual(opportunity.status, Opportunity.Status.NEW)
        self.assertEqual(Opportunity.objects.count(), opportunity_count)
        self.assertEqual(Interaction.objects.count(), 0)

    def test_quote_creation_preserves_native_event_without_crm_sync(self):
        quote, opportunity = self._create_linked_quote("Created event opportunity")

        event = quote.events.get(event_type=QuoteEvent.EventType.CREATED)
        self.assertEqual(event.quote, quote)
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.metadata, {"initial_status": Quote.Status.DRAFT})
        self._assert_crm_unchanged(quote, opportunity, opportunity_count=1)

    def test_finalized_sent_and_accepted_events_do_not_sync_crm(self):
        quote, opportunity = self._create_linked_quote("Accepted path opportunity")
        opportunity_count = Opportunity.objects.count()

        self._transition(quote, "finalize", Quote.Status.FINALIZED)
        self._assert_event(quote, QuoteEvent.EventType.FINALIZED, Quote.Status.DRAFT, Quote.Status.FINALIZED)
        self._assert_crm_unchanged(quote, opportunity, opportunity_count)

        self._transition(quote, "send", Quote.Status.SENT)
        self._assert_event(quote, QuoteEvent.EventType.SENT, Quote.Status.FINALIZED, Quote.Status.SENT)
        self._assert_crm_unchanged(quote, opportunity, opportunity_count)

        self._transition(quote, "mark_won", Quote.Status.ACCEPTED)
        self._assert_event(quote, QuoteEvent.EventType.ACCEPTED, Quote.Status.SENT, Quote.Status.ACCEPTED)
        self._assert_crm_unchanged(quote, opportunity, opportunity_count)

    def test_lost_event_does_not_sync_crm(self):
        quote, opportunity = self._create_linked_quote("Lost path opportunity")
        opportunity_count = Opportunity.objects.count()

        self._transition(quote, "finalize", Quote.Status.FINALIZED)
        self._transition(quote, "send", Quote.Status.SENT)
        self._transition(quote, "mark_lost", Quote.Status.LOST)

        self._assert_event(quote, QuoteEvent.EventType.LOST, Quote.Status.SENT, Quote.Status.LOST)
        self._assert_crm_unchanged(quote, opportunity, opportunity_count)

    def test_expired_event_does_not_sync_crm(self):
        quote, opportunity = self._create_linked_quote("Expired path opportunity")
        opportunity_count = Opportunity.objects.count()

        self._transition(quote, "finalize", Quote.Status.FINALIZED)
        self._transition(quote, "mark_expired", Quote.Status.EXPIRED)

        self._assert_event(quote, QuoteEvent.EventType.EXPIRED, Quote.Status.FINALIZED, Quote.Status.EXPIRED)
        self._assert_crm_unchanged(quote, opportunity, opportunity_count)
