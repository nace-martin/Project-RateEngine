import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from core.dataclasses import (
    CalculatedChargeLine,
    CalculatedTotals,
    QuoteCharges,
    QuoteInput,
    ShipmentDetails,
    Piece,
    LocationRef,
)
from core.models import Currency, Country, Location
from pricing_v4.adapter import PricingServiceV4Adapter, PricingMode
from quotes.completeness import (
    evaluate_from_lines,
    COMPONENT_DESTINATION_LOCAL,
    COMPONENT_ORIGIN_LOCAL,
    COMPONENT_FREIGHT,
)
from quotes.reply_schemas import (
    ReplyAnalysisResult,
    ExtractedAssertion,
    AssertionCategory,
    AssertionStatus,
    AnalysisSummary,
)
from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB, SPEAcknowledgementDB
from quotes.spot_services import ReplyAnalysisService, SpotTriggerReason


pytestmark = pytest.mark.django_db


def _create_location(code: str, country: Country) -> Location:
    return Location.objects.create(
        code=code,
        name=f"{code} Airport",
        country=country,
    )


def _setup_user_and_locations():
    currency = Currency.objects.create(code="PGK", name="Papua New Guinea Kina")
    pg = Country.objects.create(code="PG", name="Papua New Guinea", currency=currency)
    au = Country.objects.create(code="AU", name="Australia", currency=currency)

    origin = _create_location("BNE", au)
    destination = _create_location("POM", pg)

    user = get_user_model().objects.create_user(username="spotuser", password="testpass")
    return user, origin, destination


def _create_spe(
    user,
    origin_code: str,
    dest_code: str,
    origin_country: str,
    dest_country: str,
    service_scope: str,
    status: str = "draft",
):
    ctx = {
        "origin_country": origin_country,
        "destination_country": dest_country,
        "origin_code": origin_code,
        "destination_code": dest_code,
        "commodity": "GCR",
        "total_weight_kg": 100.0,
        "pieces": 1,
        "service_scope": service_scope.lower(),
    }

    return SpotPricingEnvelopeDB.objects.create(
        status=status,
        shipment_context_json=ctx,
        conditions_json={},
        spot_trigger_reason_code=SpotTriggerReason.MISSING_SCOPE_RATES,
        spot_trigger_reason_text="Missing required rate components",
        created_by=user,
        expires_at=timezone.now() + timedelta(hours=72),
    )


def _acknowledge_spe(user, spe: SpotPricingEnvelopeDB):
    SPEAcknowledgementDB.objects.create(
        envelope=spe,
        acknowledged_by=user,
        acknowledged_at=timezone.now(),
        statement=SPEAcknowledgementDB.ACKNOWLEDGEMENT_STATEMENT,
    )


def _quote_input(shipment_type: str, service_scope: str) -> QuoteInput:
    origin_ref = LocationRef(
        id=uuid.uuid4(),
        code="BNE",
        name="BNE Airport",
        country_code="AU",
        currency_code="AUD",
    )
    dest_ref = LocationRef(
        id=uuid.uuid4(),
        code="POM",
        name="POM Airport",
        country_code="PG",
        currency_code="PGK",
    )

    shipment = ShipmentDetails(
        mode="AIR",
        shipment_type=shipment_type,
        incoterm="DAP",
        payment_term="PREPAID",
        is_dangerous_goods=False,
        pieces=[
            Piece(
                pieces=1,
                length_cm=Decimal("10"),
                width_cm=Decimal("10"),
                height_cm=Decimal("10"),
                gross_weight_kg=Decimal("100"),
            )
        ],
        service_scope=service_scope,
        origin_location=origin_ref,
        destination_location=dest_ref,
    )

    return QuoteInput(
        customer_id=uuid.uuid4(),
        contact_id=uuid.uuid4(),
        output_currency="PGK",
        quote_date=date.today(),
        shipment=shipment,
    )


def _analysis_result_with_components():
    assertions = [
        ExtractedAssertion(
            text="Airfreight rate",
            category=AssertionCategory.RATE,
            status=AssertionStatus.CONFIRMED,
            confidence=0.95,
            rate_amount=Decimal("5.00"),
            rate_currency="USD",
            rate_unit="per_kg",
        ),
        ExtractedAssertion(
            text="Origin handling",
            category=AssertionCategory.ORIGIN_CHARGES,
            status=AssertionStatus.CONFIRMED,
            confidence=0.95,
            rate_amount=Decimal("50.00"),
            rate_currency="USD",
            rate_unit="flat",
        ),
        ExtractedAssertion(
            text="Destination handling",
            category=AssertionCategory.DEST_CHARGES,
            status=AssertionStatus.CONFIRMED,
            confidence=0.95,
            rate_amount=Decimal("75.00"),
            rate_currency="USD",
            rate_unit="flat",
        ),
    ]

    summary = AnalysisSummary(
        has_rate=True,
        has_currency=True,
    )

    return ReplyAnalysisResult(
        raw_text="Airfreight 5/kg, origin 50, dest 75",
        assertions=assertions,
        summary=summary,
        warnings=[],
    )


def test_ai_reply_analysis_autopopulates_spe_charges(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
        status="draft",
    )

    analysis_result = _analysis_result_with_components()
    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", lambda *args, **kwargs: analysis_result)

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/spot/analyze-reply/",
        {"text": "rate reply", "spe_id": str(spe.id), "use_ai": True},
        format="json",
    )

    assert response.status_code == 200

    spe.refresh_from_db()
    charges = list(spe.charge_lines.all())

    assert {c.bucket for c in charges} == {"airfreight", "origin_charges", "destination_charges"}
    assert COMPONENT_FREIGHT in {c.code for c in charges}
    assert COMPONENT_ORIGIN_LOCAL in {c.code for c in charges}
    assert COMPONENT_DESTINATION_LOCAL in {c.code for c in charges}
    assert any(c.is_primary_cost for c in charges if c.bucket == "airfreight")


