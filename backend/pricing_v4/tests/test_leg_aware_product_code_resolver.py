from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from pricing_v4.contracts.charge_context import (
    ChargeContext,
    CommercialPosition,
    JourneyDirection,
    JourneyPattern,
    LegRole,
    ProductCodeDomain,
    ProductCodeResolutionStatus,
    TransportMode,
)
from pricing_v4.models import CanonicalChargeType, ProductCode, ProductCodeContextRule
from pricing_v4.services.leg_aware_product_code_resolver import LegAwareProductCodeResolver

pytestmark = pytest.mark.django_db


def product_code(id_: int, code: str, domain: str, *, active: bool = True, retired: bool = False) -> ProductCode:
    product = ProductCode.objects.create(
        id=id_,
        code=code,
        description=code.replace("-", " "),
        domain=domain,
        category=ProductCode.CATEGORY_FREIGHT,
        is_gst_applicable=domain != ProductCode.DOMAIN_EXPORT,
        gst_rate="0.1000" if domain != ProductCode.DOMAIN_EXPORT else "0.0000",
        gst_treatment=ProductCode.GST_TREATMENT_STANDARD if domain != ProductCode.DOMAIN_EXPORT else ProductCode.GST_TREATMENT_ZERO_RATED,
        gl_revenue_code="4100",
        gl_cost_code="5100",
        default_unit=ProductCode.UNIT_SHIPMENT,
        is_active=active,
        retired_at=timezone.now() if retired else None,
    )
    return product


def canonical_type(code: str = "AIR_FREIGHT") -> CanonicalChargeType:
    charge_type, _ = CanonicalChargeType.objects.get_or_create(
        code=code,
        defaults={
            "name": code.replace("_", " ").title(),
            "category": "FREIGHT",
            "is_active": True,
        },
    )
    charge_type.is_active = True
    charge_type.save(update_fields=["is_active"])
    return charge_type


def make_rule(
    charge_type: CanonicalChargeType,
    product: ProductCode,
    *,
    leg_role: LegRole,
    commercial_position: CommercialPosition = CommercialPosition.FREIGHT,
    transport_mode: TransportMode = TransportMode.INTERNATIONAL_AIR,
    operational_location: str = "",
    calculation_basis: str = "",
    service_scope: str = "",
    priority: int = 100,
    active: bool = True,
    review_status: str = ProductCodeContextRule.ReviewStatus.APPROVED,
) -> ProductCodeContextRule:
    rule = ProductCodeContextRule.objects.create(
        canonical_charge_type=charge_type,
        product_code=product,
        product_code_domain=product.domain,
        leg_role=leg_role.value,
        commercial_position=commercial_position.value,
        transport_mode=transport_mode.value,
        operational_location=operational_location,
        calculation_basis=calculation_basis,
        service_scope=service_scope,
        priority=priority,
        is_active=active,
        review_status=review_status,
        source=ProductCodeContextRule.RuleSource.ADMIN,
    )
    rule.full_clean()
    return rule


def context(
    *,
    direction: JourneyDirection = JourneyDirection.IMPORT,
    pattern: JourneyPattern = JourneyPattern.IMP_POM,
    leg_role: LegRole = LegRole.INTERNATIONAL_IMPORT,
    domain: ProductCodeDomain = ProductCodeDomain.IMPORT,
    position: CommercialPosition = CommercialPosition.FREIGHT,
    mode: TransportMode = TransportMode.INTERNATIONAL_AIR,
    canonical: str = "AIR_FREIGHT",
    operational_location: str | None = None,
    calculation_basis: str | None = None,
    service_scope: str | None = None,
) -> ChargeContext:
    return ChargeContext(
        journey_direction=direction,
        journey_pattern=pattern,
        leg_role=leg_role,
        leg_sequence=1,
        product_code_domain=domain,
        commercial_position=position,
        transport_mode=mode,
        canonical_charge_type=canonical,
        leg_key="01:test",
        operational_location=operational_location,
        calculation_basis=calculation_basis,
        service_scope=service_scope,
        currency="PGK",
        tax_treatment="STANDARD",
        source_evidence={"source": "test"},
    )


def resolve(ctx: ChargeContext, requested=None):
    return LegAwareProductCodeResolver().resolve(ctx, requested_product_code=requested)


def test_international_import_leg_selects_import_product_code():
    cct = canonical_type()
    pc = product_code(2101, "IMP-AIR-FRT", ProductCode.DOMAIN_IMPORT)
    make_rule(cct, pc, leg_role=LegRole.INTERNATIONAL_IMPORT)

    result = resolve(context())

    assert result.status == ProductCodeResolutionStatus.ASSIGNED
    assert result.selected_product_code == "IMP-AIR-FRT"
    assert result.resolved_context["product_code_domain"] == "IMPORT"


