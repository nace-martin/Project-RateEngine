from datetime import date, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from accounts.permissions import IsAdmin, IsManagerOrAdmin
from core.security import validate_csv_upload
from quotes.completeness import (
    COMPONENT_DESTINATION_LOCAL,
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
    required_components,
)

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
from .services.rate_admin import (
    create_rate_change_log,
    ensure_rate_lineage,
    get_rate_history_queryset,
    revise_rate_row,
    serialize_rate_snapshot,
)
from .category_rules import is_local_rate_category

import logging

logger = logging.getLogger(__name__)


def _normalize_scope(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    if normalized == "P2P":
        return "A2A"
    return normalized


def _normalize_code(value: str | None) -> str:
    return (value or "").strip().upper()


def _active_queryset(model_cls, *, on_date: date):
    return model_cls.objects.filter(valid_from__lte=on_date, valid_until__gte=on_date)


def _classify_export_cogs_component(row) -> str | None:
    category = (getattr(row.product_code, "category", "") or "").upper()
    code = (getattr(row.product_code, "code", "") or "").upper()
    if category == ProductCode.CATEGORY_FREIGHT or "FRT" in code or "FREIGHT" in code:
        return COMPONENT_FREIGHT
    return None


def _classify_import_lane_cogs_component(row) -> str | None:
    category = (getattr(row.product_code, "category", "") or "").upper()
    code = (getattr(row.product_code, "code", "") or "").upper()
    if category == ProductCode.CATEGORY_FREIGHT or "FRT" in code or "FREIGHT" in code:
        return COMPONENT_FREIGHT
    return COMPONENT_ORIGIN_LOCAL


def _classify_domestic_cogs_component(row) -> str | None:
    category = (getattr(row.product_code, "category", "") or "").upper()
    code = (getattr(row.product_code, "code", "") or "").upper()
    if category == ProductCode.CATEGORY_FREIGHT or "FRT" in code or "FREIGHT" in code:
        return COMPONENT_FREIGHT
    return COMPONENT_ORIGIN_LOCAL


def _local_component_for_location(*, direction: str, location: str, origin_airport: str, destination_airport: str) -> str | None:
    if direction == "IMPORT":
        if location == origin_airport:
            return COMPONENT_ORIGIN_LOCAL
        if location == destination_airport:
            return COMPONENT_DESTINATION_LOCAL
        return None
    if direction == "EXPORT":
        if location == origin_airport:
            return COMPONENT_ORIGIN_LOCAL
        if location == destination_airport:
            return COMPONENT_DESTINATION_LOCAL
        return None
    return None


def _counterparty_kind(row) -> str | None:
    if getattr(row, "agent_id", None):
        return "agent"
    if getattr(row, "carrier_id", None):
        return "carrier"
    return None


def _build_counterparty_hints(
    *,
    direction: str,
    service_scope: str,
    origin_airport: str,
    destination_airport: str,
    buy_currency: str | None = None,
    quote_date: date | None = None,
):
    today = quote_date or timezone.localdate()
    direction = _normalize_code(direction)
    scope = _normalize_scope(service_scope)
    origin_airport = _normalize_code(origin_airport)
    destination_airport = _normalize_code(destination_airport)
    buy_currency = _normalize_code(buy_currency) or None

    required = sorted(required_components(direction, scope))
    component_types = {component: set() for component in required}
    agent_map: dict[int, Agent] = {}
    carrier_map: dict[int, Carrier] = {}

    def maybe_register(row, component: str | None):
        if component not in component_types:
            return
        kind = _counterparty_kind(row)
        if kind is None:
            return
        component_types[component].add(kind)
        if kind == "agent" and getattr(row, "agent", None) is not None:
            agent_map[row.agent_id] = row.agent
        elif kind == "carrier" and getattr(row, "carrier", None) is not None:
            carrier_map[row.carrier_id] = row.carrier

    def apply_currency_filter(qs):
        if buy_currency:
            return qs.filter(currency=buy_currency)
        return qs

    if direction == "IMPORT":
        lane_rows = apply_currency_filter(
            _active_queryset(ImportCOGS, on_date=today).filter(
                origin_airport=origin_airport,
                destination_airport=destination_airport,
            )
        ).select_related("product_code", "agent", "carrier")
        for row in lane_rows:
            maybe_register(row, _classify_import_lane_cogs_component(row))

        local_rows = apply_currency_filter(
            _active_queryset(LocalCOGSRate, on_date=today).filter(
                direction="IMPORT",
                location__in=[code for code in [origin_airport, destination_airport] if code],
            )
        ).select_related("product_code", "agent", "carrier")
        for row in local_rows:
            maybe_register(
                row,
                _local_component_for_location(
                    direction="IMPORT",
                    location=_normalize_code(row.location),
                    origin_airport=origin_airport,
                    destination_airport=destination_airport,
                ),
            )
    elif direction == "EXPORT":
        lane_rows = apply_currency_filter(
            _active_queryset(ExportCOGS, on_date=today).filter(
                origin_airport=origin_airport,
                destination_airport=destination_airport,
            )
        ).select_related("product_code", "agent", "carrier")
        for row in lane_rows:
            if is_local_rate_category(getattr(row.product_code, "category", None)):
                continue
            maybe_register(row, _classify_export_cogs_component(row))

        local_rows = apply_currency_filter(
            _active_queryset(LocalCOGSRate, on_date=today).filter(
                direction="EXPORT",
                location__in=[code for code in [origin_airport, destination_airport] if code],
            )
        ).select_related("product_code", "agent", "carrier")
        for row in local_rows:
            maybe_register(
                row,
                _local_component_for_location(
                    direction="EXPORT",
                    location=_normalize_code(row.location),
                    origin_airport=origin_airport,
                    destination_airport=destination_airport,
                ),
            )
    elif direction == "DOMESTIC":
        domestic_rows = apply_currency_filter(
            _active_queryset(DomesticCOGS, on_date=today).filter(
                origin_zone=origin_airport,
                destination_zone=destination_airport,
            )
        ).select_related("product_code", "agent", "carrier")
        for row in domestic_rows:
            maybe_register(row, _classify_domestic_cogs_component(row))

    available_types: list[str] = []
    if agent_map:
        available_types.append("agent")
    if carrier_map:
        available_types.append("carrier")

    if available_types == ["agent"]:
        advisory = "Only agent-scoped buy rows are active for this quote context."
    elif available_types == ["carrier"]:
        advisory = "Only carrier-scoped buy rows are active for this quote context."
    elif len(available_types) == 2:
        advisory = "Both agent- and carrier-scoped buy rows are active for this quote context."
    else:
        advisory = "No counterparty-specific buy rows are active for this quote context."

    return {
        "direction": direction,
        "service_scope": scope,
        "origin_airport": origin_airport,
        "destination_airport": destination_airport,
        "buy_currency": buy_currency,
        "quote_date": today.isoformat(),
        "required_components": required,
        "available_counterparty_types": available_types,
        "recommended_counterparty_type": available_types[0] if len(available_types) == 1 else None,
        "component_counterparty_types": {
            component: sorted(types)
            for component, types in component_types.items()
        },
        "agents": AgentSerializer(
            sorted(agent_map.values(), key=lambda item: item.code),
            many=True,
        ).data,
        "carriers": CarrierSerializer(
            sorted(carrier_map.values(), key=lambda item: item.code),
            many=True,
        ).data,
        "advisory": advisory,
    }

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
            return Response({"error": "Internal Pricing Engine Error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
from .models import Agent, Carrier, CustomerDiscount, ProductCode
from .serializers import (
    AgentSerializer,
    CarrierSerializer,
    CustomerDiscountSerializer,
    CustomerDiscountListSerializer,
    ProductCodeSerializer,
)


class V4RateCardUploadView(APIView):
    """
    Bulk import V4 SELL rate rows from CSV into Export/Import/Domestic rate tables.

    Path: /api/v4/rates/upload/
    """
    permission_classes = [IsManagerOrAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload_file = request.FILES.get("file")
        dry_run = str(request.data.get("dry_run", "")).strip().lower() in {"1", "true", "yes", "on"}
        if not upload_file:
            return Response(
                {"success": False, "message": "CSV file is required (multipart field: file)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            validate_csv_upload(upload_file)
        except DjangoValidationError as exc:
            return Response(
                {"success": False, "message": "; ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = import_v4_rate_cards_csv(upload_file, dry_run=dry_run)
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
                "dry_run": result.dry_run,
                "message": (
                    "V4 rate CSV preview generated successfully. No rows were imported."
                    if result.dry_run
                    else "V4 rate CSV import completed successfully."
                ),
                "processed_rows": result.processed_rows,
                "created_rows": result.created_rows,
                "updated_rows": result.updated_rows,
                "preview_rows": result.preview_rows,
            },
            status=status.HTTP_200_OK if result.dry_run else status.HTTP_201_CREATED,
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

    def get_queryset(self):
        qs = super().get_queryset()
        domain = (self.request.query_params.get('domain') or '').strip().upper()
        if domain:
            qs = qs.filter(domain=domain)
        return qs


class QuoteCounterpartyHintsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]

    def get(self, request):
        direction = _normalize_code(request.query_params.get("direction"))
        service_scope = _normalize_scope(request.query_params.get("service_scope"))
        origin_airport = _normalize_code(request.query_params.get("origin_airport"))
        destination_airport = _normalize_code(request.query_params.get("destination_airport"))
        buy_currency = _normalize_code(request.query_params.get("buy_currency")) or None
        quote_date_raw = (request.query_params.get("quote_date") or "").strip()

        errors: dict[str, str] = {}
        if direction not in {"IMPORT", "EXPORT", "DOMESTIC"}:
            errors["direction"] = "direction must be one of IMPORT, EXPORT, or DOMESTIC."
        if service_scope not in {"A2A", "D2A", "A2D", "D2D"}:
            errors["service_scope"] = "service_scope must be one of A2A, D2A, A2D, or D2D."
        if not origin_airport:
            errors["origin_airport"] = "origin_airport is required."
        if not destination_airport:
            errors["destination_airport"] = "destination_airport is required."
        if buy_currency and len(buy_currency) != 3:
            errors["buy_currency"] = "buy_currency must be a 3-letter ISO code."

        quote_date = None
        if quote_date_raw:
            try:
                quote_date = date.fromisoformat(quote_date_raw)
            except ValueError:
                errors["quote_date"] = "quote_date must be in YYYY-MM-DD format."

        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        payload = _build_counterparty_hints(
            direction=direction,
            service_scope=service_scope,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            buy_currency=buy_currency,
            quote_date=quote_date,
        )
        return Response(payload, status=status.HTTP_200_OK)


# =============================================================================
# PRICING REFERENCE VIEWSETS
# =============================================================================


class CarrierViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Carrier.objects.all().order_by('code')
    serializer_class = CarrierSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'name']


class AgentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Agent.objects.all().order_by('code')
    serializer_class = AgentSerializer
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'name', 'country_code']


# =============================================================================
# V4 SELL RATE VIEWSETS
# =============================================================================

from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    DomesticCOGS,
    DomesticSellRate,
    ExportCOGS,
    ExportSellRate,
    ImportCOGS,
    ImportSellRate,
    LocalCOGSRate,
    LocalSellRate,
    RateChangeLog,
)
from .serializers import (
    DomesticCOGSSerializer,
    ExportCOGSSerializer,
    ExportSellRateSerializer,
    ImportCOGSSerializer,
    ImportSellRateSerializer,
    DomesticSellRateSerializer,
    LocalSellRateSerializer,
    LocalCOGSRateSerializer,
    RateChangeLogSerializer,
    RateRevisionRequestSerializer,
)


class BaseRateViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields: list[str] = []
    search_fields: list[str] = []
    ordering_fields: list[str] = []
    active_delete_message = 'Active rate rows cannot be deleted directly. Use retire instead.'
    future_delete_message = 'Future-dated rate row deleted.'

    def get_serializer_context(self):
        context = super().get_serializer_context()
        return context

    def _get_audit_save_kwargs(self, *, creating: bool) -> dict[str, object]:
        serializer_model = self.get_serializer_class().Meta.model
        kwargs: dict[str, object] = {}
        if creating and hasattr(serializer_model, 'created_by'):
            kwargs['created_by'] = self.request.user
        if hasattr(serializer_model, 'updated_by'):
            kwargs['updated_by'] = self.request.user
        return kwargs

    def perform_create(self, serializer):
        instance = serializer.save(**self._get_audit_save_kwargs(creating=True))
        ensure_rate_lineage(instance)
        create_rate_change_log(
            instance=instance,
            actor=self.request.user,
            action=RateChangeLog.Action.CREATE,
            before_snapshot=None,
            after_snapshot=serialize_rate_snapshot(instance),
        )

    def perform_update(self, serializer):
        before_snapshot = serialize_rate_snapshot(serializer.instance)
        instance = serializer.save(**self._get_audit_save_kwargs(creating=False))
        ensure_rate_lineage(instance)
        create_rate_change_log(
            instance=instance,
            actor=self.request.user,
            action=RateChangeLog.Action.UPDATE,
            before_snapshot=before_snapshot,
            after_snapshot=serialize_rate_snapshot(instance),
        )

    def perform_destroy(self, instance):
        ensure_rate_lineage(instance)
        before_snapshot = serialize_rate_snapshot(instance)
        table_name = instance._meta.db_table
        object_pk = str(instance.pk)
        actor = self.request.user
        lineage_id = getattr(instance, 'lineage_id', None)
        instance.delete()
        RateChangeLog.objects.create(
            table_name=table_name,
            object_pk=object_pk,
            actor=actor,
            action=RateChangeLog.Action.DELETE,
            lineage_id=lineage_id,
            before_snapshot=before_snapshot,
            after_snapshot=None,
        )

    def get_queryset(self):
        qs = super().get_queryset()
        today = timezone.localdate()
        status_filter = (self.request.query_params.get('status') or '').strip().lower()
        valid_on = (self.request.query_params.get('valid_on') or '').strip()

        if valid_on:
            try:
                comparison_date = date.fromisoformat(valid_on)
            except ValueError:
                comparison_date = today
            qs = qs.filter(valid_from__lte=comparison_date, valid_until__gte=comparison_date)
        elif status_filter == 'active':
            qs = qs.filter(valid_from__lte=today, valid_until__gte=today)
        elif status_filter == 'expired':
            qs = qs.filter(valid_until__lt=today)
        elif status_filter == 'scheduled':
            qs = qs.filter(valid_from__gt=today)

        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        today = timezone.localdate()
        if instance.valid_from <= today <= instance.valid_until:
            return Response(
                {'detail': self.active_delete_message},
                status=status.HTTP_409_CONFLICT,
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def retire(self, request, pk=None):
        instance = self.get_object()
        ensure_rate_lineage(instance)
        today = timezone.localdate()

        if instance.valid_until < today:
            serializer = self.get_serializer(instance)
            return Response(serializer.data, status=status.HTTP_200_OK)

        before_snapshot = serialize_rate_snapshot(instance)
        if instance.valid_from >= today:
            table_name = instance._meta.db_table
            object_pk = str(instance.pk)
            lineage_id = getattr(instance, 'lineage_id', None)
            instance.delete()
            RateChangeLog.objects.create(
                table_name=table_name,
                object_pk=object_pk,
                actor=request.user,
                action=RateChangeLog.Action.RETIRE,
                lineage_id=lineage_id,
                before_snapshot=before_snapshot,
                after_snapshot=None,
            )
            return Response(
                {
                    'retired': True,
                    'deleted': True,
                    'detail': self.future_delete_message,
                },
                status=status.HTTP_200_OK,
            )

        instance.valid_until = today - timedelta(days=1)
        update_fields = ['valid_until', 'updated_at']
        if hasattr(instance, 'updated_by_id'):
            instance.updated_by = request.user
            update_fields.insert(1, 'updated_by')
        instance.save(update_fields=update_fields)
        create_rate_change_log(
            instance=instance,
            actor=request.user,
            action=RateChangeLog.Action.RETIRE,
            before_snapshot=before_snapshot,
            after_snapshot=serialize_rate_snapshot(instance),
        )
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        instance = self.get_object()
        history_qs = get_rate_history_queryset(instance)
        serializer = RateChangeLogSerializer(history_qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def revise(self, request, pk=None):
        instance = self.get_object()
        revision_control = RateRevisionRequestSerializer(
            data={'retire_previous': request.data.get('retire_previous', True)}
        )
        revision_control.is_valid(raise_exception=True)
        retire_previous = revision_control.validated_data['retire_previous']

        revision_payload = request.data.copy()
        if hasattr(revision_payload, 'pop'):
            revision_payload.pop('retire_previous', None)

        serializer_context = self.get_serializer_context()
        if retire_previous:
            serializer_context = {
                **serializer_context,
                'overlap_exclude_pks': [instance.pk],
            }

        serializer = self.get_serializer(data=revision_payload, context=serializer_context)
        serializer.is_valid(raise_exception=True)

        try:
            revised_instance = revise_rate_row(
                source_instance=instance,
                validated_data=serializer.validated_data,
                actor=request.user,
                retire_previous=retire_previous,
            )
        except ValueError as exc:
            raise ValidationError({'valid_from': str(exc)}) from exc

        response_serializer = self.get_serializer(revised_instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class ExportSellRateViewSet(BaseRateViewSet):
    queryset = ExportSellRate.objects.select_related('product_code').order_by(
        'origin_airport', 'destination_airport', 'product_code__code', '-valid_from'
    )
    serializer_class = ExportSellRateSerializer
    filterset_fields = ['origin_airport', 'destination_airport', 'product_code', 'currency', 'valid_from', 'valid_until']
    search_fields = ['product_code__code', 'product_code__description', 'origin_airport', 'destination_airport']
    ordering_fields = ['product_code__code', 'origin_airport', 'destination_airport', 'valid_from', 'updated_at']


class ImportSellRateViewSet(BaseRateViewSet):
    queryset = ImportSellRate.objects.select_related('product_code').order_by(
        'origin_airport', 'destination_airport', 'product_code__code', '-valid_from'
    )
    serializer_class = ImportSellRateSerializer
    filterset_fields = ['origin_airport', 'destination_airport', 'product_code', 'currency', 'valid_from', 'valid_until']
    search_fields = ['product_code__code', 'product_code__description', 'origin_airport', 'destination_airport']
    ordering_fields = ['product_code__code', 'origin_airport', 'destination_airport', 'valid_from', 'updated_at']


class ExportCOGSViewSet(BaseRateViewSet):
    queryset = ExportCOGS.objects.select_related('product_code', 'agent', 'carrier').order_by(
        'origin_airport', 'destination_airport', 'product_code__code', '-valid_from'
    )
    serializer_class = ExportCOGSSerializer
    filterset_fields = ['origin_airport', 'destination_airport', 'product_code', 'currency', 'agent', 'carrier', 'valid_from', 'valid_until']
    search_fields = ['product_code__code', 'product_code__description', 'origin_airport', 'destination_airport', 'agent__name', 'carrier__name']
    ordering_fields = ['product_code__code', 'origin_airport', 'destination_airport', 'valid_from', 'updated_at']
    active_delete_message = 'Active Export COGS rows cannot be deleted directly. Use retire instead.'
    future_delete_message = 'Future-dated Export COGS row deleted.'


class ImportCOGSViewSet(BaseRateViewSet):
    queryset = ImportCOGS.objects.select_related(
        'product_code', 'agent', 'carrier', 'created_by', 'updated_by'
    ).order_by('origin_airport', 'destination_airport', 'product_code__code', '-valid_from')
    serializer_class = ImportCOGSSerializer
    filterset_fields = ['origin_airport', 'destination_airport', 'product_code', 'currency', 'agent', 'carrier', 'valid_from', 'valid_until']
    search_fields = ['product_code__code', 'product_code__description', 'origin_airport', 'destination_airport', 'agent__name', 'carrier__name']
    ordering_fields = ['product_code__code', 'origin_airport', 'destination_airport', 'valid_from', 'updated_at']
    active_delete_message = 'Active Import COGS rows cannot be deleted directly. Use retire instead.'
    future_delete_message = 'Future-dated Import COGS row deleted.'


class DomesticSellRateViewSet(BaseRateViewSet):
    queryset = DomesticSellRate.objects.select_related('product_code').order_by(
        'origin_zone', 'destination_zone', 'product_code__code', '-valid_from'
    )
    serializer_class = DomesticSellRateSerializer
    filterset_fields = ['origin_zone', 'destination_zone', 'product_code', 'currency', 'valid_from', 'valid_until']
    search_fields = ['product_code__code', 'product_code__description', 'origin_zone', 'destination_zone']
    ordering_fields = ['product_code__code', 'origin_zone', 'destination_zone', 'valid_from', 'updated_at']


class DomesticCOGSViewSet(BaseRateViewSet):
    queryset = DomesticCOGS.objects.select_related('product_code', 'agent', 'carrier').order_by(
        'origin_zone', 'destination_zone', 'product_code__code', '-valid_from'
    )
    serializer_class = DomesticCOGSSerializer
    filterset_fields = ['origin_zone', 'destination_zone', 'product_code', 'currency', 'agent', 'carrier', 'valid_from', 'valid_until']
    search_fields = ['product_code__code', 'product_code__description', 'origin_zone', 'destination_zone', 'agent__name', 'carrier__name']
    ordering_fields = ['product_code__code', 'origin_zone', 'destination_zone', 'valid_from', 'updated_at']
    active_delete_message = 'Active Domestic COGS rows cannot be deleted directly. Use retire instead.'
    future_delete_message = 'Future-dated Domestic COGS row deleted.'


class LocalSellRateViewSet(BaseRateViewSet):
    queryset = LocalSellRate.objects.select_related('product_code').order_by(
        'location', 'direction', 'payment_term', 'product_code__code', '-valid_from'
    )
    serializer_class = LocalSellRateSerializer
    filterset_fields = ['location', 'direction', 'payment_term', 'product_code', 'currency', 'valid_from', 'valid_until']
    search_fields = ['product_code__code', 'product_code__description', 'location']
    ordering_fields = ['product_code__code', 'location', 'direction', 'payment_term', 'valid_from', 'updated_at']


class LocalCOGSRateViewSet(BaseRateViewSet):
    queryset = LocalCOGSRate.objects.select_related('product_code', 'agent', 'carrier').order_by(
        'location', 'direction', 'product_code__code', '-valid_from'
    )
    serializer_class = LocalCOGSRateSerializer
    filterset_fields = ['location', 'direction', 'product_code', 'currency', 'agent', 'carrier', 'valid_from', 'valid_until']
    search_fields = ['product_code__code', 'product_code__description', 'location', 'agent__name', 'carrier__name']
    ordering_fields = ['product_code__code', 'location', 'direction', 'valid_from', 'updated_at']
    active_delete_message = 'Active Local COGS rows cannot be deleted directly. Use retire instead.'
    future_delete_message = 'Future-dated Local COGS row deleted.'


# =============================================================================
# LOGICAL RATE CARDS VIEW
# =============================================================================

from .rate_card_config import LOGICAL_RATE_CARDS


class LogicalRateCardsView(APIView):
    """
    Returns logical V4 pricing cards aligned to the current rate architecture.

    Path: /api/v4/rate-cards/
    """
    permission_classes = [permissions.IsAuthenticated, IsManagerOrAdmin]
    
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



