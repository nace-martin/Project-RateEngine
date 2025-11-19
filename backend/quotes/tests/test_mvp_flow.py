
import pytest
from decimal import Decimal
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from django.utils import timezone
from core.models import Airport, City, Country, FxSnapshot, Currency, Policy, Location
from parties.models import Company, Contact, CustomerCommercialProfile
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent, LEG_CHOICES
from quotes.models import Quote

pytestmark = pytest.mark.django_db

def _mk_user_and_client():
    User = get_user_model()
    user = User.objects.create_user(
        username="tester", email="t@example.com", password="pass", is_staff=True, role='manager'
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return user, client


def _mk_airport(iata, city_name, country_code):
    country, _ = Country.objects.get_or_create(code=country_code, defaults={'name': country_code})
    city, _ = City.objects.get_or_create(name=city_name, country=country)
    airport, _ = Airport.objects.get_or_create(iata_code=iata, defaults={'name': city_name, 'city': city})
    return airport


def _mk_customer(name="Test Customer"):
    obj, _ = Company.objects.get_or_create(name=name, defaults={'company_type': 'CUSTOMER'})
    return obj


def _setup_test_data():
    # Create some service components
    air_freight = ServiceComponent.objects.create(code='AIR_FREIGHT', description='Air Freight', cost_type='COGS', unit='PER_KG', mode='AIR', leg=LEG_CHOICES[1][0])
    dest_charges = ServiceComponent.objects.create(code='DEST_CHARGES', description='Destination Charges', cost_type='COGS', unit='PER_SHIPMENT', mode='AIR', leg=LEG_CHOICES[2][0])

    service_rule, _ = ServiceRule.objects.get_or_create(
        mode='AIR',
        direction='IMPORT',
        incoterm='DAP',
        payment_term='PREPAID',
        service_scope='A2A',
        defaults={'description': 'Test rule'},
    )
    ServiceRuleComponent.objects.update_or_create(
        service_rule=service_rule,
        service_component=air_freight,
        defaults={'sequence': 1},
    )
    ServiceRuleComponent.objects.update_or_create(
        service_rule=service_rule,
        service_component=dest_charges,
        defaults={'sequence': 2},
    )

    Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinean Kina"})
    Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar"})

    FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source="test",
        rates={"AUD": {"tt_buy": 1.0, "tt_sell": 1.0}, "USD": {"tt_buy": 1.0, "tt_sell": 1.0}},
    )
    Policy.objects.get_or_create(
        name="Test Policy",
        defaults={
            "margin_pct": Decimal("0.00"),
            "caf_import_pct": Decimal("0.00"),
            "caf_export_pct": Decimal("0.00"),
            "effective_from": timezone.now(),
            "is_active": True,
        },
    )

    return air_freight, dest_charges


def _ensure_location_for_airport(airport):
    location, _ = Location.objects.get_or_create(
        airport=airport,
        defaults={
            "kind": Location.Kind.AIRPORT,
            "name": airport.name or airport.iata_code,
            "code": airport.iata_code,
            "country": airport.city.country if airport.city else None,
            "city": airport.city,
        },
    )
    return location


def test_v3_quote_creation_with_overrides_and_totals():
    """
    Tests V3 quote creation using overrides and checks the calculated totals.
    """
    # ---- Setup actors and data ----
    _, client = _mk_user_and_client()
    bne = _mk_airport("BNE", "Brisbane", "AU")
    pom = _mk_airport("POM", "Port Moresby", "PG")
    origin_location = _ensure_location_for_airport(bne)
    destination_location = _ensure_location_for_airport(pom)
    cust = _mk_customer()
    contact = Contact.objects.create(company=cust, first_name='Test', last_name='User', email='test@user.com')
    air_freight, dest_charges = _setup_test_data()
    
    profile, _ = CustomerCommercialProfile.objects.get_or_create(company=cust, defaults={'default_margin_percent': 0})

    # ---- 1) Create Quote with Overrides ----
    payload = {
        "customer_id": str(cust.id),
        "contact_id": str(contact.id),
        "mode": "AIR",
        "incoterm": "DAP",
        "service_scope": "A2A",
        "origin_location_id": str(origin_location.id),
        "destination_location_id": str(destination_location.id),
        "dimensions": [
            {
                "pieces": 1,
                "length_cm": "120",
                "width_cm": "80",
                "height_cm": "70",
                "gross_weight_kg": "85.00",
            }
        ],
        "payment_term": "PREPAID",
        "overrides": [
            {
                "service_component_id": str(air_freight.id),
                "cost_fcy": "7.10",
                "currency": "AUD",
                "unit": "PER_KG",
            },
            {
                "service_component_id": str(dest_charges.id),
                "cost_fcy": "120.00",
                "currency": "AUD",
                "unit": "PER_SHIPMENT",
            }
        ]
    }
    r = client.post("/api/v3/quotes/compute/", data=payload, format="json")
    assert r.status_code == 201, r.content
    
    response_data = r.json()
    
    # Dimensions: 120 x 80 x 70 = 672,000 ccm -> 112kg volumetric vs 85kg gross
    # Air freight cost = 112 * 7.10 = 795.20
    # Dest charges cost = 120.00
    # Total cost = 915.20
    assert response_data['latest_version']['totals']['total_sell_fcy'] == '915.20'


def test_v3_quote_rejects_legacy_airport_fields():
    _, client = _mk_user_and_client()
    cust = _mk_customer("Legacy Contract Co")
    contact = Contact.objects.create(company=cust, first_name='Legacy', last_name='Field', email='legacy@example.com')

    payload = {
        "customer_id": str(cust.id),
        "contact_id": str(contact.id),
        "mode": "AIR",
        "incoterm": "DAP",
        "service_scope": "A2A",
        "origin_airport_code": "BNE",
        "destination_airport_code": "POM",
        "dimensions": [
            {
                "pieces": 1,
                "length_cm": "10",
                "width_cm": "10",
                "height_cm": "10",
                "gross_weight_kg": "10.00",
            }
        ],
        "payment_term": "PREPAID",
    }

    response = client.post("/api/v3/quotes/compute/", data=payload, format="json")
    assert response.status_code == 400
    assert "origin_location_id" in response.json()
