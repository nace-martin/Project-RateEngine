from contextlib import nullcontext

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models.functions import Lower

from parties.models import Company, Contact

from ._seed_utils import (
    ensure_required_columns,
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
        companies_by_uuid, companies_by_name = self._prefetch_companies(rows)
        contacts_by_email = self._prefetch_contacts(rows)

        try:
            context = nullcontext() if dry_run else transaction.atomic()
            with context:
                create_contacts: list[Contact] = []
                update_contacts: list[Contact] = []
                primary_email_by_company: dict[str, str] = {}
                for row_number, row in rows:
                    self._process_row(
                        row_number,
                        row,
                        dry_run,
                        allow_reassign,
                        counts,
                        expected_emails_by_company,
                        companies_by_uuid,
                        companies_by_name,
                        contacts_by_email,
                        create_contacts,
                        update_contacts,
                        primary_email_by_company,
                    )
                if not dry_run:
                    self._apply_bulk_changes(
                        create_contacts,
                        update_contacts,
                        primary_email_by_company,
                        expected_emails_by_company,
                        strict_sync,
                        counts,
                    )
                if strict_sync:
                    if dry_run:
                        self._apply_strict_sync(expected_emails_by_company, counts, dry_run=True)
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
        companies_by_uuid: dict[str, Company],
        companies_by_name: dict[str, Company],
        contacts_by_email: dict[str, Contact],
        create_contacts: list[Contact],
        update_contacts: list[Contact],
        primary_email_by_company: dict[str, str],
    ):
        email = row.get("email", "").strip().lower()
        if not email:
            raise CommandError(f"Row {row_number}: email is required")

        company = self._resolve_company(row_number, row, companies_by_uuid, companies_by_name)
        if not company:
            raise CommandError(
                f"Row {row_number}: company not found by company_uuid/company_name"
            )
        company_id = str(company.id)
        expected_emails_by_company.setdefault(company_id, set()).add(email)

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
        if is_primary:
            primary_email_by_company[company_id] = email

        contact = contacts_by_email.get(email)
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
            contacts_by_email[email] = contact
            if not dry_run:
                create_contacts.append(contact)
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
                update_contacts.append(contact)
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    def _apply_bulk_changes(
        self,
        create_contacts: list[Contact],
        update_contacts: list[Contact],
        primary_email_by_company: dict[str, str],
        expected_emails_by_company: dict[str, set[str]],
        strict_sync: bool,
        counts: dict,
    ):
        if create_contacts:
            Contact.objects.bulk_create(create_contacts, batch_size=500)
        if update_contacts:
            Contact.objects.bulk_update(
                update_contacts,
                ["company", "first_name", "last_name", "phone", "is_primary", "is_active"],
                batch_size=500,
            )

        for company_id, primary_email in primary_email_by_company.items():
            demoted_candidates = Contact.objects.filter(company_id=company_id, is_primary=True).annotate(
                email_lower=Lower("email")
            ).exclude(
                email_lower=primary_email
            )
            demoted = (
                Contact.objects.filter(id__in=demoted_candidates.values_list("id", flat=True))
                .update(is_primary=False)
            )
            counts["demoted_primary"] += demoted

        if strict_sync:
            self._apply_strict_sync(expected_emails_by_company, counts, dry_run=False)

    def _apply_strict_sync(self, expected_emails_by_company: dict[str, set[str]], counts: dict, dry_run: bool):
        for company_id, expected_emails in expected_emails_by_company.items():
            to_deactivate = Contact.objects.filter(company_id=company_id, is_active=True).annotate(
                email_lower=Lower("email")
            ).exclude(
                email_lower__in=expected_emails
            )
            deactivated = (
                to_deactivate.count()
                if dry_run
                else Contact.objects.filter(
                    id__in=to_deactivate.values_list("id", flat=True)
                ).update(is_active=False, is_primary=False)
            )
            counts["deactivated"] += deactivated

    def _prefetch_companies(self, rows: list[tuple[int, dict]]) -> tuple[dict[str, Company], dict[str, Company]]:
        company_uuids = set()
        company_names = set()
        for row_number, row in rows:
            company_uuid = parse_optional_uuid(row.get("company_uuid", ""), "company_uuid", row_number)
            if company_uuid:
                company_uuids.add(company_uuid)
            company_name = row.get("company_name", "").strip()
            if company_name:
                company_names.add(company_name.lower())

        companies_by_uuid: dict[str, Company] = {}
        companies_by_name: dict[str, Company] = {}

        for company in Company.objects.filter(id__in=company_uuids).only("id", "name"):
            companies_by_uuid[str(company.id)] = company
            companies_by_name[company.name.lower()] = company

        if company_names:
            for company in Company.objects.all().only("id", "name"):
                lower_name = company.name.lower()
                if lower_name in company_names:
                    companies_by_uuid.setdefault(str(company.id), company)
                    companies_by_name[lower_name] = company

        return companies_by_uuid, companies_by_name

    def _prefetch_contacts(self, rows: list[tuple[int, dict]]) -> dict[str, Contact]:
        emails = {
            row.get("email", "").strip().lower()
            for _, row in rows
            if row.get("email", "").strip()
        }
        if not emails:
            return {}
        return {
            (contact.email or "").lower(): contact
            for contact in Contact.objects.annotate(email_lower=Lower("email")).filter(
                email_lower__in=emails
            )
        }

    def _resolve_company(
        self,
        row_number: int,
        row: dict,
        companies_by_uuid: dict[str, Company],
        companies_by_name: dict[str, Company],
    ):
        company_uuid = parse_optional_uuid(row.get("company_uuid", ""), "company_uuid", row_number)
        if company_uuid:
            company = companies_by_uuid.get(str(company_uuid))
            if company:
                return company
        company_name = row.get("company_name", "").strip()
        if not company_name:
            return None
        return companies_by_name.get(company_name.lower())
