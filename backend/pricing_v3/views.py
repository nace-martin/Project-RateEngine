from dataclasses import asdict
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
import csv
import io
from decimal import Decimal

from quotes.models import Quote
from services.models import ServiceRule, ServiceComponent
from .resolvers import QuoteContextBuilder, BuyChargeResolver
from pricing_v2.dataclasses_v3 import Piece, ShipmentDetails, QuoteInput

from rest_framework import viewsets
from .models import Zone, RateCard, RateLine, RateBreak, QuoteSpotRate, QuoteSpotCharge
from .serializers import (
    ZoneSerializer, RateCardSerializer, RateLineSerializer,
    QuoteSpotRateSerializer, QuoteSpotChargeSerializer
)

# RBAC permissions
from accounts.permissions import CanEditRateCards

class ZoneViewSet(viewsets.ModelViewSet):
    """Zone management - requires Manager or Admin role."""
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer
    permission_classes = [CanEditRateCards]  # Manager/Admin only

class QuoteSpotRateViewSet(viewsets.ModelViewSet):
    """Quote spot rates - authenticated users can view, write requires auth."""
    queryset = QuoteSpotRate.objects.all()
    serializer_class = QuoteSpotRateSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        quote_id = self.request.query_params.get('quote')
        if quote_id:
            queryset = queryset.filter(quote_id=quote_id)
        return queryset

class QuoteSpotChargeViewSet(viewsets.ModelViewSet):
    """Quote spot charges - authenticated users can view, write requires auth."""
    queryset = QuoteSpotCharge.objects.all()
    serializer_class = QuoteSpotChargeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        spot_rate_id = self.request.query_params.get('spot_rate')
        if spot_rate_id:
            queryset = queryset.filter(spot_rate_id=spot_rate_id)
        return queryset

class RateCardViewSet(viewsets.ModelViewSet):
    """Rate card management - requires Manager or Admin role."""
    queryset = RateCard.objects.all()
    serializer_class = RateCardSerializer
    permission_classes = [CanEditRateCards]  # Manager/Admin only

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser])
    def import_csv(self, request, pk=None):
        rate_card = self.get_object()
        file_obj = request.FILES.get('file')
        
        if not file_obj:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded_file = file_obj.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.DictReader(io_string)
            
            created_count = 0
            errors = []
            
            # Expected columns: Component, Method, MinCharge, Unit, Rates, Description
            
            for row_idx, row in enumerate(reader, start=1):
                try:
                    component_code = row.get('Component', '').strip()
                    method = row.get('Method', 'FLAT').strip().upper()
                    min_charge = row.get('MinCharge', '0').strip() or '0'
                    unit = row.get('Unit', '').strip() or None
                    rates_str = row.get('Rates', '').strip()
                    description = row.get('Description', '').strip()
                    
                    if not component_code:
                        continue # Skip empty rows

                    # Find Component
                    component = ServiceComponent.objects.filter(code=component_code).first()
                    if not component:
                        errors.append(f"Row {row_idx}: Component '{component_code}' not found.")
                        continue

                    # Create Line
                    line = RateLine.objects.create(
                        card=rate_card,
                        component=component,
                        method=method,
                        min_charge=Decimal(min_charge),
                        unit=unit,
                        description=description
                    )
                    
                    # Parse Rates/Breaks
                    if method == 'WEIGHT_BREAK':
                        # Format: 0-45:10.00; 45-100:8.00
                        breaks = rates_str.split(';')
                        for brk in breaks:
                            if not brk.strip(): continue
                            parts = brk.split(':')
                            if len(parts) != 2:
                                errors.append(f"Row {row_idx}: Invalid break format '{brk}'. Expected 'Range:Rate'.")
                                continue
                            
                            range_part, rate_part = parts
                            rate = Decimal(rate_part.strip())
                            
                            range_vals = range_part.split('-')
                            from_val = Decimal(range_vals[0].strip())
                            to_val = None
                            if len(range_vals) > 1 and range_vals[1].strip().lower() not in ['max', '', 'inf']:
                                to_val = Decimal(range_vals[1].strip())
                                
                            RateBreak.objects.create(
                                line=line,
                                from_value=from_val,
                                to_value=to_val,
                                rate=rate
                            )
                    elif method == 'PERCENT':
                        # Rate column contains percentage e.g. 0.20
                        line.percent_value = Decimal(rates_str) if rates_str else Decimal("0")
                        line.save()
                    elif method in ['FLAT', 'PER_UNIT']:
                        # Rate column contains the rate if per unit, or just min charge if flat?
                        # Usually PER_UNIT has a rate. We store it as a single break 0-Max.
                        if rates_str:
                            rate = Decimal(rates_str)
                            RateBreak.objects.create(
                                line=line,
                                from_value=0,
                                to_value=None,
                                rate=rate
                            )
                            
                    created_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {row_idx}: {str(e)}")
            
            return Response({
                "message": f"Imported {created_count} lines.",
                "errors": errors
            }, status=status.HTTP_200_OK if not errors else status.HTTP_207_MULTI_STATUS)
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class RateLineViewSet(viewsets.ModelViewSet):
    """Rate line management - requires Manager or Admin role."""
    queryset = RateLine.objects.all()
    serializer_class = RateLineSerializer
    permission_classes = [CanEditRateCards]  # Manager/Admin only

