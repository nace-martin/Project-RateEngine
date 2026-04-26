from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.models import ChargeAlias
from pricing_v4.services.charge_alias_candidates import collect_manual_resolution_candidates


class Command(BaseCommand):
    help = "Create inactive ChargeAlias candidates from repeated manual SPOT resolutions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report candidate aliases without writing ChargeAlias rows.",
        )
        parser.add_argument(
            "--min-occurrences",
            type=int,
            default=2,
            help="Minimum repeated manual resolutions required before creating a candidate.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        min_occurrences = max(int(options["min_occurrences"] or 1), 1)
        candidates, unstable_groups = collect_manual_resolution_candidates(
            min_occurrences=min_occurrences
        )

        summary = {
            "created": 0,
            "skipped_existing_equivalent": 0,
            "skipped_existing_candidate": 0,
            "skipped_conflict": 0,
            "unstable_groups": len(unstable_groups),
        }

        self.stdout.write("=" * 72)
        self.stdout.write("Creating ChargeAlias candidates from manual SPOT resolutions")
        self.stdout.write("=" * 72)
        self.stdout.write(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
        self.stdout.write(f"Minimum occurrences: {min_occurrences}")
        self.stdout.write(f"Stable candidate groups: {len(candidates)}")
        self.stdout.write(f"Unstable mixed-target groups skipped: {len(unstable_groups)}")
        self.stdout.write("")

        with transaction.atomic():
            for candidate in candidates:
                self._process_candidate(candidate, summary, dry_run)
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"[{'DRY RUN' if dry_run else 'APPLIED'}] ChargeAlias candidate summary"
            )
        )
        self.stdout.write(f"- Created: {summary['created']}")
        self.stdout.write(
            f"- Skipped (approved/active equivalent exists): {summary['skipped_existing_equivalent']}"
        )
        self.stdout.write(
            f"- Skipped (candidate/duplicate already exists): {summary['skipped_existing_candidate']}"
        )
        self.stdout.write(f"- Skipped (conflicting alias scope exists): {summary['skipped_conflict']}")
        self.stdout.write(f"- Unstable mixed-target groups: {summary['unstable_groups']}")

    def _process_candidate(self, candidate, summary, dry_run):
        base_qs = ChargeAlias.objects.filter(
            normalized_alias_text=candidate.normalized_alias_text,
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=candidate.mode_scope,
            direction_scope=candidate.direction_scope,
        )
        equivalent_qs = base_qs.filter(product_code=candidate.product_code)
        if equivalent_qs.filter(review_status=ChargeAlias.ReviewStatus.APPROVED).exists() or equivalent_qs.filter(
            is_active=True
        ).exists():
            summary["skipped_existing_equivalent"] += 1
            self.stdout.write(
                f"  Skip approved/active equivalent: {candidate.alias_text} -> {candidate.product_code.code}"
            )
            return

        if equivalent_qs.exists():
            summary["skipped_existing_candidate"] += 1
            self.stdout.write(
                f"  Skip existing candidate/duplicate: {candidate.alias_text} -> {candidate.product_code.code}"
            )
            return

        conflict_qs = base_qs.exclude(product_code=candidate.product_code)
        if conflict_qs.exists():
            summary["skipped_conflict"] += 1
            self.stdout.write(
                self.style.WARNING(
                    f"  Skip conflicting scope: {candidate.alias_text} "
                    f"{candidate.mode_scope}/{candidate.direction_scope} existing targets="
                    f"{', '.join(conflict_qs.values_list('product_code__code', flat=True).distinct())}"
                )
            )
            return

        alias = ChargeAlias(
            alias_text=candidate.alias_text,
            normalized_alias_text=candidate.normalized_alias_text,
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=candidate.mode_scope,
            direction_scope=candidate.direction_scope,
            product_code=candidate.product_code,
            priority=100,
            is_active=False,
            alias_source=ChargeAlias.AliasSource.MANUAL_REVIEW,
            review_status=ChargeAlias.ReviewStatus.CANDIDATE,
            notes=self._build_notes(candidate),
        )
        alias.full_clean()
        summary["created"] += 1
        action = "Would create" if dry_run else "Created"
        if not dry_run:
            alias.save()
        self.stdout.write(f"  {action} candidate {candidate.alias_text} -> {candidate.product_code.code}")

    @staticmethod
    def _build_notes(candidate) -> str:
        origins = ", ".join(candidate.origin_countries) if candidate.origin_countries else "-"
        batches = ", ".join(candidate.source_batches) if candidate.source_batches else "-"
        examples = ", ".join(candidate.raw_examples) if candidate.raw_examples else candidate.alias_text
        return (
            "Generated from repeated manual SPOT resolutions. "
            f"Occurrences={candidate.occurrences}. "
            f"Origins={origins}. "
            f"Source batches={batches}. "
            f"Examples={examples}."
        )