def test_international_export_leg_selects_export_product_code():
    cct = canonical_type()
    pc = product_code(1101, "EXP-AIR-FRT", ProductCode.DOMAIN_EXPORT)
    make_rule(cct, pc, leg_role=LegRole.INTERNATIONAL_EXPORT)

    result = resolve(
        context(
            direction=JourneyDirection.EXPORT,
            pattern=JourneyPattern.EXP_POM,
            leg_role=LegRole.INTERNATIONAL_EXPORT,
            domain=ProductCodeDomain.EXPORT,
        )
    )

    assert result.status == ProductCodeResolutionStatus.ASSIGNED
    assert result.selected_product_code == "EXP-AIR-FRT"


@pytest.mark.parametrize(
    "leg_role,pattern",
    [
        (LegRole.DOMESTIC_ON_FORWARDING, JourneyPattern.IMP_LAE),
        (LegRole.DOMESTIC_PRE_CARRIAGE, JourneyPattern.EXP_LAE),
    ],
)
def test_domestic_on_forwarding_and_pre_carriage_select_domestic_product_codes(leg_role, pattern):
    cct = canonical_type()
    pc = product_code(3101, "DOM-AIR-FRT", ProductCode.DOMAIN_DOMESTIC)
    make_rule(cct, pc, leg_role=leg_role, transport_mode=TransportMode.DOMESTIC_AIR)

    result = resolve(
        context(
            pattern=pattern,
            leg_role=leg_role,
            domain=ProductCodeDomain.DOMESTIC,
            mode=TransportMode.DOMESTIC_AIR,
        )
    )

    assert result.status == ProductCodeResolutionStatus.ASSIGNED
    assert result.selected_product_code == "DOM-AIR-FRT"


def test_overall_journey_direction_cannot_override_leg_domain():
    cct = canonical_type()
    domestic = product_code(3102, "DOM-IMPORT-JOURNEY-FRT", ProductCode.DOMAIN_DOMESTIC)
    make_rule(cct, domestic, leg_role=LegRole.DOMESTIC_ON_FORWARDING, transport_mode=TransportMode.DOMESTIC_AIR)

    result = resolve(
        context(
            direction=JourneyDirection.IMPORT,
            pattern=JourneyPattern.IMP_LAE,
            leg_role=LegRole.DOMESTIC_ON_FORWARDING,
            domain=ProductCodeDomain.DOMESTIC,
            mode=TransportMode.DOMESTIC_AIR,
        )
    )

    assert result.status == ProductCodeResolutionStatus.ASSIGNED
    assert result.selected_product_code == domestic.code


def test_raw_client_direction_cannot_override_trusted_context_domain():
    cct = canonical_type()
    domestic = product_code(3103, "DOM-TRUSTED-FRT", ProductCode.DOMAIN_DOMESTIC)
    make_rule(cct, domestic, leg_role=LegRole.DOMESTIC_ON_FORWARDING, transport_mode=TransportMode.DOMESTIC_AIR)

    raw_payload = context(
        direction=JourneyDirection.IMPORT,
        pattern=JourneyPattern.IMP_LAE,
        leg_role=LegRole.DOMESTIC_ON_FORWARDING,
        domain=ProductCodeDomain.DOMESTIC,
        mode=TransportMode.DOMESTIC_AIR,
    ).to_audit_dict()
    raw_payload["raw_client_direction"] = "EXPORT"

    result = LegAwareProductCodeResolver().resolve(raw_payload)

    assert result.status == ProductCodeResolutionStatus.ASSIGNED
    assert result.resolved_context["product_code_domain"] == "DOMESTIC"


def test_exact_single_match_assigns():
    cct = canonical_type()
    generic = product_code(2102, "IMP-GENERIC", ProductCode.DOMAIN_IMPORT)
    specific = product_code(2103, "IMP-POM-SPECIFIC", ProductCode.DOMAIN_IMPORT)
    make_rule(cct, generic, leg_role=LegRole.INTERNATIONAL_IMPORT)
    make_rule(cct, specific, leg_role=LegRole.INTERNATIONAL_IMPORT, operational_location="POM")

    result = resolve(context(operational_location="POM"))

    assert result.status == ProductCodeResolutionStatus.ASSIGNED
    assert result.selected_product_code == specific.code


def test_equal_specificity_matches_remain_ambiguous():
    cct = canonical_type()
    first = product_code(2104, "IMP-AMB-1", ProductCode.DOMAIN_IMPORT)
    second = product_code(2105, "IMP-AMB-2", ProductCode.DOMAIN_IMPORT)
    make_rule(cct, first, leg_role=LegRole.INTERNATIONAL_IMPORT)
    make_rule(cct, second, leg_role=LegRole.INTERNATIONAL_IMPORT)

    result = resolve(context())

    assert result.status == ProductCodeResolutionStatus.NEEDS_CLARIFICATION
    assert "Equal-specificity" in result.review_reason


def test_priority_cannot_hide_equal_specificity_configuration_conflict():
    cct = canonical_type()
    first = product_code(2106, "IMP-PRIORITY-1", ProductCode.DOMAIN_IMPORT)
    second = product_code(2107, "IMP-PRIORITY-2", ProductCode.DOMAIN_IMPORT)
    make_rule(cct, first, leg_role=LegRole.INTERNATIONAL_IMPORT, priority=1)
    make_rule(cct, second, leg_role=LegRole.INTERNATIONAL_IMPORT, priority=999)

    result = resolve(context())

    assert result.status == ProductCodeResolutionStatus.NEEDS_CLARIFICATION


