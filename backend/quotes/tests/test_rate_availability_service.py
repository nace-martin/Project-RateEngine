from datetime import date, timedelta
from decimal import Decimal

import pytest

from pricing_v4.models import (
    Agent,
    CommodityChargeRule,
    ExportCOGS,
    ImportCOGS,
    LocalCOGSRate,
    LocalSellRate,
    ProductCode,
    Surcharge,
)
from quotes.completeness import (
    COMPONENT_DESTINATION_LOCAL,
    COMPONENT_FREIGHT,
    COMPONENT_ORIGIN_LOCAL,
)
from quotes.spot_services import (
    CommodityRateRuleService,
    RateAvailabilityService,
    SpotTriggerEvaluator,
    SpotTriggerReason,
)


pytestmark = pytest.mark.django_db


def _today_window():
    return date.today() - timedelta(days=1), date.today() + timedelta(days=30)


def _agent() -> Agent:
    return Agent.objects.create(
        code="SPOT-MATRIX",
        name="SPOT Matrix Agent",
        country_code="PG",
        agent_type="ORIGIN",
    )


def _pc(id_: int, code: str, domain: str, category: str, unit: str = "SHIPMENT") -> ProductCode:
    return ProductCode.objects.create(
        id=id_,
        code=code,
        description=code,
        domain=domain,
        category=category,
        is_gst_applicable=True,
        gl_revenue_code="4100",
        gl_cost_code="5100",
        default_unit=unit,
    )


def _evaluate(direction: str, scope: str, availability: dict[str, bool]):
    return SpotTriggerEvaluator.evaluate(
        origin_country="AU" if direction == "IMPORT" else "PG",
        destination_country="PG" if direction == "IMPORT" else "AU",
        direction=direction,
        service_scope=scope,
        component_availability=availability,
    )


