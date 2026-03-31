import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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
from core.tests.helpers import create_location
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
    AnalysisSafetySignals,
)
from quotes.ai_intake_schemas import RawExtractedCharge, NormalizedCharge, ExtractionAuditResult
from quotes.spot_models import (
    SpotPricingEnvelopeDB,
    SPESourceBatchDB,
    SPEChargeLineDB,
    SPEAcknowledgementDB,
)
from quotes.spot_services import ReplyAnalysisService, SpotTriggerReason


pytestmark = pytest.mark.django_db


def _create_location(code: str, country: Country) -> Location:
    return create_location(
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
    missing_components=None,
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
    if missing_components is not None:
        ctx["missing_components"] = list(missing_components)

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


def _quote_input(shipment_type: str, service_scope: str, weight_kg: Decimal = Decimal("100")) -> QuoteInput:
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
                gross_weight_kg=weight_kg,
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
        missing_components=[COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL],
    )

    analysis_result = _analysis_result_with_components()
    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", lambda *args, **kwargs: analysis_result)
    monkeypatch.setattr(
        "quotes.spot_services.RateAvailabilityService.get_availability",
        lambda **kwargs: {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        },
    )

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


def test_ai_reply_analysis_creates_source_batch_and_links_lines(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
        status="draft",
        missing_components=[COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL],
    )

    analysis_result = _analysis_result_with_components()
    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", lambda *args, **kwargs: analysis_result)
    monkeypatch.setattr(
        "quotes.spot_services.RateAvailabilityService.get_availability",
        lambda **kwargs: {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        },
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/spot/analyze-reply/",
        {
            "text": "airline freight and local costs",
            "spe_id": str(spe.id),
            "use_ai": True,
            "source_kind": "AIRLINE",
            "target_bucket": "airfreight",
            "label": "PX Freight Quote",
        },
        format="json",
    )

    assert response.status_code == 200
    payload = response.json()

    source_batch = SPESourceBatchDB.objects.get(id=payload["source_batch_id"])
    assert source_batch.envelope_id == spe.id
    assert source_batch.source_kind == SPESourceBatchDB.SourceKind.AIRLINE
    assert source_batch.target_bucket == SPESourceBatchDB.TargetBucket.AIRFREIGHT
    assert source_batch.label == "PX Freight Quote"
    assert source_batch.charge_lines.count() == 3
    assert spe.charge_lines.exclude(source_batch=source_batch).count() == 0

    detail_response = client.get(f"/api/v3/spot/envelopes/{spe.id}/")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert len(detail_payload["sources"]) == 1
    assert detail_payload["sources"][0]["label"] == "PX Freight Quote"
    assert detail_payload["sources"][0]["charge_count"] == 3
    assert {charge["source_batch_id"] for charge in detail_payload["charges"]} == {str(source_batch.id)}


def test_ai_reply_analysis_reuses_matching_batch_and_preserves_other_batches(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
        status="draft",
        missing_components=[COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL],
    )

    analysis_result = _analysis_result_with_components()
    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", lambda *args, **kwargs: analysis_result)
    monkeypatch.setattr(
        "quotes.spot_services.RateAvailabilityService.get_availability",
        lambda **kwargs: {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        },
    )

    client = APIClient()
    client.force_authenticate(user=user)

    first_response = client.post(
        "/api/v3/spot/analyze-reply/",
        {
            "text": "airline quote v1",
            "spe_id": str(spe.id),
            "use_ai": True,
            "source_kind": "AIRLINE",
            "target_bucket": "airfreight",
            "label": "PX Freight Quote",
        },
        format="json",
    )
    assert first_response.status_code == 200
    first_batch_id = first_response.json()["source_batch_id"]

    second_response = client.post(
        "/api/v3/spot/analyze-reply/",
        {
            "text": "agent destination quote",
            "spe_id": str(spe.id),
            "use_ai": True,
            "source_kind": "AGENT",
            "target_bucket": "destination_charges",
            "label": "KUL Agent Charges",
        },
        format="json",
    )
    assert second_response.status_code == 200
    second_batch_id = second_response.json()["source_batch_id"]
    assert second_batch_id != first_batch_id

    third_response = client.post(
        "/api/v3/spot/analyze-reply/",
        {
            "text": "airline quote v2",
            "spe_id": str(spe.id),
            "use_ai": True,
            "source_kind": "AIRLINE",
            "target_bucket": "airfreight",
            "label": "PX Freight Quote",
        },
        format="json",
    )
    assert third_response.status_code == 200
    assert third_response.json()["source_batch_id"] == first_batch_id

    first_batch = SPESourceBatchDB.objects.get(id=first_batch_id)
    second_batch = SPESourceBatchDB.objects.get(id=second_batch_id)
    assert first_batch.charge_lines.count() == 3
    assert second_batch.charge_lines.count() == 3
    assert spe.source_batches.count() == 2
    assert spe.charge_lines.count() == 6


