from decimal import Decimal
from datetime import timedelta
from itertools import product
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core.tests.helpers import create_location
from parties.models import Company
from quotes.lifecycle import QuoteLifecycleService
from quotes.models import Quote, QuoteLine, QuoteTotal, QuoteVersion
from quotes.spot_models import SpotPricingEnvelopeDB


pytestmark = pytest.mark.django_db


COMPONENT_BUCKETS = {
    "ORIGIN_LOCAL": "origin_charges",
    "FREIGHT": "airfreight",
    "DESTINATION_LOCAL": "destination_charges",
}


@pytest.fixture
def user():
    User = get_user_model()
    return User.objects.create_user(
        username=f"lifecycle-{uuid4().hex[:8]}",
        password="pass123",
        role="manager",
    )


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def quote_context(user):
    customer = Company.objects.create(
        name=f"Lifecycle Customer {uuid4().hex[:6]}",
        is_customer=True,
    )
    return {
        "customer": customer,
        "origin": create_location(name=f"Origin {uuid4().hex[:6]}", code="ORG"),
        "destination": create_location(name=f"Destination {uuid4().hex[:6]}", code="DST"),
        "user": user,
    }


def _create_quote_with_components(
    quote_context,
    *,
    shipment_type="IMPORT",
    service_scope="D2D",
    payment_term="PREPAID",
    missing_components=None,
    status=Quote.Status.DRAFT,
):
    quote = Quote.objects.create(
        customer=quote_context["customer"],
        mode="AIR",
        shipment_type=shipment_type,
        incoterm="DAP",
        payment_term=payment_term,
        service_scope=service_scope,
        output_currency="PGK",
        origin_location=quote_context["origin"],
        destination_location=quote_context["destination"],
        status=status,
        created_by=quote_context["user"],
    )
    if status == Quote.Status.FINALIZED:
        quote.finalized_at = timezone.now()
        quote.finalized_by = quote_context["user"]
        quote.save(update_fields=["finalized_at", "finalized_by"])

    version = QuoteVersion.objects.create(
        quote=quote,
        version_number=1,
        status=status,
        created_by=quote_context["user"],
        engine_version="V4",
    )
    missing = set(missing_components or [])
    for component, bucket in COMPONENT_BUCKETS.items():
        is_missing = component in missing
        QuoteLine.objects.create(
            quote_version=version,
            service_component=None,
            bucket=bucket,
            leg="MAIN",
            component=component,
            cost_pgk=Decimal("0.00") if is_missing else Decimal("10.00"),
            sell_pgk=Decimal("0.00") if is_missing else Decimal("15.00"),
            sell_pgk_incl_gst=Decimal("0.00") if is_missing else Decimal("16.50"),
            sell_fcy=Decimal("0.00") if is_missing else Decimal("15.00"),
            sell_fcy_incl_gst=Decimal("0.00") if is_missing else Decimal("16.50"),
            sell_fcy_currency="PGK",
            is_rate_missing=is_missing,
        )
    QuoteTotal.objects.create(
        quote_version=version,
        total_cost_pgk=Decimal("30.00"),
        total_sell_pgk=Decimal("45.00"),
        total_sell_pgk_incl_gst=Decimal("49.50"),
        total_sell_fcy=Decimal("45.00"),
        total_sell_fcy_incl_gst=Decimal("49.50"),
        total_sell_fcy_currency="PGK",
        has_missing_rates=bool(missing),
    )
    quote.latest_version = version
    return quote


@pytest.mark.parametrize("shipment_type,service_scope,payment_term", product(
    ["IMPORT", "EXPORT"],
    ["A2A", "A2D", "D2A", "D2D"],
    ["PREPAID", "COLLECT"],
))
def test_lifecycle_matrix_all_rates_present_is_ready(
    quote_context,
    shipment_type,
    service_scope,
    payment_term,
):
    quote = _create_quote_with_components(
        quote_context,
        shipment_type=shipment_type,
        service_scope=service_scope,
        payment_term=payment_term,
    )

    result = QuoteLifecycleService.evaluate(quote)

    assert result.status_recommendation == "READY"
    assert result.missing_components == []
    assert result.requires_spot is False
    assert result.can_finalize is True
    assert result.can_delete is True


@pytest.mark.parametrize("shipment_type,payment_term", product(["IMPORT", "EXPORT"], ["PREPAID", "COLLECT"]))
@pytest.mark.parametrize(
    "service_scope,missing_components,expected_missing,requires_spot",
    [
        ("A2A", ["FREIGHT"], ["FREIGHT"], True),
        ("A2D", ["FREIGHT"], [], False),
        ("A2D", ["DESTINATION_LOCAL"], ["DESTINATION_LOCAL"], True),
        ("D2A", ["ORIGIN_LOCAL"], ["ORIGIN_LOCAL"], True),
        ("D2A", ["DESTINATION_LOCAL"], [], False),
        ("D2D", ["ORIGIN_LOCAL", "FREIGHT"], ["ORIGIN_LOCAL", "FREIGHT"], True),
        (
            "D2D",
            ["ORIGIN_LOCAL", "FREIGHT", "DESTINATION_LOCAL"],
            ["ORIGIN_LOCAL", "FREIGHT", "DESTINATION_LOCAL"],
            True,
        ),
    ],
)
def test_lifecycle_matrix_missing_components_drive_spot_metadata(
    quote_context,
    shipment_type,
    payment_term,
    service_scope,
    missing_components,
    expected_missing,
    requires_spot,
):
    quote = _create_quote_with_components(
        quote_context,
        shipment_type=shipment_type,
        service_scope=service_scope,
        payment_term=payment_term,
        missing_components=missing_components,
    )

    result = QuoteLifecycleService.evaluate(quote)

    assert set(result.missing_components) == set(expected_missing)
    assert result.requires_spot is requires_spot
    assert result.can_finalize is not requires_spot
    assert quote.status == Quote.Status.DRAFT


def test_draft_quote_delete_allowed(api_client, quote_context):
    quote = _create_quote_with_components(quote_context)

    response = api_client.delete(f"/api/v3/quotes/{quote.id}/")

    assert response.status_code == 204
    assert not Quote.objects.filter(id=quote.id).exists()


def test_draft_quote_with_unfinalized_spe_delete_allowed(api_client, quote_context):
    quote = _create_quote_with_components(quote_context, missing_components=["FREIGHT"])
    spe = SpotPricingEnvelopeDB.objects.create(
        quote=quote,
        shipment_context_json={"origin_country": "AU", "destination_country": "PG"},
        spot_trigger_reason_code="MISSING_SCOPE_RATES",
        spot_trigger_reason_text="Missing required rate components",
        expires_at=timezone.now() + timedelta(hours=72),
    )

    response = api_client.delete(f"/api/v3/quotes/{quote.id}/")

    assert response.status_code == 204
    assert not Quote.objects.filter(id=quote.id).exists()
    spe.refresh_from_db()
    assert spe.quote_id is None


def test_finalized_quote_delete_blocked(api_client, quote_context):
    quote = _create_quote_with_components(
        quote_context,
        status=Quote.Status.FINALIZED,
    )

    response = api_client.delete(f"/api/v3/quotes/{quote.id}/")

    assert response.status_code == 400
    assert response.data["lifecycle"]["can_delete"] is False
    assert Quote.objects.filter(id=quote.id).exists()
