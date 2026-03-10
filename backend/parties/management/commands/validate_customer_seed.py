from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from core.models import Currency
from parties.models import Company

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
        "Validate customer/contact seed CSV files before import. "
        "Checks headers, required fields, enums, currencies, and cross-file references."
    )

    def add_arguments(self, parser):
        parser.add_argument("--customers", help="Path to customers CSV file")
        parser.add_argument("--contacts", help="Path to contacts CSV file")

    def handle(self, *args, **options):
        customers_path = options.get("customers")
        contacts_path = options.get("contacts")
        if not customers_path and not contacts_path:
            raise CommandError("Provide at least one file: --customers and/or --contacts")

        errors: list[str] = []
        customer_names_from_csv: set[str] = set()

        if customers_path:
            customer_names_from_csv.update(self._validate_customers(customers_path, errors))
        if contacts_path:
            self._validate_contacts(contacts_path, customer_names_from_csv, errors)

        if errors:
            self.stdout.write(self.style.ERROR(f"Validation failed with {len(errors)} issue(s):"))
            for issue in errors:
                self.stdout.write(self.style.ERROR(f"- {issue}"))
            raise CommandError("Customer seed validation failed")

        self.stdout.write(self.style.SUCCESS("Validation passed. No issues found."))

    def _validate_customers(self, csv_path: str, errors: list[str]) -> set[str]:
        headers, rows = load_csv_rows(csv_path)
        ensure_required_columns(headers, ["company_name"], "Customers CSV")

        names = [row.get("company_name", "").strip() for _, row in rows if row.get("company_name", "").strip()]
        dup_names = [name for name, count in Counter(name.lower() for name in names).items() if count > 1]
        for duplicate in dup_names:
            errors.append(f"Customers CSV has duplicate company_name: {duplicate}")

        known_currency_codes = set(Currency.objects.values_list("code", flat=True))

        for row_number, row in rows:
            company_name = row.get("company_name", "").strip()
            if not company_name:
                errors.append(f"Customers row {row_number}: company_name is required")
                continue
            try:
                parse_optional_uuid(row.get("company_uuid", ""), "company_uuid", row_number)
                parse_bool(row.get("is_agent", ""), "is_agent", row_number)
                parse_bool(row.get("is_carrier", ""), "is_carrier", row_number)
                parse_payment_term(row.get("payment_term_default", ""), row_number)
                parse_decimal(row.get("default_margin_percent", ""), "default_margin_percent", row_number)
                parse_decimal(row.get("min_margin_percent", ""), "min_margin_percent", row_number)
            except CommandError as exc:
                errors.append(str(exc))

            currency_code = row.get("preferred_quote_currency", "").strip().upper()
            if currency_code and currency_code not in known_currency_codes:
                errors.append(
                    f"Customers row {row_number}: preferred_quote_currency '{currency_code}' does not exist"
                )

        self.stdout.write(self.style.SUCCESS(f"Customers CSV checked: {len(rows)} row(s)"))
        return {name.lower() for name in names}

    def _validate_contacts(self, csv_path: str, csv_customer_names: set[str], errors: list[str]):
        headers, rows = load_csv_rows(csv_path)
        ensure_required_columns(headers, ["company_name", "email"], "Contacts CSV")

        emails = [row.get("email", "").strip().lower() for _, row in rows if row.get("email", "").strip()]
        dup_emails = [email for email, count in Counter(emails).items() if count > 1]
        for duplicate in dup_emails:
            errors.append(f"Contacts CSV has duplicate email: {duplicate}")

        db_customer_names = set(
            Company.objects.filter(is_customer=True).values_list("name", flat=True)
        )
        db_customer_names = {name.lower() for name in db_customer_names}

        for row_number, row in rows:
            company_name = row.get("company_name", "").strip()
            email = row.get("email", "").strip().lower()
            full_name = row.get("full_name", "").strip()
            first_name = row.get("first_name", "").strip()

            if not company_name:
                errors.append(f"Contacts row {row_number}: company_name is required")
            if not email:
                errors.append(f"Contacts row {row_number}: email is required")

            try:
                parse_optional_uuid(row.get("company_uuid", ""), "company_uuid", row_number)
                parse_bool(row.get("is_primary", ""), "is_primary", row_number)
            except CommandError as exc:
                errors.append(str(exc))

            if not full_name and not first_name:
                errors.append(
                    f"Contacts row {row_number}: first_name or full_name is required"
                )

            if company_name:
                key = company_name.lower()
                if key not in csv_customer_names and key not in db_customer_names:
                    errors.append(
                        f"Contacts row {row_number}: company_name '{company_name}' not found in customers CSV or DB"
                    )

        self.stdout.write(self.style.SUCCESS(f"Contacts CSV checked: {len(rows)} row(s)"))
