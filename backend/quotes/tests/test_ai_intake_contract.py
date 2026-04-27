from decimal import Decimal

import pytest

from quotes.ai_intake_schemas import (
    ExtractionAuditResult,
    NormalizedCharge,
    RawExtractedCharge,
)
from quotes.ai_intake_service import parse_rate_quote_text


class _FakeGeminiClient:
    def GenerativeModel(self, _model_name):
        return object()


@pytest.mark.django_db
def test_ai_intake_returns_structured_quote_input_only(monkeypatch):
    monkeypatch.setattr(
        "quotes.ai_intake_service.get_gemini_client",
        lambda: _FakeGeminiClient(),
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_raw_charges",
        lambda *_args, **_kwargs: [
            RawExtractedCharge(
                raw_label="Air Freight",
                raw_amount_string="AUD 5.00/kg",
                currency_hint="AUD",
            ),
        ],
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._normalize_charges",
        lambda *_args, **_kwargs: [
            NormalizedCharge(
                original_raw_label="Air Freight",
                v4_product_code="EXP-FRT-AIR",
                v4_bucket="FREIGHT",
                unit_basis="PER_KG",
                amount=Decimal("5.00"),
                rate_per_unit=Decimal("5.00"),
                currency="AUD",
                confidence="HIGH",
            ),
        ],
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._audit_extraction",
        lambda *_args, **_kwargs: ExtractionAuditResult(
            is_safe_to_proceed=True,
            missed_charges=[],
            hallucinations_detected=[],
        ),
    )

    result = parse_rate_quote_text(
        "Quote in AUD\nAir Freight AUD 5.00/kg",
        context={"shipment_type": "EXPORT"},
    )

    assert result.success is True
    assert result.quote_input is not None
    payload = result.quote_input.model_dump(mode="python")

    assert set(payload.keys()) == {"quote_currency", "charge_lines"}
    assert payload["quote_currency"] == "AUD"
    assert len(payload["charge_lines"]) == 1

    line_payload = payload["charge_lines"][0]
    forbidden_fields = {
        "total_cost_pgk",
        "total_sell_pgk",
        "fx_applied",
        "tax_breakdown",
        "gst_amount",
        "sell_incl_gst",
        "margin_amount",
        "margin_percent",
        "caf_applied",
        "margin_applied",
    }

    assert forbidden_fields.isdisjoint(line_payload.keys())


def _patch_successful_audit(monkeypatch):
    monkeypatch.setattr(
        "quotes.ai_intake_service._audit_extraction",
        lambda *_args, **_kwargs: ExtractionAuditResult(
            is_safe_to_proceed=True,
            missed_charges=[],
            hallucinations_detected=[],
        ),
    )


def _normalizer_from_raw_capture(captured):
    def _fake_normalize(_model, raw_charges, **_kwargs):
        captured["raw_charges"] = list(raw_charges)
        return [
            NormalizedCharge(
                original_raw_label=charge.raw_label,
                v4_product_code="UNMAPPED",
                friendly_description=charge.raw_label,
                v4_bucket="ORIGIN",
                unit_basis="PER_SHIPMENT",
                amount=Decimal("1.00"),
                currency=charge.currency_hint or "USD",
                confidence="LOW",
            )
            for charge in raw_charges
        ]

    return _fake_normalize


@pytest.mark.django_db
def test_ai_intake_pattern_fallback_extracts_short_label_with_parenthetical_note(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "quotes.ai_intake_service.get_gemini_client",
        lambda: _FakeGeminiClient(),
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_raw_charges",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._normalize_charges",
        _normalizer_from_raw_capture(captured),
    )
    _patch_successful_audit(monkeypatch)

    result = parse_rate_quote_text(
        "Agent quote\nHandle:USD50(for small cargo)",
        context={"shipment_type": "IMPORT"},
    )

    assert result.success is True
    raw_charges = captured["raw_charges"]
    assert len(raw_charges) == 1
    assert raw_charges[0].raw_label == "Handle"
    assert raw_charges[0].raw_amount_string == "USD50(for small cargo)"
    assert raw_charges[0].currency_hint == "USD"
    assert result.lines[0].unit_basis == "PER_SHIPMENT"
    assert result.lines[0].notes == "for small cargo"
    assert result.lines[0].confidence == 0.35
    assert result.lines[0].source_excerpt == "Handle:USD50(for small cargo)"
    assert result.lines[0].source_line_number == 2
    assert result.lines[0].source_line_identity == "pattern-line:2:HANDLE"


@pytest.mark.django_db
def test_ai_intake_pattern_fallback_extracts_mixed_email_block(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "quotes.ai_intake_service.get_gemini_client",
        lambda: _FakeGeminiClient(),
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_raw_charges",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._normalize_charges",
        _normalizer_from_raw_capture(captured),
    )
    _patch_successful_audit(monkeypatch)

    result = parse_rate_quote_text(
        "\n".join([
            "Please find charges below:",
            "DOC:USD30",
            "CUS:USD50",
            "Pick Up+Gate In:USD200",
        ]),
        context={"shipment_type": "IMPORT"},
    )

    assert result.success is True
    assert [charge.raw_label for charge in captured["raw_charges"]] == [
        "DOC",
        "CUS",
        "Pick Up+Gate In",
    ]


@pytest.mark.django_db
def test_ai_intake_pattern_fallback_does_not_duplicate_ai_charge(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "quotes.ai_intake_service.get_gemini_client",
        lambda: _FakeGeminiClient(),
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_raw_charges",
        lambda *_args, **_kwargs: [
            RawExtractedCharge(
                raw_label="Handle",
                raw_amount_string="USD 50",
                currency_hint="USD",
            ),
        ],
    )
    monkeypatch.setattr(
        "quotes.ai_intake_service._normalize_charges",
        _normalizer_from_raw_capture(captured),
    )
    _patch_successful_audit(monkeypatch)

    result = parse_rate_quote_text(
        "Agent quote\nHandle:USD50(for small cargo)",
        context={"shipment_type": "IMPORT"},
    )

    assert result.success is True
    assert len(captured["raw_charges"]) == 1
    assert captured["raw_charges"][0].raw_label == "Handle"
