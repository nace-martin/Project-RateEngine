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
from parties.models import Company
from quotes.models import Quote, RouteAutomationPolicyDB, ShipmentJourneyDB, ShipmentLegDB
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


def make_quote(user=None):
    user = user or make_user()
    customer = Company.objects.create(name=f"Phase 16E Customer {timezone.now().timestamp()}", is_customer=True)
    return Quote.objects.create(customer=customer, mode="AIR", shipment_type=Quote.ShipmentType.IMPORT, created_by=user)


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

    assert result.status == JourneyStatus.NEEDS_REVIEW
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

    assert result.status == JourneyStatus.NEEDS_REVIEW
    assert JourneyPlannerBlockerCode.JOURNEY_DIRECTION_UNSUPPORTED in result.blockers
    assert result.legs == []


def test_multi_stop_requests_fail_visibly_without_guessing_legs():
    result = plan(request_payload(origin="SIN", destination="LAE", via_codes=["BNE"]))

    assert result.status == JourneyStatus.NEEDS_REVIEW
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

    with pytest.raises((IntegrityError, ValidationError)):
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
                status=ShipmentJourneyDB.Status.NEEDS_REVIEW,
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


def assert_invalid_without_legs(payload, expected_blocker):
    result = plan(payload)
    assert result.status == JourneyStatus.NEEDS_REVIEW
    assert expected_blocker in result.blockers
    assert result.legs == []


def test_missing_import_overseas_origin_code_blocks_without_legs():
    assert_invalid_without_legs(request_payload(origin="", destination="POM"), JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)


def test_missing_export_overseas_destination_code_blocks_without_legs():
    assert_invalid_without_legs(request_payload(origin_country="PG", destination_country="SG", origin="POM", destination=""), JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)


def test_non_air_service_domain_blocks_without_legs():
    assert_invalid_without_legs(request_payload(service_domain="SEA"), JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID)


def test_missing_service_domain_blocks_without_legs():
    assert_invalid_without_legs(request_payload(service_domain=""), JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID)


def test_missing_quote_date_blocks_without_legs():
    assert_invalid_without_legs(request_payload(quote_date=""), JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID)


def test_non_png_country_with_png_origin_code_blocks_without_legs():
    assert_invalid_without_legs(request_payload(origin_country="SG", destination_country="PG", origin="POM", destination="LAE"), JourneyPlannerBlockerCode.JOURNEY_GATEWAY_INVALID)


def test_non_png_country_with_png_destination_code_blocks_without_legs():
    assert_invalid_without_legs(request_payload(origin_country="PG", destination_country="AU", origin="LAE", destination="LAE"), JourneyPlannerBlockerCode.JOURNEY_GATEWAY_INVALID)


def test_generic_supplier_origin_destination_text_cannot_be_trusted_route_codes():
    payload = request_payload()
    payload.pop("customer_origin_code")
    payload.pop("customer_destination_code")
    payload["origin"] = "Singapore free text"
    payload["destination"] = "Port Moresby free text"
    assert_invalid_without_legs(payload, JourneyPlannerBlockerCode.JOURNEY_PATTERN_UNSUPPORTED)


def test_invalid_numeric_date_and_boolean_inputs_return_controlled_blockers():
    result = plan(request_payload(actual_weight="not-decimal", quote_date="bad-date", pickup_requested="maybe"))
    assert result.status == JourneyStatus.NEEDS_REVIEW
    assert JourneyPlannerBlockerCode.JOURNEY_REQUEST_INVALID in result.blockers
    assert result.legs == []


def test_spot_only_journey_reused_when_quote_parent_later_supplied():
    user = make_user()
    spe = make_spe(user=user, origin="SIN", destination="POM")
    quote = make_quote(user=user)
    payload = request_payload(origin="SIN", destination="POM")

    first = ShipmentJourneyPersistenceService().persist_plan(plan=plan(payload), spot_envelope=spe, created_by=user)
    second = ShipmentJourneyPersistenceService().persist_plan(plan=plan(payload), quote=quote, spot_envelope=spe, created_by=user)

    assert second.id == first.id
    assert second.quote_id == quote.id
    assert second.spot_envelope_id == spe.id
    assert second.revision == 1
    assert ShipmentJourneyDB.objects.filter(quote=quote).count() == 1
    assert ShipmentJourneyDB.objects.filter(spot_envelope=spe).count() == 1


