import sys

from django.core.management.base import BaseCommand
from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v4.commercial_models import CommercialTermsPolicy

from core.models import Policy


class Command(BaseCommand):
    help = "Read-only diagnostics for pricing policy health (Wave 3B2 cutover to CommercialTermsPolicy)"

    def handle(self, *args, **options):
        # 1. Active Calculation Authority: CommercialTermsPolicy
        comm_policies = CommercialTermsPolicy.objects.all().order_by("-valid_from")
        comm_total_count = comm_policies.count()
        comm_active_policies = CommercialTermsPolicy.objects.filter(is_active=True).order_by("-valid_from")
        comm_active_count = comm_active_policies.count()
        latest_comm_active = comm_active_policies.first()

        # Instantiate V4 Adapter with None to see which policy it resolves
        adapter = PricingServiceV4Adapter(None)
        resolved_comm_policy = adapter.get_commercial_terms_policy()

        self.stdout.write(self.style.NOTICE("=== Commercial Terms Policy Health Report (Active Authority) ==="))
        self.stdout.write(f"Total CommercialTermsPolicy records: {comm_total_count}")
        self.stdout.write(f"Active CommercialTermsPolicy records: {comm_active_count}")

        if latest_comm_active:
            self.stdout.write(
                f"Latest active CommercialTermsPolicy: {latest_comm_active.policy_code} "
                f"(valid_from={latest_comm_active.valid_from}, valid_until={latest_comm_active.valid_until or 'indefinite'}, "
                f"margin={latest_comm_active.target_gross_margin_percent}%, "
                f"import_caf={latest_comm_active.import_caf_percent}%, "
                f"export_caf={latest_comm_active.export_caf_percent}%, "
                f"gst={latest_comm_active.gst_standard_percent}%)"
            )
        else:
            self.stdout.write("Latest active CommercialTermsPolicy: None")

        if resolved_comm_policy:
            self.stdout.write(
                f"Adapter resolved CommercialTermsPolicy: {resolved_comm_policy.policy_code} "
                f"(ID: {resolved_comm_policy.id}, margin_rate: {resolved_comm_policy.target_gross_margin_rate})"
            )
        else:
            self.stdout.write(self.style.ERROR("Adapter resolved CommercialTermsPolicy: None (CALCULATION WILL FAIL CLOSED)"))

        # 2. Legacy FK Compatibility: core.Policy
        legacy_policies = Policy.objects.all().order_by("-effective_from")
        legacy_total = legacy_policies.count()
        legacy_active = Policy.objects.filter(is_active=True).count()
        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("=== Legacy core.Policy Status (Historical FK Compatibility Only) ==="))
        self.stdout.write(f"Total legacy core.Policy records: {legacy_total} (active: {legacy_active})")
        self.stdout.write("Note: core.Policy is retained strictly for Quote.policy / QuoteVersion.policy FK compatibility.")

        # 3. Health Check Evaluation
        if comm_active_count != 1:
            self.stdout.write(
                self.style.ERROR(
                    f"\nHealth: ERROR, active CommercialTermsPolicy count is {comm_active_count}, expected exactly 1!"
                )
            )
            if comm_active_count > 1:
                self.stdout.write(self.style.ERROR("Duplicate active commercial terms policies found:"))
                for p in comm_active_policies:
                    self.stdout.write(
                        self.style.ERROR(
                            f" - {p.policy_code} (ID: {p.id}, valid_from: {p.valid_from}, valid_until: {p.valid_until})"
                        )
                    )
            sys.exit(1)

        if resolved_comm_policy is None:
            self.stdout.write(self.style.ERROR("\nHealth: ERROR, adapter failed to resolve an active CommercialTermsPolicy!"))
            sys.exit(1)

        self.stdout.write(self.style.SUCCESS("\nHealth: OK, exactly one active CommercialTermsPolicy resolved"))
