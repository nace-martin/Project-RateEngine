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
