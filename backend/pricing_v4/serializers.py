from datetime import date
from decimal import Decimal
from typing import Any

from django.db import models
from rest_framework import serializers
from pricing_v4.category_rules import is_local_rate_category
from .models import (
    Agent,
    Carrier,
    ProductCode,
    DomesticCOGS,
    DomesticSellRate,
    ExportCOGS,
    ExportSellRate,
    ImportCOGS,
    ImportSellRate,
    LocalCOGSRate,
    LocalSellRate,
    ComponentMargin,
    CustomerDiscount,
    RateChangeLog,
    Surcharge,
)
from parties.models import Company

RATE_AUDIT_FIELDS = [
    'created_at',
    'updated_at',
    'created_by',
    'created_by_username',
    'updated_by',
    'updated_by_username',
    'lineage_id',
    'supersedes_rate',
]


def _is_internal_pricing_field(field_name: str) -> bool:
    """
    Identify internal/commercial-sensitive pricing fields that must not be
    exposed to Sales users (or any non-manager/admin caller).
    """
    key = (field_name or "").lower()
    if not key:
        return False
    if key.startswith("buy_"):
        return True
    if "cogs" in key or "margin" in key:
        return True
    # V4 engine payloads primarily expose COGS via cost_* / total_cost fields.
    if key.startswith("cost") or "_cost" in key:
        return True
    return False


def scrub_pricing_result_payload(payload: Any, include_internal_fields: bool = False) -> Any:
    """
    Recursively remove internal pricing fields (COGS / cost / buy / margin)
    from a V4 pricing response unless explicitly allowed.
    """
    if include_internal_fields:
        return payload

    if isinstance(payload, dict):
        sanitized = {}
        for key, value in payload.items():
            if _is_internal_pricing_field(str(key)):
                continue
            sanitized[key] = scrub_pricing_result_payload(value, include_internal_fields=False)
        return sanitized

    if isinstance(payload, list):
        return [scrub_pricing_result_payload(item, include_internal_fields=False) for item in payload]

    if isinstance(payload, tuple):
        return tuple(scrub_pricing_result_payload(item, include_internal_fields=False) for item in payload)

    return payload

class ProductCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCode
        fields = ['id', 'code', 'description', 'domain', 'category', 'default_unit']


class CarrierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Carrier
        fields = ['id', 'code', 'name', 'carrier_type']


class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Agent
        fields = ['id', 'code', 'name', 'country_code', 'agent_type']


def _validate_weight_breaks(value: Any) -> list[dict[str, str]] | None:
    if value in (None, ""):
        return None
    if not isinstance(value, list):
        raise serializers.ValidationError("weight_breaks must be a JSON array.")

    normalized: list[dict[str, str]] = []
    seen_thresholds: set[Decimal] = set()
    last_threshold: Decimal | None = None

    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise serializers.ValidationError(f"weight_breaks[{index}] must be an object.")

        if 'min_kg' not in row or 'rate' not in row:
            raise serializers.ValidationError(
                f"weight_breaks[{index}] must include min_kg and rate."
            )

        try:
            min_kg = Decimal(str(row.get('min_kg')))
            rate = Decimal(str(row.get('rate')))
        except Exception as exc:
            raise serializers.ValidationError(
                f"weight_breaks[{index}] contains invalid numeric values."
            ) from exc

        if min_kg < 0:
            raise serializers.ValidationError(f"weight_breaks[{index}].min_kg cannot be negative.")
        if rate < 0:
            raise serializers.ValidationError(f"weight_breaks[{index}].rate cannot be negative.")
        if min_kg in seen_thresholds:
            raise serializers.ValidationError("weight_breaks must use unique min_kg tiers.")
        if last_threshold is not None and min_kg <= last_threshold:
            raise serializers.ValidationError("weight_breaks must be sorted by ascending min_kg.")

        seen_thresholds.add(min_kg)
        last_threshold = min_kg
        normalized.append(
            {
                "min_kg": format(min_kg.normalize(), 'f'),
                "rate": format(rate.normalize(), 'f'),
            }
        )

    return normalized


def _normalize_text(value: Any, uppercase: bool = True) -> str:
    normalized = (value or "").strip()
    return normalized.upper() if uppercase else normalized


