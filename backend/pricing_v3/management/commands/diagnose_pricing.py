from django.core.management.base import BaseCommand
from quotes.models import Quote
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import QuoteInput, ShipmentDetails, LocationRef, Piece
from services.models import ServiceComponent
from ratecards.models import PartnerRateLane, PartnerRate
from core.models import Location

class Command(BaseCommand):
    help = 'Diagnoses why PricingServiceV3 is not finding rates'

    def add_arguments(self, parser):
        parser.add_argument('quote_id', type=str)

    def handle(self, *args, **options):
        quote_id = options['quote_id']
        quote = Quote.objects.get(id=quote_id)
        
        self.stdout.write(f"=== DIAGNOSTIC FOR QUOTE {quote_id} ===\n")
        
        # 1. Check the Quote object fields
        self.stdout.write(f"Quote Mode: {quote.mode}")
        self.stdout.write(f"Quote Shipment Type: {quote.shipment_type}")
        self.stdout.write(f"Quote Origin: {quote.origin_location}")
        self.stdout.write(f"Quote Destination: {quote.destination_location}\n")
        
        # 2. Build QuoteInput like the views.py does
        origin_location = quote.origin_location
        dest_location = quote.destination_location
        
        # Build LocationRef
        def loc_to_ref(loc: Location):
            return LocationRef(
                id=loc.id,
                code=loc.code,
                name=loc.name,
                country_code=loc.country.code if loc.country else None,
                currency_code=loc.country.currency.code if loc.country and loc.country.currency else None,
            )
        
        origin_ref = loc_to_ref(origin_location)
        dest_ref = loc_to_ref(dest_location)
        
        # Minimal ShipmentDetails
        shipment = ShipmentDetails(
            mode=quote.mode,
            shipment_type=quote.shipment_type,
            incoterm=quote.incoterm,
            payment_term=quote.payment_term,
            is_dangerous_goods=quote.is_dangerous_goods,
            pieces=[Piece(pieces=1, length_cm=10, width_cm=10, height_cm=10, gross_weight_kg=100)],
            service_scope=quote.service_scope,
            direction=quote.shipment_type,
            origin_location=origin_ref,
            destination_location=dest_ref,
        )
        
        quote_input = QuoteInput(
            customer_id=quote.customer.id,
            contact_id=quote.contact.id,
            output_currency='PGK',
            shipment=shipment,
            overrides=[]
        )
        
        # 3. Instantiate PricingServiceV3
        service = PricingServiceV3(quote_input)
        
        # 4. Check what codes are used
        origin_code = origin_ref.code
        dest_code = dest_ref.code
        
        self.stdout.write(f"Resolved Origin Code: {origin_code}")
        self.stdout.write(f"Resolved Dest Code: {dest_code}\n")
        
        # 5. Check PartnerRateLane table
        self.stdout.write("=== Checking PartnerRateLane Table ===")
        lanes = PartnerRateLane.objects.filter(
            mode=quote.mode,
            origin_airport__iata_code=origin_code,
            destination_airport__iata_code=dest_code,
        )
        
        self.stdout.write(f"Found {lanes.count()} lanes matching mode + airports")
        
        for lane in lanes:
            self.stdout.write(f"  - Lane {lane.id}: {lane}")
            self.stdout.write(f"    Mode: {lane.mode}")
            self.stdout.write(f"    Shipment Type: {lane.shipment_type}")
            self.stdout.write(f"    Rate Card: {lane.rate_card.name}")
            
            # Check if it has rates
            rates_count = lane.rates.count()
            self.stdout.write(f"    Total Rates: {rates_count}")
            
            # List all rates
            for rate in lane.rates.all().select_related('service_component'):
                self.stdout.write(f"      - Component: {rate.service_component.code}")
        
        # 6. Try the exact query that PricingServiceV3._get_buy_rate uses
        self.stdout.write("\n=== Testing Actual PricingServiceV3 Query ===")
        
        # Pick a test component
        test_comp = ServiceComponent.objects.filter(code='FRT_AIR').first()
        if test_comp:
            self.stdout.write(f"Testing with component: {test_comp.code}")
            
            # This is the EXACT query from line 323-330 of pricing_service_v3.py
            try:
                rate = PartnerRate.objects.get(
                    lane__mode=quote.mode,
                    lane__shipment_type=quote.shipment_type,
                    lane__origin_airport__iata_code=origin_code,
                    lane__destination_airport__iata_code=dest_code,
                    service_component=test_comp
                )
                self.stdout.write(f"  SUCCESS: Found rate!")
                self.stdout.write(f"    Rate: {rate}")
                self.stdout.write(f"    Lane: {rate.lane}")
                self.stdout.write(f"    Lane Shipment Type: {rate.lane.shipment_type}")
            except PartnerRate.DoesNotExist:
                self.stdout.write(f"  FAILED: No rate found")
                self.stdout.write(f"  Query filters:")
                self.stdout.write(f"    - lane__mode={quote.mode}")
                self.stdout.write(f"    - lane__shipment_type={quote.shipment_type}")
                self.stdout.write(f"    - lane__origin_airport__iata_code={origin_code}")
                self.stdout.write(f"    - lane__destination_airport__iata_code={dest_code}")
                self.stdout.write(f"    - service_component={test_comp}")
            except Exception as e:
                self.stdout.write(f"  ERROR: {e}")
