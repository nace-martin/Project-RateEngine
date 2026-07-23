from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.core.management import call_command
from django.utils import timezone

from pricing_v4.contracts.charge_context import JourneyDirection, JourneyPattern, LegRole, ProductCodeDomain, TransportMode
from quotes.contracts.journey_contracts import JourneyPlannerBlockerCode, JourneyStatus
from quotes.models import RouteAutomationPolicyDB, ShipmentJourneyDB, ShipmentLegDB
from quotes.services.air_journey_planner import AirJourneyPlanner
from quotes.services.journey_persistence import ShipmentJourneyPersistenceService, get_route_policy_state
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB

pytestmark = pytest.mark.django_db


def request_payload(origin_country="SG", destination_country="PG", origin="SIN", destination="POM", **overrides):
    payload = {
        "origin_country": origin_country,
        "destination_country": destination_country,
        "customer_origin_code": origin,
        "customer_destination_code": destination,
        "service_domain": "AIR",
        "service_scope": "A2A",
        "quote_date": date(2026, 1, 15).isoformat(),
        "pieces": 2,
        "actual_weight": "10.5",
        "volumetric_weight": "12.0",
        "chargeable_weight": "12.0",
        "commodity": "GEN",
        "pickup_requested": False,
        "delivery_requested": False,
    }
    payload.update(overrides)
    return payload


def plan(payload):
    return AirJourneyPlanner().plan(payload)


def make_user():
    return get_user_model().objects.create_user(username="phase16e", password="test")


def make_spe(user=None, origin="SIN", destination="POM", origin_country="SG", destination_country="PG"):
    user = user or make_user()
    return SpotPricingEnvelopeDB.objects.create(
        shipment_context_json={
            "origin_country": origin_country,
            "destination_country": destination_country,
            "origin_code": origin,
            "destination_code": destination,
            "mode": "AIR",
        },
        conditions_json={},
        spot_trigger_reason_code="PHASE16E_TEST",
        spot_trigger_reason_text="Phase 16E test",
        created_by=user,
        expires_at=timezone.now() + timedelta(days=1),
    )


def persist(payload, spe=None, user=None):
    user = user or make_user()
    spe = spe or make_spe(user=user, origin=payload["customer_origin_code"], destination=payload["customer_destination_code"], origin_country=payload["origin_country"], destination_country=payload["destination_country"])
    return ShipmentJourneyPersistenceService().persist_plan(plan=plan(payload), spot_envelope=spe, created_by=user)


# ARCH-16C-001
def test_imp_pom_exact_leg_structure():
    result = plan(request_payload(origin="SIN", destination="POM"))

    assert result.direction == JourneyDirection.IMPORT
    assert result.pattern == JourneyPattern.IMP_POM
    assert result.gateway_code == "POM"
    assert [leg.leg_key for leg in result.legs] == ["01:INTERNATIONAL_IMPORT:SIN:POM"]
    assert result.legs[0].product_code_domain == ProductCodeDomain.IMPORT


# ARCH-16C-002
def test_imp_lae_includes_import_and_domestic_legs():
    result = plan(request_payload(origin="SIN", destination="LAE"))

    assert result.pattern == JourneyPattern.IMP_LAE
    assert [leg.role for leg in result.legs] == [LegRole.INTERNATIONAL_IMPORT, LegRole.DOMESTIC_ON_FORWARDING]
    assert [leg.product_code_domain for leg in result.legs] == [ProductCodeDomain.IMPORT, ProductCodeDomain.DOMESTIC]
    assert [leg.leg_key for leg in result.legs] == ["01:INTERNATIONAL_IMPORT:SIN:POM", "02:DOMESTIC_ON_FORWARDING:POM:LAE"]


# ARCH-16C-003
def test_imp_hgu_includes_import_and_domestic_legs():
    result = plan(request_payload(origin="SIN", destination="HGU"))

    assert result.pattern == JourneyPattern.IMP_HGU
    assert [leg.role for leg in result.legs] == [LegRole.INTERNATIONAL_IMPORT, LegRole.DOMESTIC_ON_FORWARDING]
    assert result.legs[1].origin_code == "POM"
    assert result.legs[1].destination_code == "HGU"


# ARCH-16C-004
def test_exp_pom_exact_leg_structure():
    result = plan(request_payload(origin_country="PG", destination_country="SG", origin="POM", destination="SIN"))

    assert result.direction == JourneyDirection.EXPORT
    assert result.pattern == JourneyPattern.EXP_POM
    assert [leg.leg_key for leg in result.legs] == ["01:INTERNATIONAL_EXPORT:POM:SIN"]
    assert result.legs[0].product_code_domain == ProductCodeDomain.EXPORT


