import sys
from django.core.management.base import BaseCommand
from core.models import Policy
from pricing_v4.adapter import PricingServiceV4Adapter

class Command(BaseCommand):
    help = "Read-only diagnostics for pricing policy health"

    def handle(self, *args, **options):
        policies = Policy.objects.all().order_by("-effective_from")
        total_count = policies.count()
        
        active_policies = Policy.objects.filter(is_active=True).order_by("-effective_from")
        active_count = active_policies.count()
        
        latest_overall = Policy.objects.order_by("-effective_from").first()
        latest_active = active_policies.first()
        
        # Instantiate V4 Adapter with None to see which policy it resolves
        adapter = PricingServiceV4Adapter(None)
        resolved_policy = getattr(adapter, "policy", None)
        
        self.stdout.write(self.style.NOTICE("=== Pricing Policy Health Report ==="))
        self.stdout.write(f"Total policies in database: {total_count}")
        
        if latest_overall:
            status_str = "active" if latest_overall.is_active else "inactive"
            self.stdout.write(f"Latest policy overall: {latest_overall.name} ({status_str})")
        else:
            self.stdout.write("Latest policy overall: None")
            
        if latest_active:
            self.stdout.write(f"Latest active policy: {latest_active.name}")
        else:
            self.stdout.write("Latest active policy: None")
            
        if resolved_policy:
            self.stdout.write(f"Selected pricing policy: {resolved_policy.name} (ID: {resolved_policy.id}, margin_pct: {resolved_policy.margin_pct})")
        else:
            self.stdout.write("Selected pricing policy: None")
            
        if active_count != 1:
            self.stdout.write(self.style.ERROR(f"Health: ERROR, active policy count is {active_count}, expected exactly 1!"))
            if active_count > 1:
                self.stdout.write(self.style.ERROR("Duplicate active policies found:"))
                for p in active_policies:
                    self.stdout.write(self.style.ERROR(f" - {p.name} (ID: {p.id}, margin_pct: {p.margin_pct}, effective_from: {p.effective_from})"))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("Health: OK, exactly one active policy"))