def test_percentage_only_charge_does_not_satisfy_required_component():
    user = get_user_model().objects.create_user(username="spotpct", password="testpass")
    spe = _create_spe(
        user=user,
        origin_code="BNE",
        dest_code="POM",
        origin_country="AU",
        dest_country="PG",
        service_scope="A2D",
        status="ready",
    )
    _acknowledge_spe(user, spe)

    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="FREIGHT",
        description="Airfreight",
        amount=Decimal("5.00"),
        currency="USD",
        unit="per_kg",
        bucket="airfreight",
        is_primary_cost=True,
        entered_at=timezone.now(),
        source_reference="Test",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="DEST_PCT",
        description="Destination surcharge",
        amount=Decimal("10.00"),
        currency="USD",
        unit="percentage",
        bucket="destination_charges",
        is_primary_cost=False,
        entered_at=timezone.now(),
        source_reference="Test",
    )

    adapter = PricingServiceV4Adapter(_quote_input("IMPORT", "A2D"), spot_envelope_id=spe.id)
    lines = adapter._calculate_spot_lines()

    dest_lines = [line for line in lines if line.bucket == "destination_charges"]
    assert dest_lines, "Expected destination line for percentage charge"
    assert all(line.is_informational for line in dest_lines)

    coverage = evaluate_from_lines(lines, "IMPORT", "A2D")
    assert COMPONENT_DESTINATION_LOCAL in coverage.missing_required


def test_conditional_charge_does_not_satisfy_completeness():
    user = get_user_model().objects.create_user(username="spotcond", password="testpass")
    spe = _create_spe(
        user=user,
        origin_code="POM",
        dest_code="BNE",
        origin_country="PG",
        dest_country="AU",
        service_scope="D2A",
        status="ready",
    )
    _acknowledge_spe(user, spe)

    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="FREIGHT",
        description="Airfreight",
        amount=Decimal("5.00"),
        currency="USD",
        unit="per_kg",
        bucket="airfreight",
        is_primary_cost=True,
        entered_at=timezone.now(),
        source_reference="Test",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="ORIGIN_COND",
        description="Origin handling (conditional)",
        amount=Decimal("25.00"),
        currency="USD",
        unit="flat",
        bucket="origin_charges",
        is_primary_cost=False,
        conditional=True,
        entered_at=timezone.now(),
        source_reference="Test",
    )

    adapter = PricingServiceV4Adapter(_quote_input("EXPORT", "D2A"), spot_envelope_id=spe.id)
    lines = adapter._calculate_spot_lines()

    origin_lines = [line for line in lines if line.bucket == "origin_charges"]
    assert origin_lines, "Expected origin line for conditional charge"
    assert all(line.is_informational for line in origin_lines)

    coverage = evaluate_from_lines(lines, "EXPORT", "D2A")
    assert COMPONENT_ORIGIN_LOCAL in coverage.missing_required


def test_ai_fill_makes_spe_complete_for_compute(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
        status="draft",
    )

    coverage_before = evaluate_from_lines([], "IMPORT", "D2D")
    assert COMPONENT_FREIGHT in coverage_before.missing_required
    assert COMPONENT_ORIGIN_LOCAL in coverage_before.missing_required
    assert COMPONENT_DESTINATION_LOCAL in coverage_before.missing_required

    analysis_result = _analysis_result_with_components()
    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", lambda *args, **kwargs: analysis_result)

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/v3/spot/analyze-reply/",
        {"text": "rate reply", "spe_id": str(spe.id), "use_ai": True},
        format="json",
    )
    assert response.status_code == 200

    # Mark SPE ready and acknowledge for compute
    SpotPricingEnvelopeDB.objects.filter(id=spe.id).update(status=SpotPricingEnvelopeDB.Status.READY)
    spe.refresh_from_db()
    _acknowledge_spe(user, spe)

    def fake_calculate(self):
        self.pricing_mode = PricingMode.SPOT
        spe_db = SpotPricingEnvelopeDB.objects.prefetch_related("charge_lines").get(id=self.spot_envelope_id)
        lines = []
        for cl in spe_db.charge_lines.all():
            lines.append(CalculatedChargeLine(
                service_component_id=uuid.uuid4(),
                service_component_code=cl.code,
                service_component_desc=cl.description,
                leg="MAIN",
                cost_pgk=Decimal("0.0"),
                sell_pgk=Decimal("0.0"),
                sell_pgk_incl_gst=Decimal("0.0"),
                sell_fcy=Decimal("0.0"),
                sell_fcy_incl_gst=Decimal("0.0"),
                cost_source="SPOT",
                bucket=cl.bucket,
                is_informational=cl.conditional,
                is_rate_missing=False,
            ))

        totals = CalculatedTotals(
            total_cost_pgk=Decimal("0.0"),
            total_sell_pgk=Decimal("0.0"),
            total_sell_pgk_incl_gst=Decimal("0.0"),
            total_sell_fcy=Decimal("0.0"),
            total_sell_fcy_incl_gst=Decimal("0.0"),
            total_sell_fcy_currency="PGK",
            has_missing_rates=False,
            notes=None,
        )
        return QuoteCharges(lines=lines, totals=totals)

    monkeypatch.setattr(PricingServiceV4Adapter, "calculate_charges", fake_calculate)

    compute_response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/compute/",
        {"quote_request": {"service_scope": "D2D", "payment_term": "PREPAID", "output_currency": "PGK"}},
        format="json",
    )

    assert compute_response.status_code == 200
    data = compute_response.json()
    assert data["is_complete"] is True
