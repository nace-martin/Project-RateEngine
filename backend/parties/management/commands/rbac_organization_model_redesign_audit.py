import json
from collections import Counter, defaultdict

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models

from accounts.models import UserMembership
from parties.models import Branch, Company, Contact, Department, Organization


PARENT_ORGANIZATION = "Express Freight Management"
LEGACY_OPERATING_ENTITIES = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
LEGACY_ARCHIVE_ORGANIZATIONS = ("EFM Express Air Cargo", "Test Org")
LEGACY_EAC_ORGANIZATION = "EFM Express Air Cargo"
TARGET_MODEL = "Option B: add OperatingEntity between Organization and Branch"
SAMPLE_LIMIT = 5


class Command(BaseCommand):
    help = "Read-only Phase 10A audit for corrected organization hierarchy redesign."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        report = build_report()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_report():
    organizations = list(Organization.objects.order_by("name", "id"))
    branches = list(Branch.objects.select_related("organization").order_by("organization__name", "name", "id"))
    departments = list(
        Department.objects.select_related("organization", "branch").order_by("organization__name", "name", "id")
    )
    memberships = list(
        UserMembership.objects.select_related("user", "organization", "branch", "department", "role").order_by(
            "organization__name", "user__username", "id"
        )
    )
    dependency_counts = fk_dependency_counts()

    return {
        "phase": "10A",
        "write_enabled": False,
        "business_rule": (
            "Express Freight Management is the only organization. EFM PNG, EFM Australia, EFM Fiji, "
            "and EFM Solomon Islands are not organizations."
        ),
        "current_counts": {
            "organizations": len(organizations),
            "branches": len(branches),
            "departments": len(departments),
            "user_memberships": len(memberships),
        },
        "organizations": organization_rows(organizations),
        "branches": branch_rows(branches),
        "departments": department_rows(departments),
        "memberships": membership_report(memberships),
        "scoped_records": scoped_record_report(),
        "quote_spot_productcode": quote_spot_productcode_report(),
        "fk_dependencies": dependency_counts,
        "migration_classification": migration_classification(organizations, branches, departments),
        "duplicate_risks": duplicate_risks(branches, departments),
        "recommended_target_model": recommended_target_model(),
        "risks": risks(dependency_counts),
        "migration_steps": migration_steps(),
        "rollback_plan": rollback_plan(),
        "test_strategy": test_strategy(),
    }


def organization_rows(organizations):
    rows = []
    for org in organizations:
        rows.append(
            {
                "id": str(org.id),
                "name": safe(org.name),
                "slug": safe(org.slug),
                "is_active": org.is_active,
                "classification": classify_organization(org.name),
                "branch_count": Branch.objects.filter(organization=org).count(),
                "department_count": Department.objects.filter(organization=org).count(),
                "membership_count": UserMembership.objects.filter(organization=org).count(),
            }
        )
    return rows


def branch_rows(branches):
    return [
        {
            "id": str(branch.id),
            "name": safe(branch.name),
            "code": safe(branch.code),
            "organization": safe(branch.organization.name),
            "classification": "migrate/reparent" if branch.organization.name != PARENT_ORGANIZATION else "canonical keep",
            "department_count": Department.objects.filter(branch=branch).count(),
            "membership_count": UserMembership.objects.filter(branch=branch).count(),
        }
        for branch in branches
    ]


def department_rows(departments):
    return [
        {
            "id": str(department.id),
            "name": safe(department.name),
            "code": safe(department.code),
            "organization": safe(department.organization.name),
            "branch": safe(department.branch.name) if department.branch else "",
            "classification": (
                "migrate/reparent"
                if department.organization.name != PARENT_ORGANIZATION
                else "canonical keep"
            ),
            "membership_count": UserMembership.objects.filter(department=department).count(),
        }
        for department in departments
    ]


def membership_report(memberships):
    rows = []
    by_status = Counter()
    for membership in memberships:
        status = "canonical keep" if membership.organization.name == PARENT_ORGANIZATION else "migrate/reparent"
        if membership.organization.name == LEGACY_EAC_ORGANIZATION:
            status = "migrate/reparent"
        by_status[status] += 1
        rows.append(
            {
                "id": membership.id,
                "username": safe(membership.user.username),
                "organization": safe(membership.organization.name),
                "branch": safe(membership.branch.name) if membership.branch else "",
                "department": safe(membership.department.name) if membership.department else "",
                "role": safe(membership.role.code) if membership.role else "",
                "is_active": membership.is_active,
                "classification": status,
            }
        )
    return {"count": len(memberships), "by_classification": dict(sorted(by_status.items())), "samples": rows[:SAMPLE_LIMIT]}


