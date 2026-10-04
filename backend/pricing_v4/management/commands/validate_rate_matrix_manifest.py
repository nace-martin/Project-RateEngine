"""Dry-run validation of a Rate Matrix ingestion manifest (Pilot Gate B3C)."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from pricing_v4.services.rate_matrix_manifest import validate_manifest_text


class Command(BaseCommand):
    help = (
        "Validate a strict JSON Rate Matrix manifest against the Pilot Gate B3A contract and "
        "the current database. Dry run only: this command never writes and has no apply mode."
    )

    def add_arguments(self, parser):
        parser.add_argument("manifest", help="Path to the JSON manifest file.")
        parser.add_argument(
            "--format",
            choices=("text", "json"),
            default="text",
            help="Report format (default: text).",
        )

    def handle(self, *args, **options):
        path = Path(options["manifest"])
        if not path.is_file():
            raise CommandError(f"Manifest file not found: {path}")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise CommandError(f"Manifest is not valid UTF-8: {exc}") from exc

        report = validate_manifest_text(text)
        self.stdout.write(report.render_json() if options["format"] == "json" else report.render_text())
        if not report.passed:
            raise CommandError(
                f"Rate Matrix manifest dry-run FAILED with {len(report.errors)} error(s). Nothing was written."
            )
