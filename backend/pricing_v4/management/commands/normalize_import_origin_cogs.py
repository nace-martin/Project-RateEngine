from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from pricing_v4.models import ImportCOGS, LocalCOGSRate


TARGET_PRODUCT_CODES = (
    "IMP-SCREEN-ORIGIN",
    "IMP-CTO-ORIGIN",
    "IMP-DOC-ORIGIN",
    "IMP-AGENCY-ORIGIN",
    "IMP-AWB-ORIGIN",
    "IMP-PICKUP",
    "IMP-FSC-PICKUP",
)


class Command(BaseCommand):
    help = (
        "Move IMPORT origin-side AU LocalCOGSRate rows from destination-station storage "
        "into canonical lane-based ImportCOGS rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the normalized ImportCOGS rows and delete the source LocalCOGSRate rows.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))
        rows = list(
            LocalCOGSRate.objects.filter(
                direction="IMPORT",
                agent__country_code="AU",
                location__isnull=False,
                product_code__code__in=TARGET_PRODUCT_CODES,
            )
            .select_related("product_code", "agent", "carrier")
            .order_by("location", "agent__code", "product_code__code", "valid_from", "id")
        )

        if not rows:
            self.stdout.write("No AU import-origin LocalCOGSRate rows found.")
            return

        lane_map = self._build_lane_map(rows)
        grouped = defaultdict(list)
        for row in rows:
            grouped[(row.location, row.agent_id, row.carrier_id)].append(row)

        summary = {
            "rows_seen": len(rows),
            "rows_moved": 0,
            "rows_deleted": 0,
            "rows_skipped": 0,
            "import_rows_created": 0,
            "import_rows_updated": 0,
        }

        if apply_changes:
            with transaction.atomic():
                self._process_groups(grouped, lane_map, summary, apply_changes=True)
        else:
            self._process_groups(grouped, lane_map, summary, apply_changes=False)

        mode = "Applied" if apply_changes else "Dry run"
        self.stdout.write(
            f"{mode} complete. "
            f"seen={summary['rows_seen']} moved={summary['rows_moved']} deleted={summary['rows_deleted']} "
            f"skipped={summary['rows_skipped']} created={summary['import_rows_created']} "
            f"updated={summary['import_rows_updated']}"
        )

    def _build_lane_map(self, rows):
        lane_map = {}
        for row in rows:
            key = (row.location, row.agent_id, row.carrier_id)
            if key in lane_map:
                continue

            lane_qs = ImportCOGS.objects.filter(destination_airport=row.location)
            if row.agent_id:
                lane_qs = lane_qs.filter(agent_id=row.agent_id)
            elif row.carrier_id:
                lane_qs = lane_qs.filter(carrier_id=row.carrier_id)

            origins = sorted(
                {
                    str(origin or "").upper()
                    for origin in lane_qs.values_list("origin_airport", flat=True)
                    if str(origin or "").strip()
                }
            )
            lane_map[key] = origins
        return lane_map

    def _process_groups(self, grouped, lane_map, summary, *, apply_changes):
        for key, rows in grouped.items():
            destination, agent_id, carrier_id = key
            origins = lane_map.get(key) or []
            counterparty = rows[0].agent.code if rows[0].agent_id else rows[0].carrier.code

            if not origins:
                summary["rows_skipped"] += len(rows)
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipping {len(rows)} row(s) for {counterparty} @ {destination}: "
                        "no canonical import lanes found."
                    )
                )
                continue

            self.stdout.write(
                f"{'Applying' if apply_changes else 'Planning'} {len(rows)} row(s) for "
                f"{counterparty} @ {destination} across origins {', '.join(origins)}"
            )

            for row in rows:
                for origin in origins:
                    action = self._upsert_import_cogs(
                        row=row,
                        origin_airport=origin,
                        destination_airport=destination,
                        apply_changes=apply_changes,
                    )
                    if action == "create":
                        summary["import_rows_created"] += 1
                    elif action == "update":
                        summary["import_rows_updated"] += 1

                summary["rows_moved"] += 1
                if apply_changes:
                    row.delete()
                    summary["rows_deleted"] += 1

    def _upsert_import_cogs(self, *, row, origin_airport, destination_airport, apply_changes):
        payload = self._build_import_payload(row)
        matches = ImportCOGS.objects.filter(
            product_code=row.product_code,
            origin_airport=origin_airport,
            destination_airport=destination_airport,
            agent_id=row.agent_id,
            carrier_id=row.carrier_id,
            currency=row.currency,
            valid_from=row.valid_from,
            valid_until=row.valid_until,
        ).order_by("-valid_from", "-updated_at", "-id")

        if matches.exists():
            existing = matches.first()
            needs_update = any(getattr(existing, field) != value for field, value in payload.items())
            if apply_changes and needs_update:
                for field, value in payload.items():
                    setattr(existing, field, value)
                existing.save(update_fields=[*payload.keys(), "updated_at"])
            return "update" if needs_update else "noop"

        if apply_changes:
            ImportCOGS.objects.create(
                product_code=row.product_code,
                origin_airport=origin_airport,
                destination_airport=destination_airport,
                agent_id=row.agent_id,
                carrier_id=row.carrier_id,
                currency=row.currency,
                valid_from=row.valid_from,
                valid_until=row.valid_until,
                **payload,
            )
        return "create"

    @staticmethod
    def _build_import_payload(row):
        rate_type = str(row.rate_type or "").upper()
        payload = {
            "rate_per_kg": None,
            "rate_per_shipment": None,
            "min_charge": row.min_charge,
            "max_charge": row.max_charge,
            "is_additive": row.is_additive,
            "percent_rate": None,
            "weight_breaks": row.weight_breaks,
        }
        if rate_type == "PER_KG":
            payload["rate_per_kg"] = row.amount
            payload["rate_per_shipment"] = row.additive_flat_amount if row.is_additive else None
        elif rate_type == "PERCENT":
            payload["percent_rate"] = row.amount
        else:
            payload["rate_per_shipment"] = row.amount
        return payload
