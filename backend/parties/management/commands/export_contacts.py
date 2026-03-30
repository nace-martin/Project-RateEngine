from __future__ import annotations

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from parties.models import Contact


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


class Command(BaseCommand):
    help = (
        "Export customer contacts from the current database into the same CSV shape "
        "that import_contacts expects."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Output path for contacts CSV")
        parser.add_argument(
            "--company",
            action="append",
            default=[],
            help="Exact company name to include. Repeat for multiple companies.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include inactive contacts and contacts for inactive companies.",
        )

    def handle(self, *args, **options):
        output_path = Path(options["file"])
        queryset = self._build_queryset(
            company_names=options["company"],
            include_inactive=options["include_inactive"],
        )
        rows = [self._serialize(contact) for contact in queryset]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "company_uuid",
                    "company_name",
                    "email",
                    "first_name",
                    "last_name",
                    "full_name",
                    "phone",
                    "is_primary",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS("Contact export complete"))
        self.stdout.write(f"- Rows exported: {len(rows)}")
        self.stdout.write(f"- Output file: {output_path}")

    def _build_queryset(self, *, company_names: list[str], include_inactive: bool):
        queryset = (
            Contact.objects.select_related("company")
            .filter(Q(company__is_customer=True) | Q(company__company_type="CUSTOMER"))
            .order_by("company__name", "-is_primary", "last_name", "first_name", "email")
        )
        if not include_inactive:
            queryset = queryset.filter(is_active=True, company__is_active=True)
        if company_names:
            normalized = [name.strip() for name in company_names if name.strip()]
            if not normalized:
                raise CommandError("At least one non-empty --company value is required when filtering by company.")
            query = Q()
            for name in normalized:
                query |= Q(company__name__iexact=name)
            queryset = queryset.filter(query)
        return queryset

    def _serialize(self, contact: Contact) -> dict[str, str]:
        full_name = f"{contact.first_name} {contact.last_name}".strip()
        return {
            "company_uuid": str(contact.company_id),
            "company_name": contact.company.name,
            "email": (contact.email or "").lower(),
            "first_name": contact.first_name or "",
            "last_name": contact.last_name or "",
            "full_name": full_name,
            "phone": contact.phone or "",
            "is_primary": _bool_text(bool(contact.is_primary)),
        }
