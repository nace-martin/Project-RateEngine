import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from core.models import Currency, Location
from pricing_v4.category_rules import is_local_rate_category
from pricing_v4.models import (
    DomesticSellRate,
    ExportSellRate,
    ImportSellRate,
    LocalSellRate,
    ProductCode,
)


REQUIRED_COLUMNS = {
    "rate_type",
    "origin_code",
    "destination_code",
    "product_code",
    "currency",
    "amount",
    "valid_from",
    "valid_until",
}

RATE_TYPE_MAP = {
    "EXPORT": ExportSellRate,
    "IMPORT": ImportSellRate,
    "DOMESTIC": DomesticSellRate,
}

PRODUCT_DOMAIN_BY_RATE_TYPE = {
    "EXPORT": ProductCode.DOMAIN_EXPORT,
    "IMPORT": ProductCode.DOMAIN_IMPORT,
    "DOMESTIC": ProductCode.DOMAIN_DOMESTIC,
}

AMOUNT_BASIS_CHOICES = {"PER_SHIPMENT", "PER_KG", "PERCENT"}
PAYMENT_TERM_CHOICES = {"PREPAID", "COLLECT", "ANY"}
TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n", ""}


class V4RateCSVImportValidationError(Exception):
    def __init__(self, errors: dict[str, str], message: str = "CSV import validation failed") -> None:
        super().__init__(message)
        self.errors = errors
        self.message = message


@dataclass
class PreparedRateRow:
    row_number: int
    model_cls: type
    lookup: dict[str, Any]
    defaults: dict[str, Any]


@dataclass
class V4RateCSVImportResult:
    processed_rows: int
    created_rows: int
    updated_rows: int


def import_v4_rate_cards_csv(uploaded_file) -> V4RateCSVImportResult:
    """
    Parse, validate, and bulk import V4 SELL rate rows from CSV.

    Local charge categories for EXPORT/IMPORT are automatically written to
    LocalSellRate (location-based) rather than lane-based tables.

    The import is all-or-nothing: if any row is invalid, no database writes occur.
    """
    with transaction.atomic():
        rows = _read_csv_rows(uploaded_file)
        prepared_rows = _validate_and_prepare_rows(rows)

        created_rows = 0
        updated_rows = 0
        for prepared in prepared_rows:
            obj, created = prepared.model_cls.objects.update_or_create(
                **prepared.lookup,
                defaults=prepared.defaults,
            )
            if created:
                created_rows += 1
            else:
                updated_rows += 1

        return V4RateCSVImportResult(
            processed_rows=len(prepared_rows),
            created_rows=created_rows,
            updated_rows=updated_rows,
        )


def _read_csv_rows(uploaded_file) -> list[tuple[int, dict[str, str]]]:
    if uploaded_file is None:
        raise V4RateCSVImportValidationError({"file": "No CSV file was provided."})

    try:
        raw_bytes = uploaded_file.read()
    except Exception as exc:
        raise V4RateCSVImportValidationError({"file": f"Could not read uploaded file: {exc}"}) from exc

    if not raw_bytes:
        raise V4RateCSVImportValidationError({"file": "Uploaded CSV file is empty."})

    try:
        decoded = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise V4RateCSVImportValidationError(
            {"file": "CSV must be UTF-8 encoded (BOM supported)."}
        ) from exc

    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise V4RateCSVImportValidationError({"file": "CSV header row is missing."})

    normalized_fieldnames = {_normalize_header(name) for name in reader.fieldnames if name is not None}
    missing_columns = sorted(REQUIRED_COLUMNS - normalized_fieldnames)
    if missing_columns:
        raise V4RateCSVImportValidationError(
            {
                "header": (
                    "Missing required columns: " + ", ".join(missing_columns)
                )
            }
        )

    rows: list[tuple[int, dict[str, str]]] = []
    for row_number, row in enumerate(reader, start=2):
        normalized_row = {
            _normalize_header(key): (value.strip() if isinstance(value, str) else "")
            for key, value in (row or {}).items()
            if key is not None
        }
        if _is_blank_row(normalized_row):
            continue
        rows.append((row_number, normalized_row))

    if not rows:
        raise V4RateCSVImportValidationError({"file": "CSV contains no data rows."})

    return rows