def test_ai_reply_analysis_accepts_pdf_upload(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
        status="draft",
        missing_components=[COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL],
    )

    analysis_result = _analysis_result_with_components()
    captured = {}

    def _fake_analyze_with_ai(*, raw_text, shipment_context=None, availability=None):
        captured["raw_text"] = raw_text
        return analysis_result

    class _ExtractionResult:
        success = True
        text = "PDF extracted rate reply"
        warnings = ["Used Gemini multimodal PDF extraction fallback."]
        error = None

    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", _fake_analyze_with_ai)
    monkeypatch.setattr("quotes.ai_intake_service.extract_rate_quote_text_from_pdf", lambda _content, context=None: _ExtractionResult())
    monkeypatch.setattr(
        "quotes.spot_services.RateAvailabilityService.get_availability",
        lambda **kwargs: {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        },
    )

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/spot/analyze-reply/",
        {
            "file": SimpleUploadedFile("quote.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
            "spe_id": str(spe.id),
            "use_ai": "true",
        },
        format="multipart",
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["raw_text"] == "PDF extracted rate reply"
    assert any("multimodal PDF extraction fallback" in warning for warning in payload["warnings"])

    spe.refresh_from_db()
    assert spe.charge_lines.count() == 3


def test_ai_reply_analysis_pdf_extraction_failure_returns_400(monkeypatch):
    user, _, _ = _setup_user_and_locations()

    class _ExtractionResult:
        success = False
        text = ""
        warnings = []
        error = "PDF extraction failed"

    monkeypatch.setattr("quotes.ai_intake_service.extract_rate_quote_text_from_pdf", lambda _content, context=None: _ExtractionResult())

    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post(
        "/api/v3/spot/analyze-reply/",
        {
            "file": SimpleUploadedFile("quote.pdf", b"%PDF-1.4 fake", content_type="application/pdf"),
            "use_ai": "true",
        },
        format="multipart",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "PDF extraction failed"


def test_ai_rule_meta_null_is_accepted_and_persisted(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="P2P",
        status="draft",
        missing_components=[COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL],
    )

    class _FakeModel:
        pass

    class _FakeGenAI:
        def GenerativeModel(self, _model_name):
            return _FakeModel()

    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_raw_charges",
        lambda model, text, shipment_context=None: [
            RawExtractedCharge(
                raw_label="Airfreight",
                raw_amount_string="USD 5.00/kg",
                currency_hint="USD",
                is_conditional=False,
            )
        ],
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._normalize_charges",
        lambda model, raw_charges, shipment_context=None, quote_currency_hint=None: [
            NormalizedCharge(
                original_raw_label="Airfreight",
                v4_product_code="FREIGHT",
                v4_bucket="FREIGHT",
                unit_basis="PER_KG",
                amount=Decimal("5.00"),
                rate_per_unit=Decimal("5.00"),
                currency="USD",
                confidence="HIGH",
            )
        ],
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._audit_extraction",
        lambda model, original_text, normalized_charges: ExtractionAuditResult(
            is_safe_to_proceed=True,
            missed_charges=[],
            hallucinations_detected=[],
        ),
    )

    monkeypatch.setattr(
        "quotes.ai_intake_service.get_gemini_client",
        lambda: _FakeGenAI(),
    )

    monkeypatch.setattr(
        "quotes.spot_services.RateAvailabilityService.get_availability",
        lambda **kwargs: {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        },
    )

    client = APIClient()
    client.force_authenticate(user=user)

    analyze_response = client.post(
        "/api/v3/spot/analyze-reply/",
        {
            "text": "Airfreight USD 5/kg confirmed for this lane.",
            "spe_id": str(spe.id),
            "use_ai": True,
        },
        format="json",
    )
    assert analyze_response.status_code == 200

    spe.refresh_from_db()
    charges = list(spe.charge_lines.all())
    assert charges, "Expected AI auto-fill to persist at least one charge"
    assert all((charge.rule_meta or {}) == {} for charge in charges)

    detail_response = client.get(f"/api/v3/spot/envelopes/{spe.id}/")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["charges"], "Expected charges in SPE detail payload"
    assert all(charge["rule_meta"] == {} for charge in detail_payload["charges"])


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
        missing_components=[COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL],
    )

    coverage_before = evaluate_from_lines([], "IMPORT", "D2D")
    assert COMPONENT_FREIGHT in coverage_before.missing_required
    assert COMPONENT_ORIGIN_LOCAL in coverage_before.missing_required
    assert COMPONENT_DESTINATION_LOCAL in coverage_before.missing_required

    analysis_result = _analysis_result_with_components()
    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", lambda *args, **kwargs: analysis_result)
    monkeypatch.setattr(
        "quotes.spot_services.RateAvailabilityService.get_availability",
        lambda **kwargs: {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        },
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/v3/spot/analyze-reply/",
        {"text": "rate reply", "spe_id": str(spe.id), "use_ai": True},
        format="json",
    )
    assert response.status_code == 200

    source_batch_id = response.json()["source_batch_id"]
    review_response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/sources/{source_batch_id}/review/",
        {"reviewed_safe_to_quote": True},
        format="json",
    )
    assert review_response.status_code == 200

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


