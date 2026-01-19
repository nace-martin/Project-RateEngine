from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError

from .serializers import QuoteRequestSerializerV4
from .engine import PricingEngineFactory
from .engine.export_engine import ExportPricingEngine

import logging

logger = logging.getLogger(__name__)

class PricingEngineView(APIView):
    """
    V4 Pricing Engine API Endpoint.
    
    Path: /api/v4/quote/calculate/
    """
    
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
                    is_dg=False, # TODO: Add is_dg to request
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
            response_data = self._serialize_result(result)
            
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

    def _serialize_result(self, result):
        """
        Helper to convert Dataclasses to Dict.
        """
        if not result:
            return {}
            
        # Recursive conversion or simple dict
        import dataclasses
        return dataclasses.asdict(result)


# =============================================================================
# CUSTOMER DISCOUNT VIEWSET
# =============================================================================

from rest_framework import viewsets, permissions, filters
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


class CustomerDiscountViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing customer-specific discounts.
    
    List/Retrieve: All authenticated users
    Create/Update/Delete: Manager and Admin only
    """
    queryset = CustomerDiscount.objects.select_related(
        'customer', 'product_code'
    ).order_by('-created_at')
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['customer__name', 'product_code__code', 'product_code__description', 'notes']
    ordering_fields = ['created_at', 'valid_until', 'customer__name']
    
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

