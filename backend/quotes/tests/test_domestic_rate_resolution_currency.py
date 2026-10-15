from datetime import date, timedelta
from decimal import Decimal

import pytest

from pricing_v4.models import Carrier, DomesticCOGS, ProductCode
from quotes.services.rate_resolution import RateResolutionContext, resolve_quote_rate_dimensions


pytestmark = pytest.mark.django_db


def test_domestic_rate_resolution_ignores_foreign_buy_currency_override():
    freight = ProductCode.objects.create(
        id=3982,
        code="DOM-FRT-RESOLUTION-PGK",
        description="Domestic Freight Resolution PGK",
        domain=ProductCode.DOMAIN_DOMESTIC,
        category=ProductCode.CATEGORY_FREIGHT,
        is_gst_applicable=True,
        gst_rate=Decimal("0.10"),
        gl_revenue_code="4100",
        gl_cost_code="5100",
        default_unit=ProductCode.UNIT_KG,
    )
    carrier = Carrier.objects.create(
        code="PX-RESOLUTION-PGK",
        name="Air Niugini Resolution PGK",
        carrier_type="AIRLINE",
    )
    valid_from = date.today() - timedelta(days=30)
    valid_until = date.today() + timedelta(days=365)

    DomesticCOGS.objects.create(
        product_code=freight,
        origin_zone="POM",
        destination_zone="LAE",
        carrier=carrier,
        currency="PGK",
        rate_per_kg=Decimal("6.10"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    DomesticCOGS.objects.create(
        product_code=freight,
        origin_zone="POM",
        destination_zone="LAE",
        carrier=carrier,
        currency="USD",
        rate_per_kg=Decimal("99.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    for incoming_buy_currency in ("USD", "AUD"):
        resolved = resolve_quote_rate_dimensions(
            RateResolutionContext(
                customer_id="11111111-1111-1111-1111-111111111111",
                shipment_type="DOMESTIC",
                service_scope="A2A",
                payment_term="PREPAID",
                origin_airport="POM",
                destination_airport="LAE",
                quote_date=date.today(),
                override_buy_currency=incoming_buy_currency,
            )
        )

        assert resolved.buy_currency == "PGK"
        assert resolved.carrier_id == carrier.id
        assert resolved.resolution_basis == "derived_shared_dimensions"
        assert resolved.trace["component_candidates"]["FREIGHT"]["currencies"] == ["PGK"]
