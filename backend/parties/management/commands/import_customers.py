from contextlib import nullcontext

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Currency
from parties.models import Company, CustomerCommercialProfile

from ._seed_utils import (
    ensure_required_columns,
    is_nullish,
    load_csv_rows,
    parse_bool,
    parse_decimal,
    parse_optional_uuid,
    parse_payment_term,
)


class Command(BaseCommand):
    help = (
        "Import customer companies and commercial profiles from CSV. "
        "Idempotent upsert by company_uuid (if provided) else company_name."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to customers CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report changes without writing to the database",
        )

    def _process_row(self, row_number: int, row: dict, dry_run: bool, counts: dict):
        company_name = row.get("company_name", "").strip()
        if not company_name:
            raise CommandError(f"Row {row_number}: company_name is required")

        company_uuid = parse_optional_uuid(row.get("company_uuid", ""), "company_uuid", row_number)
        company = None
        if company_uuid:
            company = Company.objects.filter(id=company_uuid).first()
        if not company:
            company = Company.objects.filter(name__iexact=company_name).first()

        is_agent = parse_bool(row.get("is_agent", ""), "is_agent", row_number)
        is_carrier = parse_bool(row.get("is_carrier", ""), "is_carrier", row_number)
        company_type = row.get("company_type", "").strip().upper() if not is_nullish(row.get("company_type", "")) else None

        created = False
        if not company:
            company = Company(
                name=company_name,
                is_customer=True,
                is_agent=bool(is_agent) if is_agent is not None else False,
                is_carrier=bool(is_carrier) if is_carrier is not None else False,
                company_type=company_type or "CUSTOMER",
                tax_id=row.get("tax_id", "").strip(),
            )
            created = True
            if not dry_run:
                company.save()
            counts["company_created"] += 1
        else:
            changed = False
            if company.name != company_name:
                company.name = company_name
                changed = True
            if not company.is_customer:
                company.is_customer = True
                changed = True
            if is_agent is not None and company.is_agent != is_agent:
                company.is_agent = is_agent
                changed = True
            if is_carrier is not None and company.is_carrier != is_carrier:
                company.is_carrier = is_carrier
                changed = True
            if company_type and company.company_type != company_type:
                company.company_type = company_type
                changed = True
            tax_id = row.get("tax_id", "").strip()
            if tax_id and company.tax_id != tax_id:
                company.tax_id = tax_id
                changed = True

            if changed:
                if not dry_run:
                    company.save()
                counts["company_updated"] += 1
            else:
                counts["company_unchanged"] += 1

        self._upsert_profile(row_number, row, company, created, dry_run, counts)

    def _upsert_profile(self, row_number: int, row: dict, company: Company, company_created: bool, dry_run: bool, counts: dict):
        has_profile_fields = any(
            not is_nullish(row.get(key, ""))
            for key in [
                "preferred_quote_currency",
                "payment_term_default",
                "default_margin_percent",
                "min_margin_percent",
            ]
        )
        if not has_profile_fields and not company_created:
            return

        currency_code = row.get("preferred_quote_currency", "").strip().upper()
        preferred_currency = None
        if currency_code:
            preferred_currency = Currency.objects.filter(code=currency_code).first()
            if not preferred_currency:
                raise CommandError(
                    f"Row {row_number}: preferred_quote_currency '{currency_code}' does not exist in core_currency"
                )

        payment_term = parse_payment_term(row.get("payment_term_default", ""), row_number)
        default_margin = parse_decimal(row.get("default_margin_percent", ""), "default_margin_percent", row_number)
        min_margin = parse_decimal(row.get("min_margin_percent", ""), "min_margin_percent", row_number)

        profile = getattr(company, "commercial_profile", None)
        profile_created = False
        if not profile:
            profile = CustomerCommercialProfile(company=company)
            profile_created = True

        changed = False
        if not is_nullish(row.get("preferred_quote_currency", "")):
            if profile.preferred_quote_currency_id != (
                preferred_currency.code if preferred_currency else None
            ):
                profile.preferred_quote_currency = preferred_currency
                changed = True
        if not is_nullish(row.get("payment_term_default", "")):
            if profile.payment_term_default != payment_term:
                profile.payment_term_default = payment_term
                changed = True
        if not is_nullish(row.get("default_margin_percent", "")):
            if profile.default_margin_percent != default_margin:
                profile.default_margin_percent = default_margin
                changed = True
        if not is_nullish(row.get("min_margin_percent", "")):
            if profile.min_margin_percent != min_margin:
                profile.min_margin_percent = min_margin
                changed = True

        if profile_created:
            counts["profile_created"] += 1
            if not dry_run:
                profile.save()
        elif changed:
            counts["profile_updated"] += 1
            if not dry_run:
                profile.save()

    def handle(self, *args, **options):
        csv_path = options["file"]
        dry_run = options["dry_run"]

        headers, rows = load_csv_rows(csv_path)
        ensure_required_columns(headers, ["company_name"], "Customers CSV")

        counts = {
            "company_created": 0,
            "company_updated": 0,
            "company_unchanged": 0,
            "profile_created": 0,
            "profile_updated": 0,
        }

        try:
            context = nullcontext() if dry_run else transaction.atomic()
            with context:
                for row_number, row in rows:
                    self._process_row(row_number, row, dry_run, counts)
                if dry_run:
                    raise CommandError("Dry run complete")
        except CommandError as exc:
            if str(exc) == "Dry run complete":
                pass
            else:
                raise

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Customer import summary"))
        self.stdout.write(f"- Rows processed: {len(rows)}")
        self.stdout.write(f"- Companies created: {counts['company_created']}")
        self.stdout.write(f"- Companies updated: {counts['company_updated']}")
        self.stdout.write(f"- Companies unchanged: {counts['company_unchanged']}")
        self.stdout.write(f"- Profiles created: {counts['profile_created']}")
        self.stdout.write(f"- Profiles updated: {counts['profile_updated']}")