def scoped_record_report():
    specs = (
        ("parties.Company", Company),
        ("parties.Contact", Contact),
        ("crm.Opportunity", apps.get_model("crm", "Opportunity")),
        ("crm.Interaction", apps.get_model("crm", "Interaction")),
        ("crm.Task", apps.get_model("crm", "Task")),
        ("quotes.Quote", apps.get_model("quotes", "Quote")),
        ("quotes.SpotPricingEnvelopeDB", apps.get_model("quotes", "SpotPricingEnvelopeDB")),
        ("shipments.Shipment", apps.get_model("shipments", "Shipment")),
    )
    return {label: scoped_model_summary(model) for label, model in specs}


def scoped_model_summary(model):
    fields = {field.name: field for field in model._meta.fields}
    summary = {"total": model.objects.count()}
    for field in ("organization", "branch", "department"):
        model_field = fields.get(field)
        if isinstance(model_field, models.ForeignKey):
            summary[f"with_{field}"] = model.objects.filter(**{f"{field}__isnull": False}).count()
            if field == "organization":
                legacy_filter = {f"{field}__name__in": legacy_org_names()}
            else:
                legacy_filter = {f"{field}__organization__name__in": legacy_org_names()}
            summary[f"legacy_{field}"] = model.objects.filter(**legacy_filter).count()
    summary["samples"] = sample_rows(model.objects.order_by("pk")[:SAMPLE_LIMIT])
    return summary


def quote_spot_productcode_report():
    ProductCode = apps.get_model("pricing_v4", "ProductCode")
    SPEChargeLineDB = apps.get_model("quotes", "SPEChargeLineDB")
    return {
        "quotes": scoped_model_summary(apps.get_model("quotes", "Quote")),
        "spot_envelopes": scoped_model_summary(apps.get_model("quotes", "SpotPricingEnvelopeDB")),
        "product_codes": {
            "total": ProductCode.objects.count(),
            "note": "ProductCode has no organization/branch/department FK; affected indirectly through rate ownership, SPOT charge resolution, and quote calculation context.",
            "charge_lines_with_resolved_product_code": SPEChargeLineDB.objects.filter(resolved_product_code__isnull=False).count(),
            "charge_lines_with_manual_resolved_product_code": SPEChargeLineDB.objects.filter(
                manual_resolved_product_code__isnull=False
            ).count(),
        },
    }


def fk_dependency_counts():
    targets = {
        Organization: "organization",
        Branch: "branch",
        Department: "department",
    }
    rows = []
    for model in sorted(apps.get_models(), key=lambda m: m._meta.label):
        for field in model._meta.fields:
            if isinstance(field, models.ForeignKey) and field.remote_field.model in targets:
                legacy_filter = {f"{field.name}__name__in": legacy_org_names()}
                if field.remote_field.model is Branch:
                    legacy_filter = {f"{field.name}__organization__name__in": legacy_org_names()}
                if field.remote_field.model is Department:
                    legacy_filter = {f"{field.name}__organization__name__in": legacy_org_names()}
                queryset = model.objects.filter(**{f"{field.name}__isnull": False})
                rows.append(
                    {
                        "model": model._meta.label,
                        "field": field.name,
                        "target": targets[field.remote_field.model],
                        "on_delete": getattr(field.remote_field.on_delete, "__name__", str(field.remote_field.on_delete)),
                        "non_null_count": queryset.count(),
                        "legacy_scope_count": model.objects.filter(**legacy_filter).count(),
                        "samples": sample_rows(queryset.order_by("pk")[:SAMPLE_LIMIT]),
                    }
                )
    return rows


def migration_classification(organizations, branches, departments):
    return {
        "organizations": Counter(classify_organization(org.name) for org in organizations),
        "branches": Counter("migrate/reparent" if b.organization.name != PARENT_ORGANIZATION else "canonical keep" for b in branches),
        "departments": Counter(
            "migrate/reparent" if d.organization.name != PARENT_ORGANIZATION else "canonical keep" for d in departments
        ),
        "labels": {
            "canonical keep": "Express Freight Management and any already-correct child rows.",
            "migrate/reparent": "Operating entities, branches, departments, memberships, and scoped records under legacy organizations.",
            "archive/deactivate": "EFM Express Air Cargo and Test Org organization records after dependencies move.",
            "delete only if safely unused": "Legacy organization rows with zero FK dependencies after audited migration.",
        },
    }


def duplicate_risks(branches, departments):
    branch_names = defaultdict(set)
    department_names = defaultdict(set)
    for branch in branches:
        branch_names[branch.name.casefold()].add(branch.organization.name)
    for department in departments:
        department_names[department.name.casefold()].add(department.organization.name)
    return {
        "duplicated_branches_under_legacy_organizations": [
            {"name": name, "organizations": sorted(orgs)}
            for name, orgs in sorted(branch_names.items())
            if len(orgs) > 1
        ],
        "duplicated_departments_under_legacy_organizations": [
            {"name": name, "organizations": sorted(orgs)}
            for name, orgs in sorted(department_names.items())
            if len(orgs) > 1
        ],
    }


