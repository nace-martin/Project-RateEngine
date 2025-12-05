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
    # Pydantic returns errors as a list of dicts with 'loc', 'msg', 'type' keys
    errors = response.json()
    assert any('origin_location_id' in str(e.get('loc', [])) for e in errors)

# --- V3 Weight Break Tier Rating Tests ---

class WeightBreakTierRatingTestCase(APITestCase):
    def setUp(self):
        # 1. Setup User and Client
        User = get_user_model()
        self.user = User.objects.create_user(
            username="tier_tester", email="tier_tester@example.com", password="pass", is_staff=True, role='manager'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # 2. Setup Currencies, FX, and Policy
        Currency.objects.get_or_create(code="PGK", defaults={"name": "Papua New Guinean Kina"})
        Currency.objects.get_or_create(code="AUD", defaults={"name": "Australian Dollar"})
        FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(),
            source="test",
            # Use 1:1 AUD:PGK for easy cost assertion
            rates={"AUD": {"tt_buy": "2.50", "tt_sell": "2.60"}, "USD": {"tt_buy": 1.0, "tt_sell": 1.0}},
        )
        Policy.objects.get_or_create(
            name="Test Policy",
            defaults={
                "margin_pct": Decimal("0.15"), # 15% margin
                "caf_import_pct": Decimal("0.05"), # 5% CAF on buy rates
                "effective_from": timezone.now(),
                "is_active": True,
            },
        )

        # 3. Setup Locations
        bne_ap = _mk_airport("BNE", "Brisbane", "AU")
        pom_ap = _mk_airport("POM", "Port Moresby", "PG")
        self.origin_loc = _ensure_location_for_airport(bne_ap)
        self.dest_loc = _ensure_location_for_airport(pom_ap)

        # 4. Setup Customer
        self.customer = _mk_customer("Tiered Rate Customer")
        self.contact = Contact.objects.create(company=self.customer, first_name='Tier', last_name='Test', email='tier@test.com')
        CustomerCommercialProfile.objects.get_or_create(company=self.customer, defaults={'default_margin_percent': 0})
        
        # 5. Setup Service Component with TIERED rates
        self.air_freight_tiered = ServiceComponent.objects.create(
            code='FRT_AIR',
            description='Air Freight (Tiered)',
            mode='AIR',
            leg='MAIN',
            tiering_json={
                "type": "weight_break",
                "currency": "AUD",
                "minimum_charge": "330.00",
                "breaks": [
                    { "min_kg": 45,   "rate_per_kg": "7.05" },
                    { "min_kg": 100,  "rate_per_kg": "6.75" },
                    { "min_kg": 250,  "rate_per_kg": "6.55" },
                    { "min_kg": 500,  "rate_per_kg": "6.25" },
                    { "min_kg": 1000, "rate_per_kg": "5.95" }
                ]
            }
        )
        
        # 6. Setup a simple destination charge for total calculation
        self.dest_charges_simple = ServiceComponent.objects.create(
            code='DEST_HAND', description='Destination Handling', mode='AIR', leg='DESTINATION', base_pgk_cost="150.00"
        )
        
        # 7. Setup the Service Rule to include these components
        service_rule, _ = ServiceRule.objects.get_or_create(
            mode='AIR', direction='IMPORT', incoterm='EXW', payment_term='COLLECT', service_scope='D2D',
            defaults={'description': 'Test Tiered Rule'},
        )
        ServiceRuleComponent.objects.get_or_create(
            service_rule=service_rule, service_component=self.air_freight_tiered, defaults={'sequence': 1}
        )
        ServiceRuleComponent.objects.get_or_create(
            service_rule=service_rule, service_component=self.dest_charges_simple, defaults={'sequence': 2}
        )

    def _get_quote_line(self, response_data, component_code):
        """Helper to find a specific charge line in the quote response."""
        lines = response_data['latest_version']['lines']
        for line in lines:
            if line['service_component']['code'] == component_code:
                return line
        return None

    def test_quote_with_mid_tier_weight(self):
        """Tests a chargeable weight that falls into the 100kg tier."""
        payload = {
            "customer_id": str(self.customer.id), "contact_id": str(self.contact.id), "mode": "AIR",
            "incoterm": "EXW", "service_scope": "D2D", "payment_term": "COLLECT",
            "origin_location_id": str(self.origin_loc.id), "destination_location_id": str(self.dest_loc.id),
            "dimensions": [{"pieces": 1, "length_cm": 10, "width_cm": 10, "height_cm": 10, "gross_weight_kg": "120.00"}] # 120kg falls in 100kg tier
        }
        
        r = self.client.post("/api/v3/quotes/compute/", data=payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        
        response_data = r.json()
        
        # --- Assertions for FRT_AIR line ---
        frt_line = self._get_quote_line(response_data, 'FRT_AIR')
        self.assertIsNotNone(frt_line)
        
        # Cost Calculation:
        # Rate = 6.75 AUD per kg
        # Cost FCY = 120kg * 6.75 = 810.00 AUD
        self.assertEqual(frt_line['cost_fcy'], '810.00')
        self.assertEqual(frt_line['cost_fcy_currency'], 'AUD')
        self.assertEqual(frt_line['cost_source'], 'TIERED_RATECARD')
        
        # Cost PGK = Cost FCY * (FX Rate * (1 + CAF))
        # Cost PGK = 810.00 * (2.50 * 1.05) = 810.00 * 2.625 = 2126.25 PGK
        self.assertEqual(frt_line['cost_pgk'], '2126.25')

        # Sell Calculation:
        # Sell PGK = Cost PGK * (1 + Margin)
        # Sell PGK = 2126.25 * 1.15 = 2445.19 PGK
        self.assertEqual(frt_line['sell_pgk'], '2445.19')

    def test_quote_with_minimum_charge(self):
        """Tests a chargeable weight below the lowest tier, which should trigger the minimum."""
        payload = {
            "customer_id": str(self.customer.id), "contact_id": str(self.contact.id), "mode": "AIR",
            "incoterm": "EXW", "service_scope": "D2D", "payment_term": "COLLECT",
            "origin_location_id": str(self.origin_loc.id), "destination_location_id": str(self.dest_loc.id),
            "dimensions": [{"pieces": 1, "length_cm": 10, "width_cm": 10, "height_cm": 10, "gross_weight_kg": "20.00"}] # 20kg is below 45kg tier
        }

        r = self.client.post("/api/v3/quotes/compute/", data=payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        response_data = r.json()
        
        frt_line = self._get_quote_line(response_data, 'FRT_AIR')
        self.assertIsNotNone(frt_line)
        
        # Cost Calculation:
        # Rate for 20kg would be 7.05 -> 20 * 7.05 = 141.00 AUD
        # This is LESS than the minimum of 330.00 AUD, so minimum applies.
        self.assertEqual(frt_line['cost_fcy'], '330.00') # <-- Should be the minimum charge
        self.assertEqual(frt_line['cost_fcy_currency'], 'AUD')

        # Cost PGK = 330.00 * (2.50 * 1.05) = 330.00 * 2.625 = 866.25 PGK
        self.assertEqual(frt_line['cost_pgk'], '866.25')
        
        # Sell PGK = 866.25 * 1.15 = 996.19 PGK
        self.assertEqual(frt_line['sell_pgk'], '996.19')

    def test_quote_with_highest_tier(self):
        """Tests a chargeable weight that falls into the highest tier."""
        payload = {
            "customer_id": str(self.customer.id), "contact_id": str(self.contact.id), "mode": "AIR",
            "incoterm": "EXW", "service_scope": "D2D", "payment_term": "COLLECT",
            "origin_location_id": str(self.origin_loc.id), "destination_location_id": str(self.dest_loc.id),
            "dimensions": [{"pieces": 1, "length_cm": 10, "width_cm": 10, "height_cm": 10, "gross_weight_kg": "1500.00"}] # 1500kg falls in 1000kg tier
        }
        
        r = self.client.post("/api/v3/quotes/compute/", data=payload, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        response_data = r.json()

        frt_line = self._get_quote_line(response_data, 'FRT_AIR')
        self.assertIsNotNone(frt_line)

        # Cost Calculation:
        # Rate = 5.95 AUD per kg
        # Cost FCY = 1500kg * 5.95 = 8925.00 AUD
        self.assertEqual(frt_line['cost_fcy'], '8925.00')
        
        # Cost PGK = 8925.00 * (2.50 * 1.05) = 8925.00 * 2.625 = 23428.13 PGK
        self.assertEqual(frt_line['cost_pgk'], '23428.13')
        
        # Sell PGK = 23428.13 * 1.15 = 26942.35 PGK
        self.assertEqual(frt_line['sell_pgk'], '26942.35')