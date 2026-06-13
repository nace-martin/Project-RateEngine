from decimal import Decimal
import pytest
from quotes.ai_intake_schemas import RawExtractedCharge, NormalizedCharge, ExtractionAuditResult
from quotes.ai_intake_service import parse_rate_quote_text, _extract_pattern_charge_candidates

JENNI_CONLON_EMAIL = """
Hi,

Please see below standard NZ export rates which are applicable for any POM imports on collect basis.

EXPORT AKL AIRFREIGHT:
- Airfreight AKL – POM via PX(BNE): USD 3.50/kg (+100kg)
- PX AWB FEE: USD 50.00/awb
- Fuel Surcharge: USD 1.10/kg (subject to change)
- Security Fee: USD 0.15/kg
- Admin Fee: USD 25.00/shipment
- Pick Up - metro area: USD 85.00/shipment (min 50kg, then USD 0.40/kg thereafter)
- X-ray: USD 15.00/shipment (if applicable)
- Additional Screening: POA (optional)

EXPORT:
- Documentation Fee: NZD 35.00/shipment
- AWB Fee: NZD 25.00/shipment
- Compliance Fee: NZD 15.00/shipment
- Airport Security Fee: NZD 12.50/shipment
- Terminal Handling Fee: NZD 45.00/shipment
- Air Transfer Fee: NZD 20.00/shipment
- Customs Clearance: NZD 85.00/shipment
- EDI Fee: NZD 18.00/shipment
"""


class _FakeGeminiClient:
    def GenerativeModel(self, _model_name):
        return object()


@pytest.mark.django_db
def test_pattern_fallback_extracts_all_jenni_conlon_charges():
    # Verify that the regex-based deterministic fallback alone extracts all 15 expected lines
    raw_candidates = _extract_pattern_charge_candidates(JENNI_CONLON_EMAIL)
    assert len(raw_candidates) >= 15

    labels = {c.raw_label for c in raw_candidates}
    expected_labels = {
        "Airfreight AKL – POM via PX(BNE)",
        "PX AWB FEE",
        "Fuel Surcharge",
        "Security Fee",
        "Admin Fee",
        "Pick Up - metro area",
        "X-ray",
        "Documentation Fee",
        "AWB Fee",
        "Compliance Fee",
        "Airport Security Fee",
        "Terminal Handling Fee",
        "Air Transfer Fee",
        "Customs Clearance",
        "EDI Fee",
    }
    
    # Assert each expected label is in the extracted list
    for label in expected_labels:
        assert any(label in x for x in labels), f"Missing expected label: {label}"


@pytest.mark.django_db
def test_ai_intake_recovers_charges_when_normalization_fails(monkeypatch):
    monkeypatch.setattr(
        "quotes.ai_intake_service.get_gemini_client",
        lambda: _FakeGeminiClient(),
    )
    # Mock extractor to return empty so we fall back to pattern extraction
    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_raw_charges",
        lambda *_args, **_kwargs: [],
    )
    # Force Normalizer to raise Exception simulating malformed output
    def mock_normalize_failed(*_args, **_kwargs):
        raise RuntimeError("Normalizer failed with malformed JSON: Unterminated string starting at line 4")
    monkeypatch.setattr(
        "quotes.ai_intake_service._normalize_charges",
        mock_normalize_failed,
    )

    context = {
        "shipment_type": "IMPORT",
        "origin_code": "AKL",
        "destination_code": "POM",
        "service_scope": "D2D",
        "payment_term": "COLLECT",
        "missing_components": ["ORIGIN_LOCAL", "FREIGHT"]
    }

    result = parse_rate_quote_text(
        JENNI_CONLON_EMAIL,
        context=context,
    )

    # Normalization failed, so success must be False (requiring manual review)
    assert result.success is False
    assert len(result.warnings) > 0
    assert any("AI normalization failed" in w for w in result.warnings)
    
    # We must NOT return raw=0
    assert len(result.raw_extracted_charges) >= 15
    assert len(result.normalized_charges) >= 15

    # Fallback charges must be marked correctly
    for charge in result.normalized_charges:
        assert charge.confidence == "LOW"
        assert charge.v4_product_code == "UNMAPPED"
        
        # Verify classification guardrail:
        # Since this is an IMPORT COLLECT shipment and NZ export sections are being parsed,
        # none of these NZ local charges should be classified as PNG destination charges.
        assert charge.v4_bucket in {"ORIGIN", "FREIGHT"}, f"Charge {charge.original_raw_label} was bucketed as {charge.v4_bucket}"

    # Verify key values preserved
    airfreight = next(c for c in result.normalized_charges if "Airfreight" in c.original_raw_label)
    assert airfreight.unit_basis == "PER_KG"
    assert airfreight.amount == Decimal("3.50")
    assert airfreight.rate_per_unit == Decimal("3.50")
    assert airfreight.currency == "USD"

    awb_fee = next(c for c in result.normalized_charges if "PX AWB FEE" in c.original_raw_label)
    assert awb_fee.unit_basis == "PER_SHIPMENT"
    assert awb_fee.amount == Decimal("50.00")
    assert awb_fee.currency == "USD"

    doc_fee = next(c for c in result.normalized_charges if "Documentation Fee" in c.original_raw_label)
    assert doc_fee.unit_basis == "PER_SHIPMENT"
    assert doc_fee.amount == Decimal("35.00")
    assert doc_fee.currency == "NZD"
