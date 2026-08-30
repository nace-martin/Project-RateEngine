from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import Country
from core.tests.helpers import create_location
from parties.models import Company, Contact
from quotes.models import Quote
from quotes.services.air_journey_planner import AirJourneyPlanner
from quotes.services.spot_quote_context import build_trusted_quote_context


class SpotJourneyContractBaselineTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="spot-journey-baseline", password="x")
        customer = Company.objects.create(name="SPOT Journey Baseline", is_customer=True)
        contact = Contact.objects.create(company=customer, first_name="SPOT", last_name="Owner")
        china = Country.objects.create(code="CN", name="China")
        png = Country.objects.create(code="PG", name="Papua New Guinea")
        self.can = create_location(code="CAN", name="Guangzhou", country=china)
        self.pom = create_location(code="POM", name="Port Moresby", country=png)
        self.quote = Quote.objects.create(
            customer=customer,
            contact=contact,
            mode="AIR",
            shipment_type=Quote.ShipmentType.IMPORT,
            origin_location=self.can,
            destination_location=self.pom,
            service_scope="D2D",
            incoterm="EXW",
            payment_term=Quote.PaymentTerm.COLLECT,
            commodity_code="GCR",
            output_currency="PGK",
            request_details_json={
                "dimensions": [{
                    "pieces": 1,
                    "length_cm": "100",
                    "width_cm": "100",
                    "height_cm": "60",
                    "gross_weight_kg": "100",
                    "package_type": "Pallet",
                }],
                "buy_currency": "USD",
            },
            created_by=user,
        )

    def test_trusted_spot_snapshot_is_directly_plannable_without_client_reconstruction(self):
        context, missing = build_trusted_quote_context(self.quote)

        self.assertEqual(missing, [])
        self.assertEqual(context["service_domain"], "AIR")
        self.assertEqual(context["quote_date"], self.quote.created_at.date().isoformat())
        self.assertEqual(context["chargeable_weight_kg"], 100.0)
        self.assertTrue(context["pickup_requested"])
        self.assertTrue(context["delivery_requested"])

        plan = AirJourneyPlanner().plan(context)

        self.assertEqual(plan.status.value, "PLANNED")
        self.assertEqual(plan.pattern.value, "IMP_POM")
        self.assertEqual(plan.blockers, [])
        self.assertEqual(
            [leg.leg_key for leg in plan.legs],
            ["01:INTERNATIONAL_IMPORT:CAN:POM"],
        )

    def test_service_scope_changes_pickup_delivery_flags_without_guessing(self):
        expectations = {
            "A2A": (False, False),
            "D2A": (True, False),
            "A2D": (False, True),
            "D2D": (True, True),
        }
        for scope, expected in expectations.items():
            with self.subTest(scope=scope):
                self.quote.service_scope = scope
                self.quote.save(update_fields=["service_scope", "updated_at"])
                context, missing = build_trusted_quote_context(self.quote)
                self.assertEqual(missing, [])
                self.assertEqual(
                    (context["pickup_requested"], context["delivery_requested"]),
                    expected,
                )