def _current_or_attr(
    attrs: dict[str, Any],
    instance: Any,
    field_name: str,
    default: Any = None,
) -> Any:
    if field_name in attrs:
        return attrs.get(field_name)
    if instance is not None:
        return getattr(instance, field_name, default)
    return default


def _validate_effective_date_window(valid_from: Any, valid_until: Any) -> None:
    if valid_from and valid_until and valid_until <= valid_from:
        raise serializers.ValidationError({'valid_until': 'valid_until must be later than valid_from.'})


def _validate_non_negative_fields(field_values: list[tuple[str, Any]]) -> None:
    for field_name, value in field_values:
        if value is not None and value < 0:
            raise serializers.ValidationError({field_name: f'{field_name} cannot be negative.'})


def _validate_charge_bounds(min_charge: Any, max_charge: Any) -> None:
    if min_charge is not None and max_charge is not None and max_charge < min_charge:
        raise serializers.ValidationError({'max_charge': 'max_charge cannot be less than min_charge.'})


def _normalize_weight_breaks(attrs: dict[str, Any], weight_breaks: Any) -> list[dict[str, str]] | None:
    try:
        normalized_breaks = _validate_weight_breaks(weight_breaks)
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({'weight_breaks': exc.detail}) from exc
    if normalized_breaks is not None:
        attrs['weight_breaks'] = normalized_breaks
    return normalized_breaks


def _validate_lane_basis(
    *,
    rate_per_kg: Any,
    rate_per_shipment: Any,
    percent_rate: Any,
    weight_breaks: Any,
    is_additive: bool,
    supports_percent_rate: bool,
) -> None:
    uses_percent = percent_rate is not None
    uses_tiers = bool(weight_breaks)
    uses_per_kg = rate_per_kg is not None
    uses_flat = rate_per_shipment is not None

    if not any([uses_percent, uses_tiers, uses_per_kg, uses_flat]):
        if supports_percent_rate:
            raise serializers.ValidationError(
                'Provide one pricing basis: rate_per_kg, rate_per_shipment, percent_rate, or weight_breaks.'
            )
        raise serializers.ValidationError(
            'Provide one pricing basis: rate_per_kg, rate_per_shipment, or weight_breaks.'
        )

    if not supports_percent_rate and uses_percent:
        raise serializers.ValidationError({'percent_rate': 'percent_rate is not supported for this table.'})

    if uses_percent and any([uses_tiers, uses_per_kg, uses_flat, bool(is_additive)]):
        raise serializers.ValidationError(
            {'percent_rate': 'percent_rate must be the only pricing basis on the row.'}
        )

    if uses_tiers and any([uses_percent, uses_per_kg, uses_flat, bool(is_additive)]):
        raise serializers.ValidationError(
            {'weight_breaks': 'weight_breaks cannot be combined with other pricing bases.'}
        )

    if is_additive and not (uses_per_kg and uses_flat):
        raise serializers.ValidationError(
            {'is_additive': 'is_additive requires both rate_per_kg and rate_per_shipment.'}
        )


def _validate_local_basis(
    *,
    rate_type: str,
    amount: Any,
    is_additive: bool,
    additive_flat_amount: Any,
    min_charge: Any,
    max_charge: Any,
    weight_breaks: Any,
    percent_of_product_code: Any,
) -> None:
    if amount is None:
        raise serializers.ValidationError({'amount': 'amount is required.'})

    if rate_type == 'PERCENT':
        if not percent_of_product_code:
            raise serializers.ValidationError(
                {'percent_of_product_code': 'percent_of_product_code is required for PERCENT rates.'}
            )
        if is_additive or additive_flat_amount is not None:
            raise serializers.ValidationError(
                {'is_additive': 'PERCENT rates cannot use additive flat amounts.'}
            )
        if weight_breaks:
            raise serializers.ValidationError({'weight_breaks': 'PERCENT rates cannot use weight_breaks.'})
    else:
        if percent_of_product_code:
            raise serializers.ValidationError(
                {'percent_of_product_code': 'percent_of_product_code can only be set for PERCENT rates.'}
            )

    if rate_type == 'FIXED':
        if is_additive or additive_flat_amount is not None:
            raise serializers.ValidationError({'is_additive': 'FIXED rates cannot be additive.'})
        if weight_breaks:
            raise serializers.ValidationError({'weight_breaks': 'FIXED rates cannot use weight_breaks.'})
    elif rate_type == 'PER_KG':
        if weight_breaks and is_additive:
            raise serializers.ValidationError(
                {'weight_breaks': 'weight_breaks cannot be combined with additive per-kg pricing.'}
            )
        if is_additive and additive_flat_amount is None:
            raise serializers.ValidationError(
                {'additive_flat_amount': 'additive_flat_amount is required when is_additive is true.'}
            )
        if not is_additive and additive_flat_amount is not None:
            raise serializers.ValidationError(
                {'additive_flat_amount': 'additive_flat_amount requires is_additive=true.'}
            )
    else:
        if weight_breaks:
            raise serializers.ValidationError({'weight_breaks': 'weight_breaks require rate_type=PER_KG.'})

    _validate_charge_bounds(min_charge, max_charge)


