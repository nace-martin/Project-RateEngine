import json

from django.core.management.base import BaseCommand

from .rbac_historical_scope_backfill_plan import build_report as build_backfill_report


READY = "READY_FOR_ENFORCEMENT_DESIGN"
NOT_READY = "NOT_READY_FOR_ENFORCEMENT_DESIGN"


SURFACES = [
    {
        "name": "CRM opportunity list/detail",
        "code_path": "backend/crm/views.py:OpportunityViewSet.get_queryset",
        "current_state": "global_unfiltered",
        "required_rule": "filter Opportunity by organization, branch, and department for scoped roles",
    },
    {
        "name": "CRM interaction list/detail",
        "code_path": "backend/crm/views.py:InteractionViewSet.get_queryset",
        "current_state": "global_unfiltered",
        "required_rule": "filter Interaction by direct scope or scoped company/opportunity parent",
    },
    {
        "name": "CRM task list/detail",
        "code_path": "backend/crm/views.py:TaskViewSet.get_queryset",
        "current_state": "global_unfiltered",
        "required_rule": "filter Task by direct scope or scoped company/opportunity parent",
    },
    {
        "name": "Company/customer list",
        "code_path": "backend/parties/views.py:CustomerV3ViewSet.get_queryset",
        "current_state": "global_unfiltered",
        "required_rule": "filter Company by organization, branch, and department for scoped roles",
    },
    {
        "name": "Company selector search",
        "code_path": "backend/parties/views.py:CompanyV3SearchView.get_queryset",
        "current_state": "global_unfiltered",
        "required_rule": "filter selector results to scoped Company records",
    },
    {
        "name": "Contact selector by company",
        "code_path": "backend/parties/views.py:CompanyContactListV3View.get_queryset",
        "current_state": "parent_direct_lookup_unfiltered",
        "required_rule": "authorize parent Company scope before returning Contact rows",
    },
    {
        "name": "Opportunity selectors",
        "code_path": "backend/crm/views.py:OpportunityViewSet.get_queryset",
        "current_state": "global_unfiltered",
        "required_rule": "filter opportunity selector options to scoped Opportunity records",
    },
    {
        "name": "Interaction/Task selectors",
        "code_path": "backend/crm/views.py:InteractionViewSet.get_queryset; backend/crm/views.py:TaskViewSet.get_queryset",
        "current_state": "global_unfiltered",
        "required_rule": "filter interaction and task selector options by scoped parent records",
    },
    {
        "name": "Quote customer detail lookup",
        "code_path": "backend/quotes/views/services.py:CustomerDetailAPIView._get_company",
        "current_state": "partially_scope_filtered",
        "required_rule": "replace legacy owner/quote organization filter with canonical scope checks",
    },
    {
        "name": "Quote compute customer/contact lookup",
        "code_path": "backend/quotes/views/calculation.py:QuoteCalculationAPIView",
        "current_state": "direct_id_lookup_unfiltered",
        "required_rule": "validate customer and contact scope before quote calculation",
    },
    {
        "name": "SPOT customer lookup",
        "code_path": "backend/quotes/spot_views.py",
        "current_state": "direct_id_lookup_unfiltered",
        "required_rule": "validate customer/contact scope before SPE quote creation",
    },
]


class Command(BaseCommand):
    help = "Read-only post-backfill validation and RBAC enforcement readiness diagnostics."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["text", "json"], default="text")

    def handle(self, *args, **options):
        report = build_report()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return
        write_text(self.stdout, report)


def build_report():
    backfill = build_backfill_report()
    summary = backfill["summary"]
    strategy = backfill["proposed_apply_strategy"]
    blockers = []
    if strategy["apply_eligible_records"]:
        blockers.append("apply_eligible_records_remaining")
    if summary["unclassified_records"]:
        blockers.append("unclassified_records_remaining")
    return {
        "write_enabled": False,
        "readiness_status": NOT_READY if blockers else READY,
        "readiness_blockers": blockers,
        "post_backfill": {
            "summary": summary,
            "models": {
                name: {
                    "summary": payload["summary"],
                    "manual_review_exclusions": payload["blocker_reasons"],
                }
                for name, payload in backfill["models"].items()
            },
            "apply_eligible_records": strategy["apply_eligible_records"],
            "manual_review_excluded_records": strategy["manual_review_excluded_records"],
        },
        "enforcement_surfaces": SURFACES,
        "global_or_unfiltered_surfaces": [
            surface for surface in SURFACES if "unfiltered" in surface["current_state"]
        ],
        "proposed_enforcement_rules": proposed_rules(),
        "admin_override_considerations": [
            "admin and superuser may require cross-scope visibility for operations",
            "cross-scope access should be explicit and auditable",
            "non-admin roles should use canonical membership organization/branch/department scope",
        ],
    }


def proposed_rules():
    return [
        {
            "role_scope": "admin",
            "rule": "allow cross-scope access where business-approved; preserve audit trail",
        },
        {
            "role_scope": "manager",
            "rule": "allow records in the user's canonical organization/branch/department scope",
        },
        {
            "role_scope": "sales",
            "rule": "allow own records plus explicitly approved scoped records",
        },
        {
            "role_scope": "finance/system",
            "rule": "define explicit read/write override before enabling enforcement",
        },
    ]


def write_text(stdout, report):
    stdout.write("RBAC enforcement readiness report")
    stdout.write("=================================")
    stdout.write("Mode: read-only diagnostics")
    stdout.write(f"Readiness: {report['readiness_status']}")
    post = report["post_backfill"]
    summary = post["summary"]
    stdout.write(
        "Post-backfill: "
        f"total={summary['total_records']}, complete={summary['records_complete']}, "
        f"missing_org={summary['records_missing_organization']}, "
        f"missing_branch={summary['records_missing_branch']}, "
        f"missing_department={summary['records_missing_department']}, "
        f"apply_eligible={post['apply_eligible_records']}, "
        f"manual_review={post['manual_review_excluded_records']}"
    )
    stdout.write("")
    stdout.write("Surfaces currently global/unfiltered:")
    for surface in report["global_or_unfiltered_surfaces"]:
        stdout.write(f"- {surface['name']}: {surface['current_state']} ({surface['code_path']})")
    stdout.write("")
    stdout.write("Required enforcement rules:")
    for rule in report["proposed_enforcement_rules"]:
        stdout.write(f"- {rule['role_scope']}: {rule['rule']}")
