from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from django.core.management.base import BaseCommand

from pricing_v4.models import (
    DomesticCOGS,
    DomesticSellRate,
    ExportCOGS,
    ExportSellRate,
    ImportSellRate,
    LocalCOGSRate,
    LocalSellRate,
)
from pricing_v4.services.pricing_rate_scope import PricingRateScope, classify_pricing_rate_scope


LANE_TABLES = (
    ExportCOGS,
    ExportSellRate,
    ImportSellRate,
    DomesticCOGS,
    DomesticSellRate,
)
LOCAL_TABLES = (
    LocalCOGSRate,
    LocalSellRate,
)


@dataclass(frozen=True)
class DuplicateSignature:
    table_name: str
    product_code: str
    counterparty_type: str
    counterparty_code: str
    currency: str
    amount_signature: tuple[str, ...]
    fixed_endpoint_name: str
    fixed_endpoint_value: str


class Command(BaseCommand):
    help = "Dry-run audit of lane-vs-local scope risk across pricing rate tables."

    def handle(self, *args, **options):
        lane_rows = list(_iter_lane_rows())
        local_rows = list(_iter_local_rows())

        non_lane_in_lane_tables = [
            row for row in lane_rows
            if classify_pricing_rate_scope(row) in {
                PricingRateScope.ORIGIN,
                PricingRateScope.DESTINATION,
                PricingRateScope.LOCAL,
            }
        ]
        lane_in_local_tables = [
            row for row in local_rows
            if classify_pricing_rate_scope(row) == PricingRateScope.LANE
        ]
        unknown_rows = [
            row for row in [*lane_rows, *local_rows]
            if classify_pricing_rate_scope(row) == PricingRateScope.UNKNOWN
        ]
        duplicate_groups = _duplicate_non_lane_groups(non_lane_in_lane_tables)

        self.stdout.write("Pricing rate scope audit (dry run)")
        self.stdout.write("No rows were changed.")
        self.stdout.write("")
        _write_rows(self.stdout, "Non-lane candidates stored in lane-shaped tables:", non_lane_in_lane_tables)
        self.stdout.write("")
        _write_rows(self.stdout, "Lane candidates stored in local tables:", lane_in_local_tables)
        self.stdout.write("")
        _write_duplicate_groups(self.stdout, duplicate_groups)
        self.stdout.write("")
        _write_rows(self.stdout, "UNKNOWN scope rows:", unknown_rows)
        self.stdout.write("")
        self.stdout.write("Phase 2 direction:")
        self.stdout.write("- Add explicit scope only after table-specific data review.")
        self.stdout.write("- Keep lane rows requiring both route endpoints or zones.")
        self.stdout.write("- Keep local rows keyed by direction/location, not full lane.")
        self.stdout.write("- Normalize duplicated non-lane lane-table rows into local tables or scoped rows.")
        self.stdout.write("- Preserve current selector ordering and quote output while migrating.")


def _iter_lane_rows():
    for model_cls in LANE_TABLES:
        queryset = model_cls.objects.select_related("product_code")
        if _has_counterparty_fields(model_cls):
            queryset = queryset.select_related("agent", "carrier")
        for row in queryset.order_by("product_code__code", "id"):
            yield row


def _iter_local_rows():
    for model_cls in LOCAL_TABLES:
        queryset = model_cls.objects.select_related("product_code")
        if _has_counterparty_fields(model_cls):
            queryset = queryset.select_related("agent", "carrier")
        for row in queryset.order_by("product_code__code", "location", "direction", "id"):
            yield row


def _has_counterparty_fields(model_cls) -> bool:
    fields = {field.name for field in model_cls._meta.fields}
    return {"agent", "carrier"}.issubset(fields)


def _duplicate_non_lane_groups(rows: Iterable[object]):
    groups = defaultdict(list)
    for row in rows:
        for signature in _duplicate_signatures(row):
            groups[signature].append(row)
    return {
        signature: members
        for signature, members in groups.items()
        if len({_variable_endpoint(row, signature.fixed_endpoint_name) for row in members}) > 1
    }