def _reject_overlap(
    *,
    model: type[models.Model],
    instance: Any,
    lookup: dict[str, Any],
    valid_from: Any,
    valid_until: Any,
    message: str,
    exclude_pks: list[Any] | None = None,
) -> None:
    overlap_qs = model.objects.filter(
        valid_from__lte=valid_until,
        valid_until__gte=valid_from,
        **lookup,
    )
    if instance is not None:
        overlap_qs = overlap_qs.exclude(pk=instance.pk)
    if exclude_pks:
        overlap_qs = overlap_qs.exclude(pk__in=exclude_pks)
    if overlap_qs.exists():
        conflict_rows = [
            f"#{row.pk} ({row.valid_from} to {row.valid_until})"
            for row in overlap_qs.order_by('valid_from', 'valid_until', 'pk')[:5]
        ]
        raise serializers.ValidationError(
            {
                'valid_from': f"{message} Conflicts with {', '.join(conflict_rows)}.",
                'conflicts': conflict_rows,
            }
        )


class EffectiveDatedRateSerializer(serializers.ModelSerializer):
    product_code_code = serializers.CharField(source='product_code.code', read_only=True)
    product_code_description = serializers.CharField(source='product_code.description', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True, allow_null=True)
    updated_by_username = serializers.CharField(source='updated_by.username', read_only=True, allow_null=True)
    is_active = serializers.SerializerMethodField()

    def get_is_active(self, obj):
        today = date.today()
        return obj.valid_from <= today <= obj.valid_until


