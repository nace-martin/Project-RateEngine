from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from quotes.services.air_journey_planner import AirJourneyPlanner
from quotes.services.journey_persistence import get_route_policy_state


class Command(BaseCommand):
    help = "Read-only Phase 16E-A air journey planner diagnostics for supplied JourneyRequest JSON."

    def add_arguments(self, parser):
        parser.add_argument("--request", required=True, help="JourneyRequest JSON payload.")
        parser.add_argument("--format", choices=["json"], default="json")

    def handle(self, *args, **options):
        try:
            payload = json.loads(options["request"])
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid --request JSON: {exc}") from exc

        plan = AirJourneyPlanner().plan(payload)
        policy = get_route_policy_state(plan.pattern.value if plan.pattern else None)
        output = {
            "normalized_request": plan.request.to_dict(),
            "direction": plan.direction.value if plan.direction else None,
            "pattern": plan.pattern.value if plan.pattern else None,
            "gateway": plan.gateway_code,
            "legs": [leg.to_dict() for leg in plan.legs],
            "fingerprint": plan.input_fingerprint,
            "blockers": [blocker.value for blocker in plan.blockers],
            "route_policy": policy.to_dict(),
            "writes_performed": False,
        }
        self.stdout.write(json.dumps(output, indent=2, sort_keys=True))
