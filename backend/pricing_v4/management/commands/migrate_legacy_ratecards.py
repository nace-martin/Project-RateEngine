"""Django management command: migrate_legacy_ratecards.

Audits, classifies, and evaluates legacy V3 ratecards (PartnerRateCard,
PartnerRateLane, PartnerRate) against clean Rate Matrix standards.

Usage:
  python backend/manage.py migrate_legacy_ratecards
  python backend/manage.py migrate_legacy_ratecards --json
  python backend/manage.py migrate_legacy_ratecards --card-id 15
"""

import json

from django.core.management.base import BaseCommand

from pricing_v4.services.ratecard_migration import RatecardMigrationService


class Command(BaseCommand):
    help = "Audit and classify legacy V3 ratecards against clean Rate Matrix standards (read-only audit)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--card-id",
            type=int,
            default=None,
            help="Filter execution to a single legacy PartnerRateCard ID",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            default=False,
            help="Output machine-readable JSON summary",
        )
        parser.add_argument(
            "--audit-only",
            action="store_true",
            default=False,
            help="Explicit audit-only flag (default is always read-only audit)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Dry-run flag (default is always read-only audit)",
        )

    def handle(self, *args, **options):
        card_id = options.get("card_id")
        json_output = options.get("json", False)

        service = RatecardMigrationService()
        self.stdout.write("=== READ-ONLY AUDIT: Auditing legacy ratecards against clean Rate Matrix ===")
        report = service.audit_and_classify()

        if card_id:
            report.card_summaries = [c for c in report.card_summaries if c["card_id"] == card_id]

        if json_output:
            data = {
                "total_cards": report.total_cards,
                "total_lanes": report.total_lanes,
                "total_rates": report.total_rates,
                "classification_counts": report.classification_counts,
                "parity_counts": report.parity_counts,
                "target_rows_created": report.target_rows_created,
                "blockers_count": len(report.blockers),
            }
            self.stdout.write(json.dumps(data, indent=2))
            return

        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("LEGACY RATECARD INVENTORY & CLASSIFICATION SUMMARY")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Total Legacy Cards: {report.total_cards}")
        self.stdout.write(f"Total Legacy Lanes: {report.total_lanes}")
        self.stdout.write(f"Total Legacy Rates: {report.total_rates}")

        self.stdout.write("\nClassification Breakdown:")
        for cls_name, count in sorted(report.classification_counts.items()):
            self.stdout.write(f"  - {cls_name:20s}: {count:4d} rates")

        self.stdout.write("\nParity Proof Counts:")
        for status, count in sorted(report.parity_counts.items()):
            self.stdout.write(f"  - {status:20s}: {count:4d} rates")

        self.stdout.write("\nTarget Clean Rate Matrix Rows Created:")
        for model_name, count in report.target_rows_created.items():
            self.stdout.write(f"  - {model_name:20s}: {count:4d} rows")

        self.stdout.write("\nCard-by-Card Audit Breakdown:")
        for c in report.card_summaries:
            self.stdout.write(
                f"\n  [Card {c['card_id']}] {c['card_name']}\n"
                f"    Type: {c['rate_type']} | CCY: {c['currency_code']} | "
                f"Lanes: {c['lanes_count']} | Rates: {c['rates_count']} | "
                f"Classification: {c['classification']}"
            )
            if c["blockers"]:
                for b in c["blockers"]:
                    self.stdout.write(f"      [BLOCKER] {b}")

        self.stdout.write("\nAudit completed. Zero target Rate Matrix rows created.")