class BaseLaneRateSerializer(EffectiveDatedRateSerializer):
    origin_field_name = 'origin_airport'
    destination_field_name = 'destination_airport'
    expected_domain: str | None = None
    local_table_label = 'Local Rates'
    overlap_message = 'Overlapping effective-date rows already exist for this rate key.'
    supports_percent_rate = True
    normalize_route_upper = True
    require_counterparty = False
    lane_type_label = 'lane'
    read_only_audit_fields: list[str] = []

    def validate(self, attrs):
        attrs = super().validate(attrs)

        product_code = _current_or_attr(attrs, self.instance, 'product_code')
        valid_from = _current_or_attr(attrs, self.instance, 'valid_from')
        valid_until = _current_or_attr(attrs, self.instance, 'valid_until')
        currency = _normalize_text(_current_or_attr(attrs, self.instance, 'currency'))
        origin_value = _normalize_text(
            _current_or_attr(attrs, self.instance, self.origin_field_name),
            uppercase=self.normalize_route_upper,
        )
        destination_value = _normalize_text(
            _current_or_attr(attrs, self.instance, self.destination_field_name),
            uppercase=self.normalize_route_upper,
        )
        rate_per_kg = _current_or_attr(attrs, self.instance, 'rate_per_kg')
        rate_per_shipment = _current_or_attr(attrs, self.instance, 'rate_per_shipment')
        min_charge = _current_or_attr(attrs, self.instance, 'min_charge')
        max_charge = _current_or_attr(attrs, self.instance, 'max_charge')
        percent_rate = _current_or_attr(attrs, self.instance, 'percent_rate')
        is_additive = bool(_current_or_attr(attrs, self.instance, 'is_additive', False))
        weight_breaks = _current_or_attr(attrs, self.instance, 'weight_breaks')
        agent = _current_or_attr(attrs, self.instance, 'agent')
        carrier = _current_or_attr(attrs, self.instance, 'carrier')

        if product_code and self.expected_domain and product_code.domain != self.expected_domain:
            raise serializers.ValidationError(
                {'product_code': f'This table requires {self.expected_domain.title()} ProductCodes.'}
            )
        if product_code and is_local_rate_category(product_code.category):
            raise serializers.ValidationError(
                {'product_code': f"{product_code.code} is a local charge and must be created in {self.local_table_label}."}
            )
        if self.require_counterparty and bool(agent) == bool(carrier):
            raise serializers.ValidationError({'agent': 'Select exactly one counterparty: either agent or carrier.'})

        _validate_effective_date_window(valid_from, valid_until)
        _validate_non_negative_fields([
            ('rate_per_kg', rate_per_kg),
            ('rate_per_shipment', rate_per_shipment),
            ('min_charge', min_charge),
            ('max_charge', max_charge),
            ('percent_rate', percent_rate),
        ])
        _validate_charge_bounds(min_charge, max_charge)

        normalized_breaks = _normalize_weight_breaks(attrs, weight_breaks)
        if normalized_breaks is not None:
            weight_breaks = normalized_breaks

        _validate_lane_basis(
            rate_per_kg=rate_per_kg,
            rate_per_shipment=rate_per_shipment,
            percent_rate=percent_rate,
            weight_breaks=weight_breaks,
            is_additive=is_additive,
            supports_percent_rate=self.supports_percent_rate,
        )

        lookup = {
            'product_code': product_code,
            self.origin_field_name: origin_value,
            self.destination_field_name: destination_value,
            'currency': currency,
        }
        if self.require_counterparty:
            lookup['agent'] = agent
            lookup['carrier'] = carrier

        _reject_overlap(
            model=self.Meta.model,
            instance=self.instance,
            lookup=lookup,
            valid_from=valid_from,
            valid_until=valid_until,
            message=self.overlap_message,
            exclude_pks=self.context.get('overlap_exclude_pks'),
        )

        attrs[self.origin_field_name] = origin_value
        attrs[self.destination_field_name] = destination_value
        attrs['currency'] = currency
        return attrs


