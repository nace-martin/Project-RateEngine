from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.exceptions import ValidationError as DjangoValidationError

from .serializers import QuoteRequestSerializerV4, scrub_pricing_result_payload
from .engine import PricingEngineFactory
from .engine.export_engine import ExportPricingEngine
from .services.csv_importer import (
    V4RateCSVImportValidationError,
    import_v4_rate_cards_csv,
)

import logging

logger = logging.getLogger(__name__)

class PricingEngineView(APIView):
    """
    V4 Pricing Engine API Endpoint.
    
    Path: /api/v4/quote/calculate/
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = QuoteRequestSerializerV4(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        payload = serializer.validated_data
        service_type = payload['service_type']
        
        try:
            # 1. Instantiate Engine
            engine = PricingEngineFactory.get_engine(service_type, payload)
            
            # 2. Calculate Quote
            result = None
            
            if service_type == 'EXPORT':
                # Export Engine specific: needs list of product codes
                # Infer scope for get_product_codes
                scope = payload.get('service_scope', 'P2P')
                if scope == 'A2A': scope = 'P2P' # Map A2A to P2P for Export; A2D handled in ExportEngine
                
                # Retrieve applicable product codes
                # Assumption: ExportEngine.get_product_codes handles string scope 'P2P', 'D2A', 'D2D'
                product_codes = ExportPricingEngine.get_product_codes(
                    is_dg=payload.get('is_dg', False),
                    service_scope=scope
                )
                result = engine.calculate_quote(product_codes)
                
            elif service_type == 'DOMESTIC':
                result = engine.calculate_quote()
                
            elif service_type == 'IMPORT':
                result = engine.calculate_quote()
                
            # 3. Serialize Result
            # For now, just dumping the dataclass as dict
            # We might want a serializer for the response later
            response_data = self._serialize_result(result, request)
            
            # 4. Check for 'No Rate Found'
            # If total_sell is zero and we expected charges, or explicit error flags
            if response_data.get('lines'):
                missing_rates = [l for l in response_data['lines'] if l.get('is_rate_missing')]
                if missing_rates:
                    # Partial success or failure?
                    # User asked for: "Handle 'No Rate Found' gracefully by returning a specific error code"
                    # If CRITICAL rates are missing (freight), it's an error.
                    freight_missing = any('FRT' in l.get('product_code', '') for l in missing_rates)
                    if freight_missing:
                         return Response({
                            "error": "No freight rate found for this route.",
                            "code": "ERR_NO_ROUTE",
                            "details": missing_rates
                        }, status=status.HTTP_400_BAD_REQUEST)

            return Response(response_data, status=status.HTTP_200_OK)
            
        except ValueError as e:
            return Response({"error": str(e), "code": "ERR_VALIDATION"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Pricing Engine Error")
            return Response({"error": "Internal Pricing Engine Error", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _serialize_result(self, result, request):
        """
        Helper to convert Dataclasses to Dict.
        """
        if not result:
            return {}
            
        # Recursive conversion or simple dict
        import dataclasses
        raw_data = dataclasses.asdict(result)
        include_internal_fields = IsManagerOrAdmin().has_permission(request, self)
        return scrub_pricing_result_payload(
            raw_data,
            include_internal_fields=include_internal_fields,
        )


# =============================================================================
# CUSTOMER DISCOUNT VIEWSET
# =============================================================================

from rest_framework import viewsets, filters
from .models import CustomerDiscount, ProductCode
from .serializers import CustomerDiscountSerializer, CustomerDiscountListSerializer, ProductCodeSerializer


class IsManagerOrAdmin(permissions.BasePermission):
    """Only Manager and Admin roles can manage discounts."""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # Read-only for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        # Write operations require Manager or Admin
        return getattr(request.user, 'role', None) in ['manager', 'admin']


class V4RateCardUploadView(APIView):
    """
    Bulk import V4 SELL rate rows from CSV into Export/Import/Domestic rate tables.

    Path: /api/v4/rates/upload/
    """
    permission_classes = [IsManagerOrAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload_file = request.FILES.get("file")
        if not upload_file:
            return Response(
                {"success": False, "message": "CSV file is required (multipart field: file)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = import_v4_rate_cards_csv(upload_file)
        except V4RateCSVImportValidationError as exc:
            return Response(
                {
                    "success": False,
                    "message": exc.message,
                    "errors": exc.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("V4 CSV bulk import failed")
            return Response(
                {
                    "success": False,
                    "message": "Bulk import failed due to an internal error. No rows were imported.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "success": True,
                "message": "V4 rate CSV import completed successfully.",
                "processed_rows": result.processed_rows,
                "created_rows": result.created_rows,
                "updated_rows": result.updated_rows,
            },
            status=status.HTTP_201_CREATED,
        )


class CustomerDiscountViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing customer-specific discounts.
    
    List/Retrieve: All authenticated users
    Create/Update/Delete: Manager and Admin only
    """
    queryset = CustomerDiscount.objects.select_related(
        'customer', 'product_code'
    ).order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['customer__name', 'product_code__code', 'product_code__description', 'notes']
    ordering_fields = ['created_at', 'valid_until', 'customer__name']

    def get_permissions(self):
        # Read requires auth; write requires manager/admin.
        if self.request.method in permissions.SAFE_METHODS:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        qs = super().get_queryset()
        role = getattr(self.request.user, 'role', None)

        # Sales users must not enumerate commercial discount tables.
        if role == 'sales':
            return qs.none()

        return qs
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerDiscountListSerializer
        return CustomerDiscountSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ProductCodeListViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for listing ProductCodes (for discount form dropdown).
    """
    queryset = ProductCode.objects.all().order_by('domain', 'code')
    serializer_class = ProductCodeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'description']


# =============================================================================
# V4 SELL RATE VIEWSETS
# =============================================================================

from django_filters.rest_framework import DjangoFilterBackend
from .models import ExportSellRate, ImportSellRate, DomesticSellRate, LocalSellRate, LocalCOGSRate
from .serializers import (
    ExportSellRateSerializer,
    ImportSellRateSerializer,
    DomesticSellRateSerializer,
    LocalSellRateSerializer,
    LocalCOGSRateSerializer,
)


class ExportSellRateViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Export Sell Rates.
    
    Path: /api/v4/rates/export/
    """
    queryset = ExportSellRate.objects.select_related('product_code').order_by(
        'origin_airport', 'destination_airport', 'product_code__code'
    )
    serializer_class = ExportSellRateSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['origin_airport', 'destination_airport', 'product_code', 'currency']
    search_fields = ['product_code__code', 'product_code__description', 'origin_airport', 'destination_airport']
    ordering_fields = ['product_code__code', 'origin_airport', 'destination_airport', 'valid_from']


class ImportSellRateViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Import Sell Rates.
    
    Path: /api/v4/rates/import/
    """
    queryset = ImportSellRate.objects.select_related('product_code').order_by(
        'origin_airport', 'destination_airport', 'product_code__code'
    )
    serializer_class = ImportSellRateSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['origin_airport', 'destination_airport', 'product_code', 'currency']
    search_fields = ['product_code__code', 'product_code__description', 'origin_airport', 'destination_airport']
    ordering_fields = ['product_code__code', 'origin_airport', 'destination_airport', 'valid_from']


class DomesticSellRateViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Domestic Sell Rates.
    
    Path: /api/v4/rates/domestic/
    """
    queryset = DomesticSellRate.objects.select_related('product_code').order_by(
        'origin_zone', 'destination_zone', 'product_code__code'
    )
    serializer_class = DomesticSellRateSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['origin_zone', 'destination_zone', 'product_code', 'currency']
    search_fields = ['product_code__code', 'product_code__description', 'origin_zone', 'destination_zone']
    ordering_fields = ['product_code__code', 'origin_zone', 'destination_zone', 'valid_from']


class LocalSellRateViewSet(viewsets.ModelViewSet):
    """
    API endpoint for local Origin/Destination sell tariffs.

    Path: /api/v4/rates/local-sell/
    """
    queryset = LocalSellRate.objects.select_related('product_code').order_by(
        'location', 'direction', 'product_code__code'
    )
    serializer_class = LocalSellRateSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['location', 'direction', 'payment_term', 'product_code', 'currency']
    search_fields = ['product_code__code', 'product_code__description', 'location']
    ordering_fields = ['product_code__code', 'location', 'direction', 'payment_term', 'valid_from']


