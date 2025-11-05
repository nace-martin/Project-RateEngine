
import pytest
from decimal import Decimal
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from django.utils import timezone
from core.models import Airport, City, Country, FxSnapshot, Currency
from parties.models import Company, Contact, CustomerCommercialProfile
from services.models import ServiceComponent, IncotermRule, LEG_CHOICES
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

    # Create an incoterm rule
    incoterm_rule, _ = IncotermRule.objects.get_or_create(
        mode='AIR',
        shipment_type='IMPORT',
        incoterm='DAP'
    )
    incoterm_rule.service_components.add(air_freight, dest_charges)

    Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinean Kina"})
    Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar"})

    FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source="test",
        rates={"AUD": {"tt_buy": 1.0, "tt_sell": 1.0}, "USD": {"tt_buy": 1.0, "tt_sell": 1.0}},
    )

    return air_freight, dest_charges


def test_v3_quote_creation_with_overrides_and_totals():
    """
    Tests V3 quote creation using overrides and checks the calculated totals.
    """
    # ---- Setup actors and data ----
    _, client = _mk_user_and_client()
    bne = _mk_airport("BNE", "Brisbane", "AU")
    pom = _mk_airport("POM", "Port Moresby", "PG")
    cust = _mk_customer()
    contact = Contact.objects.create(company=cust, first_name='Test', last_name='User', email='test@user.com')
    air_freight, dest_charges = _setup_test_data()
    
    profile, _ = CustomerCommercialProfile.objects.get_or_create(company=cust, defaults={'default_margin_percent': 0})

    # ---- 1) Create Quote with Overrides ----
    payload = {
        "customer_id": str(cust.id),
        "contact_id": str(contact.id),
        "mode": "AIR",
        "shipment_type": "IMPORT",
        "incoterm": "DAP",
        "origin_airport_code": "BNE",
        "destination_airport_code": "POM",
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
        "output_currency": "AUD",
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
    
    # With 0% margin, sell should equal cost
    # Chargeable weight is 112kg
    # Air freight cost = 112 * 7.10 = 795.20
    # Dest charges cost = 120.00
    # Total cost = 795.20 + 120.00 = 915.20
    assert response_data['latest_version']['totals']['total_sell_fcy'] == '915.20'