class BaseLocalRateSerializer(EffectiveDatedRateSerializer):
    expected_domain_by_direction: dict[str, str] = {}
    require_counterparty = False
    overlap_message = 'Overlapping effective-date rows already exist for this local rate key.'
    local_rate_label = 'local rates'

    def validate(self, attrs):
        attrs = super().validate(attrs)

        product_code = _current_or_attr(attrs, self.instance, 'product_code')
        direction = _normalize_text(_current_or_attr(attrs, self.instance, 'direction'))
        location = _normalize_text(_current_or_attr(attrs, self.instance, 'location'))
        currency = _normalize_text(_current_or_attr(attrs, self.instance, 'currency'))
        payment_term = _normalize_text(_current_or_attr(attrs, self.instance, 'payment_term'))
        rate_type = _normalize_text(_current_or_attr(attrs, self.instance, 'rate_type'))
        amount = _current_or_attr(attrs, self.instance, 'amount')
        is_additive = bool(_current_or_attr(attrs, self.instance, 'is_additive', False))
        additive_flat_amount = _current_or_attr(attrs, self.instance, 'additive_flat_amount')
        min_charge = _current_or_attr(attrs, self.instance, 'min_charge')
        max_charge = _current_or_attr(attrs, self.instance, 'max_charge')
        weight_breaks = _current_or_attr(attrs, self.instance, 'weight_breaks')
        percent_of_product_code = _current_or_attr(attrs, self.instance, 'percent_of_product_code')
        valid_from = _current_or_attr(attrs, self.instance, 'valid_from')
        valid_until = _current_or_attr(attrs, self.instance, 'valid_until')
        agent = _current_or_attr(attrs, self.instance, 'agent')
        carrier = _current_or_attr(attrs, self.instance, 'carrier')

        if self.require_counterparty and bool(agent) == bool(carrier):
            raise serializers.ValidationError({'agent': 'Select exactly one counterparty: either agent or carrier.'})

        if product_code and not is_local_rate_category(product_code.category):
            raise serializers.ValidationError(
                {'product_code': f"{product_code.code} is lane-based and must be created in lane rate tables."}
            )

        expected_domain = self.expected_domain_by_direction.get(direction)
        if product_code and expected_domain and product_code.domain != expected_domain:
            raise serializers.ValidationError(
                {'product_code': f'{direction} local rates require {expected_domain.title()} ProductCodes.'}
            )

        if percent_of_product_code:
            if not is_local_rate_category(percent_of_product_code.category):
                raise serializers.ValidationError(
                    {'percent_of_product_code': 'percent_of_product_code must reference a local ProductCode.'}
                )
            if expected_domain and percent_of_product_code.domain != expected_domain:
                raise serializers.ValidationError(
                    {'percent_of_product_code': f'percent_of_product_code must also be in the {expected_domain.title()} domain.'}
                )

        _validate_effective_date_window(valid_from, valid_until)
        _validate_non_negative_fields([
            ('amount', amount),
            ('additive_flat_amount', additive_flat_amount),
            ('min_charge', min_charge),
            ('max_charge', max_charge),
        ])

        normalized_breaks = _normalize_weight_breaks(attrs, weight_breaks)
        if normalized_breaks is not None:
            weight_breaks = normalized_breaks

        _validate_local_basis(
            rate_type=rate_type,
            amount=amount,
            is_additive=is_additive,
            additive_flat_amount=additive_flat_amount,
            min_charge=min_charge,
            max_charge=max_charge,
            weight_breaks=weight_breaks,
            percent_of_product_code=percent_of_product_code,
        )

        lookup = {
            'product_code': product_code,
            'location': location,
            'direction': direction,
            'currency': currency,
        }
        if hasattr(self.Meta.model, 'payment_term'):
            conflicting_payment_terms = ['ANY', payment_term] if payment_term != 'ANY' else ['ANY', 'PREPAID', 'COLLECT']
            lookup['payment_term__in'] = conflicting_payment_terms
        if self.require_counterparty:
            lookup['agent'] = agent
            lookup['carrier'] = carrier

        _reject_overlap(
            model=self.Meta.model,
            instance=self.instance,
            lookup=lookup,
            valid_from=valid_from,
            valid_until=valid_until,
            message=self.overlap_message,
            exclude_pks=self.context.get('overlap_exclude_pks'),
        )

        attrs['location'] = location
        attrs['direction'] = direction
        attrs['currency'] = currency
        if 'payment_term' in attrs or hasattr(self.Meta.model, 'payment_term'):
            attrs['payment_term'] = payment_term
        return attrs


class ExportSellRateSerializer(BaseLaneRateSerializer):
    expected_domain = ProductCode.DOMAIN_EXPORT
    local_table_label = 'Local Sell Rates'
    overlap_message = 'Overlapping effective-date rows already exist for this Export Sell key.'

    class Meta:
        model = ExportSellRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_airport', 'destination_airport', 'currency',
            'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'percent_rate', 'weight_breaks', 'is_additive',
            'valid_from', 'valid_until', *RATE_AUDIT_FIELDS, 'is_active',
        ]
        read_only_fields = ['id', *RATE_AUDIT_FIELDS, 'is_active']


class ImportSellRateSerializer(BaseLaneRateSerializer):
    expected_domain = ProductCode.DOMAIN_IMPORT
    local_table_label = 'Local Sell Rates'
    overlap_message = 'Overlapping effective-date rows already exist for this Import Sell key.'

    class Meta:
        model = ImportSellRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_airport', 'destination_airport', 'currency',
            'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'percent_rate', 'weight_breaks', 'is_additive',
            'valid_from', 'valid_until', *RATE_AUDIT_FIELDS, 'is_active',
        ]
        read_only_fields = ['id', *RATE_AUDIT_FIELDS, 'is_active']


