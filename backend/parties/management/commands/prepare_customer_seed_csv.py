import csv
import re
from collections import Counter, OrderedDict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Command(BaseCommand):
    help = (
        "Transform raw customer/contact sheet into import-ready customers.csv and contacts.csv. "
        "Position is ignored by design."
    )

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True, help="Path to raw input CSV")
        parser.add_argument("--customers-out", required=True, help="Output path for customers CSV")
        parser.add_argument("--contacts-out", required=True, help="Output path for contacts CSV")
        parser.add_argument(
            "--report-out",
            help="Optional output path for skipped/duplicate issue report CSV",
        )

    def handle(self, *args, **options):
        input_path = Path(options["input"])
        customers_out = Path(options["customers_out"])
        contacts_out = Path(options["contacts_out"])
        report_out = Path(options["report_out"]) if options.get("report_out") else None

        if not input_path.exists():
            raise CommandError(f"Input file not found: {input_path}")

        rows = self._read_rows(input_path)
        if not rows:
            raise CommandError("Input file has no data rows.")

        customers, contacts, skipped, issues = self._transform(rows)
        self._write_customers(customers_out, customers)
        self._write_contacts(contacts_out, contacts)
        if report_out:
            self._write_report(report_out, issues)

        self.stdout.write(self.style.SUCCESS("Seed CSV preparation complete"))
        self.stdout.write(f"- Input rows: {len(rows)}")
        self.stdout.write(f"- Customers output rows: {len(customers)}")
        self.stdout.write(f"- Contacts output rows: {len(contacts)}")
        self.stdout.write(f"- Skipped rows: {skipped}")
        if issues:
            by_reason = Counter(item["reason"] for item in issues)
            for reason, count in sorted(by_reason.items()):
                self.stdout.write(f"  - {reason}: {count}")
        self.stdout.write(f"- Customers file: {customers_out}")
        self.stdout.write(f"- Contacts file: {contacts_out}")
        if report_out:
            self.stdout.write(f"- Issues report: {report_out}")

    def _read_rows(self, input_path: Path) -> list[dict]:
        decode_error = None
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                with input_path.open("r", encoding=encoding, newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames:
                        raise CommandError("Input CSV is missing header row.")

                    header_map = self._build_header_map(reader.fieldnames)
                    missing = [key for key in ("organization", "email") if key not in header_map]
                    if missing:
                        raise CommandError(
                            f"Input CSV missing required column(s): {', '.join(missing)}. "
                            "Expected columns include Organization and Email."
                        )

                    parsed_rows: list[dict] = []
                    for row_number, row in enumerate(reader, start=2):
                        parsed_rows.append(
                            {
                                "row_number": row_number,
                                "organization": self._read_field(row, header_map, "organization"),
                                "full_name": self._read_field(row, header_map, "full_name"),
                                "email": self._read_field(row, header_map, "email").lower(),
                                "city": self._read_field(row, header_map, "city"),
                                "state": self._read_field(row, header_map, "state"),
                                "country": self._read_field(row, header_map, "country"),
                            }
                        )
                    return parsed_rows
            except UnicodeDecodeError as exc:
                decode_error = exc
                continue

        raise CommandError(
            f"Unable to decode input CSV using utf-8-sig/cp1252/latin-1: {decode_error}"
        )

    def _build_header_map(self, headers: list[str]) -> dict[str, str]:
        mapping = {}
        for original in headers:
            canonical = self._canonical_header(original)
            if canonical and canonical not in mapping:
                mapping[canonical] = original
        return mapping

    def _canonical_header(self, header: str) -> str:
        key = " ".join((header or "").strip().lower().replace("_", " ").split())
        if key in {"organization", "organisation", "company", "company name"}:
            return "organization"
        if key.startswith("full name"):
            return "full_name"
        if key == "email":
            return "email"
        if key == "city":
            return "city"
        if key in {"state", "state province", "province"}:
            return "state"
        if key == "country":
            return "country"
        if key == "position":
            return "position"
        return ""

    def _read_field(self, row: dict, header_map: dict[str, str], key: str) -> str:
        column = header_map.get(key)
        if not column:
            return ""
        value = row.get(column)
        if value is None:
            return ""
        return str(value).strip()

    def _transform(self, rows: list[dict]):
        customer_index: OrderedDict[str, str] = OrderedDict()
        contacts: list[dict] = []
        seen_emails: set[str] = set()
        primary_assigned: set[str] = set()
        skipped = 0
        issues: list[dict] = []

        for row in rows:
            organization = row["organization"].strip()
            email = row["email"].strip().lower()

            if not organization or not email:
                skipped += 1
                issues.append(
                    {
                        "row_number": row["row_number"],
                        "reason": "missing_organization_or_email",
                        "organization": organization,
                        "full_name": row["full_name"],
                        "email": email,
                        "city": row["city"],
                        "state": row["state"],
                        "country": row["country"],
                    }
                )
                continue

            if not EMAIL_REGEX.match(email):
                skipped += 1
                issues.append(
                    {
                        "row_number": row["row_number"],
                        "reason": "invalid_email_format",
                        "organization": organization,
                        "full_name": row["full_name"],
                        "email": email,
                        "city": row["city"],
                        "state": row["state"],
                        "country": row["country"],
                    }
                )
                continue

            org_key = organization.lower()
            if org_key not in customer_index:
                customer_index[org_key] = organization

            if email in seen_emails:
                skipped += 1
                issues.append(
                    {
                        "row_number": row["row_number"],
                        "reason": "duplicate_email_in_input",
                        "organization": organization,
                        "full_name": row["full_name"],
                        "email": email,
                        "city": row["city"],
                        "state": row["state"],
                        "country": row["country"],
                    }
                )
                continue
            seen_emails.add(email)

            full_name = row["full_name"].strip() or self._derive_name_from_email(email)
            is_primary = "true" if org_key not in primary_assigned else "false"
            primary_assigned.add(org_key)

            contacts.append(
                {
                    "company_name": customer_index[org_key],
                    "full_name": full_name,
                    "email": email,
                    "is_primary": is_primary,
                    "city": row["city"],
                    "state": row["state"],
                    "country": row["country"],
                }
            )

        customers = [{"company_name": name} for name in customer_index.values()]
        return customers, contacts, skipped, issues

    def _derive_name_from_email(self, email: str) -> str:
        local = (email or "").split("@")[0]
        local = local.replace(".", " ").replace("_", " ").replace("-", " ").strip()
        if not local:
            return "Unknown Contact"
        return " ".join(part.capitalize() for part in local.split())

    def _write_customers(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["company_name"])
            writer.writeheader()
            writer.writerows(rows)

    def _write_contacts(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "company_name",
                    "full_name",
                    "email",
                    "is_primary",
                    "city",
                    "state",
                    "country",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)

    def _write_report(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "row_number",
                    "reason",
                    "organization",
                    "full_name",
                    "email",
                    "city",
                    "state",
                    "country",
                ],
            )
            writer.writeheader()
            writer.writerows(rows)
