from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.tests.helpers import create_location
from parties.models import Company
from quotes.models import Quote, QuoteLine, QuoteTotal, QuoteVersion


class QuoteFinalizationMissingRateRegressionTest(APITestCase):
    """Battle Test #3: finalization must agree with persisted charge-line truth."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="battle-test-03-manager",
            password="pass123",
            email="battle-test-03@example.com",
            role=User.ROLE_MANAGER,
        )
        self.client.force_authenticate(user=self.user)

        self.customer = Company.objects.create(name="Battle Test 03 Customer")
        self.origin = create_location(name="Port Moresby", code="POM")
        self.destination = create_location(name="Brisbane", code="BNE")

    def _create_draft_quote(self, *, line_is_missing: bool, totals_say_missing: bool):
        quote = Quote.objects.create(
            customer=self.customer,
            mode="AIR",
            shipment_type=Quote.ShipmentType.EXPORT,
            service_scope="A2A",
            payment_term=Quote.PaymentTerm.PREPAID,
            output_currency="PGK",
            origin_location=self.origin,
            destination_location=self.destination,
            status=Quote.Status.DRAFT,
            created_by=self.user,
        )
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            status=Quote.Status.DRAFT,
            created_by=self.user,
            engine_version="V4",
        )
        QuoteLine.objects.create(
            quote_version=version,
            cost_pgk=Decimal("100.00"),
            sell_pgk=Decimal("150.00") if not line_is_missing else Decimal("0.00"),
            sell_pgk_incl_gst=Decimal("150.00") if not line_is_missing else Decimal("0.00"),
            cost_source="BASE_COST",
            is_rate_missing=line_is_missing,
            leg="MAIN",
            bucket="airfreight",
        )
        QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=Decimal("100.00"),
            total_sell_pgk=Decimal("150.00") if not line_is_missing else Decimal("0.00"),
            total_sell_pgk_incl_gst=Decimal("150.00") if not line_is_missing else Decimal("0.00"),
            total_sell_fcy_currency="PGK",
            has_missing_rates=totals_say_missing,
            engine_version="V4",
        )
        return quote

    def test_finalize_blocks_when_line_is_missing_even_if_totals_flag_is_false(self):
        quote = self._create_draft_quote(line_is_missing=True, totals_say_missing=False)
        url = reverse("quotes:quote-transition", kwargs={"quote_id": quote.id})

        response = self.client.post(url, {"action": "finalize"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()["detail"],
            "Cannot finalize quote with missing rates. Complete all required rates first.",
        )
        quote.refresh_from_db()
        self.assertEqual(quote.status, Quote.Status.DRAFT)
        self.assertIsNone(quote.finalized_at)

    def test_finalize_still_succeeds_for_genuinely_complete_quote(self):
        quote = self._create_draft_quote(line_is_missing=False, totals_say_missing=False)
        url = reverse("quotes:quote-transition", kwargs={"quote_id": quote.id})

        response = self.client.post(url, {"action": "finalize"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], Quote.Status.FINALIZED)
        quote.refresh_from_db()
        self.assertEqual(quote.status, Quote.Status.FINALIZED)
        self.assertIsNotNone(quote.finalized_at)