def test_ai_source_warnings_do_not_block_acknowledgement(monkeypatch):
    user, origin, destination = _setup_user_and_locations()
    spe = _create_spe(
        user=user,
        origin_code=origin.code,
        dest_code=destination.code,
        origin_country="AU",
        dest_country="PG",
        service_scope="D2D",
        status="draft",
        missing_components=[COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL],
    )

    analysis_result = _analysis_result_with_components().model_copy(
        update={
            "warnings": ["Possible missed destination charges. Review before quoting."],
            "safety_signals": AnalysisSafetySignals(
                imported_charge_count=3,
                critic_safe_to_proceed=False,
                critic_missed_charges=["Destination delivery fee"],
            ),
        }
    )
    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", lambda *args, **kwargs: analysis_result)
    monkeypatch.setattr(
        "quotes.spot_services.RateAvailabilityService.get_availability",
        lambda **kwargs: {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        },
    )

    client = APIClient()
    client.force_authenticate(user=user)

    analyze_response = client.post(
        "/api/v3/spot/analyze-reply/",
        {"text": "rate reply", "spe_id": str(spe.id), "use_ai": True},
        format="json",
    )
    assert analyze_response.status_code == 200

    detail_response = client.get(f"/api/v3/spot/envelopes/{spe.id}/")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["intake_safety"]["is_safe_to_quote"] is True
    assert detail_payload["intake_safety"]["blocking_issues"] == []
    assert detail_payload["sources"][0]["review_status"] == "NOT_REQUIRED"
    assert detail_payload["sources"][0]["warnings"] == ["Possible missed destination charges. Review before quoting."]

    acknowledge_response = client.post(
        f"/api/v3/spot/envelopes/{spe.id}/acknowledge/",
        {},
        format="json",
    )
    assert acknowledge_response.status_code == 200
    assert acknowledge_response.json()["success"] is True
