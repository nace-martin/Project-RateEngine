from contextlib import nullcontext

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from parties.models import Company, Contact

from ._seed_utils import (
    ensure_required_columns,
    is_nullish,
    load_csv_rows,
    parse_bool,
    parse_optional_uuid,
)


class Command(BaseCommand):
    help = (
        "Import customer contacts from CSV. "
        "Idempotent upsert by email. Resolves company by company_uuid or company_name."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to contacts CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report changes without writing to the database",
        )
        parser.add_argument(
            "--allow-reassign",
            action="store_true",
            help="Allow moving an existing contact email to a different company",
        )
        parser.add_argument(
            "--strict-sync",
            action="store_true",
            help="Deactivate existing active contacts not present in the CSV for imported companies",
        )

    def handle(self, *args, **options):
        csv_path = options["file"]
        dry_run = options["dry_run"]
        allow_reassign = options["allow_reassign"]
        strict_sync = options["strict_sync"]

        headers, rows = load_csv_rows(csv_path)
        ensure_required_columns(headers, ["company_name", "email"], "Contacts CSV")

        counts = {
            "created": 0,
            "updated": 0,
            "unchanged": 0,
            "demoted_primary": 0,
            "deactivated": 0,
        }
        expected_emails_by_company: dict[str, set[str]] = {}

        try:
            context = nullcontext() if dry_run else transaction.atomic()
            with context:
                for row_number, row in rows:
                    self._process_row(
                        row_number,
                        row,
                        dry_run,
                        allow_reassign,
                        counts,
                        expected_emails_by_company,
                    )
                if strict_sync:
                    self._apply_strict_sync(expected_emails_by_company, dry_run, counts)
                if dry_run:
                    raise CommandError("Dry run complete")
        except CommandError as exc:
            if str(exc) == "Dry run complete":
                pass
            else:
                raise

        mode = "DRY RUN" if dry_run else "APPLIED"
        self.stdout.write(self.style.SUCCESS(f"[{mode}] Contact import summary"))
        self.stdout.write(f"- Rows processed: {len(rows)}")
        self.stdout.write(f"- Contacts created: {counts['created']}")
        self.stdout.write(f"- Contacts updated: {counts['updated']}")
        self.stdout.write(f"- Contacts unchanged: {counts['unchanged']}")
        self.stdout.write(f"- Existing primaries demoted: {counts['demoted_primary']}")
        self.stdout.write(f"- Contacts deactivated (strict sync): {counts['deactivated']}")

    def _process_row(
        self,
        row_number: int,
        row: dict,
        dry_run: bool,
        allow_reassign: bool,
        counts: dict,
        expected_emails_by_company: dict[str, set[str]],
    ):
        email = row.get("email", "").strip().lower()
        if not email:
            raise CommandError(f"Row {row_number}: email is required")

        company = self._resolve_company(row_number, row)
        if not company:
            raise CommandError(
                f"Row {row_number}: company not found by company_uuid/company_name"
            )
        expected_emails_by_company.setdefault(str(company.id), set()).add(email)

        full_name = row.get("full_name", "").strip()
        first_name = row.get("first_name", "").strip()
        last_name = row.get("last_name", "").strip()
        if full_name and (not first_name and not last_name):
            parts = full_name.split()
            first_name = parts[0]
            last_name = " ".join(parts[1:]) if len(parts) > 1 else "Contact"

        if not first_name:
            raise CommandError(
                f"Row {row_number}: first_name or full_name is required for contact '{email}'"
            )
        if not last_name:
            last_name = "Contact"

        phone = row.get("phone", "").strip()
        is_primary = parse_bool(row.get("is_primary", ""), "is_primary", row_number)
        is_primary = bool(is_primary) if is_primary is not None else False

        contact = Contact.objects.filter(email__iexact=email).first()
        if contact and contact.company_id != company.id and not allow_reassign:
            raise CommandError(
                f"Row {row_number}: contact '{email}' belongs to another company. "
                "Use --allow-reassign to move it."
            )

        if not contact:
            contact = Contact(
                company=company,
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                is_primary=is_primary,
                is_active=True,
            )
            if not dry_run:
                contact.save()
                if is_primary:
                    demoted = Contact.objects.filter(company=company, is_primary=True).exclude(id=contact.id).update(is_primary=False)
                    counts["demoted_primary"] += demoted
            counts["created"] += 1
            return

        changed = False
        if contact.company_id != company.id:
            contact.company = company
            changed = True
        if contact.first_name != first_name:
            contact.first_name = first_name
            changed = True
        if contact.last_name != last_name:
            contact.last_name = last_name
            changed = True
        if contact.phone != phone:
            contact.phone = phone
            changed = True
        if contact.is_primary != is_primary:
            contact.is_primary = is_primary
            changed = True
        if not contact.is_active:
            contact.is_active = True
            changed = True

        if changed:
            if not dry_run:
                contact.save()
                if is_primary:
                    demoted = Contact.objects.filter(company=company, is_primary=True).exclude(id=contact.id).update(is_primary=False)
                    counts["demoted_primary"] += demoted
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    def _apply_strict_sync(self, expected_emails_by_company: dict[str, set[str]], dry_run: bool, counts: dict):
        for company_id, expected_emails in expected_emails_by_company.items():
            active_contacts = Contact.objects.filter(company_id=company_id, is_active=True)
            to_deactivate = []
            for contact in active_contacts:
                if (contact.email or "").lower() not in expected_emails:
                    contact.is_active = False
                    contact.is_primary = False
                    to_deactivate.append(contact)

            if to_deactivate:
                counts["deactivated"] += len(to_deactivate)
                if not dry_run:
                    Contact.objects.bulk_update(to_deactivate, ["is_active", "is_primary"])

    def _resolve_company(self, row_number: int, row: dict):
        company_uuid = parse_optional_uuid(row.get("company_uuid", ""), "company_uuid", row_number)
        if company_uuid:
            company = Company.objects.filter(id=company_uuid).first()
            if company:
                return company
        company_name = row.get("company_name", "").strip()
        if not company_name:
            return None
        return Company.objects.filter(name__iexact=company_name).first()
