from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from pricing_v4.management.commands.seed_charge_aliases import PACK_A_ALIASES
from pricing_v4.models import ChargeAlias, ProductCode
from quotes.services.charge_normalization import NormalizationStatus, resolve_charge_alias


class SeedChargeAliasesCommandTests(TestCase):
    def test_dry_run_reports_creates_without_writing_aliases(self):
        self._seed_pack_a_product_codes()

        stdout = StringIO()
        call_command("seed_charge_aliases", "--dry-run", stdout=stdout)

        self.assertEqual(ChargeAlias.objects.count(), 0)
        output = stdout.getvalue()
        self.assertIn("Mode: DRY RUN", output)
        self.assertIn(f"- Created: {len(PACK_A_ALIASES)}", output)
        self.assertIn("- Missing ProductCodes: 0", output)

    def test_apply_is_idempotent_and_updates_existing_target_alias(self):
        products = self._seed_pack_a_product_codes()
        target_row = PACK_A_ALIASES[0]
        ChargeAlias.objects.create(
            alias_text=target_row.alias_text,
            match_type=target_row.match_type,
            mode_scope=target_row.mode_scope,
            direction_scope=target_row.direction_scope,
            product_code=products[target_row.product_code_code],
            priority=999,
            is_active=False,
            notes="old seed",
        )

        first_stdout = StringIO()
        call_command("seed_charge_aliases", stdout=first_stdout)

        target_alias = ChargeAlias.objects.get(
            normalized_alias_text=ChargeAlias.normalize_alias_text_value(target_row.alias_text),
            match_type=target_row.match_type,
            mode_scope=target_row.mode_scope,
            direction_scope=target_row.direction_scope,
            product_code=products[target_row.product_code_code],
        )
        self.assertEqual(target_alias.priority, target_row.priority)
        self.assertTrue(target_alias.is_active)
        self.assertEqual(target_alias.alias_source, ChargeAlias.AliasSource.SEED)
        self.assertEqual(target_alias.review_status, ChargeAlias.ReviewStatus.APPROVED)
        self.assertEqual(target_alias.notes, target_row.notes)
        self.assertEqual(ChargeAlias.objects.count(), len(PACK_A_ALIASES))
        self.assertIn("- Updated: 1", first_stdout.getvalue())

        second_stdout = StringIO()
        call_command("seed_charge_aliases", stdout=second_stdout)

        self.assertEqual(ChargeAlias.objects.count(), len(PACK_A_ALIASES))
        self.assertIn(f"- Skipped: {len(PACK_A_ALIASES)}", second_stdout.getvalue())

    def test_missing_product_codes_are_reported_and_raise_command_error(self):
        stdout = StringIO()

        with self.assertRaises(CommandError) as exc:
            call_command("seed_charge_aliases", stdout=stdout)

        self.assertIn("Missing ProductCode code(s)", str(exc.exception))
        self.assertIn("- Missing ProductCodes:", stdout.getvalue())
        self.assertEqual(ChargeAlias.objects.count(), 0)

    def test_active_conflict_is_reported_and_conflicting_seed_row_is_skipped(self):
        products = self._seed_pack_a_product_codes()
        conflict_product = ProductCode.objects.create(
            id=1999,
            code="EXP-CONFLICT",
            description="Export Conflict Product",
            domain=ProductCode.DOMAIN_EXPORT,
            category=ProductCode.CATEGORY_HANDLING,
            is_gst_applicable=False,
            gst_rate="0.00",
            gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
            gl_revenue_code="4199",
            gl_cost_code="5199",
            default_unit=ProductCode.UNIT_SHIPMENT,
        )
        target_row = PACK_A_ALIASES[0]
        ChargeAlias.objects.create(
            alias_text=target_row.alias_text.lower(),
            match_type=target_row.match_type,
            mode_scope=target_row.mode_scope,
            direction_scope=target_row.direction_scope,
            product_code=conflict_product,
            priority=target_row.priority,
            is_active=True,
        )

        stdout = StringIO()
        call_command("seed_charge_aliases", stdout=stdout)

        output = stdout.getvalue()
        self.assertIn("active conflict", output)
        self.assertFalse(
            ChargeAlias.objects.filter(
                normalized_alias_text=ChargeAlias.normalize_alias_text_value(target_row.alias_text),
                match_type=target_row.match_type,
                mode_scope=target_row.mode_scope,
                direction_scope=target_row.direction_scope,
                product_code=products[target_row.product_code_code],
            ).exists()
        )

    def test_china_agent_import_labels_resolve_after_seeding(self):
        products = self._seed_pack_a_product_codes()
        call_command("seed_charge_aliases")

        expectations = [
            ("HANDLE", "ORIGIN", "IMP-CTO-ORIGIN"),
            ("HANDLING FEE", "ORIGIN", "IMP-CTO-ORIGIN"),
            ("CUS", "ORIGIN", "IMP-CUS-CLR-ORIGIN"),
            ("CUSTOMS CLEARANCE", "ORIGIN", "IMP-CUS-CLR-ORIGIN"),
            ("EXPORT LICENSE", "ORIGIN", "IMP-PRM-ORIGIN"),
            ("PICKUP CHARGE", "ORIGIN", "IMP-PICKUP"),
            ("PICK UP+GATE IN", "ORIGIN", "IMP-PICKUP"),
            ("A/F", "MAIN", "IMP-FRT-AIR"),
            ("AIR FREIGHT", "MAIN", "IMP-FRT-AIR"),
        ]

        for label, direction_scope, product_code_code in expectations:
            result = resolve_charge_alias(
                label,
                mode_scope=ChargeAlias.ModeScope.IMPORT,
                direction_scope=direction_scope,
            )
            self.assertEqual(result.normalization_status, NormalizationStatus.MATCHED, label)
            self.assertEqual(result.resolved_product_code, products[product_code_code], label)

        self.assertEqual(products["IMP-PRM-ORIGIN"].category, ProductCode.CATEGORY_REGULATORY)
        self.assertEqual(products["IMP-CUS-CLR-ORIGIN"].category, ProductCode.CATEGORY_CLEARANCE)

    def test_generic_handling_and_clearance_labels_remain_unmapped(self):
        self._seed_pack_a_product_codes()
        call_command("seed_charge_aliases")

        for label in ("HANDLING", "CLEARANCE", "SERVICE FEE"):
            result = resolve_charge_alias(
                label,
                mode_scope=ChargeAlias.ModeScope.IMPORT,
                direction_scope=ChargeAlias.DirectionScope.ORIGIN,
            )
            self.assertEqual(result.normalization_status, NormalizationStatus.UNMAPPED, label)

    def _seed_pack_a_product_codes(self):
        products = {}
        counters = {
            ProductCode.DOMAIN_EXPORT: 1100,
            ProductCode.DOMAIN_IMPORT: 2100,
            ProductCode.DOMAIN_DOMESTIC: 3100,
        }

        for code in sorted({row.product_code_code for row in PACK_A_ALIASES}):
            domain = self._domain_for_code(code)
            existing = ProductCode.objects.filter(code=code).first()
            if existing:
                products[code] = existing
                continue

            counters[domain] += 1
            products[code] = ProductCode.objects.create(
                id=counters[domain],
                code=code,
                description=f"{code} test product",
                domain=domain,
                category=self._category_for_code(code),
                is_gst_applicable=False,
                gst_rate="0.00",
                gst_treatment=ProductCode.GST_TREATMENT_ZERO_RATED,
                gl_revenue_code="4100",
                gl_cost_code="5100",
                default_unit=ProductCode.UNIT_SHIPMENT,
            )
        return products

    @staticmethod
    def _domain_for_code(code: str):
        if code.startswith("EXP-"):
            return ProductCode.DOMAIN_EXPORT
        if code.startswith("IMP-"):
            return ProductCode.DOMAIN_IMPORT
        if code.startswith("DOM-"):
            return ProductCode.DOMAIN_DOMESTIC
        raise AssertionError(f"Unhandled ProductCode prefix for {code}")

    @staticmethod
    def _category_for_code(code: str):
        if code == "IMP-PRM-ORIGIN":
            return ProductCode.CATEGORY_REGULATORY
        if code in {"IMP-CUS-CLR-ORIGIN", "IMP-CLEAR"}:
            return ProductCode.CATEGORY_CLEARANCE
        if "FRT" in code:
            return ProductCode.CATEGORY_FREIGHT
        if "DOC" in code or "AWB" in code:
            return ProductCode.CATEGORY_DOCUMENTATION
        if "PICKUP" in code or "CARTAGE" in code or "DELIVERY" in code:
            return ProductCode.CATEGORY_CARTAGE
        if "AGENCY" in code:
            return ProductCode.CATEGORY_AGENCY
        if "SCREEN" in code:
            return ProductCode.CATEGORY_SCREENING
        if "FSC" in code:
            return ProductCode.CATEGORY_SURCHARGE
        return ProductCode.CATEGORY_HANDLING
