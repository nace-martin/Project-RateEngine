# backend/pricing_v2/tests/test_smart_quoting.py

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece
from core.models import FxSnapshot, Policy, Airport, Country, City
from services.models import ServiceComponent, IncotermRule

pytestmark = pytest.mark.django_db

@pytest.fixture
def smart_quoting_test_data(db):
    """Seeds the minimum reference data the V3 engine expects."""
    country_pg, _ = Country.objects.get_or_create(code="PG", defaults={"name": "Papua New Guinea"})
    country_au, _ = Country.objects.get_or_create(code="AU", defaults={"name": "Australia"})
    city_pom, _ = City.objects.get_or_create(country=country_pg, name="Port Moresby")
    city_bne, _ = City.objects.get_or_create(country=country_au, name="Brisbane")

    origin, _ = Airport.objects.get_or_create(iata_code="BNE", defaults={"name": "Brisbane", "city": city_bne})
    destination, _ = Airport.objects.get_or_create(iata_code="POM", defaults={"name": "Port Moresby", "city": city_pom})

    Policy.objects.create(
        name="Unit Test Policy",
        margin_pct=Decimal("0.30"),
        effective_from=timezone.now(),
        is_active=True,
    )

    FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source="unit-test",
        rates={"USD": {"tt_buy": "3.40", "tt_sell": "0.30"}},
    )

    freight = ServiceComponent.objects.create(
        code="FRT_AIR",
        description="Freight - Air",
        mode="AIR",
        base_pgk_cost=Decimal("200.00"),
    )
    handling = ServiceComponent.objects.create(
        code="HAND_DEST",
        description="Import Handling",
        mode="AIR",
        base_pgk_cost=Decimal("50.00"),
    )
    pickup = ServiceComponent.objects.create(
        code="PICKUP",
        description="Pickup",
        mode="AIR",
        base_pgk_cost=Decimal("100.00"),
    )
    delivery = ServiceComponent.objects.create(
        code="DELIVERY",
        description="Delivery",
        mode="AIR",
        base_pgk_cost=Decimal("150.00"),
    )

    # D2D
    rule_d2d = IncotermRule.objects.create(mode="AIR", shipment_type="IMPORT", incoterm="DAP", service_level="D2D", payment_term="PREPAID")
    rule_d2d.service_components.set([freight, handling, pickup, delivery])

    # A2D
    rule_a2d = IncotermRule.objects.create(mode="AIR", shipment_type="IMPORT", incoterm="DAP", service_level="A2D", payment_term="PREPAID")
    rule_a2d.service_components.set([freight, handling, delivery])

    # D2A
    rule_d2a = IncotermRule.objects.create(mode="AIR", shipment_type="IMPORT", incoterm="DAP", service_level="D2A", payment_term="PREPAID")
    rule_d2a.service_components.set([freight, handling, pickup])

    # A2A
    rule_a2a = IncotermRule.objects.create(mode="AIR", shipment_type="IMPORT", incoterm="DAP", service_level="A2A", payment_term="PREPAID")
    rule_a2a.service_components.set([freight, handling])


    return {
        "origin": origin,
        "destination": destination,
    }

def _build_quote_input(test_data: dict, incoterm: str, origin_address: str = None, destination_address: str = None) -> QuoteInput:
    return QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency="PGK",
        shipment=ShipmentDetails(
            mode="AIR",
            shipment_type="IMPORT",
            origin_code=test_data["origin"].iata_code,
            destination_code=test_data["destination"].iata_code,
            incoterm=incoterm,
            payment_term="PREPAID",
            is_dangerous_goods=False,
            pieces=[
                Piece(
                    pieces=1,
                    length_cm=1,
                    width_cm=1,
                    height_cm=1,
                    gross_weight_kg=Decimal("100.00"),
                )
            ],
            origin_address=origin_address,
            destination_address=destination_address,
        ),
    )

def test_d2d_scenario(smart_quoting_test_data):
    quote_input = _build_quote_input(smart_quoting_test_data, "DAP", origin_address="some address", destination_address="some address")
    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()
    assert len(charges.lines) == 4

def test_a2d_scenario(smart_quoting_test_data):
    quote_input = _build_quote_input(smart_quoting_test_data, "DAP", destination_address="some address")
    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()
    assert len(charges.lines) == 3

def test_d2a_scenario(smart_quoting_test_data):
    quote_input = _build_quote_input(smart_quoting_test_data, "DAP", origin_address="some address")
    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()
    assert len(charges.lines) == 3

def test_a2a_scenario(smart_quoting_test_data):
    quote_input = _build_quote_input(smart_quoting_test_data, "DAP")
    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()
    assert len(charges.lines) == 2
