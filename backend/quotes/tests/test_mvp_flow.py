import pytest
from decimal import Decimal
from rest_framework.test import APIClient, APITestCase
from django.contrib.auth import get_user_model
import json

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
            "name": airport.name or airport.iata_code,
            "code": airport.iata_code,
            "country": airport.city.country if airport.city else None,
            "city": airport.city,
        },
    )
    return location
