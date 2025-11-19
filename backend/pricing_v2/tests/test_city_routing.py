import pytest
import uuid
from decimal import Decimal
from django.utils import timezone

from core.models import Location, Airport, City, Country, Currency, FxSnapshot, Policy
from ratecards.models import PartnerRateCard, PartnerRateLane, PartnerRate
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent
from parties.models import Company
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, Piece, LocationRef

pytestmark = pytest.mark.django_db


@pytest.fixture
def city_routing_data(db):
    """
    Set up Lae City (CITY) linked to NAD airport and a rate from NAD->POM.
    """
    pgk, _ = Currency.objects.get_or_create(code="PGK")
    pg_country, _ = Country.objects.get_or_create(code="PG", defaults={"currency": pgk})

    nad_airport, _ = Airport.objects.get_or_create(iata_code="NAD", defaults={"name": "Nadzab"})
    pom_airport, _ = Airport.objects.get_or_create(iata_code="POM", defaults={"name": "Port Moresby"})

    lae_city_loc, _ = Location.objects.get_or_create(
        name="Lae City",
        defaults={
            "kind": "CITY",
            "country": pg_country,
            "airport": nad_airport,  # Critical link City -> Airport
            "code": "LAE",
        },
    )

    pom_airport_loc, _ = Location.objects.get_or_create(
        name="POM Airport",
        defaults={
            "kind": "AIRPORT",
            "country": pg_country,
            "airport": pom_airport,
            "code": "POM",
        },
    )

    supplier = Company.objects.create(name="Air Partner", company_type="SUPPLIER")
    card = PartnerRateCard.objects.create(supplier=supplier, name="Test Air Rates", currency_code="PGK")
    lane = PartnerRateLane.objects.create(
        rate_card=card,
        origin_airport=nad_airport,
        destination_airport=pom_airport,
        mode="AIR",
        shipment_type="DOMESTIC",
    )

    freight_comp = ServiceComponent.objects.create(
        code="FRT_AIR",
        description="Air Freight",
        mode="AIR",
        leg="MAIN",
        cost_source="PARTNER_RATECARD",
        category="TRANSPORT",
        base_pgk_cost=Decimal("0.00"),  # Force lookup
    )

    PartnerRate.objects.create(
        lane=lane,
        service_component=freight_comp,
        unit="KG",
        rate_per_kg_fcy=Decimal("5.50"),
    )

    Policy.objects.create(is_active=True, margin_pct=Decimal("0.1"), effective_from=timezone.now())
    FxSnapshot.objects.create(rates={}, as_of_timestamp=timezone.now())

    rule = ServiceRule.objects.create(
        mode="AIR",
        direction="DOMESTIC",
        incoterm="DAP",
        payment_term="PREPAID",
        service_scope="D2A",
        is_active=True,
    )
    ServiceRuleComponent.objects.create(service_rule=rule, service_component=freight_comp, sequence=1)

    return {
        "origin": lae_city_loc,
        "dest": pom_airport_loc,
        "comp": freight_comp,
    }


def test_city_origin_maps_to_airport_rate(city_routing_data):
    """
    Ensure that quoting from Lae City finds the NAD->POM rate.
    """
    origin = city_routing_data["origin"]
    dest = city_routing_data["dest"]

    origin_ref = LocationRef(
        id=origin.id,
        kind=origin.kind,
        code=origin.code,
        name=origin.name,
        country_code="PG",
    )
    dest_ref = LocationRef(
        id=dest.id,
        kind=dest.kind,
        code=dest.code,
        name=dest.name,
        country_code="PG",
    )

    shipment = ShipmentDetails(
        mode="AIR",
        shipment_type="DOMESTIC",
        incoterm="DAP",
        payment_term="PREPAID",
        is_dangerous_goods=False,
        service_scope="D2A",
        origin_location=origin_ref,
        destination_location=dest_ref,
        pieces=[
            Piece(
                pieces=1,
                gross_weight_kg=Decimal("10.0"),
                length_cm=Decimal("10"),
                width_cm=Decimal("10"),
                height_cm=Decimal("10"),
            )
        ],
    )

    quote_input = QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency="PGK",
        shipment=shipment,
    )

    service = PricingServiceV3(quote_input)
    charges = service.calculate_charges()

    freight_line = next(l for l in charges.lines if l.service_component_code == "FRT_AIR")

    assert freight_line.cost_pgk == Decimal("55.00")
    assert freight_line.cost_source == "PARTNER_RATECARD"
    assert "Test Air Rates" in freight_line.cost_source_description