class DomesticSellRateSerializer(BaseLaneRateSerializer):
    origin_field_name = 'origin_zone'
    destination_field_name = 'destination_zone'
    expected_domain = ProductCode.DOMAIN_DOMESTIC
    supports_percent_rate = True
    normalize_route_upper = True
    overlap_message = 'Overlapping effective-date rows already exist for this Domestic Sell key.'

    class Meta:
        model = DomesticSellRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_zone', 'destination_zone', 'currency',
            'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'percent_rate', 'weight_breaks', 'is_additive',
            'valid_from', 'valid_until', *RATE_AUDIT_FIELDS, 'is_active',
        ]
        read_only_fields = ['id', *RATE_AUDIT_FIELDS, 'is_active']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        currency = attrs.get('currency') or getattr(self.instance, 'currency', None)
        if currency != 'PGK':
            raise serializers.ValidationError({'currency': 'Domestic sell rates must use PGK.'})
        return attrs


class ExportCOGSSerializer(BaseLaneRateSerializer):
    agent_name = serializers.CharField(source='agent.name', read_only=True, allow_null=True)
    carrier_name = serializers.CharField(source='carrier.name', read_only=True, allow_null=True)
    expected_domain = ProductCode.DOMAIN_EXPORT
    local_table_label = 'Local COGS Rates'
    overlap_message = 'Overlapping effective-date rows already exist for this Export COGS key.'
    require_counterparty = True
    supports_percent_rate = False

    class Meta:
        model = ExportCOGS
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_airport', 'destination_airport',
            'carrier', 'carrier_name', 'agent', 'agent_name',
            'currency', 'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'weight_breaks', 'is_additive',
            'valid_from', 'valid_until', *RATE_AUDIT_FIELDS, 'is_active',
        ]
        read_only_fields = ['id', *RATE_AUDIT_FIELDS, 'is_active']


class ImportCOGSSerializer(BaseLaneRateSerializer):
    agent_name = serializers.CharField(source='agent.name', read_only=True, allow_null=True)
    carrier_name = serializers.CharField(source='carrier.name', read_only=True, allow_null=True)
    expected_domain = ProductCode.DOMAIN_IMPORT
    local_table_label = 'Local COGS Rates'
    overlap_message = 'Overlapping effective-date rows already exist for this Import COGS key.'
    require_counterparty = True
    supports_percent_rate = True

    class Meta:
        model = ImportCOGS
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_airport', 'destination_airport',
            'carrier', 'carrier_name', 'agent', 'agent_name',
            'currency', 'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'is_additive', 'percent_rate', 'weight_breaks',
            'valid_from', 'valid_until', *RATE_AUDIT_FIELDS, 'is_active',
        ]
        read_only_fields = ['id', *RATE_AUDIT_FIELDS, 'is_active']


class DomesticCOGSSerializer(BaseLaneRateSerializer):
    origin_field_name = 'origin_zone'
    destination_field_name = 'destination_zone'
    agent_name = serializers.CharField(source='agent.name', read_only=True, allow_null=True)
    carrier_name = serializers.CharField(source='carrier.name', read_only=True, allow_null=True)
    expected_domain = ProductCode.DOMAIN_DOMESTIC
    overlap_message = 'Overlapping effective-date rows already exist for this Domestic COGS key.'
    require_counterparty = True
    supports_percent_rate = False

    class Meta:
        model = DomesticCOGS
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'origin_zone', 'destination_zone',
            'carrier', 'carrier_name', 'agent', 'agent_name',
            'currency', 'rate_per_kg', 'rate_per_shipment', 'min_charge', 'max_charge',
            'weight_breaks', 'is_additive',
            'valid_from', 'valid_until', *RATE_AUDIT_FIELDS, 'is_active',
        ]
        read_only_fields = ['id', *RATE_AUDIT_FIELDS, 'is_active']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        currency = attrs.get('currency') or getattr(self.instance, 'currency', None)
        if currency != 'PGK':
            raise serializers.ValidationError({'currency': 'Domestic COGS rates must use PGK.'})
        return attrs