def _duplicate_signatures(row: object) -> list[DuplicateSignature]:
    table_name = type(row).__name__
    counterparty_type, counterparty_code = _counterparty(row)
    base = {
        "table_name": table_name,
        "product_code": row.product_code.code,
        "counterparty_type": counterparty_type,
        "counterparty_code": counterparty_code,
        "currency": getattr(row, "currency", ""),
        "amount_signature": _amount_signature(row),
    }
    signatures = []
    origin_value = _origin_value(row)
    destination_value = _destination_value(row)
    if origin_value:
        signatures.append(
            DuplicateSignature(
                **base,
                fixed_endpoint_name="origin",
                fixed_endpoint_value=origin_value,
            )
        )
    if destination_value:
        signatures.append(
            DuplicateSignature(
                **base,
                fixed_endpoint_name="destination",
                fixed_endpoint_value=destination_value,
            )
        )
    return signatures


def _write_rows(stdout, title: str, rows: list[object]):
    stdout.write(title)
    if not rows:
        stdout.write("- none")
        return
    for row in rows:
        scope = classify_pricing_rate_scope(row)
        stdout.write(
            "- "
            f"{type(row).__name__} #{row.id} {row.product_code.code} "
            f"scope={scope.value} endpoint={_endpoint_label(row)} "
            f"counterparty={':'.join(_counterparty(row))} "
            f"currency={getattr(row, 'currency', '')} amount={_amount_signature(row)}"
        )


def _write_duplicate_groups(stdout, duplicate_groups):
    stdout.write("Likely duplicate non-lane rows in lane-shaped tables:")
    if not duplicate_groups:
        stdout.write("- none")
        return
    for signature, members in duplicate_groups.items():
        variable_endpoint_name = "destination" if signature.fixed_endpoint_name == "origin" else "origin"
        variables = ", ".join(sorted({_variable_endpoint(row, signature.fixed_endpoint_name) for row in members}))
        ids = ", ".join(f"{type(row).__name__}#{row.id}" for row in members)
        stdout.write(
            "- "
            f"{signature.table_name} {signature.product_code} "
            f"{signature.counterparty_type}:{signature.counterparty_code} "
            f"{signature.currency} amount={signature.amount_signature} "
            f"{signature.fixed_endpoint_name}={signature.fixed_endpoint_value} "
            f"{variable_endpoint_name}s={variables} row_ids={ids}"
        )


def _endpoint_label(row: object) -> str:
    if hasattr(row, "origin_airport"):
        return f"{row.origin_airport}->{row.destination_airport}"
    if hasattr(row, "origin_zone"):
        return f"{row.origin_zone}->{row.destination_zone}"
    return f"{row.direction}@{row.location}"


def _origin_value(row: object) -> str:
    return str(getattr(row, "origin_airport", getattr(row, "origin_zone", "")) or "")


def _destination_value(row: object) -> str:
    return str(getattr(row, "destination_airport", getattr(row, "destination_zone", "")) or "")


def _variable_endpoint(row: object, fixed_endpoint_name: str) -> str:
    if fixed_endpoint_name == "origin":
        return _destination_value(row)
    return _origin_value(row)


def _counterparty(row: object) -> tuple[str, str]:
    agent = getattr(row, "agent", None)
    carrier = getattr(row, "carrier", None)
    if getattr(row, "agent_id", None) and agent:
        return ("agent", agent.code)
    if getattr(row, "carrier_id", None) and carrier:
        return ("carrier", carrier.code)
    return ("none", "")


def _amount_signature(row: object) -> tuple[str, ...]:
    return (
        _decimal_value(getattr(row, "rate_per_kg", None)),
        _decimal_value(getattr(row, "rate_per_shipment", None)),
        _decimal_value(getattr(row, "amount", None)),
        str(getattr(row, "rate_type", "") or ""),
        _decimal_value(getattr(row, "min_charge", None)),
        _decimal_value(getattr(row, "max_charge", None)),
        _decimal_value(getattr(row, "percent_rate", None)),
        str(getattr(row, "weight_breaks", None) or ""),
    )


def _decimal_value(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.normalize())
