from decimal import Decimal
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.utils import timezone

from core.models import Location, FxSnapshot, Policy, Country, City, Airport
from quotes.models import Quote
from services.models import ServiceComponent, ServiceRule, ServiceRuleComponent
from parties.models import Company
from pricing_v3.models import QuoteSpotRate, QuoteSpotCharge, ChargeMethod, ChargeUnit

class QuoteComputeViewTests(APITestCase):
    def setUp(self):
        # Setup common data
        self.company = Company.objects.create(name="Test Supplier")
        self.customer = Company.objects.create(name="Test Customer")
        
        self.country = Country.objects.create(code="AU", name="Australia")
        self.city = City.objects.create(country=self.country, name="Brisbane")
        self.airport = Airport.objects.create(iata_code="BNE", name="Brisbane Airport", city=self.city)
        self.location = Location.objects.create(
            kind="AIRPORT", name="BNE Airport", code="BNE", 
            country=self.country, city=self.city, airport=self.airport
        )
        
        self.component = ServiceComponent.objects.create(
            code="FRT_AIR", description="Air Freight", 
            mode="AIR", leg="MAIN", is_active=True
        )
        
        self.policy = Policy.objects.create(name="Test Policy", effective_from=timezone.now())
        self.fx_snapshot = FxSnapshot.objects.create(
            as_of_timestamp=timezone.now(), source="Test", rates={}
        )
        
        self.quote = Quote.objects.create(
            customer=self.customer,
            origin_location=self.location,
            destination_location=self.location,
            mode="AIR",
            shipment_type="IMPORT",
            incoterm="EXW",
            payment_term="PREPAID",
            service_scope="D2D",
            policy=self.policy,
            fx_snapshot=self.fx_snapshot
        )
        
        # Setup ServiceRule to ensure component is resolved
        self.rule = ServiceRule.objects.create(
            mode="AIR", direction="IMPORT", incoterm="EXW", 
            payment_term="PREPAID", service_scope="D2D",
            effective_from=timezone.now()
        )
        ServiceRuleComponent.objects.create(
            service_rule=self.rule, service_component=self.component
        )

    def test_compute_endpoint(self):
        # Add a spot rate
        spot_rate = QuoteSpotRate.objects.create(
            quote=self.quote, supplier=self.company,
            origin_location=self.location, destination_location=self.location,
            mode="AIR", currency="USD"
        )
        QuoteSpotCharge.objects.create(
            spot_rate=spot_rate, component=self.component,
            method=ChargeMethod.PER_UNIT, unit=ChargeUnit.KG,
            rate=Decimal("5.50")
        )

        url = reverse('quote-compute', args=[self.quote.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['buy_charges']), 1)
        self.assertEqual(response.data['buy_charges'][0]['source'], 'SPOT')
        self.assertEqual(response.data['buy_charges'][0]['component_code'], 'FRT_AIR')