class LocalCOGSRateViewSet(viewsets.ModelViewSet):
    """
    API endpoint for local Origin/Destination buy tariffs.

    Path: /api/v4/rates/local-cogs/
    """
    queryset = LocalCOGSRate.objects.select_related('product_code', 'agent', 'carrier').order_by(
        'location', 'direction', 'product_code__code'
    )
    serializer_class = LocalCOGSRateSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['location', 'direction', 'product_code', 'currency', 'agent', 'carrier']
    search_fields = ['product_code__code', 'product_code__description', 'location', 'agent__name', 'carrier__name']
    ordering_fields = ['product_code__code', 'location', 'direction', 'valid_from']


# =============================================================================
# LOGICAL RATE CARDS VIEW
# =============================================================================

from rest_framework.views import APIView
from .rate_card_config import LOGICAL_RATE_CARDS
from .serializers import ExportSellRateSerializer, ImportSellRateSerializer, DomesticSellRateSerializer


class LogicalRateCardsView(APIView):
    """
    Returns the 5 logical rate cards with their associated rate lines.
    
    Path: /api/v4/rate-cards/
    
    This is a read-only view layer over existing rate data.
    No impact on pricing calculations.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        result = []
        
        for card_config in LOGICAL_RATE_CARDS:
            card_data = {
                'id': card_config['id'],
                'name': card_config['name'],
                'description': card_config['description'],
                'service_scope': card_config.get('service_scope'),
                'domain': card_config['domain'],
                'lines': [],
                'line_count': 0,
                'currencies': set(),
                'corridors': set(),
            }
            
            # Get the appropriate queryset
            lines = self._get_rate_lines(card_config)
            
            # Serialize and add metadata
            for line in lines:
                card_data['lines'].append(self._serialize_line(line, card_config))
                card_data['currencies'].add(line.currency)
                origin = getattr(line, 'origin_airport', None) or getattr(line, 'origin_zone', None)
                dest = getattr(line, 'destination_airport', None) or getattr(line, 'destination_zone', None)
                if origin and dest:
                    card_data['corridors'].add(f"{origin}→{dest}")
            
            card_data['line_count'] = len(card_data['lines'])
            card_data['currencies'] = list(card_data['currencies'])
            card_data['corridors'] = sorted(list(card_data['corridors']))
            
            result.append(card_data)
        
        return Response(result)
    
    def _get_rate_lines(self, config):
        """Query the appropriate rate table with filters."""
        table_name = config['rate_table']
        currency_filter = config.get('currency_filter', [])
        origin_filter = config.get('origin_filter')
        destination_filter = config.get('destination_filter')
        
        if table_name == 'ExportSellRate':
            qs = ExportSellRate.objects.select_related('product_code')
            if currency_filter:
                qs = qs.filter(currency__in=currency_filter)
            if origin_filter:
                qs = qs.filter(origin_airport__in=origin_filter)
            if destination_filter:
                qs = qs.filter(destination_airport__in=destination_filter)
            return qs.order_by('origin_airport', 'destination_airport', 'product_code__code')
            
        elif table_name == 'ImportSellRate':
            qs = ImportSellRate.objects.select_related('product_code')
            if currency_filter:
                qs = qs.filter(currency__in=currency_filter)
            if origin_filter:
                qs = qs.filter(origin_airport__in=origin_filter)
            if destination_filter:
                qs = qs.filter(destination_airport__in=destination_filter)
            return qs.order_by('origin_airport', 'destination_airport', 'product_code__code')
            
        elif table_name == 'DomesticSellRate':
            qs = DomesticSellRate.objects.select_related('product_code')
            if currency_filter:
                qs = qs.filter(currency__in=currency_filter)
            if origin_filter:
                qs = qs.filter(origin_zone__in=origin_filter)
            if destination_filter:
                qs = qs.filter(destination_zone__in=destination_filter)
            return qs.order_by('origin_zone', 'destination_zone', 'product_code__code')
        
        return []
    
    def _serialize_line(self, line, config):
        """Serialize a rate line to dict."""
        table_name = config['rate_table']
        
        if table_name == 'ExportSellRate':
            return ExportSellRateSerializer(line).data
        elif table_name == 'ImportSellRate':
            return ImportSellRateSerializer(line).data
        elif table_name == 'DomesticSellRate':
            return DomesticSellRateSerializer(line).data
        return {}



