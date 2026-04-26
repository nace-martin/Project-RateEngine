from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from pricing_v4.models import ChargeAlias, ProductCode
from quotes.spot_models import SPEChargeLineDB


@dataclass
class ManualResolutionGroup:
    mode_scope: str
    direction_scope: str
    normalized_label: str
    count: int = 0
    raw_labels: Counter[str] = field(default_factory=Counter)
    product_codes: Counter[str] = field(default_factory=Counter)
    origin_countries: Counter[str] = field(default_factory=Counter)
    source_batches: Counter[str] = field(default_factory=Counter)

    def record(
        self,
        *,
        raw_label: str,
        product_code: str,
        origin_country: str,
        source_batch: str,
    ) -> None:
        self.count += 1
        if raw_label:
            self.raw_labels[raw_label] += 1
        if product_code:
            self.product_codes[product_code] += 1
        if origin_country:
            self.origin_countries[origin_country] += 1
        if source_batch:
            self.source_batches[source_batch] += 1


@dataclass(frozen=True)
class ManualResolutionCandidate:
    alias_text: str
    normalized_alias_text: str
    mode_scope: str
    direction_scope: str
    product_code: ProductCode
    occurrences: int
    source_batches: tuple[str, ...]
    origin_countries: tuple[str, ...]
    raw_examples: tuple[str, ...]


def collect_manual_resolution_candidates(*, min_occurrences: int = 2) -> tuple[list[ManualResolutionCandidate], list[ManualResolutionGroup]]:
    min_occurrences = max(int(min_occurrences or 1), 1)
    groups: dict[tuple[str, str, str], ManualResolutionGroup] = {}

    lines = (
        SPEChargeLineDB.objects.select_related(
            "envelope",
            "source_batch",
            "manual_resolved_product_code",
        )
        .filter(
            manual_resolution_status=SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
            manual_resolved_product_code__isnull=False,
        )
        .order_by("entered_at")
    )

    for line in lines.iterator():
        mode_scope = infer_mode_scope(line)
        direction_scope = direction_scope_for_bucket(line.bucket)
        if mode_scope is None or direction_scope is None:
            continue

        normalized_label = str(line.normalized_label or "").strip()
        if not normalized_label:
            normalized_label = ChargeAlias.normalize_alias_text_value(
                line.source_label or line.description
            )
        if not normalized_label:
            continue

        key = (mode_scope, direction_scope, normalized_label)
        group = groups.setdefault(
            key,
            ManualResolutionGroup(
                mode_scope=mode_scope,
                direction_scope=direction_scope,
                normalized_label=normalized_label,
            ),
        )
        group.record(
            raw_label=str(line.source_label or line.description or "").strip(),
            product_code=line.manual_resolved_product_code.code,
            origin_country=str(
                getattr(line.envelope, "shipment_context_json", {}).get("origin_country") or ""
            ).upper(),
            source_batch=(
                getattr(line.source_batch, "label", "")
                or getattr(line.source_batch, "source_reference", "")
                or line.source_reference
            ),
        )

    candidates: list[ManualResolutionCandidate] = []
    unstable_groups: list[ManualResolutionGroup] = []

    for group in groups.values():
        if group.count < min_occurrences:
            continue
        if len(group.product_codes) != 1:
            unstable_groups.append(group)
            continue

        product_code_value = next(iter(group.product_codes))
        product_code = ProductCode.objects.get(code=product_code_value)
        alias_text = _preferred_alias_text(group)
        candidates.append(
            ManualResolutionCandidate(
                alias_text=alias_text,
                normalized_alias_text=group.normalized_label,
                mode_scope=group.mode_scope,
                direction_scope=group.direction_scope,
                product_code=product_code,
                occurrences=group.count,
                source_batches=tuple(value for value, _ in group.source_batches.most_common(3)),
                origin_countries=tuple(value for value, _ in group.origin_countries.most_common(3)),
                raw_examples=tuple(value for value, _ in group.raw_labels.most_common(3)),
            )
        )

    candidates.sort(
        key=lambda candidate: (
            -candidate.occurrences,
            candidate.mode_scope,
            candidate.direction_scope,
            candidate.normalized_alias_text,
            candidate.product_code.code,
        )
    )
    unstable_groups.sort(
        key=lambda group: (
            -group.count,
            group.mode_scope,
            group.direction_scope,
            group.normalized_label,
        )
    )
    return candidates, unstable_groups


def infer_mode_scope(line: SPEChargeLineDB) -> str | None:
    shipment_context = getattr(line.envelope, "shipment_context_json", {}) or {}
    origin_country = str(shipment_context.get("origin_country") or "").upper()
    destination_country = str(shipment_context.get("destination_country") or "").upper()
    if not origin_country or not destination_country:
        return None
    if origin_country == "PG" and destination_country == "PG":
        return ChargeAlias.ModeScope.DOMESTIC
    if origin_country == "PG":
        return ChargeAlias.ModeScope.EXPORT
    return ChargeAlias.ModeScope.IMPORT


def direction_scope_for_bucket(bucket: str) -> str | None:
    if bucket == SPEChargeLineDB.Bucket.ORIGIN_CHARGES:
        return ChargeAlias.DirectionScope.ORIGIN
    if bucket == SPEChargeLineDB.Bucket.DESTINATION_CHARGES:
        return ChargeAlias.DirectionScope.DESTINATION
    if bucket == SPEChargeLineDB.Bucket.AIRFREIGHT:
        return ChargeAlias.DirectionScope.MAIN
    return None


def _preferred_alias_text(group: ManualResolutionGroup) -> str:
    if group.raw_labels:
        return group.raw_labels.most_common(1)[0][0]
    return group.normalized_label