def test_quote_only_journey_reused_when_spot_parent_later_supplied():
    user = make_user()
    quote = make_quote(user=user)
    spe = make_spe(user=user, origin="SIN", destination="POM")
    payload = request_payload(origin="SIN", destination="POM")

    first = ShipmentJourneyPersistenceService().persist_plan(plan=plan(payload), quote=quote, created_by=user)
    second = ShipmentJourneyPersistenceService().persist_plan(plan=plan(payload), quote=quote, spot_envelope=spe, created_by=user)

    assert second.id == first.id
    assert second.quote_id == quote.id
    assert second.spot_envelope_id == spe.id
    assert ShipmentJourneyDB.objects.filter(quote=quote).count() == 1
    assert ShipmentJourneyDB.objects.filter(spot_envelope=spe).count() == 1


def test_fresh_journey_created_with_both_parents():
    user = make_user()
    quote = make_quote(user=user)
    spe = make_spe(user=user, origin="SIN", destination="POM")

    journey = ShipmentJourneyPersistenceService().persist_plan(plan=plan(request_payload(origin="SIN", destination="POM")), quote=quote, spot_envelope=spe, created_by=user)

    assert journey.quote_id == quote.id
    assert journey.spot_envelope_id == spe.id
    assert journey.revision == 1


def test_conflicting_quote_and_spot_histories_fail_closed():
    user = make_user()
    quote = make_quote(user=user)
    spe = make_spe(user=user, origin="SIN", destination="POM")
    service = ShipmentJourneyPersistenceService()
    service.persist_plan(plan=plan(request_payload(origin="SIN", destination="POM")), quote=quote, created_by=user)
    service.persist_plan(plan=plan(request_payload(origin="SIN", destination="LAE")), spot_envelope=spe, created_by=user)

    with pytest.raises(ValidationError, match="Conflicting quote and SPOT journey histories"):
        service.persist_plan(plan=plan(request_payload(origin="SIN", destination="POM")), quote=quote, spot_envelope=spe, created_by=user)


def test_no_duplicate_quote_or_spot_revision_numbers_on_parent_handover():
    user = make_user()
    quote = make_quote(user=user)
    spe = make_spe(user=user, origin="SIN", destination="POM")
    service = ShipmentJourneyPersistenceService()
    service.persist_plan(plan=plan(request_payload(origin="SIN", destination="POM")), spot_envelope=spe, created_by=user)
    service.persist_plan(plan=plan(request_payload(origin="SIN", destination="POM")), quote=quote, spot_envelope=spe, created_by=user)

    assert ShipmentJourneyDB.objects.filter(quote=quote, revision=1).count() == 1
    assert ShipmentJourneyDB.objects.filter(spot_envelope=spe, revision=1).count() == 1


def test_finalized_journey_may_receive_only_missing_parent_audit_link():
    user = make_user()
    quote = make_quote(user=user)
    spe = make_spe(user=user, origin="SIN", destination="POM")
    journey = ShipmentJourneyPersistenceService().persist_plan(plan=plan(request_payload(origin="SIN", destination="POM")), spot_envelope=spe, created_by=user)
    before = list(journey.legs.values("leg_key", "origin_code", "destination_code"))
    journey.status = ShipmentJourneyDB.Status.FINALIZED
    journey.finalized_at = timezone.now()
    journey.save()

    updated = ShipmentJourneyPersistenceService().attach_second_parent_reference(journey=journey, quote=quote)

    assert updated.quote_id == quote.id
    assert updated.status == ShipmentJourneyDB.Status.FINALIZED
    assert list(updated.legs.values("leg_key", "origin_code", "destination_code")) == before


def test_finalized_journey_route_and_leg_data_remain_immutable():
    journey = persist(request_payload(origin="SIN", destination="LAE"))
    leg = journey.legs.order_by("sequence").first()
    journey.status = ShipmentJourneyDB.Status.FINALIZED
    journey.finalized_at = timezone.now()
    journey.save()

    journey.customer_destination_code = "POM"
    with pytest.raises(ValidationError, match="immutable"):
        journey.save()
    leg.destination_code = "HGU"
    with pytest.raises(ValidationError, match="immutable"):
        leg.save()


