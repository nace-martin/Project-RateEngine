from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from pricing_v4.contracts.charge_context import ProductCodeResolutionStatus
from pricing_v4.models import ChargeAlias
from pricing_v4.services.leg_aware_product_code_resolver import LegAwareProductCodeResolver


class Command(BaseCommand):
    help = "Read-only Phase 16D diagnostic for leg-aware ProductCode context resolution."

    def add_arguments(self, parser):
        parser.add_argument(
            "--context",
            action="append",
            default=[],
            help="JSON ChargeContext payload. May be supplied multiple times.",
        )
        parser.add_argument(
            "--context-file",
            help="Path to a JSON file containing one context object or a list of context objects.",
        )
        parser.add_argument("--format", choices=["json", "text"], default="text")

    def handle(self, *args, **options):
        contexts = self._load_contexts(options)
        if not contexts:
            raise CommandError("Provide at least one --context or --context-file payload.")

        resolver = LegAwareProductCodeResolver()
        before = self._table_counts()
        evaluated_alias_count = ChargeAlias.objects.filter(
            is_active=True,
            review_status=ChargeAlias.ReviewStatus.APPROVED,
            canonical_charge_type__isnull=False,
        ).count()

        results: list[dict[str, Any]] = []
        summary = {
            ProductCodeResolutionStatus.ASSIGNED.value: 0,
            ProductCodeResolutionStatus.NEEDS_CLARIFICATION.value: 0,
            ProductCodeResolutionStatus.NOT_FOUND.value: 0,
            ProductCodeResolutionStatus.CONTEXT_INCOMPLETE.value: 0,
            ProductCodeResolutionStatus.REJECTED.value: 0,
        }

        for idx, context in enumerate(contexts, start=1):
            result = resolver.resolve(context).to_dict()
            summary[result["status"]] += 1
            results.append({"context_index": idx, "result": result})

        after = self._table_counts()
        writes_detected = before != after
        payload = {
            "mode": "read_only",
            "contexts_evaluated": len(contexts),
            "reviewed_aliases_with_canonical_type": evaluated_alias_count,
            "summary": summary,
            "writes_detected": writes_detected,
            "results": results,
        }

        if options["format"] == "json":
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write("Leg-aware ProductCode diagnostic (read-only)")
            self.stdout.write(f"Contexts evaluated: {payload['contexts_evaluated']}")
            self.stdout.write(f"Reviewed aliases with canonical type: {evaluated_alias_count}")
            self.stdout.write(f"Summary: {summary}")
            self.stdout.write(f"Writes detected: {writes_detected}")

        if writes_detected:
            raise CommandError("Diagnostic command detected database writes; this must remain read-only.")

    def _load_contexts(self, options) -> list[dict[str, Any]]:
        contexts: list[dict[str, Any]] = []
        for raw in options.get("context") or []:
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CommandError(f"Invalid --context JSON: {exc}") from exc
            contexts.append(loaded)

        context_file = options.get("context_file")
        if context_file:
            try:
                loaded = json.loads(Path(context_file).read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise CommandError(f"Invalid --context-file: {exc}") from exc
            if isinstance(loaded, list):
                contexts.extend(loaded)
            elif isinstance(loaded, dict):
                contexts.append(loaded)
            else:
                raise CommandError("--context-file must contain a JSON object or list of objects.")
        return contexts

    def _table_counts(self) -> dict[str, int]:
        tables = [
            "product_codes",
            "product_code_context_rules",
            "charge_aliases",
            "canonical_charge_types",
            "quotes",
            "spe_charge_lines",
        ]
        existing_tables = set(connection.introspection.table_names())
        counts: dict[str, int] = {}
        with connection.cursor() as cursor:
            for table in tables:
                if table not in existing_tables:
                    counts[table] = 0
                    continue
                cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                counts[table] = int(cursor.fetchone()[0])
        return counts
