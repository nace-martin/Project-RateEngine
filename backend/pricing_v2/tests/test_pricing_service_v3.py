# backend/pricing_v2/tests/test_pricing_service_v3.py

"""V3 pricing regression tests aligned to the new dataclasses."""

import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef

from core.models import Currency, Country, City, Airport, FxSnapshot, Policy, Location
from quotes.serializers import QuoteComputeRequestSerializer
from services.models import ServiceComponent, IncotermRule


pytestmark = pytest.mark.django_db


@pytest.fixture
def v3_test_data(db):
    """Seeds the minimum reference data the V3 engine expects."""

    pgk, _ = Currency.objects.get_or_create(
        code="PGK", defaults={"name": "Papua New Guinea Kina", "minor_units": 2}
    )
    usd, _ = Currency.objects.get_or_create(
        code="USD", defaults={"name": "US Dollar", "minor_units": 2}
    )
    aud, _ = Currency.objects.get_or_create(
        code="AUD", defaults={"name": "Australian Dollar", "minor_units": 2}
    )

    country_pg, _ = Country.objects.get_or_create(
        code="PG", defaults={"name": "Papua New Guinea"}
    )
    if not country_pg.currency:
        country_pg.currency = pgk
        country_pg.save(update_fields=['currency'])

    country_au, _ = Country.objects.get_or_create(
        code="AU", defaults={"name": "Australia"}
    )
    if not country_au.currency:
        country_au.currency = aud
        country_au.save(update_fields=['currency'])
    city_pom, _ = City.objects.get_or_create(country=country_pg, name="Port Moresby")
    city_bne, _ = City.objects.get_or_create(country=country_au, name="Brisbane")

    origin, _ = Airport.objects.get_or_create(
        iata_code="BNE", defaults={"name": "Brisbane", "city": city_bne}
    )
    destination, _ = Airport.objects.get_or_create(
        iata_code="POM", defaults={"name": "Port Moresby", "city": city_pom}
    )

    origin_location, _ = Location.objects.get_or_create(
        airport=origin,
        defaults={
            "kind": Location.Kind.AIRPORT,
            "name": origin.name,
            "code": origin.iata_code,
            "country": country_au,
            "city": city_bne,
        },
    )
    destination_location, _ = Location.objects.get_or_create(
        airport=destination,
        defaults={
            "kind": Location.Kind.AIRPORT,
            "name": destination.name,
            "code": destination.iata_code,
            "country": country_pg,
            "city": city_pom,
        },
    )

    Policy.objects.create(
        name="Unit Test Policy",
        margin_pct=Decimal("0.30"),
        caf_import_pct=Decimal("0.02"),
        caf_export_pct=Decimal("0.01"),
        effective_from=timezone.now() - timedelta(days=1),
        is_active=True,
    )

    FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source="unit-test",
        rates={
            "USD": {"tt_buy": "3.40", "tt_sell": "0.30"}
        },
        caf_percent=Decimal("0.02"),
        fx_buffer_percent=Decimal("0.01"),
    )

    freight = ServiceComponent.objects.create(
        code="FRT_AIR",
        description="Freight - Air",
        mode="AIR",
        leg="ORIGIN",
        category="TRANSPORT",
        cost_type="COGS",
        cost_source="BASE_COST",
        base_pgk_cost=Decimal("200.00"),
        unit="SHIPMENT",
        tax_rate=Decimal("0.00"),
    )
    handling = ServiceComponent.objects.create(
        code="HAND_DEST",
        description="Import Handling",
        mode="AIR",
        leg="DESTINATION",
        category="HANDLING",
        cost_type="COGS",
        cost_source="BASE_COST",
        base_pgk_cost=Decimal("50.00"),
        unit="SHIPMENT",
        tax_rate=Decimal("0.10"),
    )
    fuel = ServiceComponent.objects.create(
        code="FUEL_PCT",
        description="Fuel Surcharge",
        mode="AIR",
        leg="ORIGIN",
        category="ACCESSORIAL",
        cost_type="COGS",
        cost_source="BASE_COST",
        base_pgk_cost=Decimal("0.00"),
        unit="SHIPMENT",
        tiering_json={"percent_of": "FRT_AIR", "percent": "0.10"},
        tax_rate=Decimal("0.00"),
    )

    rule = IncotermRule.objects.create(mode="AIR", shipment_type="IMPORT", incoterm="DAP")
    rule.service_components.set([freight, handling, fuel])

    return {
        "origin": origin,
        "destination": destination,
        "origin_location": origin_location,
        "destination_location": destination_location,
    }