def _validate_and_prepare_rows(rows: list[tuple[int, dict[str, str]]]) -> list[PreparedRateRow]:
    errors: dict[str, list[str]] = {}

    location_codes = set()
    currency_codes = set()
    product_ids_needed: set[int] = set()
    product_codes_needed: set[str] = set()

    for _, row in rows:
        if row.get("origin_code"):
            location_codes.add(row["origin_code"].upper())
        if row.get("destination_code"):
            location_codes.add(row["destination_code"].upper())
        if row.get("currency"):
            currency_codes.add(row["currency"].upper())

        product_ref = (row.get("product_code") or "").strip()
        if product_ref.isdigit():
            product_ids_needed.add(int(product_ref))
        elif product_ref:
            product_codes_needed.add(product_ref.upper())

    existing_locations = set(
        Location.objects.filter(code__in=location_codes, is_active=True).values_list("code", flat=True)
    )
    existing_currencies = set(
        Currency.objects.filter(code__in=currency_codes).values_list("code", flat=True)
    )
    product_by_id = ProductCode.objects.in_bulk(product_ids_needed) if product_ids_needed else {}
    product_by_code = {
        pc.code.upper(): pc
        for pc in ProductCode.objects.filter(code__in=product_codes_needed)
    }

    prepared_rows: list[PreparedRateRow] = []
    seen_keys: set[tuple] = set()

    for row_number, row in rows:
        row_errors: list[str] = []
        row_key = f"row_{row_number}"

        rate_type = (row.get("rate_type") or "").strip().upper()
        model_cls = RATE_TYPE_MAP.get(rate_type)
        if not model_cls:
            row_errors.append(
                f"Invalid rate_type '{row.get('rate_type')}'. Expected one of: EXPORT, IMPORT, DOMESTIC."
            )

        origin_code = (row.get("origin_code") or "").strip().upper()
        destination_code = (row.get("destination_code") or "").strip().upper()
        currency = (row.get("currency") or "").strip().upper()

        if not origin_code:
            row_errors.append("origin_code is required.")
        if not destination_code:
            row_errors.append("destination_code is required.")
        if not currency:
            row_errors.append("currency is required.")

        if origin_code and origin_code not in existing_locations:
            row_errors.append(f"Invalid origin_code '{origin_code}' does not exist in active Location registry.")
        if destination_code and destination_code not in existing_locations:
            row_errors.append(
                f"Invalid destination_code '{destination_code}' does not exist in active Location registry."
            )
        if currency and currency not in existing_currencies:
            row_errors.append(f"Invalid currency '{currency}' does not exist in Currency registry.")

        product = _resolve_product_code(row.get("product_code"), product_by_id, product_by_code)
        if not product:
            raw_product_ref = (row.get("product_code") or "").strip()
            row_errors.append(f"Invalid ProductCode '{raw_product_ref}' did not match registry.")
        elif rate_type and product.domain != PRODUCT_DOMAIN_BY_RATE_TYPE[rate_type]:
            row_errors.append(
                f"ProductCode '{product.code}' belongs to domain '{product.domain}', not '{PRODUCT_DOMAIN_BY_RATE_TYPE[rate_type]}'."
            )

        use_local_sell_rate = bool(
            product
            and rate_type in {"EXPORT", "IMPORT"}
            and is_local_rate_category(product.category)
        )
        if use_local_sell_rate:
            model_cls = LocalSellRate

        amount = _parse_decimal(row.get("amount"))
        if amount is None:
            row_errors.append(f"Invalid amount '{row.get('amount')}'.")
        elif amount < 0:
            row_errors.append("amount cannot be negative.")

        amount_basis = (row.get("amount_basis") or row.get("charge_basis") or "PER_SHIPMENT").strip().upper()
        if amount_basis not in AMOUNT_BASIS_CHOICES:
            row_errors.append(
                f"Invalid amount_basis '{row.get('amount_basis') or row.get('charge_basis')}'. "
                f"Expected one of: {', '.join(sorted(AMOUNT_BASIS_CHOICES))}."
            )

        valid_from = _parse_date(row.get("valid_from"))
        valid_until = _parse_date(row.get("valid_until"))
        if valid_from is None:
            row_errors.append(f"Invalid valid_from '{row.get('valid_from')}'. Use YYYY-MM-DD.")
        if valid_until is None:
            row_errors.append(f"Invalid valid_until '{row.get('valid_until')}'. Use YYYY-MM-DD.")
        if valid_from and valid_until and valid_until < valid_from:
            row_errors.append("valid_until must be on or after valid_from.")

        min_charge = _parse_optional_decimal(row.get("min_charge"))
        max_charge = _parse_optional_decimal(row.get("max_charge"))
        if row.get("min_charge") and min_charge is None:
            row_errors.append(f"Invalid min_charge '{row.get('min_charge')}'.")
        if row.get("max_charge") and max_charge is None:
            row_errors.append(f"Invalid max_charge '{row.get('max_charge')}'.")

        is_additive = _parse_bool(row.get("is_additive"))
        if row.get("is_additive") is not None and row.get("is_additive", "").strip() and is_additive is None:
            row_errors.append(f"Invalid is_additive '{row.get('is_additive')}'. Use true/false.")
        additive_flat_amount_raw = row.get("additive_flat_amount")
        additive_flat_amount = _parse_optional_decimal(additive_flat_amount_raw)
        if additive_flat_amount_raw and additive_flat_amount is None:
            row_errors.append(f"Invalid additive_flat_amount '{additive_flat_amount_raw}'.")
        if is_additive and amount_basis != "PER_KG":
            row_errors.append("is_additive=true is only valid when amount_basis=PER_KG.")

        payment_term = None
        if use_local_sell_rate:
            payment_term_raw = (row.get("payment_term") or "").strip().upper()
            if payment_term_raw:
                if payment_term_raw not in PAYMENT_TERM_CHOICES:
                    row_errors.append(
                        f"Invalid payment_term '{row.get('payment_term')}'. Expected PREPAID, COLLECT, or ANY."
                    )
                else:
                    payment_term = payment_term_raw
            else:
                payment_term = "ANY" if rate_type == "EXPORT" else "COLLECT"

        weight_breaks = None
        weight_breaks_raw = row.get("weight_breaks") or row.get("weight_breaks_json") or ""
        if weight_breaks_raw:
            try:
                weight_breaks = json.loads(weight_breaks_raw)
                if not isinstance(weight_breaks, list):
                    row_errors.append("weight_breaks must be a JSON array.")
            except json.JSONDecodeError:
                row_errors.append("weight_breaks must be valid JSON.")

        if row_errors:
            errors[row_key] = row_errors
            continue

        lookup, defaults = _build_model_payload(
            model_cls=model_cls,
            rate_type=rate_type,
            product=product,
            origin_code=origin_code,
            destination_code=destination_code,
            currency=currency,
            amount=amount,
            amount_basis=amount_basis,
            valid_from=valid_from,
            valid_until=valid_until,
            min_charge=min_charge,
            max_charge=max_charge,
            is_additive=(False if is_additive is None else is_additive),
            additive_flat_amount=additive_flat_amount,
            weight_breaks=weight_breaks,
            use_local_sell_rate=use_local_sell_rate,
            payment_term=payment_term,
        )

        if use_local_sell_rate:
            local_direction = 'EXPORT' if rate_type == 'EXPORT' else 'IMPORT'
            local_location = origin_code if local_direction == 'EXPORT' else destination_code
            dedupe_key = (
                "LOCAL_SELL",
                product.id,
                local_direction,
                local_location,
                payment_term,
                currency,
                valid_from.isoformat(),
            )
        else:
            dedupe_key = (
                rate_type,
                product.id,
                origin_code,
                destination_code,
                currency,
                valid_from.isoformat(),
            )
        if dedupe_key in seen_keys:
            errors[row_key] = [
                "Duplicate row detected in CSV for the same rate key."
            ]
            continue
        seen_keys.add(dedupe_key)

        model_instance = model_cls(**lookup, **defaults)
        try:
            model_instance.full_clean(validate_unique=False)
        except DjangoValidationError as exc:
            messages: list[str] = []
            if hasattr(exc, "message_dict"):
                for field, field_messages in exc.message_dict.items():
                    for msg in field_messages:
                        messages.append(f"{field}: {msg}")
            elif hasattr(exc, "messages"):
                messages.extend(exc.messages)
            else:
                messages.append(str(exc))
            errors[row_key] = messages
            continue

        prepared_rows.append(
            PreparedRateRow(
                row_number=row_number,
                model_cls=model_cls,
                lookup=lookup,
                defaults=defaults,
            )
        )

    if errors:
        raise V4RateCSVImportValidationError(
            errors={key: "; ".join(msgs) for key, msgs in errors.items()},
            message="CSV import failed validation. No rows were imported.",
        )

    return prepared_rows


