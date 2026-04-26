from decimal import Decimal

from django.test import SimpleTestCase

from quotes.models import QuoteLine
from quotes.quote_result_contract import line_item_from_quote_line
from quotes.serializers import V3QuoteLineSerializer
from services.models import ServiceComponent


class V3QuoteLineSerializerTests(SimpleTestCase):
    def test_spot_line_component_prefers_persisted_product_code(self):
        fallback_component = ServiceComponent(
            id="00000000-0000-0000-0000-000000000001",
            code="ORIGIN_LOCAL",
            description="Spot Origin Charge",
            mode="AIR",
            leg="ORIGIN",
            category="TRANSPORT",
        )
        line = QuoteLine(
            service_component=fallback_component,
            description="Import Origin Customs Clearance",
            product_code="IMP-CUS-CLR-ORIGIN",
            cost_pgk=Decimal("100"),
            sell_pgk=Decimal("115"),
            sell_pgk_incl_gst=Decimal("115"),
            sell_fcy=Decimal("115"),
            sell_fcy_incl_gst=Decimal("115"),
            sell_fcy_currency="PGK",
            is_rate_missing=False,
        )

        payload = V3QuoteLineSerializer(line).data

        self.assertEqual(payload["component"], "IMP-CUS-CLR-ORIGIN")
        self.assertEqual(payload["product_code"], "IMP-CUS-CLR-ORIGIN")
        self.assertEqual(payload["description"], "Import Origin Customs Clearance")

    def test_canonical_quote_result_prefers_persisted_description_over_fallback_component(self):
        fallback_component = ServiceComponent(
            id="00000000-0000-0000-0000-000000000002",
            code="ORIGIN_LOCAL",
            description="Spot Origin Charge",
            mode="AIR",
            leg="ORIGIN",
            category="TRANSPORT",
            unit="SHIPMENT",
        )
        line = QuoteLine(
            service_component=fallback_component,
            description="Import Origin Customs Clearance",
            cost_source_description="Import Origin Customs Clearance",
            product_code="IMP-CUS-CLR-ORIGIN",
            component="ORIGIN_LOCAL",
            cost_pgk=Decimal("100"),
            sell_pgk=Decimal("115"),
            sell_pgk_incl_gst=Decimal("115"),
            sell_fcy=Decimal("115"),
            sell_fcy_incl_gst=Decimal("115"),
            sell_fcy_currency="PGK",
            is_rate_missing=False,
        )

        payload = line_item_from_quote_line(
            line,
            metrics={"chargeable_weight": Decimal("1"), "pieces": 1},
            display_currency="PGK",
            engine_version="V4",
            sort_order=10,
        )

        self.assertEqual(payload["description"], "Import Origin Customs Clearance")
        self.assertEqual(payload["product_code"], "IMP-CUS-CLR-ORIGIN")
        self.assertEqual(payload["component"], "ORIGIN_LOCAL")
