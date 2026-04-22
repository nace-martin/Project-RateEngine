from datetime import date, timedelta
from decimal import Decimal

import pytest

from pricing_v4.models import Agent, ImportCOGS, ProductCode
from quotes.services.rate_resolution import (
    RateResolutionContext,
    resolve_quote_rate_dimensions,
)


pytestmark = pytest.mark.django_db


def _today_window():
    return date.today() - timedelta(days=1), date.today() + timedelta(days=30)


def _agent(code: str, name: str) -> Agent:
    return Agent.objects.create(
        code=code,
        name=name,
        country_code="AU",
        agent_type="ORIGIN",
    )


def _pc(id_: int, code: str, category: str) -> ProductCode:
    return ProductCode.objects.create(
        id=id_,
        code=code,
        description=code,
        domain="IMPORT",
        category=category,
        is_gst_applicable=True,
        gl_revenue_code="4100",
        gl_cost_code="5100",
        default_unit="KG" if category == "FREIGHT" else "SHIPMENT",
    )


def _context(service_scope: str = "A2A") -> RateResolutionContext:
    return RateResolutionContext(
        customer_id="11111111-1111-1111-1111-111111111111",
        shipment_type="IMPORT",
        service_scope=service_scope,
        payment_term="COLLECT",
        origin_airport="SYD",
        destination_airport="POM",
        quote_date=date.today(),
    )


def test_resolver_auto_selects_unique_buy_path_when_all_required_components_align():
    valid_from, valid_until = _today_window()
    agent = _agent("RES-AG-1", "Resolution Agent 1")
    freight_pc = _pc(2810, "IMP-FRT-RESOLVE", "FREIGHT")
    origin_pc = _pc(2811, "IMP-ORIGIN-HANDLING-RESOLVE", "HANDLING")
    dest_pc = _pc(2812, "IMP-CARTAGE-DEST-RESOLVE", "CARTAGE")

    for product_code, amount in [
        (freight_pc, Decimal("4.80")),
        (origin_pc, Decimal("55.00")),
        (dest_pc, Decimal("90.00")),
    ]:
        ImportCOGS.objects.create(
            product_code=product_code,
            origin_airport="SYD",
            destination_airport="POM",
            agent=agent,
            currency="AUD",
            rate_per_kg=amount if product_code == freight_pc else None,
            rate_per_shipment=amount if product_code != freight_pc else None,
            valid_from=valid_from,
            valid_until=valid_until,
        )

    resolved = resolve_quote_rate_dimensions(_context(service_scope="D2D"))

    assert resolved.buy_currency == "AUD"
    assert resolved.agent_id == agent.id
    assert resolved.carrier_id is None
    assert resolved.resolution_basis == "derived_shared_dimensions"
    assert resolved.buy_side_components == ("DESTINATION_LOCAL", "FREIGHT", "ORIGIN_LOCAL")


def test_resolver_leaves_agent_unset_when_multiple_agents_exist_for_same_component():
    valid_from, valid_until = _today_window()
    freight_pc = _pc(2820, "IMP-FRT-AGENT-AMB", "FREIGHT")
    agent_a = _agent("RES-AG-A", "Resolution Agent A")
    agent_b = _agent("RES-AG-B", "Resolution Agent B")

    for agent in (agent_a, agent_b):
        ImportCOGS.objects.create(
            product_code=freight_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=agent,
            currency="AUD",
            rate_per_kg=Decimal("4.90"),
            valid_from=valid_from,
            valid_until=valid_until,
        )

    resolved = resolve_quote_rate_dimensions(_context())

    assert resolved.buy_currency == "AUD"
    assert resolved.agent_id is None
    assert resolved.carrier_id is None
    assert resolved.resolution_basis == "derived_shared_dimensions"


def test_resolver_leaves_buy_currency_unset_when_multiple_currencies_exist_for_same_component():
    valid_from, valid_until = _today_window()
    freight_pc = _pc(2830, "IMP-FRT-CURRENCY-AMB", "FREIGHT")
    agent = _agent("RES-AG-C", "Resolution Agent C")

    for currency, amount in (("AUD", Decimal("4.80")), ("USD", Decimal("5.10"))):
        ImportCOGS.objects.create(
            product_code=freight_pc,
            origin_airport="SYD",
            destination_airport="POM",
            agent=agent,
            currency=currency,
            rate_per_kg=amount,
            valid_from=valid_from,
            valid_until=valid_until,
        )

    resolved = resolve_quote_rate_dimensions(_context())

    assert resolved.buy_currency is None
    assert resolved.agent_id == agent.id
    assert resolved.carrier_id is None
    assert resolved.resolution_basis == "derived_shared_dimensions"


def test_resolver_allows_component_level_resolution_when_components_have_different_agents():
    valid_from, valid_until = _today_window()
    origin_agent = _agent("RES-AG-O", "Resolution Origin Agent")
    dest_agent = _agent("RES-AG-D", "Resolution Destination Agent")
    freight_pc = _pc(2840, "IMP-FRT-PARTIAL", "FREIGHT")
    origin_pc = _pc(2841, "IMP-ORIGIN-HANDLING-PARTIAL", "HANDLING")
    dest_pc = _pc(2842, "IMP-CARTAGE-DEST-PARTIAL", "CARTAGE")

    ImportCOGS.objects.create(
        product_code=freight_pc,
        origin_airport="SYD",
        destination_airport="POM",
        agent=origin_agent,
        currency="AUD",
        rate_per_kg=Decimal("4.75"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    ImportCOGS.objects.create(
        product_code=origin_pc,
        origin_airport="SYD",
        destination_airport="POM",
        agent=origin_agent,
        currency="AUD",
        rate_per_shipment=Decimal("55.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    ImportCOGS.objects.create(
        product_code=dest_pc,
        origin_airport="SYD",
        destination_airport="POM",
        agent=dest_agent,
        currency="AUD",
        rate_per_shipment=Decimal("90.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    resolved = resolve_quote_rate_dimensions(_context(service_scope="D2D"))

    assert resolved.buy_currency == "AUD"
    assert resolved.agent_id is None
    assert resolved.carrier_id is None
    assert resolved.resolution_basis == "derived_shared_dimensions"