class LocalSellRateSerializer(BaseLocalRateSerializer):
    expected_domain_by_direction = {
        'EXPORT': ProductCode.DOMAIN_EXPORT,
        'IMPORT': ProductCode.DOMAIN_IMPORT,
    }
    percent_of_product_code_code = serializers.CharField(source='percent_of_product_code.code', read_only=True, allow_null=True)
    percent_of_product_code_description = serializers.CharField(source='percent_of_product_code.description', read_only=True, allow_null=True)
    overlap_message = 'Overlapping effective-date rows already exist for this Local Sell key.'

    class Meta:
        model = LocalSellRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'location', 'direction', 'payment_term', 'currency',
            'rate_type', 'amount', 'is_additive', 'additive_flat_amount',
            'min_charge', 'max_charge', 'weight_breaks',
            'percent_of_product_code', 'percent_of_product_code_code', 'percent_of_product_code_description',
            'valid_from', 'valid_until', *RATE_AUDIT_FIELDS, 'is_active',
        ]
        read_only_fields = ['id', *RATE_AUDIT_FIELDS, 'is_active']


class LocalCOGSRateSerializer(BaseLocalRateSerializer):
    expected_domain_by_direction = {
        'EXPORT': ProductCode.DOMAIN_EXPORT,
        'IMPORT': ProductCode.DOMAIN_IMPORT,
    }
    require_counterparty = True
    agent_name = serializers.CharField(source='agent.name', read_only=True, allow_null=True)
    carrier_name = serializers.CharField(source='carrier.name', read_only=True, allow_null=True)
    percent_of_product_code_code = serializers.CharField(source='percent_of_product_code.code', read_only=True, allow_null=True)
    percent_of_product_code_description = serializers.CharField(source='percent_of_product_code.description', read_only=True, allow_null=True)
    overlap_message = 'Overlapping effective-date rows already exist for this Local COGS key.'

    class Meta:
        model = LocalCOGSRate
        fields = [
            'id', 'product_code', 'product_code_code', 'product_code_description',
            'location', 'direction', 'agent', 'agent_name', 'carrier', 'carrier_name',
            'currency', 'rate_type', 'amount', 'is_additive', 'additive_flat_amount',
            'min_charge', 'max_charge', 'weight_breaks',
            'percent_of_product_code', 'percent_of_product_code_code', 'percent_of_product_code_description',
            'valid_from', 'valid_until', *RATE_AUDIT_FIELDS, 'is_active',
        ]
        read_only_fields = ['id', *RATE_AUDIT_FIELDS, 'is_active']


class RateChangeLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True, allow_null=True)

    class Meta:
        model = RateChangeLog
        fields = [
            'id',
            'table_name',
            'object_pk',
            'actor',
            'actor_username',
            'action',
            'lineage_id',
            'before_snapshot',
            'after_snapshot',
            'created_at',
        ]
        read_only_fields = fields


class RateRevisionRequestSerializer(serializers.Serializer):
    retire_previous = serializers.BooleanField(required=False, default=True)

class ComponentMarginSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComponentMargin
        fields = '__all__'

class CustomerDiscountSerializer(serializers.ModelSerializer):
    """Full serializer for create/update operations."""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    product_code_display = serializers.SerializerMethodField()
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    min_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    max_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    
    class Meta:
        model = CustomerDiscount
        fields = [
            'id', 'customer', 'customer_name', 'product_code', 'product_code_display',
            'discount_type', 'discount_value', 'currency', 'min_charge', 'max_charge',
            'valid_from', 'valid_until', 'notes',
            'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by']
    
    def get_product_code_display(self, obj):
        if obj.product_code:
            return f"{obj.product_code.code} - {obj.product_code.description}"
        return None


class CustomerDiscountListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view with expanded relations."""
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    product_code_code = serializers.CharField(source='product_code.code', read_only=True)
    product_code_description = serializers.CharField(source='product_code.description', read_only=True)
    product_code_domain = serializers.CharField(source='product_code.domain', read_only=True)
    discount_type_display = serializers.CharField(source='get_discount_type_display', read_only=True)
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = CustomerDiscount
        fields = [
            'id', 'customer', 'customer_name',
            'product_code', 'product_code_code', 'product_code_description', 'product_code_domain',
            'discount_type', 'discount_type_display', 'discount_value', 'currency',
            'min_charge', 'max_charge',
            'valid_from', 'valid_until', 'is_active', 'notes',
            'created_at'
        ]
    
    def get_is_active(self, obj):
        from datetime import date
        today = date.today()
        if obj.valid_from and today < obj.valid_from:
            return False
        if obj.valid_until and today > obj.valid_until:
            return False
        return True


class CustomerDiscountBulkLineSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    product_code = serializers.PrimaryKeyRelatedField(queryset=ProductCode.objects.all())
    discount_type = serializers.ChoiceField(choices=CustomerDiscount.DISCOUNT_TYPE_CHOICES)
    discount_value = serializers.DecimalField(max_digits=10, decimal_places=4)
    currency = serializers.CharField(max_length=3, required=False, default='PGK')
    min_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    max_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    valid_from = serializers.DateField(required=False, allow_null=True)
    valid_until = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        discount_type = attrs.get('discount_type')
        discount_value = attrs.get('discount_value')
        if discount_type == CustomerDiscount.TYPE_PERCENTAGE and (
            discount_value < 0 or discount_value > 100
        ):
            raise serializers.ValidationError({'discount_value': 'Percentage discount must be between 0 and 100.'})
        if discount_value < 0:
            raise serializers.ValidationError({'discount_value': 'Discount value cannot be negative.'})
        return attrs


class CustomerDiscountBulkUpsertSerializer(serializers.Serializer):
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.filter(models.Q(is_customer=True) | models.Q(company_type='CUSTOMER'))
    )
    lines = CustomerDiscountBulkLineSerializer(many=True)

# =============================================================================
# V4 QUOTE REQUEST SERIALIZER
# =============================================================================

class CargoDetailsSerializer(serializers.Serializer):
    weight_kg = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    volume_m3 = serializers.DecimalField(max_digits=10, decimal_places=3, min_value=0.001)
    quantity = serializers.IntegerField(min_value=1, default=1)
    # Optional: dims? For now simple weight/volume is enough for engine
    
class QuoteRequestSerializerV4(serializers.Serializer):
    """
    Strictly typed request payload for V4 Pricing Engine.
    """
    SERVICE_TYPE_CHOICES = [
        ('DOMESTIC', 'Domestic'),
        ('EXPORT', 'Export'),
        ('IMPORT', 'Import'),
    ]
    
    INCOTERMS_CHOICES = [
        ('EXW', 'Ex Works (EXW)'),
        ('FCA', 'Free Carrier (FCA)'),
        ('FOB', 'Free on Board (FOB)'),
        ('CFR', 'Cost and Freight (CFR)'),
        ('CIF', 'Cost, Insurance & Freight (CIF)'),
        ('DAP', 'Delivered at Place (DAP)'),
        ('DPU', 'Delivered at Place Unloaded (DPU)'),
        ('DDP', 'Delivered Duty Paid (DDP)'),
    ]
    
    # Context
    customer_id = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.filter(company_type='CUSTOMER'),
        source='customer',
        help_text="UUID of the customer company"
    )
    
    # Route
    origin = serializers.CharField(max_length=5, help_text="IATA Airport Code (e.g. POM) or Zone ID")
    destination = serializers.CharField(max_length=5, help_text="IATA Airport Code (e.g. BNE) or Zone ID")
    
    # Service
    service_type = serializers.ChoiceField(choices=SERVICE_TYPE_CHOICES)
    incoterms = serializers.ChoiceField(choices=INCOTERMS_CHOICES, required=False, allow_null=True)
    service_scope = serializers.ChoiceField(
        choices=['A2A', 'A2D', 'D2A', 'D2D', 'P2P'],
        default='A2A',
        help_text="Service Scope (e.g. A2A=Airport-to-Airport)"
    )
    is_dg = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Set true for dangerous goods shipments."
    )
    
    # Cargo
    cargo_details = CargoDetailsSerializer()
    
    # Optional overrides
    quote_date = serializers.DateField(required=False, help_text="Defaults to today")
    
    def validate(self, data):
        """
        Cross-field validation.
        """
        service_type = data.get('service_type')
        origin = data.get('origin')
        destination = data.get('destination')
        
        # Validations for specific service types could go here.
        # e.g. If DOMESTIC, ensure origin/dest are within PNG (logic might be in engine though)
        
        return data