def test_editing_deleting_or_adding_finalized_legs_fails():
    journey = persist(request_payload(origin="SIN", destination="POM"))
    leg = journey.legs.first()
    journey.status = ShipmentJourneyDB.Status.FINALIZED
    journey.finalized_at = timezone.now()
    journey.save()

    leg.service_scope = "D2D"
    with pytest.raises(ValidationError, match="immutable"):
        leg.save()
    with pytest.raises(ValidationError, match="immutable"):
        leg.delete()
    with pytest.raises(ValidationError, match="immutable"):
        ShipmentLegDB.objects.create(
            journey=journey,
            leg_key="02:DOMESTIC_ON_FORWARDING:POM:LAE",
            sequence=2,
            role=LegRole.DOMESTIC_ON_FORWARDING.value,
            transport_mode=TransportMode.DOMESTIC_AIR.value,
            origin_code="POM",
            destination_code="LAE",
            product_code_domain=ProductCodeDomain.DOMESTIC.value,
        )


def test_deleting_finalized_journey_fails():
    journey = persist(request_payload(origin="SIN", destination="POM"))
    journey.status = ShipmentJourneyDB.Status.FINALIZED
    journey.finalized_at = timezone.now()
    journey.save()

    with pytest.raises(ValidationError, match="cannot be deleted"):
        journey.delete()


def test_inconsistent_finalized_status_timestamp_fails_validation():
    journey = persist(request_payload(origin="SIN", destination="POM"))
    journey.status = ShipmentJourneyDB.Status.FINALIZED
    journey.finalized_at = None
    with pytest.raises(ValidationError, match="finalized_at"):
        journey.full_clean()
    journey.status = ShipmentJourneyDB.Status.PLANNED
    journey.finalized_at = timezone.now()
    with pytest.raises(ValidationError, match="FINALIZED"):
        journey.full_clean()


def test_revision_lifecycle_a_a_reuses_a_b_a_creates_third_revision():
    user = make_user()
    spe = make_spe(user=user, origin="SIN", destination="POM")
    service = ShipmentJourneyPersistenceService()
    payload_a = request_payload(origin="SIN", destination="POM")
    payload_b = request_payload(origin="SIN", destination="LAE")

    first = service.persist_plan(plan=plan(payload_a), spot_envelope=spe, created_by=user)
    same = service.persist_plan(plan=plan(payload_a), spot_envelope=spe, created_by=user)
    second = service.persist_plan(plan=plan(payload_b), spot_envelope=spe, created_by=user)
    third = service.persist_plan(plan=plan(payload_a), spot_envelope=spe, created_by=user)

    first.refresh_from_db()
    second.refresh_from_db()
    assert same.id == first.id
    assert second.revision == 2
    assert second.supersedes_id == first.id
    assert first.status == ShipmentJourneyDB.Status.SUPERSEDED
    assert third.revision == 3
    assert third.supersedes_id == second.id


def test_finalized_prior_revision_not_mutated_when_new_revision_created():
    user = make_user()
    spe = make_spe(user=user, origin="SIN", destination="POM")
    service = ShipmentJourneyPersistenceService()
    first = service.persist_plan(plan=plan(request_payload(origin="SIN", destination="POM")), spot_envelope=spe, created_by=user)
    first.status = ShipmentJourneyDB.Status.FINALIZED
    first.finalized_at = timezone.now()
    first.save()

    second = service.persist_plan(plan=plan(request_payload(origin="SIN", destination="LAE")), spot_envelope=spe, created_by=user)
    first.refresh_from_db()

    assert first.status == ShipmentJourneyDB.Status.FINALIZED
    assert second.supersedes_id == first.id
    assert second.revision == 2


def test_no_pricing_engine_productcode_resolver_or_spot_finalization_calls_occur():
    payload = request_payload(origin="SIN", destination="LAE")
    with patch("pricing_v4.adapter.PricingServiceV4Adapter.calculate_charges", side_effect=AssertionError("pricing called")), \
        patch("pricing_v4.engine.import_engine.ImportPricingEngine.calculate_quote", side_effect=AssertionError("import pricing called")), \
        patch("pricing_v4.engine.export_engine.ExportPricingEngine.calculate_quote", side_effect=AssertionError("export pricing called")), \
        patch("pricing_v4.engine.domestic_engine.DomesticPricingEngine.calculate_quote", side_effect=AssertionError("domestic pricing called")), \
        patch("pricing_v4.services.leg_aware_product_code_resolver.LegAwareProductCodeResolver.resolve", side_effect=AssertionError("resolver called")):
        journey = persist(payload)

    assert journey.legs.count() == 2