def recommended_target_model():
    return {
        "selected": TARGET_MODEL,
        "option_a": "Keep current tables and overload Branch as operating entity/branch hybrid. Fast, but ambiguous.",
        "option_b": "Add OperatingEntity between Organization and Branch. Cleanest match to the corrected business hierarchy.",
        "option_c": "Launch patch: keep one Organization, reparent current Branch/Department rows, defer OperatingEntity. Lowest short-term migration, but preserves naming debt.",
        "reason": "Country division is a real business level, not the same thing as a physical branch.",
    }


def risks(dependencies):
    legacy_refs = sum(row["legacy_scope_count"] for row in dependencies)
    return [
        f"{legacy_refs} FK references currently point at legacy organization/branch/department scope.",
        "Current uniqueness constraints are per organization, so branch and department code collisions can block a one-organization collapse.",
        "OrganizationBranding is one-to-one with Organization; branding must be separated from country/division identity before collapse.",
        "Existing RBAC readiness tooling still treats EFM PNG/Australia/Fiji/Solomons as canonical organizations and must be revised in a later PR.",
        "EAC wording must move to Air Freight department semantics without reviving EFM Express Air Cargo as a tenant.",
    ]


def migration_steps():
    return [
        "Freeze writes to organization/branch/department master data during migration window.",
        "Create or confirm Express Freight Management as the single Organization.",
        "Introduce OperatingEntity model or approved launch shim before moving country-level rows.",
        "Map EFM PNG, EFM Australia, EFM Fiji, and EFM Solomon Islands to operating entities.",
        "Reparent branches, departments, memberships, CRM/customer, quote, SPOT, shipment, role, and branding dependencies.",
        "Archive/deactivate legacy organization rows only after dependency counts reach zero.",
        "Run selectors, quote, SPOT, CRM, and RBAC regression checks before enforcement changes.",
    ]


def rollback_plan():
    return [
        "Keep pre-migration ID mapping for every organization, branch, department, and scoped record.",
        "Run migration in one transaction where practical; otherwise checkpoint per dependency group.",
        "Restore old FK values from the mapping table if validation fails before cutover.",
        "Do not delete legacy rows in the launch migration; archive only after a separate zero-dependency audit.",
    ]


def test_strategy():
    return [
        "Assert this command is read-only and reports write_enabled=false.",
        "Assert multiple Organization rows are detected.",
        "Assert EFM Express Air Cargo is classified as legacy Air Freight wording, not an organization.",
        "Assert duplicated branch and department names across legacy organizations are reported.",
        "Assert memberships and scoped CRM/customer/quote/SPOT records are counted.",
        "Assert JSON includes migration_classification and recommended_target_model.",
    ]


def classify_organization(name):
    if name == PARENT_ORGANIZATION:
        return "canonical keep"
    if name in LEGACY_OPERATING_ENTITIES:
        return "migrate/reparent"
    if name in LEGACY_ARCHIVE_ORGANIZATIONS:
        return "archive/deactivate"
    return "delete only if safely unused"


def legacy_org_names():
    return LEGACY_OPERATING_ENTITIES + LEGACY_ARCHIVE_ORGANIZATIONS


def sample_rows(queryset):
    rows = []
    for obj in queryset:
        rows.append({"id": safe(obj.pk), "label": safe(obj)})
    return rows


def safe(value):
    return str(value or "").encode("ascii", "replace").decode("ascii")


def write_text(stdout, report):
    stdout.write("RBAC organization model redesign audit - Phase 10A")
    stdout.write("==================================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(f"Business rule: {report['business_rule']}")
    stdout.write(f"Recommended target model: {report['recommended_target_model']['selected']}")
    stdout.write("")
    counts = report["current_counts"]
    stdout.write(
        "Current counts: "
        f"organizations={counts['organizations']}, branches={counts['branches']}, "
        f"departments={counts['departments']}, memberships={counts['user_memberships']}"
    )
    stdout.write("")
    stdout.write("Organizations:")
    for org in report["organizations"]:
        stdout.write(f"  - {org['name']} [{org['classification']}] branches={org['branch_count']} departments={org['department_count']} memberships={org['membership_count']}")
    stdout.write("")
    stdout.write("Dependency counts:")
    for row in report["fk_dependencies"]:
        stdout.write(
            f"  - {row['model']}.{row['field']} -> {row['target']}: "
            f"non_null={row['non_null_count']} legacy_scope={row['legacy_scope_count']} on_delete={row['on_delete']}"
        )
    stdout.write("")
    stdout.write("Risks/blockers:")
    for risk in report["risks"]:
        stdout.write(f"  - {risk}")
