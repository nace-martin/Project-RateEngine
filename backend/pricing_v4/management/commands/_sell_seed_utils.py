from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from pricing_v4.category_rules import (
    is_local_rate_category,
    resolve_export_local_location,
)
from pricing_v4.models import ExportSellRate, ImportSellRate, LocalSellRate, ProductCode


@dataclass
class SeedResult:
    table_name: str
    created: bool


def seed_export_sell_rate(
    *,
    product_code: ProductCode,
    origin_airport: str,
    destination_airport: str,
    currency: str,
    valid_from: date,
    valid_until: date,
    rate_per_shipment: Optional[Decimal] = None,
    rate_per_kg: Optional[Decimal] = None,
    min_charge: Optional[Decimal] = None,
    max_charge: Optional[Decimal] = None,
    weight_breaks=None,
    percent_rate: Optional[Decimal] = None,
    is_additive: bool = False,
    payment_term: str = "PREPAID",
    percent_of_product_code: Optional[ProductCode] = None,
) -> SeedResult:
    if is_local_rate_category(product_code.category):
        created = _upsert_local_sell_rate(
            product_code=product_code,
            location=resolve_export_local_location(
                code=product_code.code,
                description=product_code.description,
                origin_airport=origin_airport,
                destination_airport=destination_airport,
            ),
            direction="EXPORT",
            payment_term=payment_term,
            currency=currency,
            valid_from=valid_from,
            valid_until=valid_until,
            rate_per_shipment=rate_per_shipment,
            rate_per_kg=rate_per_kg,
            min_charge=min_charge,
            max_charge=max_charge,
            weight_breaks=weight_breaks,
            percent_rate=percent_rate,
            is_additive=is_additive,
            percent_of_product_code=percent_of_product_code,
        )
        return SeedResult(table_name="LocalSellRate", created=created)

    _, created = ExportSellRate.objects.update_or_create(
        product_code=product_code,
        origin_airport=origin_airport,
        destination_airport=destination_airport,
        currency=currency,
        valid_from=valid_from,
        defaults={
            "valid_until": valid_until,
            "rate_per_shipment": rate_per_shipment,
            "rate_per_kg": rate_per_kg,
            "min_charge": min_charge,
            "max_charge": max_charge,
            "weight_breaks": weight_breaks,
            "percent_rate": percent_rate,
            "is_additive": is_additive,
        },
    )
    return SeedResult(table_name="ExportSellRate", created=created)


def seed_import_sell_rate(
    *,
    product_code: ProductCode,
    origin_airport: str,
    destination_airport: str,
    currency: str,
    valid_from: date,
    valid_until: date,
    rate_per_shipment: Optional[Decimal] = None,
    rate_per_kg: Optional[Decimal] = None,
    min_charge: Optional[Decimal] = None,
    max_charge: Optional[Decimal] = None,
    weight_breaks=None,
    percent_rate: Optional[Decimal] = None,
    is_additive: bool = False,
    payment_term: str = "COLLECT",
    percent_of_product_code: Optional[ProductCode] = None,
) -> SeedResult:
    if is_local_rate_category(product_code.category):
        created = _upsert_local_sell_rate(
            product_code=product_code,
            location=destination_airport,
            direction="IMPORT",
            payment_term=payment_term,
            currency=currency,
            valid_from=valid_from,
            valid_until=valid_until,
            rate_per_shipment=rate_per_shipment,
            rate_per_kg=rate_per_kg,
            min_charge=min_charge,
            max_charge=max_charge,
            weight_breaks=weight_breaks,
            percent_rate=percent_rate,
            is_additive=is_additive,
            percent_of_product_code=percent_of_product_code,
        )
        return SeedResult(table_name="LocalSellRate", created=created)

    _, created = ImportSellRate.objects.update_or_create(
        product_code=product_code,
        origin_airport=origin_airport,
        destination_airport=destination_airport,
        currency=currency,
        valid_from=valid_from,
        defaults={
            "valid_until": valid_until,
            "rate_per_shipment": rate_per_shipment,
            "rate_per_kg": rate_per_kg,
            "min_charge": min_charge,
            "max_charge": max_charge,
            "weight_breaks": weight_breaks,
            "percent_rate": percent_rate,
            "is_additive": is_additive,
        },
    )
    return SeedResult(table_name="ImportSellRate", created=created)


def _upsert_local_sell_rate(
    *,
    product_code: ProductCode,
    location: str,
    direction: str,
    payment_term: str,
    currency: str,
    valid_from: date,
    valid_until: date,
    rate_per_shipment: Optional[Decimal],
    rate_per_kg: Optional[Decimal],
    min_charge: Optional[Decimal],
    max_charge: Optional[Decimal],
    weight_breaks,
    percent_rate: Optional[Decimal],
    is_additive: bool,
    percent_of_product_code: Optional[ProductCode],
) -> bool:
    defaults = {
        "valid_until": valid_until,
        "min_charge": min_charge,
        "max_charge": max_charge,
        "weight_breaks": weight_breaks,
        "is_additive": is_additive,
        "additive_flat_amount": None,
        "percent_of_product_code": None,
    }

    if percent_rate is not None:
        defaults["rate_type"] = "PERCENT"
        defaults["amount"] = percent_rate
        defaults["percent_of_product_code"] = percent_of_product_code
    elif rate_per_kg is not None:
        defaults["rate_type"] = "PER_KG"
        defaults["amount"] = rate_per_kg
        if is_additive:
            defaults["additive_flat_amount"] = rate_per_shipment
    else:
        defaults["rate_type"] = "FIXED"
        defaults["amount"] = rate_per_shipment or Decimal("0")

    _, created = LocalSellRate.objects.update_or_create(
        product_code=product_code,
        location=location,
        direction=direction,
        payment_term=payment_term,
        currency=currency,
        valid_from=valid_from,
        defaults=defaults,
    )
    return created
