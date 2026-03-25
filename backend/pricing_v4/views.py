from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from accounts.permissions import IsAdmin

from .serializers import (
    CustomerDiscountBulkUpsertSerializer,
    CustomerDiscountListSerializer,
    QuoteRequestSerializerV4,
    scrub_pricing_result_payload,
)
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


class CanViewLogicalRateCards(permissions.BasePermission):
    """Restrict logical pricing architecture views to managers and admins."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
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
            permission_classes = [permissions.IsAuthenticated, IsAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        qs = super().get_queryset()
        role = getattr(self.request.user, 'role', None)
        customer = self.request.query_params.get('customer')
        product_code = self.request.query_params.get('product_code')
        discount_type = self.request.query_params.get('discount_type')

        # Sales users must not enumerate commercial discount tables.
        if role == 'sales':
            return qs.none()

        if customer:
            qs = qs.filter(customer_id=customer)
        if product_code:
            qs = qs.filter(product_code_id=product_code)
        if discount_type:
            qs = qs.filter(discount_type=discount_type)

        return qs
    
    def get_serializer_class(self):
        if self.action == 'list':
            return CustomerDiscountListSerializer
        return CustomerDiscountSerializer
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class CustomerDiscountBulkUpsertAPIView(APIView):
    """
    Bulk create/update customer discounts for a single customer account.
    Keeps the underlying CustomerDiscount rows intact so pricing behavior does not change.
    """

    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def post(self, request):
        serializer = CustomerDiscountBulkUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer = serializer.validated_data['customer']
        lines = serializer.validated_data['lines']
        saved_discounts = []

        with transaction.atomic():
            for line in lines:
                discount_id = line.pop('id', None)
                defaults = {
                    **line,
                    'created_by': request.user,
                }

                if discount_id:
                    discount = CustomerDiscount.objects.filter(
                        id=discount_id,
                        customer=customer,
                    ).first()
                    if not discount:
                        return Response(
                            {'detail': f'Discount {discount_id} not found for this customer.'},
                            status=status.HTTP_404_NOT_FOUND,
                        )
                    for field_name, value in defaults.items():
                        setattr(discount, field_name, value)
                    discount.save()
                else:
                    discount, created = CustomerDiscount.objects.update_or_create(
                        customer=customer,
                        product_code=line['product_code'],
                        defaults=defaults,
                    )
                    if created and not discount.created_by_id:
                        discount.created_by = request.user
                        discount.save(update_fields=['created_by'])

                saved_discounts.append(discount)

        response_serializer = CustomerDiscountListSerializer(saved_discounts, many=True)
        return Response(
            {
                'customer': str(customer.id),
                'saved_count': len(saved_discounts),
                'discounts': response_serializer.data,
            },
            status=status.HTTP_200_OK,
        )


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

from .rate_card_config import LOGICAL_RATE_CARDS
from .models import ImportCOGS


class LogicalRateCardsView(APIView):
    """
    Returns logical V4 pricing cards aligned to the current rate architecture.

    Path: /api/v4/rate-cards/
    """
    permission_classes = [permissions.IsAuthenticated, CanViewLogicalRateCards]
    
    def get(self, request):
        result = []

        for card_config in LOGICAL_RATE_CARDS:
            card_data = {
                "id": card_config["id"],
                "name": card_config["name"],
                "description": card_config["description"],
                "service_scope": card_config.get("service_scope"),
                "domain": card_config["domain"],
                "pricing_model": card_config["pricing_model"],
                "source_tables": card_config["source_tables"],
                "notes": card_config.get("notes", []),
                "lines": [],
                "line_count": 0,
                "currencies": set(),
                "coverage": set(),
            }

            for source in card_config.get("sources", []):
                for line in self._get_source_queryset(source):
                    serialized = self._serialize_logical_line(line, source)
                    card_data["lines"].append(serialized)
                    if serialized["currency"]:
                        card_data["currencies"].add(serialized["currency"])
                    if serialized["coverage_label"]:
                        card_data["coverage"].add(serialized["coverage_label"])

            card_data["line_count"] = len(card_data["lines"])
            card_data["currencies"] = sorted(card_data["currencies"])
            card_data["coverage"] = sorted(card_data["coverage"])
            result.append(card_data)

        return Response(result)

    def _get_source_queryset(self, source):
        table_name = source["table"]
        currency_filter = source.get("currency_filter")
        direction = source.get("direction")
        payment_term = source.get("payment_term")

        if table_name == "ExportSellRate":
            qs = ExportSellRate.objects.select_related("product_code")
            if currency_filter:
                qs = qs.filter(currency__in=currency_filter)
            return qs.order_by("origin_airport", "destination_airport", "product_code__code")

        if table_name == "LocalSellRate":
            qs = LocalSellRate.objects.select_related("product_code")
            if direction:
                qs = qs.filter(direction=direction)
            if payment_term:
                qs = qs.filter(payment_term=payment_term)
            if currency_filter:
                qs = qs.filter(currency__in=currency_filter)
            return qs.order_by("location", "product_code__code")

        if table_name == "ImportCOGS":
            qs = ImportCOGS.objects.select_related("product_code", "agent", "carrier")
            if currency_filter:
                qs = qs.filter(currency__in=currency_filter)
            return qs.order_by("origin_airport", "destination_airport", "product_code__code")

        if table_name == "DomesticSellRate":
            qs = DomesticSellRate.objects.select_related("product_code")
            if currency_filter:
                qs = qs.filter(currency__in=currency_filter)
            return qs.order_by("origin_zone", "destination_zone", "product_code__code")

        return []

    def _serialize_logical_line(self, line, source):
        table_name = source["table"]

        if table_name == "ExportSellRate":
            return {
                "id": f"ExportSellRate:{line.pk}",
                "source_table": table_name,
                "source_label": source["label"],
                "pricing_role": source["pricing_role"],
                "product_code": line.product_code_id,
                "product_code_code": line.product_code.code,
                "product_code_description": line.product_code.description,
                "currency": line.currency,
                "coverage_label": f"{line.origin_airport}->{line.destination_airport}",
                "origin_code": line.origin_airport,
                "destination_code": line.destination_airport,
                "location_code": None,
                "direction": None,
                "payment_term": None,
                "rate_type": "LANE_SELL",
                "rate_per_kg": str(line.rate_per_kg) if line.rate_per_kg is not None else None,
                "rate_per_shipment": str(line.rate_per_shipment) if line.rate_per_shipment is not None else None,
                "amount": None,
                "min_charge": str(line.min_charge) if line.min_charge is not None else None,
                "max_charge": str(line.max_charge) if line.max_charge is not None else None,
                "percent_rate": str(line.percent_rate) if line.percent_rate is not None else None,
                "weight_breaks": line.weight_breaks,
                "is_additive": line.is_additive,
                "valid_from": line.valid_from.isoformat(),
                "valid_until": line.valid_until.isoformat(),
                "counterparty": None,
            }

        if table_name == "LocalSellRate":
            return {
                "id": f"LocalSellRate:{line.pk}",
                "source_table": table_name,
                "source_label": source["label"],
                "pricing_role": source["pricing_role"],
                "product_code": line.product_code_id,
                "product_code_code": line.product_code.code,
                "product_code_description": line.product_code.description,
                "currency": line.currency,
                "coverage_label": line.location,
                "origin_code": None,
                "destination_code": None,
                "location_code": line.location,
                "direction": line.direction,
                "payment_term": line.payment_term,
                "rate_type": line.rate_type,
                "rate_per_kg": None,
                "rate_per_shipment": None,
                "amount": str(line.amount) if line.amount is not None else None,
                "min_charge": str(line.min_charge) if line.min_charge is not None else None,
                "max_charge": str(line.max_charge) if line.max_charge is not None else None,
                "percent_rate": None,
                "weight_breaks": line.weight_breaks,
                "is_additive": line.is_additive,
                "valid_from": line.valid_from.isoformat(),
                "valid_until": line.valid_until.isoformat(),
                "counterparty": None,
            }

        if table_name == "ImportCOGS":
            counterparty = None
            if line.agent_id:
                counterparty = f"Agent:{line.agent.code}"
            elif line.carrier_id:
                counterparty = f"Carrier:{line.carrier.code}"

            return {
                "id": f"ImportCOGS:{line.pk}",
                "source_table": table_name,
                "source_label": source["label"],
                "pricing_role": source["pricing_role"],
                "product_code": line.product_code_id,
                "product_code_code": line.product_code.code,
                "product_code_description": line.product_code.description,
                "currency": line.currency,
                "coverage_label": f"{line.origin_airport}->{line.destination_airport}",
                "origin_code": line.origin_airport,
                "destination_code": line.destination_airport,
                "location_code": None,
                "direction": None,
                "payment_term": None,
                "rate_type": "LANE_COGS",
                "rate_per_kg": str(line.rate_per_kg) if line.rate_per_kg is not None else None,
                "rate_per_shipment": str(line.rate_per_shipment) if line.rate_per_shipment is not None else None,
                "amount": None,
                "min_charge": str(line.min_charge) if line.min_charge is not None else None,
                "max_charge": str(line.max_charge) if line.max_charge is not None else None,
                "percent_rate": None,
                "weight_breaks": line.weight_breaks,
                "is_additive": line.is_additive,
                "valid_from": line.valid_from.isoformat(),
                "valid_until": line.valid_until.isoformat(),
                "counterparty": counterparty,
            }

        if table_name == "DomesticSellRate":
            return {
                "id": f"DomesticSellRate:{line.pk}",
                "source_table": table_name,
                "source_label": source["label"],
                "pricing_role": source["pricing_role"],
                "product_code": line.product_code_id,
                "product_code_code": line.product_code.code,
                "product_code_description": line.product_code.description,
                "currency": line.currency,
                "coverage_label": f"{line.origin_zone}->{line.destination_zone}",
                "origin_code": line.origin_zone,
                "destination_code": line.destination_zone,
                "location_code": None,
                "direction": None,
                "payment_term": None,
                "rate_type": "DOMESTIC_SELL",
                "rate_per_kg": str(line.rate_per_kg) if line.rate_per_kg is not None else None,
                "rate_per_shipment": str(line.rate_per_shipment) if line.rate_per_shipment is not None else None,
                "amount": None,
                "min_charge": str(line.min_charge) if line.min_charge is not None else None,
                "max_charge": str(line.max_charge) if line.max_charge is not None else None,
                "percent_rate": str(line.percent_rate) if line.percent_rate is not None else None,
                "weight_breaks": line.weight_breaks,
                "is_additive": line.is_additive,
                "valid_from": line.valid_from.isoformat(),
                "valid_until": line.valid_until.isoformat(),
                "counterparty": None,
            }

        return {}



