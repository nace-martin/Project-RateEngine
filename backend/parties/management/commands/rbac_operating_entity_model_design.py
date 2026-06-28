import json

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models


COUNTRY_ENTITIES = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
ONLY_ORGANIZATION = "Express Freight Management"
SCOPE_MODELS_NEEDING_ENTITY = {
    "accounts.UserMembership",
    "parties.Branch",
    "parties.Department",
    "parties.Company",
    "parties.Contact",
    "crm.Opportunity",
    "crm.Interaction",
    "crm.Task",
    "quotes.Quote",
    "quotes.SpotPricingEnvelopeDB",
    "shipments.Shipment",
    "shipments.ShipmentAddress",
}


class Command(BaseCommand):
    help = "Read-only Phase 10C OperatingEntity hierarchy model design report."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        report = build_report()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_report():
    return {
        "phase": "10C",
        "write_enabled": False,
        "target_hierarchy": {
            "organization": ONLY_ORGANIZATION,
            "operating_entities": list(COUNTRY_ENTITIES),
            "branches": ["Port Moresby", "Lae", "Brisbane", "Suva", "Honiara"],
            "departments": ["Air Freight", "Sea Freight", "Customs", "Transport"],
        },
        "proposed_model": proposed_model(),
        "current_scope_references": current_scope_references(),
        "migration_order": [
            "add OperatingEntity model only; no data migration or enforcement",
            "seed EFM PNG, EFM Australia, EFM Fiji, and EFM Solomon Islands under Express Freight Management",
            "add nullable Branch.operating_entity and link branches after duplicate-code review",
            "add nullable UserMembership.operating_entity and update membership planning/readiness tooling",
            "add nullable operating_entity to records that need country-division scope",
            "only then consider selector/API/queryset/RBAC enforcement changes",
        ],
        "risks": [
            "Branch and Department codes are currently unique per Organization, not per OperatingEntity.",
            "OrganizationBranding is one-to-one with Organization; country-specific branding needs a separate approved design.",
            "UserMembership target semantics change from organization/branch/department to organization/operating_entity/branch/department.",
            "Older readiness and reassignment commands still encode country-as-organization assumptions.",
            "Rollback requires old Organization id to new OperatingEntity id mappings before any apply phase.",
        ],
    }


def proposed_model():
    return {
        "name": "OperatingEntity",
        "table": "parties_operatingentity",
        "fields": [
            {"name": "id", "type": "UUIDField", "primary_key": True},
            {"name": "organization", "type": "ForeignKey(Organization)", "on_delete": "CASCADE", "related_name": "operating_entities"},
            {"name": "code", "type": "CharField(max_length=24)", "examples": ["PNG", "AU", "FJ", "SB"]},
            {"name": "name", "type": "CharField(max_length=120)", "examples": list(COUNTRY_ENTITIES)},
            {"name": "slug", "type": "SlugField(max_length=64)"},
            {"name": "country_code", "type": "CharField(max_length=2)", "examples": ["PG", "AU", "FJ", "SB"]},
            {"name": "is_active", "type": "BooleanField", "default": True, "db_index": True},
            {"name": "created_at", "type": "DateTimeField(auto_now_add=True)"},
            {"name": "updated_at", "type": "DateTimeField(auto_now=True)"},
        ],
        "constraints": [
            "UniqueConstraint(fields=['organization', 'code'])",
            "UniqueConstraint(fields=['organization', 'slug'])",
            "UniqueConstraint(fields=['organization', 'name'])",
        ],
        "indexes": [
            "Index(fields=['organization', 'is_active'])",
            "Index(fields=['organization', 'country_code'])",
        ],
        "relationships": [
            "Organization has many OperatingEntity records.",
            "Branch should later point to OperatingEntity and remain under Organization during transition.",
            "Department should remain under Branch, with Organization retained until cleanup.",
            "UserMembership should later include OperatingEntity between Organization and Branch.",
        ],
    }


def current_scope_references():
    rows = []
    target_names = {"Organization", "Branch", "Department"}
    for model in apps.get_models():
        fields = []
        for field in model._meta.get_fields():
            if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
                continue
            remote_model = getattr(field, "remote_field", None) and field.remote_field.model
            if remote_model and remote_model.__name__ in target_names:
                fields.append({"field": field.name, "target": remote_model.__name__, "nullable": getattr(field, "null", False)})
        if fields:
            label = model._meta.label
            rows.append(
                {
                    "model": label,
                    "fields": fields,
                    "operating_entity_need": classify_model(label),
                }
            )
    return sorted(rows, key=lambda row: row["model"])


def classify_model(label):
    if label == "parties.OrganizationBranding":
        return "review_branding_model_separately"
    if label in SCOPE_MODELS_NEEDING_ENTITY:
        return "needs_operating_entity_later"
    if label in {"accounts.Role", "parties.Organization"}:
        return "organization_parent_only"
    return "review_before_migration"


def write_text(stdout, report):
    stdout.write("OperatingEntity model design - Phase 10C")
    stdout.write("=========================================")
    stdout.write("Mode: read-only design")
    stdout.write(f"Organization: {report['target_hierarchy']['organization']}")
    stdout.write(f"Operating entities: {', '.join(report['target_hierarchy']['operating_entities'])}")
    stdout.write("")
    stdout.write("Current scope references:")
    for row in report["current_scope_references"]:
        fields = ", ".join(f"{field['field']}->{field['target']}" for field in row["fields"])
        stdout.write(f"  - {row['model']}: {row['operating_entity_need']} ({fields})")
