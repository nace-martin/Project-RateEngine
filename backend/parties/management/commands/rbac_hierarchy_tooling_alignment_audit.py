import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand

from parties.models import Branch, Department, Organization


ROOT = Path(__file__).resolve().parents[4]
ONLY_ORGANIZATION = "Express Freight Management"
COUNTRY_ENTITIES = ("EFM PNG", "EFM Australia", "EFM Fiji", "EFM Solomon Islands")
BRANCHES = ("Port Moresby", "Lae", "Brisbane", "Suva", "Honiara")
DEPARTMENTS = ("Air Freight", "Sea Freight", "Customs", "Transport")
LEGACY_EAC = ("EAC", "EFM Express Air Cargo", "Express Air Cargo")

ASSUMPTIONS = (
    {
        "path": "backend/parties/management/commands/rbac_post_membership_apply_readiness.py",
        "assumption": "Treats EFM PNG/Australia/Fiji/Solomon Islands as canonical organizations for backfill readiness.",
        "classification": "requires OperatingEntity model",
        "reason": "Readiness needs to validate one parent Organization plus operating-entity membership semantics that do not exist yet.",
    },
    {
        "path": "backend/parties/management/commands/rbac_master_data_alignment_plan.py",
        "assumption": "Plans target country entities as Organization rows.",
        "classification": "requires OperatingEntity model",
        "reason": "The command should become an OperatingEntity/Branch/Department plan after the model exists.",
    },
    {
        "path": "backend/parties/management/commands/rbac_master_data_seed_alignment.py",
        "assumption": "Can create country entities as Organization rows.",
        "classification": "requires migration phase",
        "reason": "It is an apply-capable command and must not be retargeted until schema and migration plan are approved.",
    },
    {
        "path": "backend/parties/management/commands/rbac_membership_reassignment_plan.py",
        "assumption": "Suggests memberships into country-as-organization targets.",
        "classification": "requires OperatingEntity model",
        "reason": "Membership target shape cannot be corrected without somewhere to store operating entity.",
    },
    {
        "path": "backend/parties/management/commands/rbac_membership_reassignment_csv_draft.py",
        "assumption": "CSV targets use target_organization for country entities.",
        "classification": "requires OperatingEntity model",
        "reason": "CSV shape needs operating-entity columns before it can safely replace target organization semantics.",
    },
    {
        "path": "backend/parties/management/commands/rbac_membership_reassignment_table_validate.py",
        "assumption": "Validates country entities as canonical target organizations.",
        "classification": "requires OperatingEntity model",
        "reason": "Validator should reject country-as-organization targets after target schema changes.",
    },
    {
        "path": "backend/parties/management/commands/rbac_final_user_blocker_resolution_plan.py",
        "assumption": "Hardcodes sysadmin target as EFM PNG / Port Moresby / Air Freight.",
        "classification": "requires OperatingEntity model",
        "reason": "The corrected target is Express Freight Management plus EFM PNG operating entity, not EFM PNG organization.",
    },
    {
        "path": "backend/parties/management/commands/rbac_final_user_blocker_resolution_apply.py",
        "assumption": "Apply path can move users into EFM PNG organization.",
        "classification": "requires migration phase",
        "reason": "Apply logic must stay frozen until schema, migration, and rollback mappings exist.",
    },
    {
        "path": "backend/parties/management/commands/rbac_hierarchy_report.py",
        "assumption": "Describes country entities as intended operating entities but still measures them as Organization rows.",
        "classification": "safe to update now",
        "reason": "It is read-only and can be reframed to report the corrected hierarchy as stale until OperatingEntity exists.",
    },
    {
        "path": "backend/parties/tests.py",
        "assumption": "RBAC diagnostic tests assert country entities are canonical organizations in older phases.",
        "classification": "safe to update now",
        "reason": "Tests can add Phase 10B coverage without changing older command behavior in this PR.",
    },
    {
        "path": "docs/rbac-organisation-audit-plan.md",
        "assumption": "Older sections describe EFM PNG/Australia/Fiji/Solomons as Organization targets.",
        "classification": "safe to update now",
        "reason": "The doc is the running audit record and should explicitly mark those sections as superseded by Phase 10A/10B.",
    },
    {
        "path": "docs/beta-readiness-efm.md",
        "assumption": "Beta docs still present EFM Express Air Cargo as the organization/workspace.",
        "classification": "should be retired",
        "reason": "EAC is legacy Air Freight wording and should not remain live RBAC organization guidance.",
    },
    {
        "path": "docs/tenant-model-beta.md",
        "assumption": "Tenant beta notes still use EFM Express Air Cargo as organization wording.",
        "classification": "should be retired",
        "reason": "Superseded beta tenant wording conflicts with the corrected hierarchy.",
    },
)


class Command(BaseCommand):
    help = "Read-only Phase 10B audit of stale RBAC hierarchy tooling assumptions."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        report = build_report()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_report():
    rows = [assumption_row(item) for item in ASSUMPTIONS]
    return {
        "phase": "10B",
        "write_enabled": False,
        "corrected_hierarchy": {
            "organization": ONLY_ORGANIZATION,
            "operating_entities": list(COUNTRY_ENTITIES),
            "branches": list(BRANCHES),
            "departments": list(DEPARTMENTS),
            "legacy_eac_rule": "EFM Express Air Cargo / EAC is Air Freight wording only, not an organization.",
        },
        "current_master_data": current_master_data(),
        "summary": dict(sorted(Counter(row["classification"] for row in rows).items())),
        "stale_assumptions": rows,
        "next_steps": [
            "Keep apply-capable commands frozen until an OperatingEntity schema and migration plan exist.",
            "Update read-only hierarchy wording before any enforcement or selector changes.",
            "Retire beta EAC organization docs after replacement launch guidance exists.",
        ],
    }


def assumption_row(item):
    source = read_source(item["path"])
    return {
        **item,
        "exists": source is not None,
        "mentions_country_as_organization": bool(source and all(name in source for name in COUNTRY_ENTITIES)),
        "mentions_legacy_eac": bool(source and any(name in source for name in LEGACY_EAC)),
    }


def current_master_data():
    return {
        "organizations": {
            "total": Organization.objects.count(),
            "express_freight_management_exists": Organization.objects.filter(name=ONLY_ORGANIZATION).exists(),
            "country_entities_still_stored_as_organizations": list(
                Organization.objects.filter(name__in=COUNTRY_ENTITIES).order_by("name").values_list("name", flat=True)
            ),
            "legacy_eac_organization_exists": Organization.objects.filter(name="EFM Express Air Cargo").exists(),
        },
        "branches": {
            "total": Branch.objects.count(),
            "expected_names_present": list(
                Branch.objects.filter(name__in=BRANCHES).order_by("name").values_list("name", flat=True).distinct()
            ),
        },
        "departments": {
            "total": Department.objects.count(),
            "expected_names_present": list(
                Department.objects.filter(name__in=DEPARTMENTS).order_by("name").values_list("name", flat=True).distinct()
            ),
        },
    }


def read_source(relative_path):
    path = ROOT / relative_path
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(stdout, report):
    stdout.write("RBAC hierarchy tooling alignment audit - Phase 10B")
    stdout.write("==================================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(f"Correct organization: {report['corrected_hierarchy']['organization']}")
    stdout.write(f"Summary: {report['summary']}")
    stdout.write("")
    stdout.write("Stale assumptions:")
    for row in report["stale_assumptions"]:
        stdout.write(
            f"  - {row['path']}: {row['classification']} "
            f"(country_orgs={row['mentions_country_as_organization']}, eac={row['mentions_legacy_eac']})"
        )
