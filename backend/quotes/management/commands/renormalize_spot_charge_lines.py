from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from pricing_v4.models import ChargeAlias
from quotes.models import Quote
from quotes.services.charge_normalization import resolve_charge_alias
from quotes.spot_models import SPEChargeLineDB


FINALIZED_QUOTE_STATUSES = {
    Quote.Status.FINALIZED,
    Quote.Status.SENT,
    Quote.Status.ACCEPTED,
    Quote.Status.LOST,
    Quote.Status.EXPIRED,
}


class Command(BaseCommand):
    help = "Re-run deterministic normalization for existing unresolved SPE charge lines."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report changes without writing normalization fields.",
        )
        parser.add_argument(
            "--spe-id",
            help="Restrict renormalization to one SpotPricingEnvelopeDB id.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum number of eligible rows to scan.",
        )
        parser.add_argument(
            "--status",
            choices=SPEChargeLineDB.NormalizationStatus.values,
            default=SPEChargeLineDB.NormalizationStatus.UNMAPPED,
            help="Existing normalization_status to scan. Defaults to UNMAPPED.",
        )
        parser.add_argument(
            "--include-ambiguous",
            action="store_true",
            help="Also scan existing AMBIGUOUS rows.",
        )
        parser.add_argument(
            "--allow-finalized-quotes",
            action="store_true",
            help="Allow updates to SPE lines linked to finalized/sent/terminal quotes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options.get("limit")
        if limit is not None and limit < 1:
            raise CommandError("--limit must be greater than zero.")

        statuses = {options["status"]}
        if options["include_ambiguous"]:
            statuses.add(SPEChargeLineDB.NormalizationStatus.AMBIGUOUS)

        summary = {
            "scanned": 0,
            "updated": 0,
            "would_update": 0,
            "still_unmapped": 0,
            "ambiguous": 0,
            "skipped_manual": 0,
            "skipped_finalized": 0,
            "errors": 0,
        }

        queryset = self._build_queryset(
            spe_id=options.get("spe_id"),
            statuses=statuses,
            limit=limit,
        )

        self.stdout.write("=" * 72)
        self.stdout.write("Renormalizing SPE charge lines")
        self.stdout.write("=" * 72)
        self.stdout.write(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
        self.stdout.write(f"Statuses: {', '.join(sorted(statuses))}")
        if options.get("spe_id"):
            self.stdout.write(f"SPE: {options['spe_id']}")
        if limit:
            self.stdout.write(f"Limit: {limit}")
        self.stdout.write("")

        with transaction.atomic():
            for line in queryset:
                self._process_line(
                    line,
                    dry_run=dry_run,
                    allow_finalized_quotes=options["allow_finalized_quotes"],
                    summary=summary,
                )
            if dry_run:
                transaction.set_rollback(True)

        self._print_summary(summary, dry_run)

    def _build_queryset(self, *, spe_id: str | None, statuses: set[str], limit: int | None):
        queryset = (
            SPEChargeLineDB.objects.select_related(
                "envelope",
                "envelope__quote",
                "matched_alias",
                "resolved_product_code",
                "manual_resolved_product_code",
            )
            .filter(normalization_status__in=statuses)
            .order_by("entered_at", "id")
        )
        if spe_id:
            queryset = queryset.filter(envelope_id=spe_id)
        if limit:
            queryset = queryset[:limit]
        return queryset

    def _process_line(self, line: SPEChargeLineDB, *, dry_run: bool, allow_finalized_quotes: bool, summary: dict):
        summary["scanned"] += 1

        if line.manual_resolution_status or line.manual_resolved_product_code_id:
            summary["skipped_manual"] += 1
            self.stdout.write(f"  Skip manual resolution: {line.id}")
            return

        quote = getattr(line.envelope, "quote", None)
        if (
            quote is not None
            and quote.status in FINALIZED_QUOTE_STATUSES
            and not allow_finalized_quotes
        ):
            summary["skipped_finalized"] += 1
            self.stdout.write(f"  Skip finalized quote: {line.id} quote={quote.quote_number or quote.id}")
            return

        try:
            result = resolve_charge_alias(
                line.source_label or line.description,
                mode_scope=_mode_scope_for_context(line.envelope.shipment_context_json),
                direction_scope=_direction_scope_for_bucket(line.bucket),
            )
            changes = {
                "normalized_label": result.normalized_label,
                "normalization_status": result.normalization_status.value,
                "normalization_method": result.normalization_method.value,
                "matched_alias": result.resolved_charge_alias,
                "resolved_product_code": result.resolved_product_code,
            }
            changed_fields = [
                field_name
                for field_name, value in changes.items()
                if getattr(line, field_name) != value
            ]

            if result.normalization_status.value == SPEChargeLineDB.NormalizationStatus.UNMAPPED:
                summary["still_unmapped"] += 1
            if result.normalization_status.value == SPEChargeLineDB.NormalizationStatus.AMBIGUOUS:
                summary["ambiguous"] += 1

            if not changed_fields:
                self.stdout.write(f"  Reused {line.id}: {result.normalization_status.value}")
                return

            if dry_run:
                summary["would_update"] += 1
                self.stdout.write(
                    f"  Would update {line.id}: {line.normalization_status} -> {result.normalization_status.value}"
                )
                return

            for field_name, value in changes.items():
                setattr(line, field_name, value)
            line.save(update_fields=[*changes.keys()])
            summary["updated"] += 1
            self.stdout.write(f"  Updated {line.id}: {result.normalization_status.value}")
        except Exception as exc:
            summary["errors"] += 1
            self.stdout.write(self.style.ERROR(f"  Error {line.id}: {exc}"))

    def _print_summary(self, summary: dict, dry_run: bool):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"[{'DRY RUN' if dry_run else 'APPLIED'}] Renormalization summary"))
        self.stdout.write(f"- Scanned: {summary['scanned']}")
        self.stdout.write(f"- Would update: {summary['would_update']}")
        self.stdout.write(f"- Updated: {summary['updated']}")
        self.stdout.write(f"- Still unmapped: {summary['still_unmapped']}")
        self.stdout.write(f"- Ambiguous: {summary['ambiguous']}")
        self.stdout.write(f"- Skipped due to manual resolution: {summary['skipped_manual']}")
        self.stdout.write(f"- Skipped finalized quotes: {summary['skipped_finalized']}")
        self.stdout.write(f"- Errors: {summary['errors']}")


def _mode_scope_for_context(shipment_context: dict | None) -> str:
    shipment_context = shipment_context or {}
    origin_country = str(shipment_context.get("origin_country") or "").upper()
    destination_country = str(shipment_context.get("destination_country") or "").upper()
    if origin_country == "PG" and destination_country == "PG":
        return ChargeAlias.ModeScope.DOMESTIC
    if origin_country == "PG":
        return ChargeAlias.ModeScope.EXPORT
    if destination_country == "PG":
        return ChargeAlias.ModeScope.IMPORT
    return ChargeAlias.ModeScope.ANY


def _direction_scope_for_bucket(bucket: str | None) -> str:
    if bucket == SPEChargeLineDB.Bucket.ORIGIN_CHARGES:
        return ChargeAlias.DirectionScope.ORIGIN
    if bucket == SPEChargeLineDB.Bucket.DESTINATION_CHARGES:
        return ChargeAlias.DirectionScope.DESTINATION
    if bucket == SPEChargeLineDB.Bucket.AIRFREIGHT:
        return ChargeAlias.DirectionScope.MAIN
    return ChargeAlias.DirectionScope.ANY
