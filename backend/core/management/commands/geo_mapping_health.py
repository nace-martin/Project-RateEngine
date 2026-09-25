"""Read-only health report for the legacy-to-clean geography bridge."""

import json

from django.core.management.base import BaseCommand
from django.db.models import Count

from core.geo_mapping import GeoMappingError, resolve_geo_location
from core.geo_models import GeoLocationIdentifier
from core.models import Location


class Command(BaseCommand):
    help = "Report deterministic legacy Location to GeoLocation mapping health without writes."

    def handle(self, *args, **options):
        report = {
            "total_legacy_locations": 0,
            "mapped": 0,
            "unresolved": 0,
            "conflicts": 0,
            "identifier_counts_by_scheme": {
                scheme: 0 for scheme, _ in GeoLocationIdentifier.Scheme.choices
            },
            "unresolved_locations": [],
            "conflict_locations": [],
        }
        for row in Location.objects.select_related("airport__city", "city", "country").order_by("code", "id"):
            report["total_legacy_locations"] += 1
            try:
                resolve_geo_location(row)
            except GeoMappingError as exc:
                bucket = "conflicts" if exc.category == "conflict" else "unresolved"
                report[bucket] += 1
                detail_key = "conflict_locations" if bucket == "conflicts" else "unresolved_locations"
                report[detail_key].append(
                    {"id": str(row.id), "code": row.code, "reason": exc.reason}
                )
            else:
                report["mapped"] += 1
        for item in GeoLocationIdentifier.objects.values("scheme").annotate(count=Count("id")):
            report["identifier_counts_by_scheme"][item["scheme"]] = item["count"]
        self.stdout.write(json.dumps(report, sort_keys=True))