def _build_model_payload(
    *,
    model_cls: type,
    rate_type: str,
    product: ProductCode,
    origin_code: str,
    destination_code: str,
    currency: str,
    amount: Decimal,
    amount_basis: str,
    valid_from: date,
    valid_until: date,
    min_charge: Decimal | None,
    max_charge: Decimal | None,
    is_additive: bool,
    additive_flat_amount: Decimal | None,
    weight_breaks: list | None,
    use_local_sell_rate: bool,
    payment_term: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if use_local_sell_rate:
        local_direction = 'EXPORT' if rate_type == 'EXPORT' else 'IMPORT'
        local_location = origin_code if local_direction == 'EXPORT' else destination_code
        local_rate_type = "FIXED"
        if amount_basis == "PER_KG":
            local_rate_type = "PER_KG"
        elif amount_basis == "PERCENT":
            local_rate_type = "PERCENT"

        defaults = {
            "rate_type": local_rate_type,
            "amount": amount,
            "is_additive": is_additive,
            "additive_flat_amount": additive_flat_amount,
            "min_charge": min_charge,
            "max_charge": max_charge,
            "weight_breaks": weight_breaks,
            "valid_until": valid_until,
        }
        lookup = {
            "product_code": product,
            "location": local_location,
            "direction": local_direction,
            "payment_term": payment_term or ("ANY" if local_direction == "EXPORT" else "COLLECT"),
            "currency": currency,
            "valid_from": valid_from,
        }
        return lookup, defaults

    defaults: dict[str, Any] = {
        "rate_per_kg": None,
        "rate_per_shipment": None,
        "percent_rate": None,
        "min_charge": min_charge,
        "max_charge": max_charge,
        "is_additive": is_additive,
        "weight_breaks": weight_breaks,
        "valid_until": valid_until,
    }

    if amount_basis == "PER_KG":
        defaults["rate_per_kg"] = amount
        if is_additive and additive_flat_amount is not None:
            defaults["rate_per_shipment"] = additive_flat_amount
    elif amount_basis == "PERCENT":
        defaults["percent_rate"] = amount
    else:
        defaults["rate_per_shipment"] = amount

    if rate_type in {"EXPORT", "IMPORT"}:
        lookup = {
            "product_code": product,
            "origin_airport": origin_code,
            "destination_airport": destination_code,
            "currency": currency,
            "valid_from": valid_from,
        }
    else:
        defaults["currency"] = currency
        # Domestic unique_together excludes currency, but we still persist the provided currency.
        lookup = {
            "product_code": product,
            "origin_zone": origin_code,
            "destination_zone": destination_code,
            "valid_from": valid_from,
        }

    return lookup, defaults


def _resolve_product_code(
    raw_value: str | None,
    product_by_id: dict[int, ProductCode],
    product_by_code: dict[str, ProductCode],
) -> ProductCode | None:
    product_ref = (raw_value or "").strip()
    if not product_ref:
        return None
    if product_ref.isdigit():
        return product_by_id.get(int(product_ref))
    return product_by_code.get(product_ref.upper())


def _normalize_header(value: str) -> str:
    return (value or "").strip().lower()


def _is_blank_row(row: dict[str, str]) -> bool:
    for value in row.values():
        if (value or "").strip():
            return False
    return True


def _parse_decimal(value: str | None) -> Decimal | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _parse_optional_decimal(value: str | None) -> Decimal | None:
    raw = (value or "").strip()
    if not raw:
        return None
    return _parse_decimal(raw)


def _parse_bool(value: str | None) -> bool | None:
    raw = (value or "").strip().lower()
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    return None


def _parse_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None

    formats = ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y")
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