def test_missing_context_fails_closed():
    result = LegAwareProductCodeResolver().resolve(
        {
            "journey_direction": "IMPORT",
            "journey_pattern": "IMP_POM",
            "leg_role": "INTERNATIONAL_IMPORT",
            "leg_sequence": 1,
            "product_code_domain": "IMPORT",
            "commercial_position": "FREIGHT",
            "transport_mode": "INTERNATIONAL_AIR",
            "canonical_charge_type": "",
        }
    )

    assert result.status == ProductCodeResolutionStatus.CONTEXT_INCOMPLETE


def test_no_rule_returns_not_found():
    canonical_type()

    result = resolve(context())

    assert result.status == ProductCodeResolutionStatus.NOT_FOUND


def test_inactive_or_unapproved_rule_is_ignored():
    cct = canonical_type()
    inactive = product_code(2108, "IMP-INACTIVE-RULE", ProductCode.DOMAIN_IMPORT)
    candidate = product_code(2109, "IMP-CANDIDATE-RULE", ProductCode.DOMAIN_IMPORT)
    make_rule(cct, inactive, leg_role=LegRole.INTERNATIONAL_IMPORT, active=False)
    make_rule(
        cct,
        candidate,
        leg_role=LegRole.INTERNATIONAL_IMPORT,
        active=False,
        review_status=ProductCodeContextRule.ReviewStatus.CANDIDATE,
    )

    result = resolve(context())

    assert result.status == ProductCodeResolutionStatus.NOT_FOUND


def test_retired_product_code_is_never_assigned():
    cct = canonical_type()
    retired = product_code(2110, "IMP-RETIRED", ProductCode.DOMAIN_IMPORT, active=False, retired=True)
    ProductCodeContextRule.objects.create(
        canonical_charge_type=cct,
        product_code=retired,
        product_code_domain=ProductCode.DOMAIN_IMPORT,
        leg_role=LegRole.INTERNATIONAL_IMPORT.value,
        commercial_position=CommercialPosition.FREIGHT.value,
        transport_mode=TransportMode.INTERNATIONAL_AIR.value,
        is_active=True,
        review_status=ProductCodeContextRule.ReviewStatus.APPROVED,
    )

    result = resolve(context())

    assert result.status == ProductCodeResolutionStatus.NOT_FOUND


def test_incompatible_manual_product_code_selection_is_rejected():
    cct = canonical_type()
    export = product_code(1102, "EXP-WRONG", ProductCode.DOMAIN_EXPORT)
    import_pc = product_code(2111, "IMP-RIGHT", ProductCode.DOMAIN_IMPORT)
    make_rule(cct, import_pc, leg_role=LegRole.INTERNATIONAL_IMPORT)

    result = resolve(context(), requested=export)

    assert result.status == ProductCodeResolutionStatus.REJECTED
    assert "domain" in result.review_reason.lower()


def test_context_rule_domain_validation():
    cct = canonical_type()
    import_pc = product_code(2112, "IMP-VALIDATION", ProductCode.DOMAIN_IMPORT)
    rule = ProductCodeContextRule(
        canonical_charge_type=cct,
        product_code=import_pc,
        product_code_domain=ProductCode.DOMAIN_EXPORT,
        leg_role=LegRole.INTERNATIONAL_IMPORT.value,
        commercial_position=CommercialPosition.FREIGHT.value,
        transport_mode=TransportMode.INTERNATIONAL_AIR.value,
        is_active=True,
        review_status=ProductCodeContextRule.ReviewStatus.APPROVED,
    )

    with pytest.raises(Exception, match="Rule domain must equal ProductCode domain"):
        rule.full_clean()


def test_diagnostic_execution_performs_no_writes():
    cct = canonical_type()
    pc = product_code(2113, "IMP-DIAG", ProductCode.DOMAIN_IMPORT)
    make_rule(cct, pc, leg_role=LegRole.INTERNATIONAL_IMPORT)
    before_counts = {
        "product_codes": ProductCode.objects.count(),
        "rules": ProductCodeContextRule.objects.count(),
        "canonical": CanonicalChargeType.objects.count(),
    }
    stdout = StringIO()

    call_command(
        "diagnose_leg_aware_product_codes",
        "--context",
        json.dumps(context().to_audit_dict()),
        "--format",
        "json",
        stdout=stdout,
    )

    after_counts = {
        "product_codes": ProductCode.objects.count(),
        "rules": ProductCodeContextRule.objects.count(),
        "canonical": CanonicalChargeType.objects.count(),
    }
    payload = json.loads(stdout.getvalue())
    assert payload["summary"]["ASSIGNED"] == 1
    assert payload["writes_detected"] is False
    assert after_counts == before_counts
