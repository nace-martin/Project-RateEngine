import json

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from parties.models import Company, Contact
from quotes.spot_models import SpotPricingEnvelopeDB


COMPANY_SCOPE_FIELDS = [
    "account_owner",
    "is_customer",
    "is_agent",
    "is_carrier",
    "audience_type",
    "company_type",
    "is_active",
    "created_at",
    "updated_at",
]
CONTACT_SCOPE_FIELDS = [
    "company",
    "is_primary",
    "is_active",
]


class Command(BaseCommand):
    help = "Read-only Customer/Contact RBAC scope diagnostic report."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format. Defaults to text.",
        )
        parser.add_argument(
            "--show-details",
            action="store_true",
            help="Include safe per-company/contact identifiers.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum detail rows per section. Defaults to 50.",
        )

    def handle(self, *args, **options):
        limit = max(options["limit"], 0)
        payload = build_report(show_details=options["show_details"], limit=limit)

        if options["format"] == "json":
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return

        self._write_text(payload, show_details=options["show_details"])

    def _write_text(self, payload: dict, *, show_details: bool):
        summary = payload["summary"]
        self.stdout.write("Customer/contact RBAC diagnostic report")
        self.stdout.write("=======================================")
        self.stdout.write("Mode: read-only")
        self.stdout.write(
            "Companies: "
            f"total={summary['total_companies']}, "
            f"customers={summary['customer_companies']}, "
            f"contacts={summary['total_contacts']}, "
            f"no_account_owner={summary['companies_without_account_owner']}, "
            f"no_detected_link={summary['companies_without_detected_scope_link']}"
        )
        self.stdout.write(
            "Links: "
            f"companies_with_quotes={summary['companies_with_quotes']}, "
            f"companies_with_spot={summary['companies_with_spot']}, "
            f"contacts_with_company={summary['contacts_with_company']}, "
            f"contacts_with_customer_company={summary['contacts_linked_to_customer_companies']}, "
            f"contacts_with_quotes={summary['contacts_with_quotes']}"
        )
        self.stdout.write(
            "Company types: "
            f"internal={summary['internal_like_companies']}, "
            f"vendor={summary['vendor_like_companies']}, "
            f"customer={summary['customer_like_companies']}, "
            f"carrier={summary['carrier_like_companies']}, "
            f"agent={summary['agent_like_companies']}"
        )
        self.stdout.write("")
        self.stdout.write("Available future scoping fields:")
        self.stdout.write(f"  Company: {', '.join(payload['available_scope_fields']['company'])}")
        self.stdout.write(f"  Contact: {', '.join(payload['available_scope_fields']['contact'])}")

        if not show_details:
            return

        self.stdout.write("")
        self.stdout.write("Company details:")
        for row in payload["details"]["companies"]:
            self.stdout.write(
                f"  - {row['id']} {row['name']} "
                f"type={row['type']} quotes={row['linked_quote_count']} "
                f"contacts={row['linked_contact_count']} created_at={row['created_at'] or '-'}"
            )
        self.stdout.write("Contact details:")
        for row in payload["details"]["contacts"]:
            self.stdout.write(
                f"  - {row['id']} {row['display_name']} "
                f"company={row['company_id']} quotes={row['linked_quote_count']}"
            )


def build_report(*, show_details: bool = False, limit: int = 50) -> dict:
    companies = Company.objects.all()
    contacts = Contact.objects.all()
    customer_filter = Q(is_customer=True) | Q(company_type="CUSTOMER")
    spot_company_ids = SpotPricingEnvelopeDB.objects.filter(
        quote__customer_id__isnull=False
    ).values("quote__customer_id").distinct()

    payload = {
        "write_enabled": False,
        "summary": {
            "total_companies": companies.count(),
            "customer_companies": companies.filter(customer_filter).count(),
            "total_contacts": contacts.count(),
            "contacts_with_company": contacts.filter(company_id__isnull=False).count(),
            "contacts_with_quotes": contacts.filter(quotes__isnull=False).distinct().count(),
            "companies_with_quotes": companies.filter(quotes_as_customer__isnull=False).distinct().count(),
            "companies_with_spot": companies.filter(id__in=spot_company_ids).count(),
            "contacts_linked_to_customer_companies": contacts.filter(
                company__in=companies.filter(customer_filter)
            ).count(),
            "companies_without_account_owner": companies.filter(account_owner__isnull=True).count(),
            "companies_without_detected_scope_link": companies.filter(
                account_owner__isnull=True,
                quotes_as_customer__isnull=True,
                opportunities__isnull=True,
                interactions__isnull=True,
                crm_tasks__isnull=True,
                shipment_address_book_entries__isnull=True,
            ).distinct().count(),
            "internal_like_companies": companies.filter(
                is_customer=False,
                is_agent=False,
                is_carrier=False,
            ).count(),
            "vendor_like_companies": companies.filter(company_type="SUPPLIER").count(),
            "customer_like_companies": companies.filter(customer_filter).count(),
            "carrier_like_companies": companies.filter(is_carrier=True).count(),
            "agent_like_companies": companies.filter(is_agent=True).count(),
        },
        "available_scope_fields": {
            "company": COMPANY_SCOPE_FIELDS,
            "contact": CONTACT_SCOPE_FIELDS,
        },
        "notes": [
            "Company and Contact have no durable organization, branch, or department scope fields.",
            "Customer/contact API reads remain authenticated-global; this command does not enforce access.",
            "SPOT linkage is counted only where an SPE is linked to a Quote with a customer.",
        ],
    }

    if show_details:
        payload["details"] = {
            "companies": [_company_detail(company) for company in _company_details(limit)],
            "contacts": [_contact_detail(contact) for contact in _contact_details(limit)],
        }

    return payload


def _company_details(limit: int):
    queryset = (
        Company.objects.annotate(
            linked_quote_count=Count("quotes_as_customer", distinct=True),
            linked_contact_count=Count("contacts", distinct=True),
        )
        .order_by("name", "id")
    )
    return queryset[:limit] if limit else []


def _contact_details(limit: int):
    queryset = (
        Contact.objects.select_related("company")
        .annotate(linked_quote_count=Count("quotes", distinct=True))
        .order_by("company__name", "last_name", "first_name", "id")
    )
    return queryset[:limit] if limit else []


def _company_detail(company: Company) -> dict:
    return {
        "id": str(company.id),
        "name": company.name,
        "type": _company_type(company),
        "linked_quote_count": company.linked_quote_count,
        "linked_contact_count": company.linked_contact_count,
        "created_at": company.created_at.isoformat() if company.created_at else None,
    }


def _contact_detail(contact: Contact) -> dict:
    return {
        "id": str(contact.id),
        "display_name": f"{contact.first_name} {contact.last_name}".strip(),
        "company_id": str(contact.company_id),
        "linked_quote_count": contact.linked_quote_count,
    }


def _company_type(company: Company) -> str:
    values = []
    if company.is_customer or company.company_type == "CUSTOMER":
        values.append("customer")
    if company.is_agent:
        values.append("agent")
    if company.is_carrier:
        values.append("carrier")
    if company.company_type == "SUPPLIER":
        values.append("vendor")
    return ",".join(values) or "internal"