def test_ai_autofill_only_adds_ai_charges_and_preserves_existing_standard_lines(monkeypatch):
    """AI autofill should only insert charges extracted by the LLM.
    Pre-existing standard-rate SPE lines must be left untouched.
    """
    user, origin, destination = _setup_user_and_locations()
    spe = _create_spe(
        user=user,
        origin_code=destination.code,  # Export lane: POM -> BNE
        dest_code=origin.code,
        origin_country="PG",
        dest_country="AU",
        service_scope="D2D",
        status="draft",
        missing_components=[COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL],
    )

    now = timezone.now()
    # Pre-populate SPE with standard-rate lines (as if StandardChargeService ran earlier)
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code=COMPONENT_FREIGHT,
        description="Standard Airfreight",
        amount=Decimal("5.00"),
        currency="USD",
        unit="per_kg",
        bucket="airfreight",
        is_primary_cost=True,
        entered_at=now,
        source_reference="Standard Rate (ExportCOGS)",
    )
    SPEChargeLineDB.objects.create(
        envelope=spe,
        code=COMPONENT_ORIGIN_LOCAL,
        description="Standard Origin Charges",
        amount=Decimal("50.00"),
        currency="USD",
        unit="flat",
        bucket="origin_charges",
        is_primary_cost=False,
        entered_at=now,
        source_reference="Standard Rate (ExportCOGS)",
    )

    # Mock AI to return ONLY the charge it actually extracted from the email
    analysis_result = ReplyAnalysisResult(
        raw_text="Destination handling 75",
        assertions=[
            ExtractedAssertion(
                text="Destination handling",
                category=AssertionCategory.DEST_CHARGES,
                status=AssertionStatus.CONFIRMED,
                confidence=0.95,
                rate_amount=Decimal("75.00"),
                rate_currency="USD",
                rate_unit="flat",
            ),
        ],
        summary=AnalysisSummary(has_rate=False, has_currency=True),
        warnings=[],
    )
    monkeypatch.setattr(ReplyAnalysisService, "analyze_with_ai", lambda *args, **kwargs: analysis_result)
    monkeypatch.setattr(
        "quotes.spot_services.RateAvailabilityService.get_availability",
        lambda **kwargs: {
            COMPONENT_FREIGHT: False,
            COMPONENT_ORIGIN_LOCAL: False,
            COMPONENT_DESTINATION_LOCAL: False,
        },
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.post(
        "/api/v3/spot/analyze-reply/",
        {"text": "Agent replied with destination charges", "spe_id": str(spe.id), "use_ai": True},
        format="json",
    )
    assert response.status_code == 200

    spe.refresh_from_db()
    charges = list(spe.charge_lines.order_by("bucket", "code", "description"))

    # All three lines should exist: 2 standard + 1 AI
    assert {c.code for c in charges} == {COMPONENT_FREIGHT, COMPONENT_ORIGIN_LOCAL, COMPONENT_DESTINATION_LOCAL}

    freight_charge = next(c for c in charges if c.code == COMPONENT_FREIGHT)
    origin_charge = next(c for c in charges if c.code == COMPONENT_ORIGIN_LOCAL)
    destination_charge = next(c for c in charges if c.code == COMPONENT_DESTINATION_LOCAL)

    # Standard lines are untouched — same source, same amount
    assert freight_charge.source_reference == "Standard Rate (ExportCOGS)"
    assert freight_charge.amount == Decimal("5.00")
    assert origin_charge.source_reference == "Standard Rate (ExportCOGS)"
    assert origin_charge.amount == Decimal("50.00")

    # Imported line keeps the agent reply source reference
    assert destination_charge.source_reference == "Agent reply"
    assert destination_charge.amount == Decimal("75.00")


def test_spot_min_or_per_unit_uses_minimum_amount():
    user = get_user_model().objects.create_user(username="spotmin", password="testpass")
    spe = _create_spe(
        user=user,
        origin_code="BNE",
        dest_code="POM",
        origin_country="AU",
        dest_country="PG",
        service_scope="P2P",
        status="ready",
    )
    _acknowledge_spe(user, spe)

    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="FREIGHT",
        description="Airfreight min or per kg",
        amount=Decimal("0.25"),
        currency="USD",
        unit="per_kg",
        bucket="airfreight",
        is_primary_cost=True,
        min_charge=Decimal("35.00"),
        calculation_type="min_or_per_unit",
        unit_type="kg",
        rate=Decimal("0.25"),
        min_amount=Decimal("35.00"),
        entered_at=timezone.now(),
        source_reference="AI",
    )

    adapter = PricingServiceV4Adapter(
        _quote_input("IMPORT", "P2P", weight_kg=Decimal("100")),
        spot_envelope_id=spe.id,
    )
    lines = adapter._calculate_spot_lines()
    freight = next(line for line in lines if line.bucket == "airfreight")
    assert freight.cost_fcy == Decimal("35.00")


