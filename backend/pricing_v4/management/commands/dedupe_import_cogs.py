from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from pricing_v4.models import ImportCOGS


class Command(BaseCommand):
    help = (
        "Deduplicate ImportCOGS rows using the operational key "
        "(product_code, origin_airport, destination_airport, agent/carrier, currency, valid_from). "
        "Keeps the most recently updated row in each duplicate group."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Delete duplicate rows. Without this flag the command runs in dry-run mode.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        duplicate_groups = list(
            ImportCOGS.objects.values(
                "product_code_id",
                "origin_airport",
                "destination_airport",
                "agent_id",
                "carrier_id",
                "currency",
                "valid_from",
            )
            .annotate(row_count=Count("id"))
            .filter(row_count__gt=1)
            .order_by("origin_airport", "destination_airport", "product_code_id")
        )

        if not duplicate_groups:
            self.stdout.write(self.style.SUCCESS("No ImportCOGS duplicates found."))
            return

        rows_to_delete = []
        self.stdout.write(
            f"Found {len(duplicate_groups)} duplicate ImportCOGS group(s). "
            f"{'Applying cleanup.' if apply_changes else 'Dry run only.'}"
        )

        for group in duplicate_groups:
            matches = list(
                ImportCOGS.objects.filter(
                    product_code_id=group["product_code_id"],
                    origin_airport=group["origin_airport"],
                    destination_airport=group["destination_airport"],
                    agent_id=group["agent_id"],
                    carrier_id=group["carrier_id"],
                    currency=group["currency"],
                    valid_from=group["valid_from"],
                )
                .select_related("product_code", "agent", "carrier")
                .order_by("-updated_at", "-created_at", "id")
            )
            keeper = matches[0]
            duplicates = matches[1:]
            rows_to_delete.extend(row.id for row in duplicates)

            self.stdout.write(
                "KEEP "
                f"{keeper.id}: {keeper.product_code.code} "
                f"{keeper.origin_airport}->{keeper.destination_airport} "
                f"{keeper.currency} {keeper.valid_from} "
                f"(updated {keeper.updated_at:%Y-%m-%d %H:%M:%S})"
            )
            for row in duplicates:
                self.stdout.write(
                    "DROP "
                    f"{row.id}: {row.product_code.code} "
                    f"{row.origin_airport}->{row.destination_airport} "
                    f"{row.currency} {row.valid_from} "
                    f"(updated {row.updated_at:%Y-%m-%d %H:%M:%S})"
                )

        if not apply_changes:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run complete. {len(rows_to_delete)} row(s) would be deleted. Re-run with --apply to commit."
                )
            )
            return

        with transaction.atomic():
            deleted_count, _ = ImportCOGS.objects.filter(id__in=rows_to_delete).delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} duplicate ImportCOGS row(s)."))
