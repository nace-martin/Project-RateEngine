from datetime import date
from typing import Optional

from django.db.models import Q

from core.commodity import DEFAULT_COMMODITY_CODE, normalize_commodity_code
from pricing_v4.models import CommodityChargeRule


def normalize_service_scope(service_scope: Optional[str]) -> str:
    scope = (service_scope or "A2A").strip().upper()
    if scope == "P2P":
        return "A2A"
    return scope


def normalize_payment_term(payment_term: Optional[str]) -> Optional[str]:
    value = (payment_term or "").strip().upper()
    if value in {"PREPAID", "COLLECT"}:
        return value
    return None


def get_applicable_rules(
    *,
    shipment_type: str,
    service_scope: str,
    origin_code: Optional[str] = None,
    destination_code: Optional[str] = None,
    payment_term: Optional[str] = None,
    quote_date: Optional[date] = None,
    commodity_code: Optional[str] = None,
    product_code_id: Optional[int] = None,
):
    today = quote_date or date.today()
    qs = (
        CommodityChargeRule.objects
        .filter(
            shipment_type=(shipment_type or "").strip().upper(),
            service_scope=normalize_service_scope(service_scope),
            is_active=True,
            effective_from__lte=today,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
    )

    origin_code = (origin_code or "").strip().upper()
    destination_code = (destination_code or "").strip().upper()
    if origin_code:
        qs = qs.filter(Q(origin_code__isnull=True) | Q(origin_code='') | Q(origin_code=origin_code))
    if destination_code:
        qs = qs.filter(Q(destination_code__isnull=True) | Q(destination_code='') | Q(destination_code=destination_code))

    normalized_payment_term = normalize_payment_term(payment_term)
    if normalized_payment_term:
        qs = qs.filter(
            Q(payment_term__isnull=True) | Q(payment_term='') | Q(payment_term=normalized_payment_term)
        )

    if commodity_code is not None:
        qs = qs.filter(commodity_code=normalize_commodity_code(commodity_code))
    if product_code_id is not None:
        qs = qs.filter(product_code_id=product_code_id)
    return qs.select_related("product_code")


def get_auto_product_code_ids(
    *,
    shipment_type: str,
    service_scope: str,
    commodity_code: Optional[str],
    origin_code: Optional[str] = None,
    destination_code: Optional[str] = None,
    payment_term: Optional[str] = None,
    quote_date: Optional[date] = None,
) -> list[int]:
    commodity = normalize_commodity_code(commodity_code)
    if commodity == DEFAULT_COMMODITY_CODE:
        return []

    rules = get_applicable_rules(
        shipment_type=shipment_type,
        service_scope=service_scope,
        origin_code=origin_code,
        destination_code=destination_code,
        payment_term=payment_term,
        quote_date=quote_date,
        commodity_code=commodity,
    ).filter(trigger_mode=CommodityChargeRule.TRIGGER_MODE_AUTO)

    return sorted(set(rules.values_list("product_code_id", flat=True)))


def is_product_code_enabled(
    *,
    shipment_type: str,
    service_scope: str,
    commodity_code: Optional[str],
    product_code_id: int,
    origin_code: Optional[str] = None,
    destination_code: Optional[str] = None,
    payment_term: Optional[str] = None,
    quote_date: Optional[date] = None,
) -> bool:
    commodity = normalize_commodity_code(commodity_code)

    current_rules = list(
        get_applicable_rules(
            shipment_type=shipment_type,
            service_scope=service_scope,
            origin_code=origin_code,
            destination_code=destination_code,
            payment_term=payment_term,
            quote_date=quote_date,
            commodity_code=commodity,
            product_code_id=product_code_id,
        )
    )
    if any(rule.trigger_mode == CommodityChargeRule.TRIGGER_MODE_AUTO for rule in current_rules):
        return True

    any_rules = get_applicable_rules(
        shipment_type=shipment_type,
        service_scope=service_scope,
        origin_code=origin_code,
        destination_code=destination_code,
        payment_term=payment_term,
        quote_date=quote_date,
        product_code_id=product_code_id,
    )
    if any_rules.exists():
        return False

    return True
