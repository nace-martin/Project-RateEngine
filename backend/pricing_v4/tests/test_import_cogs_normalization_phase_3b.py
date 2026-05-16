from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase

from pricing_v4.models import Agent, ImportCOGS, ProductCode
from pricing_v4.services.rate_selector import (
    RateSelectionContext,
    select_import_cogs_rate,
    RateNotFoundError,
)


class ImportCOGSNormalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.valid_from = date.today() - timedelta(days=1)
        cls.valid_until = date.today() + timedelta(days=30)
        cls.agent = Agent.objects.create(
            code="EFM-AU", name="EFM Australia", country_code="AU", agent_type="ORIGIN"
        )
        cls.doc_origin = ProductCode.objects.create(
            id=2001,
            code="IMP-DOC-ORIGIN",
            description="Origin Documentation",
            category="DOCUMENTATION",
            domain="IMPORT",
            default_unit="SHIPMENT",
            is_gst_applicable=True,
        )
        cls.freight = ProductCode.objects.create(
            id=2002,
            code="IMP-FRT-AIR",
            description="Air Freight",
            category="FREIGHT",
            domain="IMPORT",
            default_unit="KG",
            is_gst_applicable=True,
        )

    def test_origin_scoped_rate_resolution_before_and_after_normalization(self):
        # 1. Create an ORIGIN scoped row as it currently exists (with destination)
        cogs = ImportCOGS.objects.create(
            product_code=self.doc_origin,
            origin_airport="BNE",
            destination_airport="POM",
            scope="ORIGIN",
            agent=self.agent,
            currency="AUD",
            rate_per_shipment=Decimal("80.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        context = RateSelectionContext(
            product_code_id=self.doc_origin.id,
            quote_date=date.today(),
            origin_airport="BNE",
            destination_airport="POM",
            agent_id=self.agent.id,
        )

        # 2. Verify it matches currently
        result = select_import_cogs_rate(context)
        self.assertEqual(result.record.id, cogs.id)

        # 3. Normalize: clear destination_airport
        cogs.destination_airport = None
        cogs.save()

        # 4. Verify it STILL matches (this is expected to FAIL if selector is not updated)
        # Note: If it fails with RateNotFoundError, it means selector doesn't handle NULL destination
        try:
            result_normalized = select_import_cogs_rate(context)
            self.assertEqual(result_normalized.record.id, cogs.id)
        except RateNotFoundError:
            self.fail("Selector failed to resolve normalized ORIGIN scoped ImportCOGS row (NULL destination)")

    def test_lane_scoped_rate_remains_strict(self):
        # LANE rows must have both origin and destination
        lane_cogs = ImportCOGS.objects.create(
            product_code=self.freight,
            origin_airport="BNE",
            destination_airport="POM",
            scope="LANE",
            agent=self.agent,
            currency="AUD",
            rate_per_kg=Decimal("5.00"),
            valid_from=self.valid_from,
            valid_until=self.valid_until,
        )

        context = RateSelectionContext(
            product_code_id=self.freight.id,
            quote_date=date.today(),
            origin_airport="BNE",
            destination_airport="POM",
            agent_id=self.agent.id,
        )

        # Matches exact
        result = select_import_cogs_rate(context)
        self.assertEqual(result.record.id, lane_cogs.id)

        # Does NOT match if origin is different
        with self.assertRaises(RateNotFoundError):
            select_import_cogs_rate(
                RateSelectionContext(
                    product_code_id=self.freight.id,
                    quote_date=date.today(),
                    origin_airport="SYD",
                    destination_airport="POM",
                    agent_id=self.agent.id,
                )
            )