class QuoteComputeView(APIView):
    """
    Debug endpoint to run the V3 Resolver pipeline for a given quote.
    Returns the list of resolved BuyCharges.
    """
    def get(self, request, quote_id):
        # 1. Load Quote and Build Context
        try:
            context = QuoteContextBuilder.build(quote_id)
        except Quote.DoesNotExist:
            return Response({"error": "Quote not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Determine Components to Resolve
        # Logic borrowed/adapted from PricingServiceV3._resolve_service_rule
        # In a real implementation, we might want to centralize this component-finding logic.
        components = []
        
        # Try to find a ServiceRule
        service_scope = getattr(context.quote, "service_scope", None)
        if service_scope:
            incoterm = context.quote.incoterm or None
            rule = ServiceRule.objects.filter(
                mode=context.quote.mode,
                direction=context.quote.shipment_type,
                incoterm=incoterm,
                payment_term=context.quote.payment_term,
                service_scope=service_scope,
                is_active=True,
            ).order_by("-effective_from").first()
            
            if rule:
                components = list(rule.service_components.filter(is_active=True))
        
        # Fallback: If no rule found, or for debugging, maybe just return empty or 
        # we could allow passing component codes in query params?
        # For now, if no components found, we return empty list.
        
        # 3. Resolve Charges
        resolver = BuyChargeResolver(context)
        buy_charges = resolver.resolve_all(components)
        
        # 4. Serialize
        data = [asdict(charge) for charge in buy_charges]
        
        return Response({
            "quote_id": quote_id,
            "components_resolved": [c.code for c in components],
            "buy_charges": data
        })

class QuoteComputeV3View(APIView):
    """
    Complete quote computation endpoint using PricingServiceV3.
    
    Returns full buy/sell breakdown with proper CAF, margins, and FX conversions.
    
    GET /api/v3/quotes/<quote_id>/compute_v3/
    
    Response:
    {
      "quote_id": "...",
      "quote_number": "...",
      "buy_lines": [...],
      "sell_lines": [...],
      "totals": {
        "cost_pgk": "1250.00",
        "cost_aud": "451.26",
        "sell_pgk": "1625.00",
        "caf_pgk": "62.50"
      },
      "exchange_rates": {...},
      "computation_date": "2025-11-25"
    }
    """
    def get(self, request, quote_id):
        from quotes.models import Quote
        from decimal import Decimal
        
        try:
            # 1. Load the quote
            quote = Quote.objects.select_related(
                'origin_location__country__currency',
                'destination_location__country__currency',
                'policy',
                'fx_snapshot'
            ).get(id=quote_id)
        except Quote.DoesNotExist:
            return Response(
                {"error": "Quote not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            # 2. Reconstruct QuoteInput from the saved quote
            # Get the latest version's payload or reconstruct from quote fields
            latest_version = quote.versions.order_by('-version_number').first()
            
            if latest_version and latest_version.payload_json:
                # Use stored payload
                payload = latest_version.payload_json
                # Convert string values to proper types for Piece dataclass
                pieces = []
                for p in payload.get('dimensions', []):
                    pieces.append(Piece(
                        pieces=int(p.get('pieces', 1)),
                        length_cm=Decimal(str(p.get('length_cm', 50))),
                        width_cm=Decimal(str(p.get('width_cm', 50))),
                        height_cm=Decimal(str(p.get('height_cm', 50))),
                        gross_weight_kg=Decimal(str(p.get('gross_weight_kg', 100)))
                    ))
            else:
                # Fallback: create a default piece
                pieces = [Piece(pieces=1, length_cm=Decimal('50'), width_cm=Decimal('50'), height_cm=Decimal('50'), gross_weight_kg=Decimal('100'))]
            
            # Build location refs
            origin_ref = self._location_to_ref(quote.origin_location)
            dest_ref = self._location_to_ref(quote.destination_location)
            
            # Build shipment details
            shipment = ShipmentDetails(
                mode=quote.mode,
                shipment_type=quote.shipment_type,
                incoterm=quote.incoterm or 'EXW',
                payment_term=quote.payment_term,
                is_dangerous_goods=quote.is_dangerous_goods,
                pieces=pieces,
                service_scope=quote.service_scope,
                direction=quote.shipment_type,
                origin_location=origin_ref,
                destination_location=dest_ref,
            )
            
            # Build quote input
            quote_input = QuoteInput(
                customer_id=quote.customer.id,
                contact_id=quote.contact.id if quote.contact else quote.customer.id,
                output_currency=quote.output_currency or 'PGK',
                shipment=shipment
            )
            
            # 3. Return stored quote lines from the database instead of recalculating
            # This ensures UI shows the same values that were computed and saved by the V4 engine
            latest_version = quote.versions.order_by('-version_number').first()
            
            if not latest_version:
                return Response(
                    {"error": "Quote has no computed version"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Build response from stored lines
            buy_lines = []
            sell_lines = []
            
            # Track totals
            total_cost_pgk = Decimal('0.00')
            total_sell_pgk = Decimal('0.00')
            total_gst = Decimal('0.00')
            
            for line in latest_version.lines.select_related('service_component'):
                sc = line.service_component
                sc_code = sc.code if sc else 'MANUAL'
                sc_desc = line.cost_source_description or (sc.description if sc else 'Spot Charge')

                # Build buy line
                buy_line = {
                    "component": sc_code,
                    "source": line.cost_source or 'V4 Engine',
                    "currency": line.cost_fcy_currency or 'PGK',
                    "method": "V4_ENGINE",
                    "description": sc_desc,
                }
                buy_lines.append(buy_line)
                
                # Calculate GST (10%)
                gst_amount = line.sell_pgk_incl_gst - line.sell_pgk if line.sell_pgk_incl_gst else Decimal('0')
                
                # Prefer saved leg/bucket if available
                leg = getattr(line, 'leg', None)
                bucket = getattr(line, 'bucket', None)

                if not leg:
                    # Fallback to manual derivation
                    leg = 'MAIN'
                    if sc and sc.leg:
                        leg = sc.leg
                        # Map 'FREIGHT' legacy to 'MAIN' if needed, or vice versa. 
                        # DB uses 'MAIN'. Frontend expects 'MAIN' or 'FREIGHT'. 
                        if leg == 'MAIN': leg = 'MAIN' 
                    elif sc:
                        if 'DEST' in sc.code or 'CLEAR' in sc.code:
                            leg = 'DESTINATION'
                        elif 'ORIGIN' in sc.code or 'PICKUP' in sc.code:
                            leg = 'ORIGIN'
                        elif 'FREIGHT' in sc.code or 'AIR' in sc.code:
                            leg = 'FREIGHT'
                    else:
                        # Fallback for manual lines
                        if 'ORIGIN' in (line.cost_source or '').upper():
                            leg = 'ORIGIN'
                        elif 'DEST' in (line.cost_source or '').upper():
                            leg = 'DESTINATION'
                        else:
                            leg = 'FREIGHT' # Assume Spot is mostly freight if unknown?
                
                # Build sell line
                sell_line = {
                    "line_type": "COMPONENT",
                    "component": sc_code,
                    "description": sc_desc,
                    "leg": leg,
                    "bucket": bucket,
                    "cost_pgk": str(line.cost_pgk),
                    "sell_pgk": str(line.sell_pgk),
                    "sell_pgk_incl_gst": str(line.sell_pgk_incl_gst or line.sell_pgk * Decimal('1.1')),
                    "gst_amount": str(gst_amount),
                    "sell_fcy": str(line.sell_fcy or line.sell_pgk),
                    "sell_fcy_incl_gst": str(line.sell_fcy_incl_gst or line.sell_fcy or line.sell_pgk),
                    "sell_currency": line.sell_fcy_currency or 'PGK',
                    "margin_percent": str(((line.sell_pgk - line.cost_pgk) / line.cost_pgk * 100) if line.cost_pgk > 0 else 0),
                    "exchange_rate": str(line.exchange_rate or 1.0),
                    "source": line.cost_source or 'V4 Engine',
                    "is_informational": getattr(line, 'is_informational', False)
                }
                sell_lines.append(sell_line)
                
                # Accumulate totals (exclude informational lines)
                if not getattr(line, 'is_informational', False):
                    total_cost_pgk += line.cost_pgk
                    total_sell_pgk += line.sell_pgk
                    total_gst += gst_amount
            
            # Get exchange rates from FX snapshot
            fx_snapshot = quote.fx_snapshot
            rates_dict = {}
            if fx_snapshot and fx_snapshot.rates:
                import json
                rates = fx_snapshot.rates if isinstance(fx_snapshot.rates, dict) else json.loads(fx_snapshot.rates)
                rates_dict = {k: v.get('tt_buy', 1.0) for k, v in rates.items() if isinstance(v, dict)}
            
            # Get totals from QuoteTotal if available
            quote_total = getattr(latest_version, 'totals', None)
            
            response_data = {
                "quote_id": str(quote_id),
                "quote_number": quote.quote_number,
                "buy_lines": buy_lines,
                "sell_lines": sell_lines,
                "totals": {
                    "cost_pgk": str(total_cost_pgk),
                    "sell_pgk": str(total_sell_pgk),
                    "sell_pgk_incl_gst": str(total_sell_pgk + total_gst),
                    "gst_amount": str(total_gst),
                    "sell_fcy": str(quote_total.total_sell_fcy if quote_total else total_sell_pgk),
                    "total_sell_fcy_incl_gst": str(quote_total.total_sell_fcy_incl_gst if quote_total else total_sell_pgk + total_gst),
                    "currency": quote_total.total_sell_fcy_currency if quote_total else (quote.output_currency or 'PGK'),
                },
                "exchange_rates": rates_dict,
                "computation_date": latest_version.created_at.strftime('%Y-%m-%d') if latest_version.created_at else quote.created_at.strftime('%Y-%m-%d'),
                "routing": {
                    "service_level": "DIRECT",
                    "routing_reason": None,
                    "requires_via_routing": False,
                    "violations": []
                },
                "notes": []
            }
            
            return Response(response_data)
            
        except Exception as e:
            import traceback
            return Response(
                {
                    "error": f"Computation error: {str(e)}",
                    "traceback": traceback.format_exc()
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _location_to_ref(self, location):
        """Helper to convert Location to LocationRef."""
        if not location:
            return None
            
        country_code = location.country.code if location.country else None
        currency_code = None
        if location.country and location.country.currency:
            currency_code = location.country.currency.code
        
        from pricing_v2.dataclasses_v3 import LocationRef
        return LocationRef(
            id=location.id,
            code=location.code,
            name=location.name,
            country_code=country_code,
            currency_code=currency_code,
        )


class RoutingValidationView(APIView):
    """
    Real-time routing validation endpoint.
    Validates cargo dimensions against aircraft constraints.
    
    POST /api/v3/routing/validate
    
    Request:
    {
        "origin": "SYD",
        "destination": "POM",
        "pieces": [
            {
                "length_cm": 250,
                "width_cm": 100,
                "height_cm": 90,
                "weight_kg": 300
            }
        ]
    }
    
    Response:
    {
        "service_level": "VIA_BNE",
        "routing_reason": "Cargo exceeds B737 constraints...",
        "requires_via_routing": true,
        "violations": [
            {
                "piece_number": 1,
                "dimension": "length",
                "actual": "250",
                "limit": "200",
                "message": "Piece 1: Length 250cm exceeds B737 limit of 200cm"
            }
        ]
    }
    """
    
    def post(self, request):
        from core.routing import RoutingValidator
        
        # Extract request data
        origin = request.data.get('origin')
        destination = request.data.get('destination')
        pieces = request.data.get('pieces', [])
        
        # Validate required fields
        if not origin or not destination:
            return Response({
                'error': 'Both origin and destination are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not pieces or len(pieces) == 0:
            return Response({
                'error': 'At least one piece is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate piece structure
        for i, piece in enumerate(pieces):
            required_fields = ['length_cm', 'width_cm', 'height_cm', 'weight_kg']
            missing = [f for f in required_fields if f not in piece]
            if missing:
                return Response({
                    'error': f'Piece {i+1} missing required fields: {", ".join(missing)}'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Run routing validation
        try:
            validator = RoutingValidator()
            service_level, reason, violations = validator.determine_required_service_level(
                origin_code=origin,
                destination_code=destination,
                pieces=pieces
            )
            
            # Format response
            return Response({
                'service_level': service_level,
                'routing_reason': reason,
                'requires_via_routing': service_level.startswith('VIA_'),
                'violations': [
                    {
                        'piece_number': v.piece_number,
                        'dimension': v.dimension,
                        'actual': str(v.actual_value),
                        'limit': str(v.limit_value),
                        'message': v.message
                    }
                    for v in violations
                ]
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': f'Routing validation failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
