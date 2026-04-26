from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from django.core.management.base import BaseCommand

from pricing_v4.models import ChargeAlias
from quotes.spot_models import SPEChargeLineDB


@dataclass
class LabelRollup:
    count: int = 0
    raw_labels: Counter[str] = field(default_factory=Counter)
    source_kinds: Counter[str] = field(default_factory=Counter)
    origin_countries: Counter[str] = field(default_factory=Counter)
    batch_labels: Counter[str] = field(default_factory=Counter)
    product_codes: Counter[str] = field(default_factory=Counter)

    def record(
        self,
        *,
        raw_label: str,
        source_kind: str,
        origin_country: str,
        batch_label: str,
        product_code: str | None = None,
    ) -> None:
        self.count += 1
        if raw_label:
            self.raw_labels[raw_label] += 1
        if source_kind:
            self.source_kinds[source_kind] += 1
        if origin_country:
            self.origin_countries[origin_country] += 1
        if batch_label:
            self.batch_labels[batch_label] += 1
        if product_code:
            self.product_codes[product_code] += 1


class Command(BaseCommand):
    help = "Summarize recurring unmapped and manually resolved SPOT charge labels for ChargeAlias review."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Maximum rows to show per summary section.",
        )
        parser.add_argument(
            "--min-occurrences",
            type=int,
            default=2,
            help="Minimum repeated manual mappings to surface as promotion candidates.",
        )

    def handle(self, *args, **options):
        limit = max(options["limit"], 1)
        min_occurrences = max(options["min_occurrences"], 1)

        unmapped: dict[tuple[str, str, str], LabelRollup] = {}
        manual_labels: dict[tuple[str, str, str], LabelRollup] = {}
        manual_mappings: dict[tuple[str, str, str, str], LabelRollup] = {}

        lines = (
            SPEChargeLineDB.objects.select_related(
                "envelope",
                "source_batch",
                "manual_resolved_product_code",
            )
            .order_by("entered_at")
        )

        for line in lines.iterator():
            normalized_label = str(line.normalized_label or "").strip()
            if not normalized_label:
                normalized_label = ChargeAlias.normalize_alias_text_value(
                    line.source_label or line.description
                )
            if not normalized_label:
                continue

            mode_scope = _infer_mode_scope(line)
            direction_scope = _direction_scope_for_bucket(line.bucket)
            raw_label = str(line.source_label or line.description or "").strip()
            source_kind = getattr(line.source_batch, "source_kind", "") or "UNKNOWN"
            batch_label = (
                getattr(line.source_batch, "label", "")
                or getattr(line.source_batch, "source_reference", "")
                or line.source_reference
            )
            origin_country = str(
                getattr(line.envelope, "shipment_context_json", {}).get("origin_country") or ""
            ).upper()

            if line.normalization_status == SPEChargeLineDB.NormalizationStatus.UNMAPPED:
                unmapped.setdefault(
                    (mode_scope, direction_scope, normalized_label),
                    LabelRollup(),
                ).record(
                    raw_label=raw_label,
                    source_kind=source_kind,
                    origin_country=origin_country,
                    batch_label=batch_label,
                )

            if (
                line.manual_resolution_status == SPEChargeLineDB.ManualResolutionStatus.RESOLVED
                and line.manual_resolved_product_code_id
            ):
                product_code = line.manual_resolved_product_code.code
                manual_labels.setdefault(
                    (mode_scope, direction_scope, normalized_label),
                    LabelRollup(),
                ).record(
                    raw_label=raw_label,
                    source_kind=source_kind,
                    origin_country=origin_country,
                    batch_label=batch_label,
                    product_code=product_code,
                )
                manual_mappings.setdefault(
                    (mode_scope, direction_scope, normalized_label, product_code),
                    LabelRollup(),
                ).record(
                    raw_label=raw_label,
                    source_kind=source_kind,
                    origin_country=origin_country,
                    batch_label=batch_label,
                    product_code=product_code,
                )

        self.stdout.write("=" * 72)
        self.stdout.write("Charge Alias Activity Summary")
        self.stdout.write("=" * 72)
        self.stdout.write(f"SPOT lines scanned: {lines.count()}")
        self.stdout.write("")

        self._print_rollup_section(
            title="Top recurring unmapped labels",
            rows=sorted(unmapped.items(), key=lambda item: (-item[1].count, item[0])),
            limit=limit,
            render_row=_render_unmapped_row,
        )
        self._print_rollup_section(
            title="Top recurring manually resolved labels",
            rows=sorted(manual_labels.items(), key=lambda item: (-item[1].count, item[0])),
            limit=limit,
            render_row=_render_manual_label_row,
        )

        candidate_rows = []
        for key, rollup in manual_mappings.items():
            mode_scope, direction_scope, normalized_label, product_code = key
            if rollup.count < min_occurrences:
                continue
            if _has_active_exact_alias(
                normalized_label=normalized_label,
                mode_scope=mode_scope,
                direction_scope=direction_scope,
                product_code=product_code,
            ):
                continue
            candidate_rows.append((key, rollup))

        self._print_rollup_section(
            title="Promotion candidates from repeated manual resolutions",
            rows=sorted(candidate_rows, key=lambda item: (-item[1].count, item[0])),
            limit=limit,
            render_row=_render_candidate_row,
        )

        self.stdout.write("")
        self.stdout.write(
            "Review flow: leave risky candidates inactive, create or edit aliases in Django admin, "
            "set review_status=APPROVED only after human review, then activate."
        )

    def _print_rollup_section(self, *, title, rows, limit, render_row):
        self.stdout.write(title)
        if not rows:
            self.stdout.write("  (none)")
            self.stdout.write("")
            return

        for key, rollup in rows[:limit]:
            self.stdout.write(f"  - {render_row(key, rollup)}")
        self.stdout.write("")


