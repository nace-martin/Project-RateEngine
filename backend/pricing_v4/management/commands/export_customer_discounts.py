from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from pricing_v4.models import CustomerDiscount


def _text(value) -> str:
    return "" if value is None else str(value)


class Command(BaseCommand):
    help = (
        "Export customer discounts from the current database into the same CSV shape "
        "that import_customer_discounts expects."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Output path for discounts CSV")
        parser.add_argument(
            "--company",
            action="append",
            default=[],
            help="Exact customer name to include. Repeat for multiple companies.",
        )
        parser.add_argument(
            "--active-on",
            help="Optional YYYY-MM-DD filter to export only discounts active on that date.",
        )

    def handle(self, *args, **options):
        output_path = Path(options["file"])
        active_on = self._parse_date(options.get("active_on"))
        queryset = self._build_queryset(company_names=options["company"], active_on=active_on)
        rows = [self._serialize(discount) for discount in queryset]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "customer_uuid",
                    "customer_name",
                    "product_code_id",
                    "product_code",
                    "discount_type",
                    "discount_value",
                    "currency",
                    "min_charge",
                    "max_charge",
                    "valid_from",
                    "valid_until",
                    "notes",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS("Customer discount export complete"))
        self.stdout.write(f"- Rows exported: {len(rows)}")
        self.stdout.write(f"- Output file: {output_path}")

    def _parse_date(self, value: str | None):
        raw = (value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise CommandError(f"Invalid --active-on date '{raw}'. Expected YYYY-MM-DD.") from exc

    def _build_queryset(self, *, company_names: list[str], active_on: date | None):
        queryset = (
            CustomerDiscount.objects.select_related("customer", "product_code")
            .filter(Q(customer__is_customer=True) | Q(customer__company_type="CUSTOMER"))
            .order_by("customer__name", "product_code__code")
        )
        if company_names:
            normalized = [name.strip() for name in company_names if name.strip()]
            if not normalized:
                raise CommandError("At least one non-empty --company value is required when filtering by company.")
            query = Q()
            for name in normalized:
                query |= Q(customer__name__iexact=name)
            queryset = queryset.filter(query)
        if active_on:
            queryset = queryset.filter(
                Q(valid_from__isnull=True) | Q(valid_from__lte=active_on),
                Q(valid_until__isnull=True) | Q(valid_until__gte=active_on),
            )
        return queryset

    def _serialize(self, discount: CustomerDiscount) -> dict[str, str]:
        return {
            "customer_uuid": str(discount.customer_id),
            "customer_name": discount.customer.name,
            "product_code_id": str(discount.product_code_id),
            "product_code": discount.product_code.code,
            "discount_type": discount.discount_type,
            "discount_value": _text(discount.discount_value),
            "currency": discount.currency or "PGK",
            "min_charge": _text(discount.min_charge),
            "max_charge": _text(discount.max_charge),
            "valid_from": _text(discount.valid_from),
            "valid_until": _text(discount.valid_until),
            "notes": discount.notes or "",
        }
