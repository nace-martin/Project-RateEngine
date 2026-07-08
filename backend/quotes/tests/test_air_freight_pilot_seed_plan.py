import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import ChargeAlias, ProductCode


class AirFreightPilotSeedPlanCommandTests(TestCase):
    def call_plan(self, *args):
        stdout = StringIO()
        call_command("air_freight_pilot_seed_plan", *args, stdout=stdout)
        return stdout.getvalue()

    def payload(self):
        return json.loads(self.call_plan("--format", "json"))

    def test_command_performs_no_writes(self):
        before = self.counts()
        self.payload()
        self.call_plan("--format", "text")
        self.assertEqual(before, self.counts())

    def test_json_output_is_stable(self):
        payload = self.payload()
        self.assertEqual(
            list(payload.keys()),
            [
                "blocked",
                "charge_alias_actions",
                "conflicts",
                "product_code_actions",
                "recommended_next_actions",
                "status",
                "summary",
                "warnings",
            ],
        )

    def test_candidate_product_codes_are_create_actions_when_missing(self):
        payload = self.payload()
        create_codes = {
            action["candidate"]["code"]
            for action in payload["product_code_actions"]
            if action["action"] == "create"
        }
        self.assertEqual(create_codes, {"IMP-HANDLE-DEST", "IMP-STORAGE-DEST"})

    def test_existing_candidate_product_code_is_reused(self):
        self.product(2042, "IMP-HANDLE-DEST", ProductCode.DOMAIN_IMPORT)
        payload = self.payload()
        action = self.action_for_code(payload, "IMP-HANDLE-DEST")
        self.assertEqual(action["action"], "reuse")
        self.assertEqual(action["existing_id"], 2042)

    def test_product_code_id_conflict_is_reported(self):
        self.product(2042, "IMP-OTHER", ProductCode.DOMAIN_IMPORT)
        payload = self.payload()
        action = self.action_for_code(payload, "IMP-HANDLE-DEST")
        self.assertEqual(action["action"], "conflict")
        self.assertIn("already belongs", action["reason"])

    def test_alias_actions_track_planned_product_code_dependency(self):
        payload = self.payload()
        action = self.alias_action(payload, "import handling", "IMPORT", "DESTINATION")
        self.assertEqual(action["action"], "create_after_product_code")
        self.assertEqual(action["depends_on_product_code"], "IMP-HANDLE-DEST")

    def test_alias_actions_skip_existing_scoped_alias(self):
        product = self.product(1001, "EXP-FRT-AIR", ProductCode.DOMAIN_EXPORT)
        ChargeAlias.objects.create(
            alias_text="freight",
            normalized_alias_text="freight",
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.MAIN,
            product_code=product,
            is_active=True,
            review_status=ChargeAlias.ReviewStatus.APPROVED,
        )
        payload = self.payload()
        action = self.alias_action(payload, "freight", "EXPORT", "MAIN")
        self.assertEqual(action["action"], "skip_existing")

    def test_alias_scope_conflict_is_reported(self):
        target = self.product(1001, "EXP-FRT-AIR", ProductCode.DOMAIN_EXPORT)
        other = self.product(1002, "EXP-FRT-OTHER", ProductCode.DOMAIN_EXPORT)
        ChargeAlias.objects.create(
            alias_text="freight",
            normalized_alias_text="freight",
            match_type=ChargeAlias.MatchType.EXACT,
            mode_scope=ChargeAlias.ModeScope.EXPORT,
            direction_scope=ChargeAlias.DirectionScope.MAIN,
            product_code=other,
            is_active=True,
            review_status=ChargeAlias.ReviewStatus.APPROVED,
        )
        self.assertEqual(target.code, "EXP-FRT-AIR")
        payload = self.payload()
        action = self.alias_action(payload, "freight", "EXPORT", "MAIN")
        self.assertEqual(action["action"], "conflict")

    def test_broad_ambiguous_items_are_blocked(self):
        payload = self.payload()
        blocked = {item["item"] for item in payload["blocked"]}
        self.assertIn("misc_recoveries", blocked)
        self.assertIn("fsc ANY/ANY", blocked)
        self.assertIn("handling generic", blocked)

    def test_text_output_works(self):
        output = self.call_plan("--format", "text")
        self.assertIn("Air Freight pilot seed plan:", output)
        self.assertIn("Recommended next actions:", output)

    def product(self, pk, code, domain):
        return ProductCode.objects.create(
            id=pk,
            code=code,
            description=code,
            domain=domain,
            category=ProductCode.CATEGORY_FREIGHT,
            is_gst_applicable=False,
            gst_rate="0.0000",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="REV",
            gl_cost_code="COS",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )

    def action_for_code(self, payload, code):
        return next(action for action in payload["product_code_actions"] if action["candidate"]["code"] == code)

    def alias_action(self, payload, alias_text, mode_scope, direction_scope):
        return next(
            action
            for action in payload["charge_alias_actions"]
            if action["alias_text"] == alias_text
            and action["mode_scope"] == mode_scope
            and action["direction_scope"] == direction_scope
        )

    def counts(self):
        return {
            "product_code": ProductCode.objects.count(),
            "charge_alias": ChargeAlias.objects.count(),
        }