def _infer_mode_scope(line: SPEChargeLineDB) -> str:
    shipment_context = getattr(line.envelope, "shipment_context_json", {}) or {}
    origin_country = str(shipment_context.get("origin_country") or "").upper()
    destination_country = str(shipment_context.get("destination_country") or "").upper()
    if origin_country == "PG" and destination_country == "PG":
        return ChargeAlias.ModeScope.DOMESTIC
    if origin_country == "PG":
        return ChargeAlias.ModeScope.EXPORT
    return ChargeAlias.ModeScope.IMPORT


def _direction_scope_for_bucket(bucket: str) -> str:
    if bucket == SPEChargeLineDB.Bucket.ORIGIN_CHARGES:
        return ChargeAlias.DirectionScope.ORIGIN
    if bucket == SPEChargeLineDB.Bucket.DESTINATION_CHARGES:
        return ChargeAlias.DirectionScope.DESTINATION
    return ChargeAlias.DirectionScope.MAIN


def _has_active_exact_alias(*, normalized_label: str, mode_scope: str, direction_scope: str, product_code: str) -> bool:
    return ChargeAlias.objects.filter(
        is_active=True,
        review_status=ChargeAlias.ReviewStatus.APPROVED,
        match_type=ChargeAlias.MatchType.EXACT,
        normalized_alias_text=normalized_label,
        mode_scope__in=[ChargeAlias.ModeScope.ANY, mode_scope],
        direction_scope__in=[ChargeAlias.DirectionScope.ANY, direction_scope],
        product_code__code=product_code,
    ).exists()


def _render_unmapped_row(key: tuple[str, str, str], rollup: LabelRollup) -> str:
    mode_scope, direction_scope, normalized_label = key
    return (
        f"{rollup.count}x | {mode_scope}/{direction_scope} | '{normalized_label}' | "
        f"examples={_top_values(rollup.raw_labels)} | origins={_top_values(rollup.origin_countries)} | "
        f"sources={_top_values(rollup.source_kinds)}"
    )


def _render_manual_label_row(key: tuple[str, str, str], rollup: LabelRollup) -> str:
    mode_scope, direction_scope, normalized_label = key
    return (
        f"{rollup.count}x | {mode_scope}/{direction_scope} | '{normalized_label}' | "
        f"targets={_top_values(rollup.product_codes)} | examples={_top_values(rollup.raw_labels)} | "
        f"origins={_top_values(rollup.origin_countries)}"
    )


def _render_candidate_row(key: tuple[str, str, str, str], rollup: LabelRollup) -> str:
    mode_scope, direction_scope, normalized_label, product_code = key
    return (
        f"{rollup.count}x | EXACT '{normalized_label}' | {mode_scope}/{direction_scope} -> {product_code} | "
        f"examples={_top_values(rollup.raw_labels)} | origins={_top_values(rollup.origin_countries)} | "
        f"source_batches={_top_values(rollup.batch_labels)}"
    )


def _top_values(counter: Counter[str], *, limit: int = 2) -> str:
    if not counter:
        return "-"
    return ", ".join(value for value, _ in counter.most_common(limit))
