from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from parties.models import Company


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _text(value) -> str:
    return "" if value is None else str(value)


class Command(BaseCommand):
    help = (
        "Export customer companies and commercial profiles from the current database "
        "into the same CSV shape that import_customers expects."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Output path for customers CSV")
        parser.add_argument(
            "--company",
            action="append",
            default=[],
            help="Exact company name to include. Repeat for multiple companies.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include inactive companies in the export.",
        )

    def handle(self, *args, **options):
        output_path = Path(options["file"])
        queryset = self._build_queryset(
            company_names=options["company"],
            include_inactive=options["include_inactive"],
        )
        rows = [self._serialize(company) for company in queryset]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "company_uuid",
                    "company_name",
                    "tax_id",
                    "is_agent",
                    "is_carrier",
                    "company_type",
                    "preferred_quote_currency",
                    "payment_term_default",
                    "default_margin_percent",
                    "min_margin_percent",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS("Customer export complete"))
        self.stdout.write(f"- Rows exported: {len(rows)}")
        self.stdout.write(f"- Output file: {output_path}")

    def _build_queryset(self, *, company_names: list[str], include_inactive: bool):
        queryset = (
            Company.objects.filter(Q(is_customer=True) | Q(company_type="CUSTOMER"))
            .select_related("commercial_profile__preferred_quote_currency")
            .order_by("name")
        )
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        if company_names:
            normalized = [name.strip() for name in company_names if name.strip()]
            if not normalized:
                raise CommandError("At least one non-empty --company value is required when filtering by company.")
            query = Q()
            for name in normalized:
                query |= Q(name__iexact=name)
            queryset = queryset.filter(query)
        return queryset

    def _serialize(self, company: Company) -> dict[str, str]:
        profile = getattr(company, "commercial_profile", None)
        currency = getattr(getattr(profile, "preferred_quote_currency", None), "code", "")
        return {
            "company_uuid": str(company.id),
            "company_name": company.name,
            "tax_id": company.tax_id or "",
            "is_agent": _bool_text(bool(company.is_agent)),
            "is_carrier": _bool_text(bool(company.is_carrier)),
            "company_type": company.company_type or "",
            "preferred_quote_currency": currency or "",
            "payment_term_default": _text(getattr(profile, "payment_term_default", "")),
            "default_margin_percent": _text(getattr(profile, "default_margin_percent", "")),
            "min_margin_percent": _text(getattr(profile, "min_margin_percent", "")),
        }
