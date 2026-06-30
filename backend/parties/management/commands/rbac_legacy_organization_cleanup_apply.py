import json

from django.core.management.base import BaseCommand
from django.db import transaction

from .rbac_legacy_organization_cleanup_plan import apply_cleanup


class Command(BaseCommand):
    help = "Guarded apply for legacy Organization cleanup. Dry-run by default."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write safe planned changes. Defaults to dry-run.")
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        with transaction.atomic():
            report = apply_cleanup(apply=options["apply"])
            if not options["apply"]:
                transaction.set_rollback(True)
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def write_text(stdout, report):
    summary = report["summary"]
    stdout.write("RBAC legacy organization cleanup apply")
    stdout.write("======================================")
    stdout.write(f"Mode: {report['mode']}")
    stdout.write(
        f"Summary: planned={summary['planned']} applied={summary['applied']} "
        f"unchanged={summary['unchanged']} blocked={summary['blocked']}"
    )