# ARCH-16C-005
def test_exp_lae_includes_domestic_and_export_legs():
    result = plan(request_payload(origin_country="PG", destination_country="SG", origin="LAE", destination="SIN"))

    assert result.pattern == JourneyPattern.EXP_LAE
    assert [leg.role for leg in result.legs] == [LegRole.DOMESTIC_PRE_CARRIAGE, LegRole.INTERNATIONAL_EXPORT]
    assert [leg.product_code_domain for leg in result.legs] == [ProductCodeDomain.DOMESTIC, ProductCodeDomain.EXPORT]
    assert [leg.leg_key for leg in result.legs] == ["01:DOMESTIC_PRE_CARRIAGE:LAE:POM", "02:INTERNATIONAL_EXPORT:POM:SIN"]


# ARCH-16C-009
def test_exp_hgu_plans_but_automation_remains_disabled():
    result = plan(request_payload(origin_country="PG", destination_country="SG", origin="HGU", destination="SIN"))

    assert result.pattern == JourneyPattern.EXP_HGU
    assert [leg.leg_key for leg in result.legs] == ["01:DOMESTIC_PRE_CARRIAGE:HGU:POM", "02:INTERNATIONAL_EXPORT:POM:SIN"]
    assert JourneyPlannerBlockerCode.ROUTE_AUTOMATION_DISABLED in result.blockers


def test_pom_is_always_international_gateway():
    for payload in [
        request_payload(origin="SIN", destination="LAE"),
        request_payload(origin_country="PG", destination_country="SG", origin="LAE", destination="SIN"),
    ]:
        result = plan(payload)
        international = [leg for leg in result.legs if leg.role in {LegRole.INTERNATIONAL_IMPORT, LegRole.INTERNATIONAL_EXPORT}][0]
        if result.direction == JourneyDirection.IMPORT:
            assert international.destination_code == "POM"
        else:
            assert international.origin_code == "POM"


def test_raw_client_direction_cannot_change_trusted_direction():
    result = plan(request_payload(origin="SIN", destination="POM", raw_direction="EXPORT", direction="EXPORT"))

    assert result.direction == JourneyDirection.IMPORT
    assert result.pattern == JourneyPattern.IMP_POM


def test_supplier_source_text_cannot_change_route():
    result = plan(request_payload(origin="SIN", destination="POM", supplier_text="Please route via LAE then HGU"))

    assert result.pattern == JourneyPattern.IMP_POM
    assert [leg.leg_key for leg in result.legs] == ["01:INTERNATIONAL_IMPORT:SIN:POM"]


@pytest.mark.parametrize("field", ["origin_country", "destination_country"])
def test_missing_countries_fail_closed(field):
    payload = request_payload()
    payload[field] = ""

    result = plan(payload)

    assert result.status == JourneyStatus.BLOCKED
    assert JourneyPlannerBlockerCode.JOURNEY_COUNTRY_MISSING in result.blockers
    assert result.legs == []


@pytest.mark.parametrize(
    "payload",
    [
        request_payload(origin_country="SG", destination_country="AU", origin="SIN", destination="BNE"),
        request_payload(origin_country="PG", destination_country="PG", origin="POM", destination="LAE"),
    ],
)
def test_unsupported_overseas_to_overseas_and_domestic_only_fail_visibly(payload):
    result = plan(payload)

    assert result.status == JourneyStatus.BLOCKED
    assert JourneyPlannerBlockerCode.JOURNEY_DIRECTION_UNSUPPORTED in result.blockers
    assert result.legs == []


def test_multi_stop_requests_fail_visibly_without_guessing_legs():
    result = plan(request_payload(origin="SIN", destination="LAE", via_codes=["BNE"]))

    assert result.status == JourneyStatus.BLOCKED
    assert JourneyPlannerBlockerCode.JOURNEY_MULTI_STOP_UNSUPPORTED in result.blockers
    assert result.legs == []


def test_deterministic_leg_keys_and_input_fingerprints():
    payload = request_payload(origin="sin", destination="lae", service_scope="a2a")

    first = plan(payload)
    second = plan({**payload, "supplier_text": "do not trust this", "raw_direction": "EXPORT"})

    assert [leg.leg_key for leg in first.legs] == [leg.leg_key for leg in second.legs]
    assert first.input_fingerprint == second.input_fingerprint


def test_missing_policy_means_disabled():
    RouteAutomationPolicyDB.objects.filter(route_pattern="IMP_POM").delete()

    policy = get_route_policy_state("IMP_POM")

    assert policy.enabled is False
    assert policy.source == "missing"


# ARCH-16C-010
def test_all_seeded_route_policies_are_disabled_and_exp_hgu_has_reason():
    patterns = set(RouteAutomationPolicyDB.objects.values_list("route_pattern", flat=True))

    assert patterns == {pattern.value for pattern in JourneyPattern}
    assert not RouteAutomationPolicyDB.objects.filter(enabled=True).exists()
    exp_hgu = RouteAutomationPolicyDB.objects.get(route_pattern="EXP_HGU")
    assert "HGU to POM readiness" in exp_hgu.disabled_reason


