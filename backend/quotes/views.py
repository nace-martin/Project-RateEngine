# backend/quotes/views.py

from rest_framework import generics, viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404

from .models import Quote, QuoteVersion, QuoteLine, QuoteTotal
from .serializers import QuoteComputeRequestSerializer, QuoteModelSerializerV3
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import (
    QuoteInput, QuoteCharges, ShipmentDetails, Piece, ManualOverride
)
from core.models import FxSnapshot, Policy, Airport # --- ADDED IMPORT ---
from parties.models import Company, Contact

class QuoteComputeV3APIView(generics.CreateAPIView):
    """
    The main V3 compute endpoint.
    Receives a quote request, calculates charges, and saves the quote.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = QuoteComputeRequestSerializer
    
    # Note: We override 'create' behavior by implementing 'post'
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            validated_data = serializer.validated_data
            
            # --- MVP CHECK: Block DG ---
            if validated_data.get('is_dangerous_goods'):
                return Response(
                    {"detail": "Dangerous Goods (DG) shipments are not yet supported."},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # --- NEW: Get location objects ---
            mode = validated_data.get('mode')
            origin_airport = validated_data.get('origin_airport')
            destination_airport = validated_data.get('destination_airport')
            
            # --- NEW: Shipment Type Classification Logic ---
            shipment_type = None
            if mode == 'AIR':
                if not origin_airport or not destination_airport:
                    return Response(
                        {"detail": "Origin and Destination airport are required for AIR mode."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Get country codes from the master data
                org_country = origin_airport.city.country.code
                dest_country = destination_airport.city.country.code
                
                if org_country == 'PG' and dest_country == 'PG':
                    shipment_type = Quote.ShipmentType.DOMESTIC
                elif org_country != 'PG' and dest_country == 'PG':
                    shipment_type = Quote.ShipmentType.IMPORT
                elif org_country == 'PG' and dest_country != 'PG':
                    shipment_type = Quote.ShipmentType.EXPORT
                else:
                    # e.g., AU to NZ
                    return Response(
                        {"detail": "Cross-border shipments not involving PNG are not yet supported."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            elif mode == 'SEA':
                 return Response(
                    {"detail": "SEA mode is not yet supported."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            else:
                 return Response(
                    {"detail": f"Mode '{mode}' is not supported."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # --- END OF NEW LOGIC ---

            try:
                # 1. Prepare input for PricingServiceV3
                quote_input = self._build_quote_input(validated_data, shipment_type)
                
                # 2. Call the pricing service
                service = PricingServiceV3(quote_input)
                calculated_charges = service.calculate_charges()
                
                # 3. Save to DB
                quote = self._save_quote_v3(
                    request, 
                    validated_data, 
                    shipment_type, # <-- Pass calculated type
                    calculated_charges, 
                    service.get_fx_snapshot(),
                    service.get_policy()
                )
                
                # 4. Serialize and return the created quote
                response_serializer = QuoteModelSerializerV3(quote)
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)

            except Exception as e:
                # Log the full exception
                print(f"Error during quote computation: {e}")
                return Response(
                    {"detail": f"An unexpected error occurred: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def _build_quote_input(self, data, shipment_type):
        """Helper to convert serializer data to PricingService dataclasses."""
        
        # --- Use validated objects ---
        origin_code = data['origin_airport'].iata_code
        destination_code = data['destination_airport'].iata_code
        # ---
        
        shipment_details = ShipmentDetails(
            mode=data['mode'],
            shipment_type=shipment_type, # <-- Use calculated type
            origin_code=origin_code,
            destination_code=destination_code,
            incoterm=data['incoterm'],
            payment_term=data['payment_term'],
            is_dangerous_goods=data['is_dangerous_goods'],
            pieces=[Piece(**p) for p in data['dimensions']]
        )
        
        overrides = [ManualOverride(**o) for o in data.get('overrides', [])]
        
        return QuoteInput(
            customer_id=data['customer_id'],
            contact_id=data['contact_id'],
            output_currency=data.get('output_currency', 'PGK'),
            shipment=shipment_details,
            overrides=overrides
        )

    @transaction.atomic
    def _save_quote_v3(self, request, validated_data, shipment_type, charges: QuoteCharges, snapshot: FxSnapshot, policy: Policy):
        """
        Helper to save the quote, version, lines, and totals to the database.
        """
        customer = get_object_or_404(Company, id=validated_data['customer_id'])
        contact = get_object_or_404(Contact, id=validated_data['contact_id'])
        
        # --- UPDATED: Create the Quote object ---
        quote = Quote.objects.create(
            customer=customer,
            contact=contact,
            mode=validated_data['mode'],
            shipment_type=shipment_type, # <-- Save calculated type
            incoterm=validated_data['incoterm'],
            payment_term=validated_data['payment_term'],
            output_currency=validated_data.get('output_currency', 'PGK'),
            origin_airport=validated_data.get('origin_airport'), # <-- Save new field
            destination_airport=validated_data.get('destination_airport'), # <-- Save new field
            # TODO: save origin_port / destination_port when SEA is added
            policy=policy,
            fx_snapshot=snapshot,
            is_dangerous_goods=validated_data['is_dangerous_goods'],
            status=Quote.Status.DRAFT,
            request_details_json=request.data,
            created_by=request.user
        )
        # --- END UPDATE ---

        # Create the first QuoteVersion
        version = QuoteVersion.objects.create(
            quote=quote,
            version_number=1,
            payload_json=request.data,
            policy=policy,
            fx_snapshot=snapshot,
            status=Quote.Status.DRAFT,
            reason="Initial Draft",
            created_by=request.user
        )
        
        # Create QuoteLines
        for line_charge in charges.lines:
            QuoteLine.objects.create(
                quote_version=version,
                service_component_id=line_charge.service_component_id,
                cost_pgk=line_charge.cost_pgk,
                cost_fcy=line_charge.cost_fcy,
                cost_fcy_currency=line_charge.cost_fcy_currency,
                sell_pgk=line_charge.sell_pgk,
                sell_pgk_incl_gst=line_charge.sell_pgk_incl_gst,
                sell_fcy=line_charge.sell_fcy,
                sell_fcy_incl_gst=line_charge.sell_fcy_incl_gst,
                sell_fcy_currency=line_charge.sell_fcy_currency,
                exchange_rate=line_charge.exchange_rate,
                cost_source=line_charge.cost_source,
                cost_source_description=line_charge.cost_source_description,
                is_rate_missing=line_charge.is_rate_missing
            )
            
        # Create QuoteTotal
        QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=charges.totals.total_cost_pgk,
            total_sell_pgk=charges.totals.total_sell_pgk,
            total_sell_pgk_incl_gst=charges.totals.total_sell_pgk_incl_gst,
            total_sell_fcy=charges.totals.total_sell_fcy,
            total_sell_fcy_incl_gst=charges.totals.total_sell_fcy_incl_gst,
            total_sell_fcy_currency=charges.totals.total_sell_fcy_currency,
            has_missing_rates=charges.totals.has_missing_rates,
            notes=charges.totals.notes
        )

        # Attach latest version for serializers expecting the attribute
        quote.latest_version = version
        return quote


class QuoteV3ViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Provides read-only (list and retrieve) endpoints for V3 Quotes.
    """
    queryset = Quote.objects.all().order_by('-created_at')
    serializer_class = QuoteModelSerializerV3
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Prefetch related data to optimize query
        return super().get_queryset().prefetch_related(
            'versions__lines__service_component',
            'versions__totals'
        )

    def retrieve(self, request, *args, **KWARGS):
        """
        Custom retrieve to ensure we always fetch the 'latest_version'.
        """
        instance = self.get_object()
        # Find the latest version
        latest_version = instance.versions.order_by('-version_number').first()
        instance.latest_version = latest_version
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def list(self, request, *args, **kwargs):
        """
        Custom list to add 'latest_version' to each quote.
        """
        queryset = self.get_queryset()
        
        # This is less efficient than retrieve, but fine for a list view.
        # A more optimized way would be to use Subquery or Annotation.
        for quote in queryset:
             latest_version = quote.versions.order_by('-version_number').first()
             quote.latest_version = latest_version

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
