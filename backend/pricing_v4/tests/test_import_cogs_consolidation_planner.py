from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from pricing_v4.models import Agent, ImportCOGS, ProductCode
from pricing_v4.services.import_cogs_scope import ImportCOGSScope
from pricing_v4.engine.import_engine import ImportPricingEngine, ServiceScope, PaymentTerm


class ImportCOGSConsolidationPlannerTests(TestCase):
    def setUp(self):
        self.valid_from = date.today() - timedelta(days=1)
        self.valid_until = date.today() + timedelta(days=30)
        self.agent = Agent.objects.create(code="EFM-AU", name="EFM Australia", country_code="AU", agent_type="ORIGIN")
        self.doc_origin = ProductCode.objects.create(
            id=2001,
            code="IMP-DOC-ORIGIN",
            description="Origin Documentation",
            category="DOCUMENTATION",
            domain="IMPORT",
            default_unit="SHIPMENT",
            is_gst_applicable=True,
        )
        self.pickup = ProductCode.objects.create(
            id=2002,
            code="IMP-PICKUP",
            description="Origin Pickup",
            category="PICKUP",
            domain="IMPORT",
            default_unit="KG",
            is_gst_applicable=True,
        )

    def test_safe_duplicate_groups_are_detected(self):
        # Create 3 rows for IMP-DOC-ORIGIN from BNE to different destinations
        # These are safe to consolidate because they are identical in all required fields
        r1 = self._create_cogs(self.doc_origin, "BNE", "POM", Decimal("80.00"))
        r2 = self._create_cogs(self.doc_origin, "BNE", "LAE", Decimal("80.00"))
        r3 = self._create_cogs(self.doc_origin, "BNE", "MAG", Decimal("80.00"))

        out = StringIO()
        call_command("plan_import_cogs_consolidation", stdout=out)
        output = out.getvalue()

        self.assertIn("[GROUP] IMP-DOC-ORIGIN (ORIGIN)", output)
        self.assertIn("Target: BNE -> *", output)
        self.assertIn(f"- #{r1.id} BNE->POM", output)
        self.assertIn(f"- #{r2.id} BNE->LAE", output)
        self.assertIn(f"- #{r3.id} BNE->MAG", output)
        self.assertIn("Safe to consolidate: YES", output)
        self.assertIn("Replace 3 rows with 1 normalized row.", output)

    def test_differing_rates_are_not_grouped_together(self):
        # Different rates for same product/origin
        r1 = self._create_cogs(self.doc_origin, "BNE", "POM", Decimal("80.00"))
        r2 = self._create_cogs(self.doc_origin, "BNE", "LAE", Decimal("90.00")) # Different amount

        out = StringIO()
        call_command("plan_import_cogs_consolidation", stdout=out)
        output = out.getvalue()

        # They should be reported as two separate SINGLE rows (candidates for normalization, but not consolidation together)
        self.assertIn(f"[SINGLE] IMP-DOC-ORIGIN (ORIGIN)\n  Current: BNE->POM (ID #{r1.id})", output)
        self.assertIn(f"[SINGLE] IMP-DOC-ORIGIN (ORIGIN)\n  Current: BNE->LAE (ID #{r2.id})", output)
        self.assertNotIn("[GROUP] IMP-DOC-ORIGIN", output)

    def test_differing_agents_are_not_grouped_together(self):
        agent2 = Agent.objects.create(code="OTHER-AG", name="Other Agent", country_code="AU")
        r1 = self._create_cogs(self.doc_origin, "BNE", "POM", Decimal("80.00"), agent=self.agent)
        r2 = self._create_cogs(self.doc_origin, "BNE", "LAE", Decimal("80.00"), agent=agent2)

        out = StringIO()
        call_command("plan_import_cogs_consolidation", stdout=out)
        output = out.getvalue()

        self.assertIn(f"ID #{r1.id}", output)
        self.assertIn(f"ID #{r2.id}", output)
        self.assertNotIn("[GROUP]", output)

    def test_differing_validity_is_not_grouped_together(self):
        r1 = self._create_cogs(self.doc_origin, "BNE", "POM", Decimal("80.00"))
        r2 = self._create_cogs(self.doc_origin, "BNE", "LAE", Decimal("80.00"))
        r2.valid_from = self.valid_from + timedelta(days=1)
        r2.save()

        out = StringIO()
        call_command("plan_import_cogs_consolidation", stdout=out)
        output = out.getvalue()

        self.assertNotIn("[GROUP]", output)

    def test_command_is_dry_run_only_and_no_rows_mutated(self):
        self._create_cogs(self.doc_origin, "BNE", "POM", Decimal("80.00"))
        
        initial_ids = set(ImportCOGS.objects.values_list("id", flat=True))
        initial_data = list(ImportCOGS.objects.values())

        out = StringIO()
        call_command("plan_import_cogs_consolidation", stdout=out)

        final_ids = set(ImportCOGS.objects.values_list("id", flat=True))
        final_data = list(ImportCOGS.objects.values())

        self.assertEqual(initial_ids, final_ids)
        self.assertEqual(initial_data, final_data)
        self.assertIn("No rows were mutated. Dry run complete.", out.getvalue())

    def test_quote_output_remains_unchanged(self):
        # This test ensures that running the command doesn't affect pricing logic results
        # which depends on the database remaining exactly the same.
        self._create_cogs(self.doc_origin, "BNE", "POM", Decimal("80.00"))
        
        engine = ImportPricingEngine(
            quote_date=date.today(),
            origin="BNE",
            destination="POM",
            chargeable_weight_kg=Decimal("100"),
            payment_term=PaymentTerm.PREPAID,
            service_scope=ServiceScope.D2D,
            preferred_agent_id=self.agent.id,
        )
        
        initial_quote = engine.calculate_quote()
        
        # Run the command
        call_command("plan_import_cogs_consolidation", stdout=StringIO())
        
        final_quote = engine.calculate_quote()
        
        self.assertEqual(initial_quote.total_cost, final_quote.total_cost)
        self.assertEqual(len(initial_quote.line_items), len(final_quote.line_items))

    def _create_cogs(self, product, origin, destination, amount, agent=None):
        return ImportCOGS.objects.create(
            product_code=product,
            origin_airport=origin,
            destination_airport=destination,
            agent=agent or self.agent,
            currency="AUD",
            rate_per_shipment=amount,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            is_additive=True
        )
