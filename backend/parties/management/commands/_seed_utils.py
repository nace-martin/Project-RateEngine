import csv
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import CommandError


TRUE_VALUES = {"1", "true", "yes", "y"}
FALSE_VALUES = {"0", "false", "no", "n"}
NULL_VALUES = {"", "null", "none", "n/a", "na", "-"}
VALID_PAYMENT_TERMS = {"PREPAID", "COLLECT"}


def normalize_key(value: str) -> str:
    return (value or "").strip().lower()


def normalize_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def is_nullish(value) -> bool:
    return normalize_value(value).lower() in NULL_VALUES


def load_csv_rows(csv_path: str) -> tuple[list[str], list[tuple[int, dict]]]:
    path = Path(csv_path)
    if not path.exists():
        raise CommandError(f"File not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise CommandError(f"CSV file has no header row: {path}")

        headers = [normalize_key(h) for h in reader.fieldnames if h is not None]
        rows: list[tuple[int, dict]] = []
        for row_number, row in enumerate(reader, start=2):
            normalized = {
                normalize_key(k): normalize_value(v)
                for k, v in row.items()
                if k is not None
            }
            rows.append((row_number, normalized))

    return headers, rows


def ensure_required_columns(headers: list[str], required: list[str], file_label: str) -> None:
    header_set = set(headers)
    missing = [column for column in required if column not in header_set]
    if missing:
        raise CommandError(
            f"{file_label} is missing required column(s): {', '.join(missing)}"
        )


def parse_bool(raw_value: str, field_name: str, row_number: int):
    if is_nullish(raw_value):
        return None
    value = normalize_value(raw_value).lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    raise CommandError(
        f"Row {row_number}: invalid boolean for {field_name}: '{raw_value}'"
    )


def parse_decimal(raw_value: str, field_name: str, row_number: int):
    if is_nullish(raw_value):
        return None
    try:
        return Decimal(normalize_value(raw_value))
    except (InvalidOperation, ValueError):
        raise CommandError(
            f"Row {row_number}: invalid decimal for {field_name}: '{raw_value}'"
        )


def parse_payment_term(raw_value: str, row_number: int):
    if is_nullish(raw_value):
        return None
    term = normalize_value(raw_value).upper()
    if term not in VALID_PAYMENT_TERMS:
        raise CommandError(
            f"Row {row_number}: payment_term_default must be PREPAID or COLLECT, got '{raw_value}'"
        )
    return term


def parse_optional_uuid(raw_value: str, field_name: str, row_number: int):
    if is_nullish(raw_value):
        return None
    try:
        return uuid.UUID(normalize_value(raw_value))
    except ValueError:
        raise CommandError(
            f"Row {row_number}: invalid UUID for {field_name}: '{raw_value}'"
        )