def _build_quote_input(v3_test_data: dict) -> QuoteInput:
    origin_loc = v3_test_data["origin_location"]
    dest_loc = v3_test_data["destination_location"]

    origin_ref = LocationRef(
        id=origin_loc.id,
        kind=origin_loc.kind,
        code=origin_loc.code,
        name=origin_loc.name,
        country_code=origin_loc.country.code if origin_loc.country else None,
        currency_code=origin_loc.country.currency.code if origin_loc.country and origin_loc.country.currency else None,
    )
    destination_ref = LocationRef(
        id=dest_loc.id,
        kind=dest_loc.kind,
        code=dest_loc.code,
        name=dest_loc.name,
        country_code=dest_loc.country.code if dest_loc.country else None,
        currency_code=dest_loc.country.currency.code if dest_loc.country and dest_loc.country.currency else None,
    )

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
            pieces=[
                Piece(
                    pieces=1,
                    length_cm=Decimal("120.00"),
                    width_cm=Decimal("80.00"),
                    height_cm=Decimal("80.00"),
                    gross_weight_kg=Decimal("100.00"),
                )
            ],
            service_scope="A2A",
            direction="IMPORT",
            origin_location=origin_ref,
            destination_location=destination_ref,
        ),
    )


def test_pricing_service_v3_calculates_quote_charges(v3_test_data):
    quote_input = _build_quote_input(v3_test_data)
    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()

    assert len(charges.lines) == 3

    lines = {line.service_component_code: line for line in charges.lines}
    freight_line = lines["FRT_AIR"]
    handling_line = lines["HAND_DEST"]
    fuel_line = lines["FUEL_PCT"]

    # Base PGK costs
    assert freight_line.cost_pgk == Decimal("200.00")
    assert handling_line.cost_pgk == Decimal("50.00")
    assert fuel_line.cost_pgk == Decimal("20.00")  # 10% of freight

    margin_multiplier = Decimal("1.30")

    expected_freight_sell_pgk = (Decimal("200.00") * margin_multiplier).quantize(Decimal("0.01"))
    expected_handling_sell_pgk = (Decimal("50.00") * margin_multiplier).quantize(Decimal("0.01"))
    expected_fuel_sell_pgk = (Decimal("20.00") * margin_multiplier).quantize(Decimal("0.01"))

    assert freight_line.sell_pgk == expected_freight_sell_pgk
    assert handling_line.sell_pgk == expected_handling_sell_pgk
    assert fuel_line.sell_pgk == expected_fuel_sell_pgk

    assert handling_line.sell_pgk_incl_gst == (
        expected_handling_sell_pgk * Decimal("1.10")
    ).quantize(Decimal("0.01"))

    assert freight_line.sell_fcy == expected_freight_sell_pgk
    assert freight_line.sell_fcy_currency == "PGK"

    assert charges.totals.total_cost_pgk == Decimal("270.00")
    assert charges.totals.total_sell_pgk == Decimal("351.00")
    assert charges.totals.total_sell_pgk_incl_gst == Decimal("357.50")
    assert charges.totals.total_sell_fcy_currency == "PGK"
    assert charges.totals.has_missing_rates is False


def test_quote_compute_serializer_requires_dimensions(v3_test_data):
    payload = {
        "customer_id": str(uuid.uuid4()),
        "contact_id": str(uuid.uuid4()),
        "mode": "AIR",
        "origin_location_id": str(v3_test_data["origin_location"].id),
        "destination_location_id": str(v3_test_data["destination_location"].id),
        "incoterm": "DAP",
        "payment_term": "PREPAID",
        "service_scope": "A2A",
        "is_dangerous_goods": False,
        "dimensions": [],
        "overrides": [],
    }

    serializer = QuoteComputeRequestSerializer(data=payload)

    with pytest.raises(ValidationError):
        serializer.is_valid(raise_exception=True)
