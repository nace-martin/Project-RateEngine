from django.core.management.base import BaseCommand
from pricing_v2.pricing_service_v3 import PricingServiceV3
from quotes.models import Quote
from decimal import Decimal
import uuid
from pricing_v2.dataclasses_v3 import QuoteInput, Piece, LocationRef, ShipmentDetails

class Command(BaseCommand):
    help = 'Verify Phase 2 pricing logic'

    def handle(self, *args, **options):
        # Create dummy input
        
        origin = LocationRef(id=uuid.uuid4(), code="BNE", name="Brisbane", country_code="AU", currency_code="AUD")
        destination = LocationRef(id=uuid.uuid4(), code="POM", name="Port Moresby", country_code="PG", currency_code="PGK")
        
        pieces = [Piece(1, Decimal("10"), Decimal("10"), Decimal("10"), Decimal("100"))]
        
        shipment = ShipmentDetails(
            mode="AIR",
            shipment_type="IMPORT",
            incoterm="EXW",
            payment_term="COLLECT",
            is_dangerous_goods=False,
            pieces=pieces,
            service_scope="D2D",
            direction="IMPORT",
            origin_location=origin,
            destination_location=destination
        )
        
        quote_input = QuoteInput(
            customer_id=uuid.uuid4(),
            contact_id=uuid.uuid4(),
            output_currency="PGK",
            shipment=shipment
        )
        
        # We need to ensure we have a valid policy in DB
        from core.models import Policy
        if not Policy.objects.exists():
            Policy.objects.create(
                name="Test Policy",
                margin_pct=Decimal("0.20"),
                caf_import_pct=Decimal("0.05"),
                caf_export_pct=Decimal("0.00"),
                gst_rate=Decimal("0.10"),
                is_active=True
            )
            
        service = PricingServiceV3(quote_input)
        charges = service.calculate_charges()
        
        output_lines = []
        output_lines.append(f"{'Component':<15} {'Leg':<15} {'Method':<15} {'Cost':<10} {'Sell':<10} {'GST':<6} {'Total':<10}")
        output_lines.append("-" * 90)
        
        target_comps = ['FRT_AIR', 'PICKUP', 'XRAY', 'PICKUP_FUEL', 'HANDLING', 'CARTAGE']
        
        for line in charges.lines:
            if line.service_component_code in target_comps:
                # Calculate actual margin
                if line.cost_pgk > 0:
                    margin = ((line.sell_pgk - line.cost_pgk) / line.cost_pgk) * 100
                else:
                    margin = Decimal(0)
                
                # Get pricing method
                method = "N/A"
                from services.models import ServiceComponent
                comp = ServiceComponent.objects.get(code=line.service_component_code)
                if comp.service_code:
                    method = comp.service_code.pricing_method
                
                gst_amt = line.sell_pgk_incl_gst - line.sell_pgk
                
                output_lines.append(f"{line.service_component_code:<15} {line.leg:<15} {method:<15} {line.cost_pgk:<10} {line.sell_pgk:<10} {gst_amt:<6} {line.sell_pgk_incl_gst:<10}")
        
        with open('verify_output.txt', 'w') as f:
            f.write('\n'.join(output_lines))
        
        self.stdout.write("Verification complete. Check verify_output.txt")