def test_spot_min_or_per_unit_uses_rate_when_weight_exceeds_minimum():
    user = get_user_model().objects.create_user(username="spotrate", password="testpass")
    spe = _create_spe(
        user=user,
        origin_code="BNE",
        dest_code="POM",
        origin_country="AU",
        dest_country="PG",
        service_scope="P2P",
        status="ready",
    )
    _acknowledge_spe(user, spe)

    SPEChargeLineDB.objects.create(
        envelope=spe,
        code="FREIGHT",
        description="Airfreight min or per kg",
        amount=Decimal("0.25"),
        currency="USD",
        unit="per_kg",
        bucket="airfreight",
        is_primary_cost=True,
        min_charge=Decimal("35.00"),
        calculation_type="min_or_per_unit",
        unit_type="kg",
        rate=Decimal("0.25"),
        min_amount=Decimal("35.00"),
        entered_at=timezone.now(),
        source_reference="AI",
    )

    adapter = PricingServiceV4Adapter(
        _quote_input("IMPORT", "P2P", weight_kg=Decimal("200")),
        spot_envelope_id=spe.id,
    )
    lines = adapter._calculate_spot_lines()
    freight = next(line for line in lines if line.bucket == "airfreight")
    assert freight.cost_fcy == Decimal("50.00")


def test_builder_maps_min_or_per_unit_fields_without_collapsing():
    analysis = ReplyAnalysisResult(
        raw_text="Terminal fee 35.00 min or 0.25 per KGS",
        assertions=[
            ExtractedAssertion(
                text="Terminal fee 35.00 min or 0.25 per KGS",
                category=AssertionCategory.DEST_CHARGES,
                status=AssertionStatus.CONFIRMED,
                confidence=0.9,
                rate_amount=Decimal("35.00"),
                rate_per_unit=Decimal("0.25"),
                rate_currency="USD",
                rate_unit="min_or_per_kg",
            )
        ],
        summary=AnalysisSummary(has_rate=True, has_currency=True),
        warnings=[],
    )

    charges = ReplyAnalysisService.build_spe_charges_from_analysis(
        analysis=analysis,
        source_reference="AI",
        shipment_context={
            "origin_country": "AU",
            "destination_country": "PG",
            "service_scope": "A2D",
        },
    )

    assert len(charges) == 1
    charge = charges[0]
    assert charge["calculation_type"] == "min_or_per_unit"
    assert charge["unit_type"] == "kg"
    assert charge["rate"] == "0.25"
    assert charge["min_amount"] == "35.00"
