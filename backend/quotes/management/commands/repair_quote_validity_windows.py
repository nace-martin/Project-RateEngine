from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from quotes.models import Quote


class Command(BaseCommand):
    help = (
        "Normalize quote valid_until windows: finalized/sent/terminal quotes "
        "to finalized(or created)+QUOTE_VALIDITY_DAYS (default 7), and clear "
        "valid_until on DRAFT/INCOMPLETE quotes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without updating records.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        validity_days = self._get_validity_days()

        finalized_like_statuses = [
            Quote.Status.FINALIZED,
            Quote.Status.SENT,
            Quote.Status.ACCEPTED,
            Quote.Status.LOST,
            Quote.Status.EXPIRED,
        ]

        finalized_like = list(
            Quote.objects.filter(status__in=finalized_like_statuses).only(
                "id",
                "quote_number",
                "status",
                "created_at",
                "finalized_at",
                "valid_until",
            )
        )
        drafts_with_expiry = list(
            Quote.objects.filter(
                status__in=[Quote.Status.DRAFT, Quote.Status.INCOMPLETE]
            )
            .exclude(valid_until__isnull=True)
            .only("id", "quote_number", "status", "valid_until")
        )

        updates = []
        for quote in finalized_like:
            base_date = (quote.finalized_at or quote.created_at).date()
            expected_valid_until = base_date + timedelta(days=validity_days)
            if quote.valid_until != expected_valid_until:
                quote.valid_until = expected_valid_until
                updates.append(quote)

        for quote in drafts_with_expiry:
            quote.valid_until = None
            updates.append(quote)

        self.stdout.write(
            f"Target validity window: {validity_days} day(s)"
        )
        self.stdout.write(
            f"Finalized/sent/terminal quotes scanned: {len(finalized_like)}"
        )
        self.stdout.write(
            f"Draft/incomplete quotes with expiry scanned: {len(drafts_with_expiry)}"
        )
        self.stdout.write(f"Quotes requiring update: {len(updates)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete. No changes applied."))
            return

        if not updates:
            self.stdout.write(self.style.SUCCESS("No quote validity repairs needed."))
            return

        with transaction.atomic():
            Quote.objects.bulk_update(updates, ["valid_until"])

        self.stdout.write(
            self.style.SUCCESS(f"Updated {len(updates)} quote(s) successfully.")
        )

    def _get_validity_days(self) -> int:
        try:
            configured = int(getattr(settings, "QUOTE_VALIDITY_DAYS", 7))
            return configured if configured > 0 else 7
        except (TypeError, ValueError):
            return 7