def test_multiple_revisions_coexist_and_material_route_change_creates_new_revision():
    user = make_user()
    spe = make_spe(user=user, origin="SIN", destination="POM")

    first = ShipmentJourneyPersistenceService().persist_plan(plan=plan(request_payload(origin="SIN", destination="POM")), spot_envelope=spe, created_by=user)
    second = ShipmentJourneyPersistenceService().persist_plan(plan=plan(request_payload(origin="SIN", destination="LAE")), spot_envelope=spe, created_by=user)

    assert first.revision == 1
    assert second.revision == 2
    assert second.supersedes_id == first.id
    assert ShipmentJourneyDB.objects.filter(spot_envelope=spe).count() == 2


def test_idempotent_same_fingerprint_persistence_returns_existing_revision():
    user = make_user()
    spe = make_spe(user=user, origin="SIN", destination="POM")
    payload = request_payload(origin="SIN", destination="POM")

    first = ShipmentJourneyPersistenceService().persist_plan(plan=plan(payload), spot_envelope=spe, created_by=user)
    second = ShipmentJourneyPersistenceService().persist_plan(plan=plan({**payload, "raw_direction": "EXPORT"}), spot_envelope=spe, created_by=user)

    assert second.id == first.id
    assert ShipmentJourneyDB.objects.filter(spot_envelope=spe).count() == 1


def test_revision_uniqueness_prevents_duplicate_revision_numbers():
    user = make_user()
    spe = make_spe(user=user, origin="SIN", destination="POM")
    journey = persist(request_payload(origin="SIN", destination="POM"), spe=spe, user=user)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ShipmentJourneyDB.objects.create(
                spot_envelope=spe,
                revision=journey.revision,
                direction=journey.direction,
                pattern=journey.pattern,
                gateway_code="POM",
                customer_origin_code="SIN",
                customer_destination_code="POM",
                route_policy_key="IMP_POM",
                rule_version=journey.rule_version,
                input_fingerprint="x" * 64,
                status=ShipmentJourneyDB.Status.BLOCKED,
                blockers_json=[],
            )


def test_finalized_revisions_cannot_be_mutated():
    journey = persist(request_payload(origin="SIN", destination="POM"))
    journey.finalized_at = timezone.now()
    journey.status = ShipmentJourneyDB.Status.FINALIZED
    journey.save()

    journey.customer_destination_code = "LAE"
    with pytest.raises(ValidationError, match="immutable"):
        journey.save()


def test_no_historical_journey_leg_backfill():
    user = make_user()
    spe = make_spe(user=user)
    line = SPEChargeLineDB.objects.create(
        envelope=spe,
        bucket=SPEChargeLineDB.Bucket.AIRFREIGHT,
        description="Existing historical line",
        currency="PGK",
        amount="1.00",
        unit=SPEChargeLineDB.Unit.FLAT,
        source_reference="test",
        entered_by=user,
        entered_at=timezone.now(),
    )

    assert line.journey_leg_id is None
    assert line.charge_context_json == {}
    assert line.product_code_resolution_audit_json == {}


def test_persistence_writes_legs_in_contiguous_sequence():
    journey = persist(request_payload(origin="SIN", destination="LAE"))

    assert list(journey.legs.values_list("sequence", flat=True)) == [1, 2]
    assert list(journey.legs.values_list("leg_key", flat=True)) == ["01:INTERNATIONAL_IMPORT:SIN:POM", "02:DOMESTIC_ON_FORWARDING:POM:LAE"]


def test_read_only_diagnostic_command_performs_no_writes():
    before = {
        "journeys": ShipmentJourneyDB.objects.count(),
        "legs": ShipmentLegDB.objects.count(),
        "policies": RouteAutomationPolicyDB.objects.count(),
    }
    stdout = StringIO()

    call_command(
        "diagnose_air_journey_plan",
        "--request",
        json.dumps(request_payload(origin="SIN", destination="LAE")),
        stdout=stdout,
    )

    after = {
        "journeys": ShipmentJourneyDB.objects.count(),
        "legs": ShipmentLegDB.objects.count(),
        "policies": RouteAutomationPolicyDB.objects.count(),
    }
    payload = json.loads(stdout.getvalue())
    assert payload["pattern"] == "IMP_LAE"
    assert payload["route_policy"]["enabled"] is False
    assert payload["writes_performed"] is False
    assert after == before


def test_no_pricing_engine_productcode_resolver_or_spot_finalization_calls_occur():
    payload = request_payload(origin="SIN", destination="LAE")
    with patch("pricing_v4.adapter.PricingServiceV4Adapter.calculate_charges", side_effect=AssertionError("pricing called")), \
        patch("pricing_v4.engine.import_engine.ImportPricingEngine.calculate_quote", side_effect=AssertionError("import pricing called")), \
        patch("pricing_v4.engine.export_engine.ExportPricingEngine.calculate_quote", side_effect=AssertionError("export pricing called")), \
        patch("pricing_v4.engine.domestic_engine.DomesticPricingEngine.calculate_quote", side_effect=AssertionError("domestic pricing called")), \
        patch("pricing_v4.services.leg_aware_product_code_resolver.LegAwareProductCodeResolver.resolve", side_effect=AssertionError("resolver called")):
        journey = persist(payload)

    assert journey.legs.count() == 2