def test_import_d2d_collect_uses_origin_fallback_and_does_not_trigger_spot():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_freight = _pc(2951, "IMP-FRT-AIR-MATRIX", "IMPORT", "FREIGHT", unit="KG")
    pc_origin = _pc(2952, "IMP-ORIGIN-HANDLING-MATRIX", "IMPORT", "HANDLING")
    pc_dest = _pc(2953, "IMP-CARTAGE-DEST-MATRIX", "IMPORT", "CARTAGE")

    ImportCOGS.objects.create(
        product_code=pc_freight,
        origin_airport="BNE",
        destination_airport="POM",
        agent=agent,
        currency="AUD",
        rate_per_kg=Decimal("5.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    # Legacy migrated shape: origin local row stored at destination.
    LocalCOGSRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="IMPORT",
        agent=agent,
        currency="AUD",
        rate_type="FIXED",
        amount=Decimal("70.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_dest,
        location="POM",
        direction="IMPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("120.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    availability = RateAvailabilityService.get_availability("BNE", "POM", "IMPORT", "D2D")
    assert availability == {
        COMPONENT_FREIGHT: True,
        COMPONENT_ORIGIN_LOCAL: True,
        COMPONENT_DESTINATION_LOCAL: True,
    }

    is_spot, trigger = _evaluate("IMPORT", "D2D", availability)
    assert is_spot is False
    assert trigger is None


def test_import_d2d_missing_origin_component_still_triggers_spot():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_freight = _pc(2961, "IMP-FRT-AIR-MISS-ORIGIN", "IMPORT", "FREIGHT", unit="KG")
    pc_dest = _pc(2962, "IMP-CARTAGE-DEST-MISS-ORIGIN", "IMPORT", "CARTAGE")

    ImportCOGS.objects.create(
        product_code=pc_freight,
        origin_airport="SYD",
        destination_airport="POM",
        agent=agent,
        currency="AUD",
        rate_per_kg=Decimal("4.75"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_dest,
        location="POM",
        direction="IMPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("140.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    availability = RateAvailabilityService.get_availability("SYD", "POM", "IMPORT", "D2D")
    is_spot, trigger = _evaluate("IMPORT", "D2D", availability)
    assert is_spot is True
    assert trigger is not None
    assert trigger.code == SpotTriggerReason.MISSING_SCOPE_RATES
    assert trigger.missing_components == [COMPONENT_ORIGIN_LOCAL]


def test_import_a2d_collect_destination_only_scope_is_not_blocked_by_missing_freight():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_dest = _pc(2971, "IMP-CARTAGE-DEST-A2D", "IMPORT", "CARTAGE")

    LocalCOGSRate.objects.create(
        product_code=pc_dest,
        location="POM",
        direction="IMPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("95.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    availability = RateAvailabilityService.get_availability("SIN", "POM", "IMPORT", "A2D")
    assert availability[COMPONENT_DESTINATION_LOCAL] is True

    is_spot, trigger = _evaluate("IMPORT", "A2D", availability)
    assert is_spot is False
    assert trigger is None


def test_export_d2a_rates_are_detected_with_lowercase_inputs():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_freight = _pc(1981, "EXP-FRT-AIR-MATRIX", "EXPORT", "FREIGHT", unit="KG")
    pc_origin = _pc(1982, "EXP-DOC-MATRIX", "EXPORT", "DOCUMENTATION")

    ExportCOGS.objects.create(
        product_code=pc_freight,
        origin_airport="POM",
        destination_airport="HIR",
        agent=agent,
        currency="USD",
        rate_per_kg=Decimal("3.20"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("80.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    availability = RateAvailabilityService.get_availability("pom", "hir", "export", "d2a")
    assert availability[COMPONENT_FREIGHT] is True
    assert availability[COMPONENT_ORIGIN_LOCAL] is True

    is_spot, trigger = _evaluate("EXPORT", "D2A", availability)
    assert is_spot is False
    assert trigger is None


def test_import_destination_global_surcharge_counts_as_coverage():
    valid_from, valid_until = _today_window()
    pc_surcharge = _pc(2981, "IMP-DEST-SURCHARGE-MATRIX", "IMPORT", "SURCHARGE")

    Surcharge.objects.create(
        product_code=pc_surcharge,
        rate_side="COGS",
        service_type="IMPORT_DEST",
        rate_type="FLAT",
        amount=Decimal("25.00"),
        currency="PGK",
        origin_filter=None,
        destination_filter=None,
        valid_from=valid_from,
        valid_until=valid_until,
        is_active=True,
    )

    availability = RateAvailabilityService.get_availability("SIN", "POM", "IMPORT", "A2D")
    assert availability[COMPONENT_DESTINATION_LOCAL] is True

    is_spot, trigger = _evaluate("IMPORT", "A2D", availability)
    assert is_spot is False
    assert trigger is None


def test_export_d2a_payment_term_mismatch_does_not_count_origin_local():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_freight = _pc(1991, "EXP-FRT-AIR-TERM", "EXPORT", "FREIGHT", unit="KG")
    pc_origin = _pc(1992, "EXP-DOC-TERM", "EXPORT", "DOCUMENTATION")

    ExportCOGS.objects.create(
        product_code=pc_freight,
        origin_airport="POM",
        destination_airport="HIR",
        agent=agent,
        currency="USD",
        rate_per_kg=Decimal("3.10"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("80.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalSellRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        payment_term="PREPAID",
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("120.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    prepaid = RateAvailabilityService.get_availability(
        "POM", "HIR", "EXPORT", "D2A", payment_term="PREPAID"
    )
    assert prepaid[COMPONENT_ORIGIN_LOCAL] is True
    is_spot, trigger = _evaluate("EXPORT", "D2A", prepaid)
    assert is_spot is False
    assert trigger is None

    collect = RateAvailabilityService.get_availability(
        "POM", "HIR", "EXPORT", "D2A", payment_term="COLLECT"
    )
    assert collect[COMPONENT_ORIGIN_LOCAL] is False
    is_spot, trigger = _evaluate("EXPORT", "D2A", collect)
    assert is_spot is True
    assert trigger is not None
    assert trigger.missing_components == [COMPONENT_ORIGIN_LOCAL]


def test_import_a2d_payment_term_mismatch_does_not_count_destination_local():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_dest = _pc(2991, "IMP-CARTAGE-DEST-TERM", "IMPORT", "CARTAGE")

    LocalCOGSRate.objects.create(
        product_code=pc_dest,
        location="POM",
        direction="IMPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("95.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalSellRate.objects.create(
        product_code=pc_dest,
        location="POM",
        direction="IMPORT",
        payment_term="PREPAID",
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("140.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )

    prepaid = RateAvailabilityService.get_availability(
        "SIN", "POM", "IMPORT", "A2D", payment_term="PREPAID"
    )
    assert prepaid[COMPONENT_DESTINATION_LOCAL] is True
    is_spot, trigger = _evaluate("IMPORT", "A2D", prepaid)
    assert is_spot is False
    assert trigger is None

    collect = RateAvailabilityService.get_availability(
        "SIN", "POM", "IMPORT", "A2D", payment_term="COLLECT"
    )
    assert collect[COMPONENT_DESTINATION_LOCAL] is False
    is_spot, trigger = _evaluate("IMPORT", "A2D", collect)
    assert is_spot is True
    assert trigger is not None
    assert trigger.missing_components == [COMPONENT_DESTINATION_LOCAL]


def test_export_d2a_missing_commodity_rate_triggers_spot_when_scope_is_covered():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_freight = _pc(1971, "EXP-FRT-AIR-COMMODITY", "EXPORT", "FREIGHT", unit="KG")
    pc_origin = _pc(1972, "EXP-DOC-COMMODITY", "EXPORT", "DOCUMENTATION")
    pc_dg = _pc(1973, "EXP-DG-COMMODITY", "EXPORT", "HANDLING")

    ExportCOGS.objects.create(
        product_code=pc_freight,
        origin_airport="POM",
        destination_airport="BNE",
        agent=agent,
        currency="USD",
        rate_per_kg=Decimal("3.40"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("80.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalSellRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        payment_term="PREPAID",
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("120.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    CommodityChargeRule.objects.create(
        shipment_type="EXPORT",
        service_scope="D2A",
        commodity_code="DG",
        product_code=pc_dg,
        leg="ORIGIN",
        trigger_mode="AUTO",
        effective_from=valid_from,
        effective_to=valid_until,
    )

    availability = RateAvailabilityService.get_availability(
        "POM", "BNE", "EXPORT", "D2A", payment_term="PREPAID"
    )
    commodity_coverage = CommodityRateRuleService.evaluate_coverage(
        "POM", "BNE", "EXPORT", "D2A", "DG", payment_term="PREPAID"
    )

    assert availability[COMPONENT_FREIGHT] is True
    assert availability[COMPONENT_ORIGIN_LOCAL] is True
    assert commodity_coverage.missing_product_codes == ["EXP-DG-COMMODITY"]

    is_spot, trigger = SpotTriggerEvaluator.evaluate(
        origin_country="PG",
        destination_country="AU",
        direction="EXPORT",
        service_scope="D2A",
        component_availability=availability,
        commodity_code="DG",
        commodity_coverage=commodity_coverage,
    )
    assert is_spot is True
    assert trigger is not None
    assert trigger.code == SpotTriggerReason.MISSING_COMMODITY_RATES
    assert trigger.missing_product_codes == ["EXP-DG-COMMODITY"]


def test_export_d2a_seeded_commodity_rate_does_not_trigger_spot_when_scope_is_covered():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_freight = _pc(1961, "EXP-FRT-AIR-COMMODITY-OK", "EXPORT", "FREIGHT", unit="KG")
    pc_origin = _pc(1962, "EXP-DOC-COMMODITY-OK", "EXPORT", "DOCUMENTATION")
    pc_dg = _pc(1963, "EXP-DG-COMMODITY-OK", "EXPORT", "HANDLING")

    ExportCOGS.objects.create(
        product_code=pc_freight,
        origin_airport="POM",
        destination_airport="BNE",
        agent=agent,
        currency="USD",
        rate_per_kg=Decimal("3.40"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("80.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalSellRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        payment_term="PREPAID",
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("120.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_dg,
        location="POM",
        direction="EXPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("250.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalSellRate.objects.create(
        product_code=pc_dg,
        location="POM",
        direction="EXPORT",
        payment_term="PREPAID",
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("350.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    CommodityChargeRule.objects.create(
        shipment_type="EXPORT",
        service_scope="D2A",
        commodity_code="DG",
        product_code=pc_dg,
        leg="ORIGIN",
        trigger_mode="AUTO",
        effective_from=valid_from,
        effective_to=valid_until,
    )

    availability = RateAvailabilityService.get_availability(
        "POM", "BNE", "EXPORT", "D2A", payment_term="PREPAID"
    )
    commodity_coverage = CommodityRateRuleService.evaluate_coverage(
        "POM", "BNE", "EXPORT", "D2A", "DG", payment_term="PREPAID"
    )

    assert commodity_coverage.is_spot_required is False

    is_spot, trigger = SpotTriggerEvaluator.evaluate(
        origin_country="PG",
        destination_country="AU",
        direction="EXPORT",
        service_scope="D2A",
        component_availability=availability,
        commodity_code="DG",
        commodity_coverage=commodity_coverage,
    )
    assert is_spot is False
    assert trigger is None


def test_export_d2a_requires_spot_rule_triggers_spot_even_with_scope_coverage():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_freight = _pc(1951, "EXP-FRT-AIR-COMMODITY-SPOT", "EXPORT", "FREIGHT", unit="KG")
    pc_origin = _pc(1952, "EXP-DOC-COMMODITY-SPOT", "EXPORT", "DOCUMENTATION")
    pc_special = _pc(1953, "EXP-AVI-SPOT-ONLY", "EXPORT", "HANDLING")

    ExportCOGS.objects.create(
        product_code=pc_freight,
        origin_airport="POM",
        destination_airport="BNE",
        agent=agent,
        currency="USD",
        rate_per_kg=Decimal("3.40"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("80.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalSellRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        payment_term="PREPAID",
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("120.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    CommodityChargeRule.objects.create(
        shipment_type="EXPORT",
        service_scope="D2A",
        commodity_code="AVI",
        product_code=pc_special,
        leg="ORIGIN",
        trigger_mode="REQUIRES_SPOT",
        effective_from=valid_from,
        effective_to=valid_until,
    )

    availability = RateAvailabilityService.get_availability(
        "POM", "BNE", "EXPORT", "D2A", payment_term="PREPAID"
    )
    commodity_coverage = CommodityRateRuleService.evaluate_coverage(
        "POM", "BNE", "EXPORT", "D2A", "AVI", payment_term="PREPAID"
    )

    assert commodity_coverage.spot_required_product_codes == ["EXP-AVI-SPOT-ONLY"]
    is_spot, trigger = SpotTriggerEvaluator.evaluate(
        origin_country="PG",
        destination_country="AU",
        direction="EXPORT",
        service_scope="D2A",
        component_availability=availability,
        commodity_code="AVI",
        commodity_coverage=commodity_coverage,
    )
    assert is_spot is True
    assert trigger.code == SpotTriggerReason.COMMODITY_REQUIRES_SPOT
    assert trigger.spot_required_product_codes == ["EXP-AVI-SPOT-ONLY"]


def test_export_d2a_requires_manual_rule_triggers_spot_with_manual_reason():
    valid_from, valid_until = _today_window()
    agent = _agent()
    pc_freight = _pc(1941, "EXP-FRT-AIR-COMMODITY-MANUAL", "EXPORT", "FREIGHT", unit="KG")
    pc_origin = _pc(1942, "EXP-DOC-COMMODITY-MANUAL", "EXPORT", "DOCUMENTATION")
    pc_special = _pc(1943, "EXP-AVI-MANUAL-ONLY", "EXPORT", "HANDLING")

    ExportCOGS.objects.create(
        product_code=pc_freight,
        origin_airport="POM",
        destination_airport="BNE",
        agent=agent,
        currency="USD",
        rate_per_kg=Decimal("3.40"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalCOGSRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        agent=agent,
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("80.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    LocalSellRate.objects.create(
        product_code=pc_origin,
        location="POM",
        direction="EXPORT",
        payment_term="PREPAID",
        currency="PGK",
        rate_type="FIXED",
        amount=Decimal("120.00"),
        valid_from=valid_from,
        valid_until=valid_until,
    )
    CommodityChargeRule.objects.create(
        shipment_type="EXPORT",
        service_scope="D2A",
        commodity_code="AVI",
        product_code=pc_special,
        leg="ORIGIN",
        trigger_mode="REQUIRES_MANUAL",
        effective_from=valid_from,
        effective_to=valid_until,
    )

    availability = RateAvailabilityService.get_availability(
        "POM", "BNE", "EXPORT", "D2A", payment_term="PREPAID"
    )
    commodity_coverage = CommodityRateRuleService.evaluate_coverage(
        "POM", "BNE", "EXPORT", "D2A", "AVI", payment_term="PREPAID"
    )

    assert commodity_coverage.manual_required_product_codes == ["EXP-AVI-MANUAL-ONLY"]
    is_spot, trigger = SpotTriggerEvaluator.evaluate(
        origin_country="PG",
        destination_country="AU",
        direction="EXPORT",
        service_scope="D2A",
        component_availability=availability,
        commodity_code="AVI",
        commodity_coverage=commodity_coverage,
    )
    assert is_spot is True
    assert trigger.code == SpotTriggerReason.COMMODITY_REQUIRES_MANUAL
    assert trigger.manual_required_product_codes == ["EXP-AVI-MANUAL-ONLY"]
