# backend/pricing_v2/tests/test_pricing_service_v3.py

"""V3 pricing regression tests covering weight, tax, and rate card logic."""

import uuid
from decimal import Decimal
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef

from core.models import Currency, Country, Airport, FxSnapshot, Policy, Location
from quotes.serializers import QuoteComputeRequestSerializer
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent
from ratecards.models import PartnerRate, PartnerRateCard, PartnerRateLane
from parties.models import Company


pytestmark = pytest.mark.django_db


@pytest.fixture
def v3_test_data(db):
    """Seeds the minimum reference data the V3 engine expects."""

    pgk, _ = Currency.objects.get_or_create(
        code="PGK", defaults={"name": "Kina", "minor_units": 2}
    )
    Country.objects.get_or_create(
        code="PG", defaults={"name": "Papua New Guinea", "currency": pgk}
    )
    Country.objects.get_or_create(
        code="AU", defaults={"name": "Australia"}
    )

    country_pg = Country.objects.get(code="PG")
    country_au = Country.objects.get(code="AU")
    if not country_pg.currency:
        country_pg.currency = pgk
        country_pg.save(update_fields=["currency"])

    origin_ap, _ = Airport.objects.get_or_create(iata_code="BNE", defaults={"name": "Brisbane"})
    dest_ap, _ = Airport.objects.get_or_create(iata_code="POM", defaults={"name": "Port Moresby"})

    origin_loc, _ = Location.objects.get_or_create(
        code="BNE",
        defaults={
            "name": "Brisbane Airport",
            "airport": origin_ap,
            "country": country_au,
        },
    )
    dest_loc, _ = Location.objects.get_or_create(
        code="POM",
        defaults={
            "name": "Port Moresby Airport",
            "airport": dest_ap,
            "country": country_pg,
        },
    )

    Policy.objects.create(
        name="Test Policy",
        margin_pct=Decimal("0.30"),
        caf_import_pct=Decimal("0.00"),
        caf_export_pct=Decimal("0.00"),
        effective_from=timezone.now() - timedelta(days=1),
        is_active=True,
    )

    FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source="unit-test",
        rates={"USD": {"tt_buy": "0.5", "tt_sell": "0.5"}},
        caf_percent=Decimal("0.00"),
        fx_buffer_percent=Decimal("0.00"),
    )

    freight = ServiceComponent.objects.create(
        code="FRT_AIR",
        description="Air Freight",
        mode="AIR",
        leg="MAIN",
        category="TRANSPORT",
        cost_source="PARTNER_RATECARD",
        base_pgk_cost=Decimal("0.00"),
        unit="KG",
    )
    handling = ServiceComponent.objects.create(
        code="HAND_DEST",
        description="Import Handling",
        mode="AIR",
        leg="DESTINATION",
        category="HANDLING",
        base_pgk_cost=Decimal("50.00"),
        unit="SHIPMENT",
    )

    supplier = Company.objects.create(name="Test Airline", company_type="SUPPLIER")
    card = PartnerRateCard.objects.create(name="BNE-POM", supplier=supplier, currency_code="PGK")
    lane = PartnerRateLane.objects.create(
        rate_card=card,
        origin_airport=origin_ap,
        destination_airport=dest_ap,
        mode="AIR",
        shipment_type="IMPORT",
    )
    PartnerRate.objects.create(
        lane=lane,
        service_component=freight,
        unit="KG",
        rate_per_kg_fcy=Decimal("2.00"),
    )

    rule = ServiceRule.objects.create(
        mode="AIR",
        direction="IMPORT",
        incoterm="DAP",
        payment_term="PREPAID",
        service_scope="A2A",
        is_active=True,
    )
    ServiceRuleComponent.objects.create(service_rule=rule, service_component=freight, sequence=1)
    ServiceRuleComponent.objects.create(service_rule=rule, service_component=handling, sequence=2)

    return {
        "origin_loc": origin_loc,
        "dest_loc": dest_loc,
    }


def _build_quote_input(test_data) -> QuoteInput:
    """Helper to build the input object."""
    origin = test_data["origin_loc"]
    dest = test_data["dest_loc"]

    return QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency="PGK",
        shipment=ShipmentDetails(
            mode="AIR",
            shipment_type="IMPORT",
            incoterm="DAP",
            payment_term="PREPAID",
            is_dangerous_goods=False,
            service_scope="A2A",
            direction="IMPORT",
            origin_location=LocationRef(
                id=origin.id,
                code="BNE",
                name="Brisbane",
                country_code="AU",
            ),
            destination_location=LocationRef(
                id=dest.id,
                code="POM",
                name="Port Moresby",
                country_code="PG",
            ),
            pieces=[
                Piece(
                    pieces=1,
                    length_cm=Decimal("100"),
                    width_cm=Decimal("100"),
                    height_cm=Decimal("60"),
                    gross_weight_kg=Decimal("50"),
                )
            ],
        ),
    )


def test_pricing_service_v3_full_calculation(v3_test_data):
    """
    Verifies chargeable weight, partner rate lookup, tax policy, and margins.
    """
    quote_input = _build_quote_input(v3_test_data)
    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()

    assert service.context["chargeable_weight_kg"] == Decimal("100.00")

    lines = {line.service_component_code: line for line in charges.lines}
    assert set(lines.keys()) == {"FRT_AIR", "HAND_DEST"}

    freight = lines["FRT_AIR"]
    assert freight.cost_pgk == Decimal("200.00")
    assert freight.sell_pgk == Decimal("260.00")
    assert freight.sell_pgk_incl_gst == Decimal("260.00")

    handling = lines["HAND_DEST"]
    assert handling.cost_pgk == Decimal("50.00")
    assert handling.sell_pgk == Decimal("65.00")
    assert handling.sell_pgk_incl_gst == Decimal("71.50")

    assert charges.totals.total_sell_pgk == Decimal("325.00")
    assert charges.totals.total_sell_pgk_incl_gst == Decimal("331.50")


def test_input_validation_still_works(v3_test_data):
    """Ensures the serializer validation logic remains intact."""
    payload = {
        "customer_id": str(uuid.uuid4()),
        "contact_id": str(uuid.uuid4()),
        "mode": "AIR",
        "overrides": [],
    }
    serializer = QuoteComputeRequestSerializer(data=payload)
    with pytest.raises(ValidationError):
        serializer.is_valid(raise_exception=True)
