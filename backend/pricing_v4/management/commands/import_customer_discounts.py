import csv
import uuid
from contextlib import nullcontext
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from parties.models import Company
from pricing_v4.models import CustomerDiscount, ProductCode


class Command(BaseCommand):
    help = (
        "Import customer discounts from CSV. "
        "Idempotent upsert by (customer, product_code)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to discounts CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report changes without writing to the database",
        )

    def handle(self, *args, **options):
        csv_path = options["file"]
        dry_run = options["dry_run"]

        headers, rows = self._load_rows(csv_path)
        self._validate_headers(headers)

        counts = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
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
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Customer discount import summary"))
        self.stdout.write(f"- Rows processed: {len(rows)}")
        self.stdout.write(f"- Discounts created: {counts['created']}")
        self.stdout.write(f"- Discounts updated: {counts['updated']}")
        self.stdout.write(f"- Discounts unchanged: {counts['unchanged']}")

    def _load_rows(self, csv_path: str):
        path = Path(csv_path)
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        decode_error = None
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with path.open("r", encoding=encoding, newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames:
                        raise CommandError("CSV has no header row.")
                    headers = [self._norm_key(h) for h in reader.fieldnames if h is not None]
                    rows = []
                    for row_number, row in enumerate(reader, start=2):
                        rows.append(
                            (
                                row_number,
                                {
                                    self._norm_key(k): self._norm_value(v)
                                    for k, v in row.items()
                                    if k is not None
                                },
                            )
                        )
                    return headers, rows
            except UnicodeDecodeError as exc:
                decode_error = exc
                continue
        raise CommandError(
            f"Unable to decode discounts CSV using utf-8-sig/cp1252/latin-1: {decode_error}"
        )

    def _validate_headers(self, headers: list[str]):
        header_set = set(headers)
        required = {"discount_type", "discount_value"}
        missing = [col for col in sorted(required) if col not in header_set]
        if missing:
            raise CommandError(
                f"Discount CSV missing required column(s): {', '.join(missing)}"
            )

        customer_keys = {"customer_uuid", "customer_name"}
        product_keys = {"product_code_id", "product_code"}
        if not (header_set & customer_keys):
            raise CommandError(
                "Discount CSV must include one of: customer_uuid, customer_name"
            )
        if not (header_set & product_keys):
            raise CommandError(
                "Discount CSV must include one of: product_code_id, product_code"
            )

    def _process_row(self, row_number: int, row: dict, dry_run: bool, counts: dict):
        customer = self._resolve_customer(row_number, row)
        product_code = self._resolve_product_code(row_number, row)
        discount_type = self._parse_discount_type(row_number, row.get("discount_type"))
        discount_value = self._parse_decimal(row_number, "discount_value", row.get("discount_value"))
        currency = (row.get("currency") or "PGK").strip().upper()
        min_charge = self._parse_optional_decimal(row_number, "min_charge", row.get("min_charge"))
        max_charge = self._parse_optional_decimal(row_number, "max_charge", row.get("max_charge"))
        valid_from = self._parse_optional_date(row_number, "valid_from", row.get("valid_from"))
        valid_until = self._parse_optional_date(row_number, "valid_until", row.get("valid_until"))
        notes = row.get("notes", "")

        if valid_from and valid_until and valid_until < valid_from:
            raise CommandError(
                f"Row {row_number}: valid_until cannot be earlier than valid_from"
            )

        existing = CustomerDiscount.objects.filter(
            customer=customer,
            product_code=product_code,
        ).first()

        if not existing:
            discount = CustomerDiscount(
                customer=customer,
                product_code=product_code,
                discount_type=discount_type,
                discount_value=discount_value,
                currency=currency,
                min_charge=min_charge,
                max_charge=max_charge,
                valid_from=valid_from,
                valid_until=valid_until,
                notes=notes,
            )
            discount.full_clean()
            counts["created"] += 1
            if not dry_run:
                discount.save()
            return

        changed = False
        changed = self._set_if_changed(existing, "discount_type", discount_type) or changed
        changed = self._set_if_changed(existing, "discount_value", discount_value) or changed
        changed = self._set_if_changed(existing, "currency", currency) or changed
        changed = self._set_if_changed(existing, "min_charge", min_charge) or changed
        changed = self._set_if_changed(existing, "max_charge", max_charge) or changed
        changed = self._set_if_changed(existing, "valid_from", valid_from) or changed
        changed = self._set_if_changed(existing, "valid_until", valid_until) or changed
        changed = self._set_if_changed(existing, "notes", notes) or changed

        if changed:
            existing.full_clean()
            counts["updated"] += 1
            if not dry_run:
                existing.save()
        else:
            counts["unchanged"] += 1

    def _resolve_customer(self, row_number: int, row: dict) -> Company:
        raw_uuid = row.get("customer_uuid", "")
        raw_name = row.get("customer_name", "")

        customer = None
        if raw_uuid:
            try:
                parsed = uuid.UUID(raw_uuid)
            except ValueError:
                raise CommandError(f"Row {row_number}: invalid customer_uuid '{raw_uuid}'")
            customer = Company.objects.filter(id=parsed).first()
            if not customer:
                raise CommandError(f"Row {row_number}: customer_uuid not found '{raw_uuid}'")

        if not customer and raw_name:
            customer = Company.objects.filter(name__iexact=raw_name).first()
            if not customer:
                raise CommandError(f"Row {row_number}: customer_name not found '{raw_name}'")

        if not customer:
            raise CommandError(
                f"Row {row_number}: provide customer_uuid or customer_name"
            )

        if not customer.is_customer:
            raise CommandError(
                f"Row {row_number}: company '{customer.name}' is not marked as customer"
            )
        return customer

    def _resolve_product_code(self, row_number: int, row: dict) -> ProductCode:
        raw_id = row.get("product_code_id", "")
        raw_code = row.get("product_code", "")

        product = None
        if raw_id:
            try:
                parsed_id = int(raw_id)
            except ValueError:
                raise CommandError(f"Row {row_number}: invalid product_code_id '{raw_id}'")
            product = ProductCode.objects.filter(id=parsed_id).first()
            if not product:
                raise CommandError(f"Row {row_number}: product_code_id not found '{raw_id}'")

        if not product and raw_code:
            product = ProductCode.objects.filter(code__iexact=raw_code).first()
            if not product:
                raise CommandError(f"Row {row_number}: product_code not found '{raw_code}'")

        if not product:
            raise CommandError(
                f"Row {row_number}: provide product_code_id or product_code"
            )
        return product

    def _parse_discount_type(self, row_number: int, value: str) -> str:
        raw = (value or "").strip().upper()
        allowed = {
            CustomerDiscount.TYPE_PERCENTAGE,
            CustomerDiscount.TYPE_FLAT_AMOUNT,
            CustomerDiscount.TYPE_RATE_REDUCTION,
            CustomerDiscount.TYPE_FIXED_CHARGE,
            CustomerDiscount.TYPE_MARGIN_OVERRIDE,
        }
        if raw not in allowed:
            raise CommandError(
                f"Row {row_number}: invalid discount_type '{value}'. Allowed: {', '.join(sorted(allowed))}"
            )
        return raw

    def _parse_decimal(self, row_number: int, field: str, value: str) -> Decimal:
        raw = (value or "").strip()
        if not raw:
            raise CommandError(f"Row {row_number}: {field} is required")
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            raise CommandError(f"Row {row_number}: invalid decimal for {field}: '{value}'")

    def _parse_optional_decimal(self, row_number: int, field: str, value: str):
        raw = (value or "").strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            raise CommandError(f"Row {row_number}: invalid decimal for {field}: '{value}'")

    def _parse_optional_date(self, row_number: int, field: str, value: str):
        raw = (value or "").strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            raise CommandError(
                f"Row {row_number}: invalid date for {field}: '{value}' (expected YYYY-MM-DD)"
            )

    def _set_if_changed(self, obj, field: str, new_value) -> bool:
        if getattr(obj, field) != new_value:
            setattr(obj, field, new_value)
            return True
        return False

    def _norm_key(self, value: str) -> str:
        return (value or "").strip().lower()

    def _norm_value(self, value) -> str:
        if value is None:
            return ""
        return str(value).strip()
